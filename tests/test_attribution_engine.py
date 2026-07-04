"""Tests for the decision-ledger attribution engine (107 sprint D3).

Three groups:
1. The identity sum-check on hand-built fixtures, each leg isolated.
2. Censoring representation — censored legs are None + reason, never imputed.
3. Ledger construction on a seeded live-schema sqlite fixture, and a
   read-only smoke over the REAL run DB (skipped when absent).
"""
from __future__ import annotations

import os
import random
import sqlite3
from pathlib import Path

import pytest

from renquant_orchestrator.attribution import (
    assert_identity,
    build_report,
    build_round_trips,
    coverage_report,
    decompose_round_trip,
    render_markdown,
)
from renquant_orchestrator.attribution import decompose as dc
from renquant_orchestrator.attribution import ledger as lg
from renquant_orchestrator.attribution import report as rp

REAL_DB = Path.home() / "git/github/RenQuant/data/runs.alpaca.db"


# ---------------------------------------------------------------------------
# 1. The identity, each leg isolated
# ---------------------------------------------------------------------------

def _base_record(**overrides):
    """A fully-observed closed round trip where every leg is zero:
    N_i == N_r, fills == references, flat benchmark, flat reference."""
    rec = {
        "decision_id": "r1:TEST",
        "date": "2026-01-05",
        "exit_date": "2026-01-12",
        "ticker": "TEST",
        "status": "closed",
        "regime": "BULL_CALM",
        "run_type": "live",
        "intended_notional": 1000.0,
        "realized_notional": 1000.0,
        "shares": 10.0,
        "entry_px": 100.0,
        "exit_px": 100.0,
        "ref_entry_px": 100.0,
        "ref_exit_px": 100.0,
        "spy_entry_px": 500.0,
        "spy_exit_px": 500.0,
        "entry_fill_confirmed": True,
        "exit_fill_confirmed": True,
    }
    rec.update(overrides)
    return rec


def _legs(rec, **kw):
    out = decompose_round_trip(rec, **kw)
    assert out["sum_check"] is not None, f"expected decomposable: {out['censored']}"
    assert out["sum_check"]["ok"], out["sum_check"]
    return out


def test_all_zero_baseline():
    out = _legs(_base_record())
    assert out["total_pnl"] == pytest.approx(0.0)
    for leg in dc.LEG_NAMES:
        assert out["legs"][leg] == pytest.approx(0.0)


def test_pure_signal_leg():
    # Reference +10%, SPY flat, fills exactly at references, N_r == N_i:
    # everything lands in SIGNAL.
    rec = _base_record(
        ref_exit_px=110.0, exit_px=110.0,
    )
    out = _legs(rec)
    assert out["legs"]["signal"] == pytest.approx(100.0)
    for leg in ("market", "sizing", "timing", "cost"):
        assert out["legs"][leg] == pytest.approx(0.0)
    assert out["total_pnl"] == pytest.approx(100.0)


def test_pure_market_leg():
    # Stock and SPY both +10% (reference == fills): SIGNAL (excess) is zero,
    # the whole move is MARKET beta.
    rec = _base_record(
        ref_exit_px=110.0, exit_px=110.0, spy_exit_px=550.0,
    )
    out = _legs(rec)
    assert out["legs"]["market"] == pytest.approx(100.0)
    assert out["legs"]["signal"] == pytest.approx(0.0)
    assert out["total_pnl"] == pytest.approx(100.0)


def test_pure_timing_leg():
    # Reference round trip is flat, but we filled the entry 1% ABOVE the
    # reference close (the POC-C leak shape): TIMING is the only nonzero leg.
    rec = _base_record(
        entry_px=101.0, exit_px=100.0,
        realized_notional=1010.0,  # 10 shares x 101 fill
    )
    out = _legs(rec)
    assert out["legs"]["timing"] == pytest.approx(1010.0 * (100.0 / 101.0 - 1.0))
    assert out["legs"]["signal"] == pytest.approx(0.0)
    assert out["legs"]["sizing"] == pytest.approx(0.0)  # r_ref == 0
    assert out["total_pnl"] == pytest.approx(out["legs"]["timing"])
    assert out["diagnostics"]["entry_slippage_bps"] == pytest.approx(100.0, rel=1e-3)


def test_pure_sizing_leg():
    # Whole-share artifact: intended $1000 but only $500 realized; reference
    # +10% and fills exactly at references -> the missing half of the gain
    # shows up as NEGATIVE sizing against a positive signal.
    rec = _base_record(
        realized_notional=500.0, shares=5.0,
        ref_exit_px=110.0, exit_px=110.0,
    )
    out = _legs(rec)
    assert out["legs"]["signal"] == pytest.approx(100.0)
    assert out["legs"]["sizing"] == pytest.approx(-50.0)
    assert out["legs"]["timing"] == pytest.approx(0.0)
    assert out["total_pnl"] == pytest.approx(50.0)


def test_cost_leg_spread_proxy_flagged_and_summed():
    rec = _base_record(ref_exit_px=110.0, exit_px=110.0)
    out = _legs(rec, half_spread_bps=5.0)
    # entry side 5bps on 1000 + exit side 5bps on 10 shares x 110
    assert out["legs"]["cost"] == pytest.approx(-(0.0005 * 1000.0 + 0.0005 * 1100.0))
    assert out["diagnostics"]["cost_is_estimate"] is True
    assert out["sum_check"]["ok"]


def test_identity_fuzz_random_inputs():
    rng = random.Random(107)
    results = []
    for _ in range(200):
        entry_px = rng.uniform(10, 500)
        shares = rng.randrange(1, 50)
        rec = _base_record(
            entry_px=entry_px,
            exit_px=entry_px * rng.uniform(0.7, 1.4),
            ref_entry_px=entry_px * rng.uniform(0.98, 1.02),
            ref_exit_px=entry_px * rng.uniform(0.7, 1.4),
            spy_entry_px=500.0,
            spy_exit_px=500.0 * rng.uniform(0.9, 1.1),
            shares=float(shares),
            realized_notional=shares * entry_px,
            intended_notional=rng.uniform(100, 3000),
        )
        results.append(decompose_round_trip(rec, half_spread_bps=rng.choice([0.0, 3.0])))
    assert all(r["sum_check"] is not None for r in results)
    assert_identity(results)  # must not raise


def test_assert_identity_raises_on_violation():
    out = _legs(_base_record(ref_exit_px=110.0, exit_px=110.0))
    out["sum_check"]["ok"] = False
    out["sum_check"]["residual"] = 1.23
    with pytest.raises(AssertionError, match="identity violated"):
        assert_identity([out])


def test_open_position_mark_to_market_isolates_entry_timing():
    # Open position marked at the latest close: exit px == ref exit px by
    # construction, so TIMING carries only the entry-side slippage.
    rec = _base_record(
        status="open_mtm",
        entry_px=101.0, realized_notional=1010.0,
        exit_px=120.0, ref_exit_px=120.0,
        exit_fill_confirmed=None, exit_reason=None,
    )
    out = _legs(rec)
    r_real = 120.0 / 101.0 - 1.0
    r_ref = 120.0 / 100.0 - 1.0
    assert out["legs"]["timing"] == pytest.approx(1010.0 * (r_real - r_ref))
    assert out["total_pnl"] == pytest.approx(1010.0 * r_real)


# ---------------------------------------------------------------------------
# 2. Censoring representation — explicit, never imputed
# ---------------------------------------------------------------------------

def test_unconfirmed_entry_fill_censors_execution_legs_not_signal():
    # The #253 shape: buy_pending submission, no fill confirmation. The
    # submit-time reference price must NOT be used as a fill.
    rec = _base_record(
        entry_fill_confirmed=False,
        entry_px=None, entry_px_reference=101.0,
        realized_notional=None,
        ref_exit_px=110.0, exit_px=110.0,
    )
    out = decompose_round_trip(rec)
    # signal + market stay computable at intended sizing
    assert out["legs"]["signal"] == pytest.approx(100.0)
    assert out["legs"]["market"] == pytest.approx(0.0)
    # execution legs censored with the #253 reason; values None (no imputation)
    for leg in ("sizing", "timing", "cost"):
        assert out["legs"][leg] is None
        assert out["censored"][leg] == dc.CENSOR_ENTRY_FILL
    assert out["total_pnl"] is None
    assert out["sum_check"] is None


def test_unconfirmed_exit_fill_censors_timing_only():
    rec = _base_record(
        exit_fill_confirmed=False,
        exit_px=None, exit_px_reference=111.0,
        ref_exit_px=110.0,
    )
    out = decompose_round_trip(rec)
    assert out["legs"]["signal"] == pytest.approx(100.0)
    assert out["legs"]["sizing"] == pytest.approx(0.0)
    assert out["legs"]["timing"] is None
    assert out["censored"]["timing"] == dc.CENSOR_EXIT_FILL
    assert out["total_pnl"] is None


def test_missing_reference_price_censors_reference_legs():
    rec = _base_record(ref_entry_px=None, ref_exit_px=None, exit_px=110.0)
    out = decompose_round_trip(rec)
    for leg in ("signal", "sizing", "timing"):
        assert out["legs"][leg] is None
        assert "no_reference_price" in out["censored"][leg]
    # total is still honestly computable from confirmed fills
    assert out["total_pnl"] == pytest.approx(100.0)
    assert out["sum_check"] is None  # not fully decomposable -> no sum-check


def test_missing_intended_notional_censors_sizing_and_signal():
    rec = _base_record(intended_notional=None, ref_exit_px=110.0, exit_px=110.0)
    out = decompose_round_trip(rec)
    for leg in ("market", "signal", "sizing"):
        assert out["legs"][leg] is None
        assert out["censored"][leg] == dc.CENSOR_NO_INTENDED
    assert out["legs"]["timing"] is not None


def test_exit_unmatched_is_fully_censored():
    out = decompose_round_trip({"decision_id": "x", "status": "exit_unmatched",
                                "date": "2026-01-05", "ticker": "T"})
    assert all(out["legs"][leg] is None for leg in dc.LEG_NAMES)
    assert all(out["censored"][leg] == dc.CENSOR_UNMATCHED_EXIT for leg in dc.LEG_NAMES)


# ---------------------------------------------------------------------------
# 3. Ledger construction on a seeded live-schema fixture
# ---------------------------------------------------------------------------

DDL = """
CREATE TABLE pipeline_runs (
  run_id TEXT PRIMARY KEY, run_date DATE, run_type TEXT, strategy TEXT,
  regime TEXT, portfolio_value REAL, cash REAL);
CREATE TABLE candidate_scores (
  run_id TEXT, ticker TEXT, role TEXT, raw_score REAL, rank_score REAL, mu REAL,
  sigma REAL, selected INTEGER, blocked_by TEXT, kelly_target_pct REAL,
  PRIMARY KEY (run_id, ticker, role));
CREATE TABLE trades (
  run_id TEXT, ticker TEXT, action TEXT, shares REAL, price REAL, invest REAL,
  target_pct REAL, exit_reason TEXT, pnl_pct REAL, hold_days INTEGER,
  trade_date DATE, order_type TEXT, kelly_target_pct REAL);
CREATE TABLE ticker_forward_returns (
  as_of_date DATE, ticker TEXT, close_price REAL, fwd_1d REAL, fwd_5d REAL,
  fwd_10d REAL, fwd_20d REAL, fwd_60d REAL, PRIMARY KEY (as_of_date, ticker));
"""


@pytest.fixture()
def seeded_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(DDL)
    runs = [
        # confirmed-fill era entry (two same-day run_ids re-record ONE fill)
        ("2026-05-01-live-aaa", "2026-05-01", "live", "s104", "BULL_CALM", 10000.0, 500.0),
        ("2026-05-01-live-bbb", "2026-05-01", "live", "s104", "BULL_CALM", 10000.0, 500.0),
        ("2026-05-10-live-ccc", "2026-05-10", "live", "s104", "BULL_CALM", 10000.0, 500.0),
        # censored era entry: buy_pending submission only (#253)
        ("2026-06-20-live-ddd", "2026-06-20", "live", "s104", "BULL_VOLATILE", 10000.0, 500.0),
    ]
    conn.executemany("INSERT INTO pipeline_runs VALUES (?,?,?,?,?,?,?)", runs)
    conn.executemany(
        "INSERT INTO candidate_scores VALUES (?,?,?,?,?,?,?,?,?,?)",
        [
            ("2026-05-01-live-aaa", "AAA", "candidate", 0.5, 0.9, 0.02, 0.1, 1, None, 0.10),
            ("2026-06-20-live-ddd", "PPP", "candidate", 0.4, 0.8, 0.01, 0.1, 0,
             "broker_pending_submitted", 0.05),
        ],
    )
    conn.executemany(
        "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            # ONE fill recorded twice across same-day run_ids -> must dedupe
            ("2026-05-01-live-aaa", "AAA", "buy", 10.0, 101.0, 1010.0, 0.101,
             None, None, None, "2026-05-01", None, 0.10),
            ("2026-05-01-live-bbb", "AAA", "buy", 10.0, 101.0, 1010.0, 0.101,
             None, None, None, "2026-05-01", None, 0.10),
            # confirmed exit
            ("2026-05-10-live-ccc", "AAA", "sell", 10.0, 108.0, 1080.0, None,
             "model_sell", 0.0693, 9, "2026-05-10", None, None),
            # censored-era submission: price is a submit-time REFERENCE
            ("2026-06-20-live-ddd", "PPP", "buy_pending", 5.0, 50.0, 250.0, 0.025,
             None, None, None, "2026-06-20", "NEW_BUY", 0.05),
        ],
    )
    conn.executemany(
        "INSERT INTO ticker_forward_returns VALUES (?,?,?,?,?,?,?,?)",
        [
            ("2026-05-01", "AAA", 100.0, 0.01, 0.03, 0.04, 0.05, 0.08),
            ("2026-05-10", "AAA", 107.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            ("2026-06-20", "PPP", 50.0, 0.01, 0.02, None, None, None),
            ("2026-06-25", "PPP", 52.0, None, None, None, None, None),
            ("2026-05-01", "SPY", 500.0, 0.001, 0.01, 0.015, 0.02, 0.03),
            ("2026-05-10", "SPY", 505.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            ("2026-06-20", "SPY", 510.0, 0.0, 0.0, None, None, None),
            ("2026-06-25", "SPY", 512.0, None, None, None, None, None),
        ],
    )
    conn.commit()
    yield conn
    conn.close()


def test_ledger_dedupes_and_censors(seeded_db):
    df = lg.load_decision_ledger(seeded_db, "live")
    assert len(df) == 2  # duplicate AAA fill collapsed; PPP pending kept
    aaa = df[df.ticker == "AAA"].iloc[0]
    assert bool(aaa.entry_fill_confirmed) is True
    assert aaa.entry_px == pytest.approx(101.0)
    assert aaa.realized_notional == pytest.approx(1010.0)
    assert aaa.intended_notional == pytest.approx(1000.0)  # 0.10 x 10000
    assert aaa.ref_entry_px == pytest.approx(100.0)
    assert aaa.rel_fwd_20d == pytest.approx(0.05 - 0.02)
    assert aaa.n_duplicate_rows == 2
    ppp = df[df.ticker == "PPP"].iloc[0]
    assert bool(ppp.entry_fill_confirmed) is False
    assert ppp.entry_px is None or (ppp.entry_px != ppp.entry_px)  # NaN/None
    assert ppp.entry_px_reference == pytest.approx(50.0)


def test_round_trips_close_open_and_decompose(seeded_db):
    trips = build_round_trips(seeded_db, "live")
    by_ticker = {t["ticker"]: t for t in trips}
    aaa = by_ticker["AAA"]
    assert aaa["status"] == "closed"
    assert aaa["exit_px"] == pytest.approx(108.0)
    assert aaa["ref_exit_px"] == pytest.approx(107.0)
    ppp = by_ticker["PPP"]
    assert ppp["status"] == "open_mtm"
    assert ppp["exit_px"] == pytest.approx(52.0)  # latest recorded close
    assert ppp["entry_fill_confirmed"] is False

    results = [decompose_round_trip(t) for t in trips]
    assert_identity(results)
    r_aaa = next(r for r in results if r["ticker"] == "AAA")
    assert r_aaa["sum_check"]["ok"]
    # hand check: N_i=1000, N_r=1010, r_ref=0.07, r_spy=0.01,
    # r_real=108/101-1
    assert r_aaa["legs"]["market"] == pytest.approx(1000 * 0.01)
    assert r_aaa["legs"]["signal"] == pytest.approx(1000 * 0.06)
    assert r_aaa["legs"]["sizing"] == pytest.approx(10 * 0.07)
    assert r_aaa["legs"]["timing"] == pytest.approx(1010 * (108.0 / 101.0 - 1 - 0.07))
    assert r_aaa["total_pnl"] == pytest.approx(1010 * (108.0 / 101.0 - 1))
    r_ppp = next(r for r in results if r["ticker"] == "PPP")
    assert r_ppp["censored"]["timing"] == dc.CENSOR_ENTRY_FILL
    assert r_ppp["legs"]["signal"] is not None  # intended-sizing legs survive


def _echo_db(rows_trades, rows_tfr=(), rows_cs=()):
    conn = sqlite3.connect(":memory:")
    conn.executescript(DDL)
    run_ids = {r[0] for r in rows_trades}
    conn.executemany(
        "INSERT INTO pipeline_runs VALUES (?,?,?,?,?,?,?)",
        [(rid, rid[:10], "live", "s104", "BULL_CALM", 10000.0, 500.0) for rid in run_ids],
    )
    conn.executemany("INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows_trades)
    if rows_tfr:
        conn.executemany("INSERT INTO ticker_forward_returns VALUES (?,?,?,?,?,?,?,?)", rows_tfr)
    if rows_cs:
        conn.executemany("INSERT INTO candidate_scores VALUES (?,?,?,?,?,?,?,?,?,?)", rows_cs)
    conn.commit()
    return conn


def test_cross_day_re_records_collapse_to_one_decision():
    # The NET shape: one fill echoed across three days at the identical price
    # but with consistent shares -> ONE decision, first date kept.
    rows = [
        (f"2026-05-0{d}-live-x{d}", "NET", "buy", 2.0, 207.07, 414.14, 0.04,
         None, None, None, f"2026-05-0{d}", None, 0.05)
        for d in (1, 2, 3)
    ]
    conn = _echo_db(rows)
    trips = build_round_trips(conn, "live")
    entries = [t for t in trips if t["status"] != "exit_unmatched"]
    assert len(entries) == 1
    assert entries[0]["date"] == "2026-05-01"
    assert entries[0]["n_re_record_days"] == 3
    assert entries[0]["shares_conflict"] is False
    assert entries[0]["realized_notional"] == pytest.approx(2.0 * 207.07)
    conn.close()


def test_cross_day_re_records_with_conflicting_shares_censor_notional():
    # The measured NET pathology: echoes at one price with shares 2/3/39 —
    # realized notional is ambiguous and must be censored, never guessed.
    rows = [
        ("2026-05-01-live-a1", "NET", "buy", 2.0, 207.07, 414.14, 0.04,
         None, None, None, "2026-05-01", None, 0.05),
        ("2026-05-02-live-a2", "NET", "buy", 3.0, 207.07, 621.21, 0.06,
         None, None, None, "2026-05-02", None, 0.05),
        ("2026-05-03-live-a3", "NET", "buy", 39.0, 207.07, 8075.73, 0.80,
         None, None, None, "2026-05-03", None, 0.05),
    ]
    tfr = [
        ("2026-05-01", "NET", 207.0, 0.0, 0.0, None, None, None),
        ("2026-05-01", "SPY", 500.0, 0.0, 0.0, None, None, None),
        ("2026-05-05", "NET", 210.0, None, None, None, None, None),
        ("2026-05-05", "SPY", 505.0, None, None, None, None, None),
    ]
    conn = _echo_db(rows, tfr)
    trips = build_round_trips(conn, "live")
    entries = [t for t in trips if t["status"] != "exit_unmatched"]
    assert len(entries) == 1
    rec = entries[0]
    assert rec["shares_conflict"] is True
    assert rec["realized_notional"] is None
    out = decompose_round_trip(rec)
    for leg in ("sizing", "timing", "cost"):
        assert out["legs"][leg] is None
        assert out["censored"][leg] == dc.CENSOR_SHARES_CONFLICT
    # intended-sizing legs survive at reference prices
    assert out["legs"]["signal"] is not None
    conn.close()


def test_intervening_exit_prevents_echo_collapse():
    # A genuine re-entry at the identical price AFTER a full round trip must
    # NOT be collapsed: the sell between the two buys blocks the merge.
    rows = [
        ("2026-05-01-live-b1", "XYZ", "buy", 2.0, 100.0, 200.0, 0.02,
         None, None, None, "2026-05-01", None, 0.02),
        ("2026-05-05-live-b2", "XYZ", "sell", 2.0, 105.0, 210.0, None,
         "model_sell", 0.05, 4, "2026-05-05", None, None),
        ("2026-05-08-live-b3", "XYZ", "buy", 2.0, 100.0, 200.0, 0.02,
         None, None, None, "2026-05-08", None, 0.02),
    ]
    conn = _echo_db(rows)
    trips = build_round_trips(conn, "live")
    entries = [t for t in trips if t["status"] != "exit_unmatched"]
    assert len(entries) == 2
    assert {t["status"] for t in entries} == {"closed", "open_mtm"}
    conn.close()


def test_sim_round_trips_refused_by_default(seeded_db):
    with pytest.raises(ValueError, match="sim"):
        build_round_trips(seeded_db, "sim")


def test_report_end_to_end_and_output_paths(seeded_db, tmp_path):
    report = build_report(seeded_db, "live")
    cov = report["coverage"]
    assert cov["n_records"] == 2
    assert cov["n_fully_decomposable"] == 1
    assert cov["n_open_mtm"] == 1
    # the censored era is visible in the coverage boundary, dated
    timing_states = cov["per_leg"]["timing"]
    assert dc.CENSOR_ENTRY_FILL in timing_states
    assert timing_states[dc.CENSOR_ENTRY_FILL]["date_min"] == "2026-06-20"
    md = render_markdown(report)
    assert "Coverage boundary" in md and "censored" in md.lower()
    paths = rp.write_report(report, tmp_path)
    assert paths["markdown"].exists() and paths["json"].exists()


def test_report_refuses_prod_output_paths():
    with pytest.raises(ValueError, match="production path"):
        rp._check_out_dir(Path.home() / "git/github/RenQuant/data/somewhere")


# ---------------------------------------------------------------------------
# 4. Real-DB smoke (read-only; skipped when the live DB is absent)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not REAL_DB.exists(), reason="live run DB not present")
def test_real_db_smoke_read_only(tmp_path):
    before = os.stat(REAL_DB).st_mtime_ns
    conn = lg.connect(REAL_DB)
    try:
        report = build_report(conn, "live")
    finally:
        conn.close()
    assert os.stat(REAL_DB).st_mtime_ns == before  # read-only, byte-for-byte
    cov = report["coverage"]
    assert cov["n_records"] > 0
    # the #253 boundary must be visible: some records censored on entry fills
    censored_timing = cov["per_leg"]["timing"].get(dc.CENSOR_ENTRY_FILL)
    assert censored_timing is not None and censored_timing["n"] > 0
    assert_identity(report["records"])
    paths = rp.write_report(report, tmp_path / "lake")
    assert paths["markdown"].exists()
