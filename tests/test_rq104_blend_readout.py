"""Tests for the blend-readout ledger job (pipeline#213 piece 3/3)."""
import importlib.util
import json
import sqlite3
from pathlib import Path

import numpy as np
import pandas as pd

_P = Path(__file__).resolve().parents[1] / "ops" / "renquant104" / "rq104_blend_readout.py"
spec = importlib.util.spec_from_file_location("bro", _P)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def test_zsum_blend_matches_frozen_construction():
    prod = pd.Series({"A": 2.0, "B": 1.0, "C": 0.0})
    clf = pd.Series({"A": 0.1, "B": 0.9, "C": 0.5})
    b = mod.zsum_blend(prod, clf)
    zp = (prod - prod.mean()) / prod.std()
    zc = (clf - clf.mean()) / clf.std()
    assert np.allclose(b.values, (zp + zc).values)
    # missing clf ticker -> clf term 0, prod term kept
    b2 = mod.zsum_blend(prod, clf.drop("C"))
    assert b2["C"] == ((prod - prod.mean()) / prod.std())["C"]


def test_top_n_deterministic_tiebreak():
    s = pd.Series({"B": 1.0, "A": 1.0, "C": 0.5})
    assert mod.top_n(s, 2) == ["A", "B"]  # tie -> ticker asc


def test_ledger_append_idempotent(tmp_path):
    led = tmp_path / "ledger.jsonl"
    row = {"run_date": "2026-07-27", "picks_prod": ["A"], "picks_blend": ["B"],
           "realized": False}
    assert mod.append_ledger(led, row) is True
    assert mod.append_ledger(led, row) is False
    assert len(led.read_text().splitlines()) == 1


def test_latest_live_run_ignores_intraday_partial_run_by_rowid():
    """An intraday/partial run inserted AFTER the post-close full run (higher
    rowid, earlier created_at) must not supersede the full run — regression
    guard for the raw-rowid-order bug (Codex review, PR #581)."""
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE pipeline_runs (run_id TEXT PRIMARY KEY, run_date TEXT, "
               "run_type TEXT, created_at TEXT)")
    db.execute("CREATE TABLE candidate_scores (run_id TEXT, ticker TEXT, panel_score REAL)")
    db.execute("INSERT INTO pipeline_runs VALUES (?,?,?,?)",
               ("2026-07-26-live-aaa", "2026-07-26", "live", "2026-07-26 14:06:00"))
    db.execute("INSERT INTO pipeline_runs VALUES (?,?,?,?)",
               ("2026-07-26-live-bbb", "2026-07-26", "live", "2026-07-26 10:15:00"))
    for t in [f"T{i}" for i in range(85)]:
        db.execute("INSERT INTO candidate_scores VALUES (?,?,?)",
                   ("2026-07-26-live-aaa", t, 1.0))
    # intraday partial run: fewer candidates, inserted (higher rowid) after
    for t in ["X", "Y"]:
        db.execute("INSERT INTO candidate_scores VALUES (?,?,?)",
                   ("2026-07-26-live-bbb", t, 1.0))
    db.commit()
    run_id, run_date = mod.latest_live_run(db)
    assert run_id == "2026-07-26-live-aaa"
    assert run_date == "2026-07-26"


def test_mature_fill_only_when_all_returns_present(tmp_path):
    led = tmp_path / "ledger.jsonl"
    row = {"run_date": "2026-06-01", "picks_prod": ["A", "B"],
           "picks_blend": ["B", "C"], "realized": False}
    led.write_text(json.dumps(row) + "\n")
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE ticker_forward_returns (ticker TEXT, as_of_date TEXT, fwd_20d REAL)")
    db.executemany("INSERT INTO ticker_forward_returns VALUES (?,?,?)",
                   [("A", "2026-06-01", 0.10), ("B", "2026-06-01", 0.02)])
    assert mod.mature_fill(led, db) == 0          # C missing -> not filled
    db.execute("INSERT INTO ticker_forward_returns VALUES ('C','2026-06-01',-0.04)")
    assert mod.mature_fill(led, db) == 1
    out = json.loads(led.read_text().splitlines()[0])
    assert out["realized"] and abs(out["spread_prod"] - 0.06) < 1e-9
    assert abs(out["spread_blend"] - (-0.01)) < 1e-9


def test_partial_coverage_records_why_it_did_not_realize(tmp_path):
    """A session that cannot resolve must say so, not look untouched.

    Realization is all-or-nothing by design — a spread over a partial pick set
    is a different statistic and the readout rule is frozen. The cost is that
    ONE unresolvable ticker drops that session from the 120-session evidence
    forever. Coverage measured 2026-07-29 is 100% on every realized date, but
    the same table holds dates carrying 2-3 tickers, where a session would
    vanish silently. These counters make the shortfall visible.
    """
    import json
    led = tmp_path / "ledger.jsonl"
    led.write_text(json.dumps({
        "run_date": "2026-06-01", "run_id": "r1",
        "picks_prod": ["A", "B"], "picks_blend": ["A", "C"],
        "realized": False}) + "\n")
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE ticker_forward_returns (ticker TEXT, as_of_date TEXT, "
               "fwd_20d REAL)")
    db.executemany("INSERT INTO ticker_forward_returns VALUES (?,?,?)",
                   [("A", "2026-06-01", 0.01), ("B", "2026-06-01", 0.02)])
    assert mod.mature_fill(led, db) == 0            # C missing -> not realized
    row = json.loads(led.read_text().splitlines()[0])
    assert row["realized"] is False
    assert row["n_resolvable_prod"] == 2
    assert row["n_resolvable_blend"] == 1           # the shortfall is recorded
    assert row["n_picks_blend"] == 2


def test_telemetry_persists_even_when_nothing_realizes(tmp_path):
    import json
    led = tmp_path / "ledger.jsonl"
    led.write_text(json.dumps({
        "run_date": "2026-06-01", "run_id": "r1",
        "picks_prod": ["A"], "picks_blend": ["Z"], "realized": False}) + "\n")
    db = sqlite3.connect(":memory:")
    db.execute("CREATE TABLE ticker_forward_returns (ticker TEXT, as_of_date TEXT, "
               "fwd_20d REAL)")
    db.executemany("INSERT INTO ticker_forward_returns VALUES (?,?,?)",
                   [("A", "2026-06-01", 0.01)])
    assert mod.mature_fill(led, db) == 0
    row = json.loads(led.read_text().splitlines()[0])
    # written despite filled == 0, so a stuck session is diagnosable next pass
    assert row["n_resolvable_blend"] == 0
