"""Was each position sized within the cap the deployed config declares?

MEASURED 2026-08-05: TSLA is 23.5 % of a $10.9k live book against
`BULL_CALM.max_position_pct = 0.12`. It was **bought that way** — the 07-28 buy
stamped `target_pct = 0.2341` while its own `kelly_target_pct` was `0.0613`.
`EME` the same day: `0.2109`. Every other buy in the window sized 0.007–0.09.

Two of thirty-three. That is an EVENT, and an event is exactly what goes
unnoticed without a check.
"""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import sys

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "ops" / "renquant104"))
import position_cap_conformance as P  # noqa: E402

_SCHEMA = """
CREATE TABLE trades (trade_date TEXT, ticker TEXT, regime TEXT,
                     target_pct REAL, kelly_target_pct REAL, exit_reason TEXT,
                     run_id TEXT);
CREATE TABLE pipeline_runs (run_id TEXT, created_at TEXT);
"""


def _db(tmp_path, *rows, runs=()):
    p = tmp_path / "runs.alpaca.db"
    con = sqlite3.connect(p)
    con.executescript(_SCHEMA)
    con.executemany("insert into trades values (?,?,?,?,?,?,?)",
                    [r if len(r) == 7 else (*r, None) for r in rows])
    con.executemany("insert into pipeline_runs values (?,?)", runs)
    con.commit()
    con.close()
    return p


def _cfg(tmp_path, params):
    p = tmp_path / "strategy_config.json"
    p.write_text(json.dumps({"regime_params": params}), encoding="utf-8")
    return p


class TestItComparesWhatWasDoneToWhatTheConfigSays:
    def test_a_buy_OVER_the_regime_cap_is_flagged(self, tmp_path):
        db = _db(tmp_path, ("2026-07-28", "TSLA", "BULL_CALM", 0.2341, 0.0613, None))
        cfg = _cfg(tmp_path, {"BULL_CALM": {"max_position_pct": 0.12}})
        r = P.scan("2026-07-01", db=db, config_path=cfg)
        b = r["buys"][0]
        assert b["state"] == P.STATE_OVER
        assert b["over_cap_by"] == pytest.approx(0.1141, abs=1e-4)
        assert b["kelly_ratio"] == pytest.approx(3.82, abs=0.01)
        assert r["n_over_cap"] == 1

    def test_a_buy_WITHIN_the_cap_is_not_flagged(self, tmp_path):
        db = _db(tmp_path, ("2026-08-04", "VLO", "BULL_CALM", 0.0559, 0.0, None))
        cfg = _cfg(tmp_path, {"BULL_CALM": {"max_position_pct": 0.12}})
        r = P.scan("2026-07-01", db=db, config_path=cfg)
        assert r["buys"][0]["state"] == P.STATE_OK
        assert r["n_over_cap"] == 0

    def test_a_cap_EQUAL_to_the_target_is_within(self, tmp_path):
        """The cap is a ceiling, not a strict inequality."""
        db = _db(tmp_path, ("2026-08-04", "X", "BULL_CALM", 0.12, 0.05, None))
        cfg = _cfg(tmp_path, {"BULL_CALM": {"max_position_pct": 0.12}})
        assert P.scan("2026-07-01", db=db, config_path=cfg)["buys"][0]["state"] == \
            P.STATE_OK


class TestSilenceIsNeverReadAsCompliance:
    """Every way the answer can be unknown gets its own ACTIONABLE state —
    inventing a cap would turn 'the config is silent' into 'within limits'."""

    def test_a_regime_with_NO_cap_declared_is_its_own_state(self, tmp_path):
        db = _db(tmp_path, ("2026-08-04", "X", "HIGH_SPIKED", 0.99, 0.05, None))
        cfg = _cfg(tmp_path, {"HIGH_SPIKED": {}})
        r = P.scan("2026-07-01", db=db, config_path=cfg)
        assert r["buys"][0]["state"] == P.STATE_NO_CAP
        assert r["n_actionable"] == 1
        assert r["n_over_cap"] == 0, "unknown is not a violation, but it IS actionable"

    def test_a_regime_MISSING_from_the_config_is_the_same(self, tmp_path):
        db = _db(tmp_path, ("2026-08-04", "X", "NOT_A_REGIME", 0.99, 0.05, None))
        cfg = _cfg(tmp_path, {"BULL_CALM": {"max_position_pct": 0.12}})
        assert P.scan("2026-07-01", db=db, config_path=cfg)["buys"][0]["state"] == \
            P.STATE_NO_CAP

    def test_a_row_with_NO_regime_recorded_is_its_own_state(self, tmp_path):
        db = _db(tmp_path, ("2026-08-04", "X", None, 0.99, 0.05, None))
        cfg = _cfg(tmp_path, {"BULL_CALM": {"max_position_pct": 0.12}})
        assert P.scan("2026-07-01", db=db, config_path=cfg)["buys"][0]["state"] == \
            P.STATE_UNKNOWN_REGIME

    def test_an_UNREADABLE_config_refuses(self, tmp_path):
        db = _db(tmp_path, ("2026-08-04", "X", "BULL_CALM", 0.05, 0.05, None))
        with pytest.raises(P.EvidenceUnreadable):
            P.scan("2026-07-01", db=db, config_path=tmp_path / "nope.json")

    def test_a_NON_OBJECT_config_root_refuses(self, tmp_path):
        db = _db(tmp_path, ("2026-08-04", "X", "BULL_CALM", 0.05, 0.05, None))
        bad = tmp_path / "c.json"
        bad.write_text("[]", encoding="utf-8")
        with pytest.raises(P.EvidenceUnreadable):
            P.scan("2026-07-01", db=db, config_path=bad)

    def test_a_MISSING_db_refuses_rather_than_reporting_zero_buys(self, tmp_path):
        cfg = _cfg(tmp_path, {"BULL_CALM": {"max_position_pct": 0.12}})
        with pytest.raises(P.EvidenceUnreadable) as exc:
            P.scan("2026-07-01", db=tmp_path / "nope.db", config_path=cfg)
        assert "no runs DB" in str(exc.value)


class TestOnlyLIVEBuysAreCounted:
    def test_simulated_rows_have_no_trade_date_and_are_excluded(self, tmp_path):
        """250 kelly_trim rows exist and 0 carry a trade_date — the sim rows
        would otherwise flood any live conformance count."""
        db = _db(tmp_path,
                 (None, "SIM", "BULL_CALM", 0.99, 0.05, "kelly_trim"),
                 ("2026-08-04", "LIVE", "BULL_CALM", 0.05, 0.05, None))
        cfg = _cfg(tmp_path, {"BULL_CALM": {"max_position_pct": 0.12}})
        r = P.scan("2026-07-01", db=db, config_path=cfg)
        assert [b["ticker"] for b in r["buys"]] == ["LIVE"]

    def test_a_SELL_is_not_a_sizing_decision(self, tmp_path):
        db = _db(tmp_path, ("2026-08-04", "X", "BULL_CALM", 0.99, 0.05, "stop_loss"))
        cfg = _cfg(tmp_path, {"BULL_CALM": {"max_position_pct": 0.12}})
        assert P.scan("2026-07-01", db=db, config_path=cfg)["buys"] == []


def test_a_breach_names_the_RUN_that_produced_it(tmp_path):
    """A breach is far easier to read when you can see WHICH cycle produced it
    — the two live breaches came from a run created off the 12-minute grid."""
    db = _db(tmp_path,
             ("2026-07-28", "TSLA", "BULL_CALM", 0.2341, 0.0613, None, "r-odd"),
             runs=[("r-odd", "2026-07-28 17:45:49")])
    cfg = _cfg(tmp_path, {"BULL_CALM": {"max_position_pct": 0.12}})
    r = P.scan("2026-07-01", db=db, config_path=cfg)
    b = r["buys"][0]
    assert b["run_id"] == "r-odd"
    assert b["run_created_at"] == "2026-07-28 17:45:49"
    text = P.render(r)
    assert "the breaching run(s):" in text and "17:45:49" in text


#: The BULL_CALM cap in force when the 2026-07-28 buys were sized. Pinned here
#: because `scan()` judges every historical buy against the cap in the CURRENTLY
#: DEPLOYED config — so raising the cap retroactively un-breaches history.
#: Measured 2026-08-06: the deployed cap moved 0.12 -> 0.30 (strategy-104#94,
#: operator directive, LONG row 2a), and the two breaches below stopped
#: registering. They did not stop having happened.
CAP_IN_FORCE_2026_07_28 = 0.12

#: The day the deployed cap moved 0.12 -> 0.30 (strategy-104 e00d935, merged
#: 2026-08-06). A retired cap is evidence about the buys made WHILE IT WAS IN
#: FORCE and about nothing else — applying it forward is the mirror image of
#: the rot this file exists to prevent. Without this bound the historical
#: assertion started failing on 2026-08-12/14 (SPG 0.1604, APH 0.1214): both
#: sized WITHIN the 0.30 cap that governed them, both "breaching" a number
#: that no longer applied. That is an alarm on compliant behaviour.
CAP_RAISED_ON = "2026-08-06"


def test_the_LIVE_book_is_what_the_record_describes(tmp_path):
    """Bound to reality: 2 of 33 live buys since 2026-07-01 breached the cap
    IN FORCE AT THE TIME, both on 2026-07-28.

    Evaluated against a pinned historical cap, not the deployed one. Under the
    deployed config this assertion silently passed as "0 breaches" the moment
    the cap was raised — a policy change is not a reason for a past breach to
    disappear from the record, and a test that lets it is how the record rots.

    The pinned cap is applied only to its OWN era (< ``CAP_RAISED_ON``); buys
    governed by the 0.30 cap are judged by `test_the_DEPLOYED_cap_...` below.
    """
    if not P.DB.is_file() or not P.CONFIG.is_file():
        pytest.skip("umbrella evidence absent — the unit tests above still ran")
    hist_cfg = _cfg(tmp_path, {"BULL_CALM": {"max_position_pct": CAP_IN_FORCE_2026_07_28}})
    r = P.scan("2026-07-01", config_path=hist_cfg)
    over = [b for b in r["buys"]
            if b["state"] == P.STATE_OVER and b["trade_date"] < CAP_RAISED_ON]
    assert {b["ticker"] for b in over} == {"TSLA", "EME"}, over
    assert {b["trade_date"] for b in over} == {"2026-07-28"}, over
    for b in over:
        assert b["kelly_ratio"] > 3.0, (
            "the breach was ~3.8x the model's own Kelly target — if that has "
            "shrunk, re-derive the record", b)
    # Both came from ONE run, and it was created off the 12-minute cadence.
    assert {b["run_id"] for b in over} == {"2026-07-28-live-6194047c"}, over
    assert all(str(b["run_created_at"]).endswith("17:45:49") for b in over), over


def test_the_DEPLOYED_cap_is_read_and_stated_not_assumed():
    """The other half of the same fact: under the cap deployed TODAY those two
    buys are within policy. Both statements are true and neither replaces the
    other, so both are asserted — and the scan result must name the cap it
    judged against, or a reader cannot tell which of the two a verdict means."""
    if not P.DB.is_file() or not P.CONFIG.is_file():
        pytest.skip("umbrella evidence absent")
    r = P.scan("2026-07-01")
    caps = r["caps"]
    assert "BULL_CALM" in caps, "a scan that does not state its cap is unreadable"
    deployed = caps["BULL_CALM"]
    over = [b for b in r["buys"] if b["state"] == P.STATE_OVER]
    if deployed is not None and deployed > CAP_IN_FORCE_2026_07_28:
        assert not over, (
            f"deployed cap {deployed} exceeds the {CAP_IN_FORCE_2026_07_28} in "
            "force on 2026-07-28, so those buys should no longer register", over)
