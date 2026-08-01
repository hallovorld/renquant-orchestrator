"""Reading the evidence must not mutate it, and a crash must not destroy it.

`mature_fill`'s comment has always said "write whenever anything changed"; the line under
it wrote unconditionally. Measured 2026-08-01 by running the readout on a non-session day
with `filled == 0` — the live ledger's mtime moved anyway. An append-only evidence file
that every diagnostic pass rewrites is not append-only, and `write_text` truncates before
it writes, so an interrupt leaves nothing.
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
import sys

import pytest

OPS = pathlib.Path(__file__).resolve().parent.parent / "ops" / "renquant104"
sys.path.insert(0, str(OPS))

import rq104_blend_readout as B  # noqa: E402

ROW = {"run_date": "2026-07-31", "run_id": "r1",
       "picks_prod": ["AAPL"], "picks_blend": ["AAPL"],
       "n_picks_prod": 1, "n_picks_blend": 1,
       "n_resolvable_prod": 1, "n_resolvable_blend": 1,
       "n_candidates": 83, "n_clf_scored": 79,
       "aged": False, "realized": False}


@pytest.fixture
def db():
    c = sqlite3.connect(":memory:")
    # The REAL column name is `as_of_date`. My first fixture said `date`, the query
    # threw, `mature_fill` returned 0 before reaching the write, and two tests failed
    # for a reason that had nothing to do with the fix under test.
    c.execute("CREATE TABLE ticker_forward_returns "
              "(ticker TEXT, as_of_date TEXT, fwd_60d REAL)")
    c.executemany("INSERT INTO ticker_forward_returns VALUES (?,?,0.01)",
                  [("AAPL", "2026-07-31")])
    c.commit()
    return c


def _ledger(tmp_path, rows=(ROW,)):
    p = tmp_path / "ledger.jsonl"
    p.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return p


def test_a_NO_OP_pass_does_not_touch_the_file(tmp_path, db):
    """The defect, pinned. Two identical passes: the second must not write."""
    p = _ledger(tmp_path)
    B.mature_fill(p, db)                      # first pass may add telemetry
    before = p.stat().st_mtime_ns, p.read_bytes()
    B.mature_fill(p, db)                      # second pass: nothing changed
    assert (p.stat().st_mtime_ns, p.read_bytes()) == before


def test_a_TELEMETRY_ONLY_change_still_writes(tmp_path, db):
    """The original intent must survive the fix: a session that becomes unresolvable has
    to show WHY on the next pass rather than looking untouched."""
    stripped = {k: v for k, v in ROW.items()
                if k not in ("n_resolvable_prod", "n_resolvable_blend", "aged")}
    p = _ledger(tmp_path, [stripped])
    before = p.read_bytes()
    B.mature_fill(p, db)
    after = json.loads(p.read_text().splitlines()[0])
    assert p.read_bytes() != before
    assert after["n_resolvable_prod"] == 1 and after["aged"] is False


def test_the_write_is_ATOMIC_so_an_interrupt_leaves_the_ledger_INTACT(tmp_path, db,
                                                                     monkeypatch):
    """`write_text` truncates and then writes. There is no other copy of these sessions."""
    p = _ledger(tmp_path)
    B.mature_fill(p, db)
    good = p.read_bytes()

    real = pathlib.Path.write_text

    def boom(self, *a, **k):
        if self.name.endswith(".tmp"):
            real(self, *a, **k)
            raise KeyboardInterrupt("simulated interrupt after the temp write")
        return real(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "write_text", boom)
    stripped = {k: v for k, v in ROW.items() if k != "aged"}
    p.write_bytes(good)
    p2 = tmp_path / "ledger.jsonl"
    p2.write_text("".join(json.dumps(r) + "\n" for r in [stripped]))
    pre = p2.read_bytes()
    with pytest.raises(KeyboardInterrupt):
        B.mature_fill(p2, db)
    assert p2.read_bytes() == pre           # previous ledger survived, byte for byte
    assert p2.read_text().strip()           # and is not empty


def test_no_TMP_file_is_left_behind_on_success(tmp_path, db):
    p = _ledger(tmp_path)
    B.mature_fill(p, db)
    assert not list(tmp_path.glob("*.tmp"))


def test_an_ABSENT_ledger_returns_zero_and_creates_nothing(tmp_path, db):
    p = tmp_path / "nope.jsonl"
    assert B.mature_fill(p, db) == 0
    assert not p.exists()


def test_an_UNREADABLE_current_ledger_writes_rather_than_assuming_a_match(tmp_path, db,
                                                                         monkeypatch):
    """`current = None` on OSError must mean "write", not "assume it already matches" —
    the fail-open reading would skip persisting a real update."""
    p = _ledger(tmp_path)
    B.mature_fill(p, db)
    calls = {"n": 0}
    real = pathlib.Path.read_text

    def flaky(self, *a, **k):
        if self.name == "ledger.jsonl":
            calls["n"] += 1
            if calls["n"] == 2:            # the comparison read, not the load
                raise OSError("simulated")
        return real(self, *a, **k)

    monkeypatch.setattr(pathlib.Path, "read_text", flaky)
    B.mature_fill(p, db)
    monkeypatch.undo()
    assert json.loads(p.read_text().splitlines()[0])["run_date"] == "2026-07-31"
