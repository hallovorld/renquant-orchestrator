"""Tests for the risk-budget ledger (107 sprint D3).

Groups:
1. Budget arithmetic on hand-built fixtures — running max-DD, burn/runway,
   HHI/concentration, beta (realized + composition incl. the sleeve leg).
2. Breach thresholds and exit codes (>80% WARN=2, >=100% CRITICAL=1).
3. Censoring — absent sleeve log, unmeasurable betas, short curves: explicit
   reasons, never imputation.
4. Statement assembly on a seeded live-schema sqlite fixture, and a
   read-only smoke over the REAL run DB (skipped when absent).
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from renquant_orchestrator.risk_budget import attribution_bridge as ab
from renquant_orchestrator.risk_budget import budget as bd
from renquant_orchestrator.risk_budget import report as rp

REAL_DB = Path.home() / "git/github/RenQuant/data/runs.alpaca.db"


# ---------------------------------------------------------------------------
# 1a. Running max-DD arithmetic
# ---------------------------------------------------------------------------

def _curve(values, start="2026-01-01"):
    dates = [f"2026-01-{d:02d}" for d in range(1, len(values) + 1)]
    return pd.DataFrame({
        "date": dates,
        "portfolio_value": values,
        "daily_return": pd.Series(values).pct_change(),
    })


def test_running_drawdown_basic():
    # peak 110 at idx2, trough 88 at idx4 -> max DD = 22/110 = 20%
    out = bd.running_drawdown(_curve([100.0, 105.0, 110.0, 99.0, 88.0, 104.5]))
    assert out["max_drawdown"] == pytest.approx(0.2)
    assert out["max_drawdown_peak_date"] == "2026-01-03"
    assert out["max_drawdown_date"] == "2026-01-05"
    # current DD = 1 - 104.5/110 = 5%
    assert out["current_drawdown"] == pytest.approx(0.05)
    assert out["censored"] is None


def test_running_drawdown_monotone_up_is_zero():
    out = bd.running_drawdown(_curve([100.0, 101.0, 102.0]))
    assert out["max_drawdown"] == pytest.approx(0.0)
    assert out["current_drawdown"] == pytest.approx(0.0)


def test_dd_consumption_fractions():
    dd = bd.running_drawdown(_curve([100.0, 110.0, 88.0]))
    cons = bd.dd_budget_consumption(dd, limit=0.15)
    assert cons["max_consumption"] == pytest.approx(0.2 / 0.15)
    assert cons["remaining_fraction"] == 0.0  # over budget clamps at 0


def test_empty_curve_censored():
    out = bd.running_drawdown(pd.DataFrame(columns=["date", "portfolio_value"]))
    assert out["censored"] == bd.CENSOR_NO_EQUITY


def test_stamped_hwm_conservative():
    # stamped HWM 120 above measured peak 110 -> conservative DD is deeper
    out = bd.running_drawdown(_curve([100.0, 110.0, 99.0]), stamped_hwm=120.0)
    assert out["max_drawdown"] == pytest.approx(0.1)
    assert out["current_drawdown_vs_stamped_hwm"] == pytest.approx(1 - 99 / 120)
    assert out["max_drawdown_conservative"] == pytest.approx(1 - 99 / 120)
    cons = bd.dd_budget_consumption(out, limit=0.15)
    assert cons["max_consumption"] == pytest.approx((1 - 99 / 120) / 0.15)


def test_stamped_hwm_below_peak_is_ignored():
    out = bd.running_drawdown(_curve([100.0, 110.0, 99.0]), stamped_hwm=105.0)
    assert out["max_drawdown_conservative"] == pytest.approx(0.1)
    assert "current_drawdown_vs_stamped_hwm" not in out


# ---------------------------------------------------------------------------
# 1b. Burn rate / runway arithmetic
# ---------------------------------------------------------------------------

def test_burn_rate_and_runway():
    # 100 -> 97 over 3 sessions from the peak: consumption goes 0 -> 0.20 of
    # a 15% budget; burn = 0.20/3 per session; runway = (1-0.20)/burn = 12.
    curve = _curve([100.0, 99.0, 98.0, 97.0])
    out = bd.burn_rate(curve, limit=0.15, window=3)
    assert out["burn_per_session"] == pytest.approx(0.2 / 3)
    assert out["runway_sessions"] == pytest.approx(12.0)
    assert out["censored"] is None


def test_burn_rate_not_burning():
    out = bd.burn_rate(_curve([100.0, 95.0, 100.0, 101.0]), limit=0.15, window=3)
    assert out["runway_sessions"] is None
    assert out["censored"] == bd.CENSOR_NOT_BURNING


def test_burn_rate_short_curve_censored():
    out = bd.burn_rate(_curve([100.0]), limit=0.15)
    assert out["censored"] == bd.CENSOR_SHORT_CURVE


# ---------------------------------------------------------------------------
# 1c. Concentration / HHI
# ---------------------------------------------------------------------------

def _positions(weights, regime="BULL_CALM", pv=10000.0):
    return {
        "regime": regime,
        "portfolio_value": pv,
        "positions": [
            {"ticker": t, "weight": w, "sector": s} for t, w, s in weights
        ],
        "invested_weight": sum(w for _, w, _ in weights),
    }


REGIME_CAPS = {"BULL_CALM": 0.12, "BULL_VOLATILE": 0.20, "CHOPPY": 0.15, "BEAR": 0.0}


def test_concentration_hhi_and_cap():
    pos = _positions([("AAA", 0.10, "tech"), ("BBB", 0.10, "tech"), ("CCC", 0.05, "fin")])
    out = bd.concentration(pos, REGIME_CAPS)
    assert out["hhi_book"] == pytest.approx(0.10**2 + 0.10**2 + 0.05**2)
    inv = 0.25
    assert out["hhi_invested"] == pytest.approx(
        (0.10 / inv) ** 2 + (0.10 / inv) ** 2 + (0.05 / inv) ** 2
    )
    assert out["effective_n_invested"] == pytest.approx(1 / out["hhi_invested"])
    assert out["top_name"] == "AAA"
    assert out["consumption"] == pytest.approx(0.10 / 0.12)
    assert out["sector_weights"]["tech"] == pytest.approx(0.20)


def test_concentration_bear_cap_zero_is_full_breach():
    pos = _positions([("AAA", 0.05, "tech")], regime="BEAR")
    out = bd.concentration(pos, REGIME_CAPS)
    assert out["consumption"] == float("inf")


def test_concentration_all_cash():
    out = bd.concentration(_positions([]), REGIME_CAPS)
    assert out["n_names"] == 0
    assert "no_positions" in out["censored"]


# ---------------------------------------------------------------------------
# 1d. Beta — realized, per-name, composition incl. the sleeve leg
# ---------------------------------------------------------------------------

def _series(vals, start=1):
    idx = [f"2026-02-{d:02d}" for d in range(start, start + len(vals))]
    return pd.Series(vals, index=idx, dtype=float)


def test_realized_beta_exact_two_x():
    # book returns exactly 2x benchmark -> beta 2, R^2 1
    bench = _series([0.01, -0.02, 0.015, 0.005, -0.01] * 5)
    book = bench * 2.0
    out = bd.realized_beta(book, bench, min_obs=20)
    assert out["beta"] == pytest.approx(2.0)
    assert out["r2"] == pytest.approx(1.0)


def test_realized_beta_censored_below_min_obs():
    bench = _series([0.01, -0.02, 0.015])
    out = bd.realized_beta(bench, bench, min_obs=20)
    assert out["censored"] is not None and "beta_unmeasurable" in out["censored"]


def test_per_name_betas_from_closes():
    # price series where the name moves exactly 3x the benchmark's daily
    # return; returns must VARY or benchmark variance is zero
    bench_rets = [0.01, -0.005, 0.02, -0.01, 0.004] * 10
    idx = [f"2026-03-{d:02d}" if d < 29 else f"2026-04-{d-28:02d}" for d in range(1, 51)]
    bench_px, name_px, b, n = [], [], 100.0, 50.0
    for r in bench_rets:
        b *= 1 + r
        n *= 1 + 3 * r
        bench_px.append(b)
        name_px.append(n)
    bench = pd.Series(bench_px, index=idx, dtype=float)
    name = pd.Series(name_px, index=idx, dtype=float)
    betas = bd.per_name_betas(
        {"SPY": bench, "AAA": name, "MISSING": None},
        window=40, min_obs=20,
    )
    assert betas["AAA"]["beta"] == pytest.approx(3.0, rel=1e-6)
    assert betas["MISSING"]["censored"] is not None


def test_beta_composition_with_sleeve_leg():
    pos = _positions([("AAA", 0.30, "tech"), ("BBB", 0.20, "fin")], pv=10000.0)
    betas = {
        "AAA": {"beta": 2.0, "n_obs": 63, "censored": None},
        "BBB": {"censored": "no_price_series(ohlcv parquet missing)", "n_obs": 0},
    }
    sleeve = {"present": True, "last": {"spy_notional": 1000.0}}
    out = bd.beta_composition(pos, betas, sleeve)
    # measured: AAA 0.3*2.0 + sleeve SPY leg 0.1*1.0 = 0.7; BBB censored
    assert out["book_beta_measured_names"] == pytest.approx(0.7)
    assert out["measured_weight"] == pytest.approx(0.40)
    assert out["unmeasured_weight"] == pytest.approx(0.20)
    assert out["censored_names"] == {"BBB": "no_price_series(ohlcv parquet missing)"}
    assert out["sleeve_leg"]["beta_contribution"] == pytest.approx(0.1)
    assert out["sleeve_leg"]["sgov_beta_assumed_zero"] is True


def test_beta_composition_never_imputes():
    # every name censored -> composition censored, NOT beta=1 fallback
    pos = _positions([("AAA", 0.30, "tech")])
    out = bd.beta_composition(pos, {"AAA": {"censored": "x", "n_obs": 0}})
    assert out["book_beta_measured_names"] is None
    assert out["censored"] == "no_measurable_names"


# ---------------------------------------------------------------------------
# 2. Breach thresholds + exit codes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "consumption,status",
    [
        (0.0, rp.STATUS_OK),
        (0.80, rp.STATUS_OK),        # threshold is strict >
        (0.801, rp.STATUS_WARN),
        (0.999, rp.STATUS_WARN),
        (1.0, rp.STATUS_CRITICAL),
        (1.5, rp.STATUS_CRITICAL),
        (None, rp.STATUS_CENSORED),  # censored can never breach
    ],
)
def test_breach_status(consumption, status):
    assert rp.breach_status(consumption) == status


def test_overall_status_and_exit_codes():
    assert rp.overall_status([rp.STATUS_OK, rp.STATUS_CENSORED]) == rp.STATUS_OK
    assert rp.overall_status([rp.STATUS_OK, rp.STATUS_WARN]) == rp.STATUS_WARN
    assert rp.overall_status([rp.STATUS_WARN, rp.STATUS_CRITICAL]) == rp.STATUS_CRITICAL
    assert rp.exit_code(rp.STATUS_OK) == 0
    assert rp.exit_code(rp.STATUS_CENSORED) == 0
    assert rp.exit_code(rp.STATUS_WARN) == 2
    assert rp.exit_code(rp.STATUS_CRITICAL) == 1


# ---------------------------------------------------------------------------
# 3. Sleeve shadow log — reversal metrics + explicit absence
# ---------------------------------------------------------------------------

def test_sleeve_absent_is_explicit(tmp_path):
    out = bd.read_sleeve_shadow(tmp_path / "nope.jsonl")
    assert out["present"] is False
    assert out["censored"] == bd.CENSOR_SLEEVE_ABSENT


def _sleeve_record(date, contribution_pct, max_dd_cons):
    return {
        "date": date,
        "book_state": {
            "sleeve_contribution_pct": contribution_pct,
            "dd_budget_pct": 0.15,
            "dd_budget_consumption_pct": max_dd_cons,
            "max_dd_budget_consumption_pct": max_dd_cons,
            "spy_notional": 1200.0,
        },
    }


def test_sleeve_reversal_metrics(tmp_path):
    log = tmp_path / "sleeve.jsonl"
    rows = [_sleeve_record(f"2026-06-{d:02d}", -0.001, 0.6) for d in range(1, 11)]
    log.write_text("\n".join(json.dumps(r) for r in rows))
    out = bd.read_sleeve_shadow(log)
    assert out["present"] is True
    rm = out["reversal_metrics"]
    assert rm["contribution_sum_pct"] == pytest.approx(-0.01)
    assert rm["max_dd_budget_consumption_pct"] == pytest.approx(0.6)
    assert rm["triggered"] is True  # negative 3m contribution AND >50% dd budget


def test_sleeve_reversal_not_triggered_on_positive_contribution(tmp_path):
    log = tmp_path / "sleeve.jsonl"
    rows = [_sleeve_record(f"2026-06-{d:02d}", +0.002, 0.9) for d in range(1, 6)]
    log.write_text("\n".join(json.dumps(r) for r in rows))
    out = bd.read_sleeve_shadow(log)
    assert out["reversal_metrics"]["triggered"] is False


# ---------------------------------------------------------------------------
# 4. Statement assembly on a seeded live-schema fixture
# ---------------------------------------------------------------------------

DDL = """
CREATE TABLE pipeline_runs (
  run_id TEXT PRIMARY KEY, run_date DATE, run_type TEXT, strategy TEXT,
  regime TEXT, portfolio_value REAL, cash REAL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE portfolio_daily_metrics (
  as_of_date DATE, run_type TEXT, strategy TEXT, portfolio_value REAL,
  daily_return REAL, beta_spy_252d REAL, PRIMARY KEY (as_of_date, run_type, strategy));
CREATE TABLE ticker_daily_state (
  run_id TEXT, date TEXT, ticker TEXT, has_position INTEGER,
  position_pct REAL, sector TEXT, PRIMARY KEY (run_id, ticker));
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
CREATE TABLE live_state_snapshots (
  run_id TEXT PRIMARY KEY, run_date DATE, high_water_mark REAL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
"""


@pytest.fixture()
def seeded_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(DDL)
    dates = [f"2026-06-{d:02d}" for d in range(1, 11)]
    # equity: peak 10500 at 06-03, trough 9450 (10% DD), partial recovery
    pvs = [10000, 10200, 10500, 10100, 9800, 9450, 9600, 9700, 9800, 9900]
    conn.executemany(
        "INSERT INTO portfolio_daily_metrics VALUES (?,?,?,?,?,?)",
        [
            (d, "live", "s104", pv,
             None if i == 0 else pv / pvs[i - 1] - 1.0, None)
            for i, (d, pv) in enumerate(zip(dates, pvs))
        ],
    )
    conn.execute(
        "INSERT INTO pipeline_runs (run_id, run_date, run_type, strategy, regime,"
        " portfolio_value, cash) VALUES (?,?,?,?,?,?,?)",
        ("2026-06-10-live-fix", "2026-06-10", "live", "s104", "BULL_CALM", 9900.0, 8910.0),
    )
    # stamped HWM matches the measured peak (no cross-source disagreement)
    conn.execute(
        "INSERT INTO live_state_snapshots (run_id, run_date, high_water_mark)"
        " VALUES (?,?,?)",
        ("2026-06-10-live-fix", "2026-06-10", 10500.0),
    )
    conn.executemany(
        "INSERT INTO ticker_daily_state VALUES (?,?,?,?,?,?)",
        [
            ("2026-06-10-live-fix", "2026-06-10", "AAA", 1, 0.11, "tech"),
            ("2026-06-10-live-fix", "2026-06-10", "BBB", 1, 0.05, "fin"),
            ("2026-06-10-live-fix", "2026-06-10", "ZZZ", 0, None, "tech"),
        ],
    )
    # SPY closes for realized book beta (daily, matching curve dates + one prior)
    spy_dates = ["2026-05-29", *dates]
    spy_px = 500.0
    rows = []
    for i, d in enumerate(spy_dates):
        rows.append((d, "SPY", spy_px, None, None, None, None, None))
        spy_px *= 1.001 if i % 2 == 0 else 0.999
    conn.executemany("INSERT INTO ticker_forward_returns VALUES (?,?,?,?,?,?,?,?)", rows)
    # one confirmed round trip for the attribution bridge
    conn.execute(
        "INSERT INTO candidate_scores VALUES (?,?,?,?,?,?,?,?,?,?)",
        ("2026-06-10-live-fix", "AAA", "candidate", 0.5, 0.9, 0.02, 0.1, 1, None, 0.10),
    )
    conn.executemany(
        "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("2026-06-10-live-fix", "AAA", "buy", 10.0, 100.0, 1000.0, 0.10,
             None, None, None, "2026-06-10", None, 0.10),
        ],
    )
    conn.execute(
        "INSERT INTO ticker_forward_returns VALUES (?,?,?,?,?,?,?,?)",
        ("2026-06-10", "AAA", 100.0, None, None, None, None, None),
    )
    conn.commit()
    return conn


def _strategy_config(tmp_path, sleeve_enabled=False):
    cfg = {
        "regime_params": {
            "BULL_CALM": {"max_position_pct": 0.12, "cash_reserve_pct": 0.0},
            "BULL_VOLATILE": {"max_position_pct": 0.20, "cash_reserve_pct": 0.2},
            "CHOPPY": {"max_position_pct": 0.15, "cash_reserve_pct": 0.3},
            "BEAR": {"max_position_pct": 0.0, "cash_reserve_pct": 1.0},
        },
        "regime": {"bear_vol_threshold": 0.35, "vol_realized_window": 20},
        "max_positions_per_sector": 6,
        "position_sizing": {"max_position_pct": 0.15},
        "sleeve": {"enabled": sleeve_enabled, "mode": "shadow", "beta_max": 0.6,
                   "beta_pos": 1.0, "dd_budget_pct": 0.15},
    }
    p = tmp_path / "strategy_config.json"
    p.write_text(json.dumps(cfg))
    return p


def _synthetic_closes(beta_multiple=1.0):
    # returns must VARY (constant growth would make benchmark variance zero)
    idx = [f"2026-{m:02d}-{d:02d}" for m in (4, 5, 6) for d in range(1, 29)]
    rets = [0.004, -0.002, 0.006, -0.003, 0.001] * (len(idx) // 5 + 1)
    spy_px, name_px, s, n = [], [], 500.0, 100.0
    for r in rets[: len(idx)]:
        s *= 1 + r
        n *= 1 + beta_multiple * r
        spy_px.append(s)
        name_px.append(n)
    spy = pd.Series(spy_px, index=idx, dtype=float)
    name = pd.Series(name_px, index=idx, dtype=float)

    def loader(ticker):
        return spy if ticker == "SPY" else name

    return loader


def test_build_statement_on_fixture(seeded_db, tmp_path):
    cfg = _strategy_config(tmp_path)
    statement = rp.build_statement(
        seeded_db,
        strategy_config=cfg,
        sleeve_log=tmp_path / "absent.jsonl",
        close_loader=_synthetic_closes(beta_multiple=1.0),
        beta_min_obs=20,
    )
    # budgets carry sources
    assert statement["budgets"]["max_drawdown"]["limit"] == 0.15
    assert "G*" in statement["budgets"]["max_drawdown"]["source"]
    assert statement["budgets"]["book_beta"]["limit"] == 0.6
    # DD: max 10% -> 66.7% of budget; OK
    dd = statement["readings"]["drawdown"]
    assert dd["max_drawdown"] == pytest.approx(0.10)
    assert statement["breaches"]["max_drawdown"]["consumption"] == pytest.approx(2 / 3)
    assert statement["breaches"]["max_drawdown"]["status"] == rp.STATUS_OK
    # concentration: top 11% vs BULL_CALM 12% cap -> 91.7% WARN
    assert statement["breaches"]["per_name_concentration"]["consumption"] == pytest.approx(
        0.11 / 0.12
    )
    assert statement["breaches"]["per_name_concentration"]["status"] == rp.STATUS_WARN
    # sleeve absent -> censored, cannot breach
    assert statement["breaches"]["sleeve_dd_sub_budget"]["status"] == rp.STATUS_CENSORED
    # overall worst = WARN -> exit 2
    assert statement["status"] == rp.STATUS_WARN
    assert statement["exit_code"] == 2
    # censoring appendix carries the sleeve absence
    assert any(c["where"] == "sleeve" for c in statement["censoring"])
    # markdown renders and mentions every budget
    md = rp.render_markdown(statement)
    for token in ("max_drawdown", "book_beta", "per_name_concentration",
                  "sleeve_dd_sub_budget", "OBSERVE-ONLY"):
        assert token in md


def test_statement_critical_on_high_beta(seeded_db, tmp_path):
    cfg = _strategy_config(tmp_path)
    statement = rp.build_statement(
        seeded_db,
        strategy_config=cfg,
        sleeve_log=tmp_path / "absent.jsonl",
        close_loader=_synthetic_closes(beta_multiple=30.0),  # pt beta >> budget
        beta_min_obs=20,
    )
    assert statement["breaches"]["book_beta"]["status"] == rp.STATUS_CRITICAL
    assert statement["exit_code"] == 1


def test_statement_censoring_propagates_from_bridge(seeded_db, tmp_path):
    # June-era pending submission -> censored legs must appear in the bridge
    seeded_db.execute(
        "INSERT INTO pipeline_runs (run_id, run_date, run_type, strategy, regime,"
        " portfolio_value, cash) VALUES (?,?,?,?,?,?,?)",
        ("2026-06-09-live-pend", "2026-06-09", "live", "s104", "BULL_CALM", 9800.0, 8000.0),
    )
    seeded_db.execute(
        "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ("2026-06-09-live-pend", "PPP", "buy_pending", 5.0, 50.0, 250.0, 0.03,
         None, None, None, "2026-06-09", None, 0.03),
    )
    seeded_db.commit()
    statement = rp.build_statement(
        seeded_db,
        strategy_config=_strategy_config(tmp_path),
        sleeve_log=tmp_path / "absent.jsonl",
        close_loader=_synthetic_closes(),
        beta_min_obs=20,
    )
    legs = statement["leg_decomposition"]["overall"]
    timing_censored = legs["leg_censored"]["timing"]
    assert any("entry_fill_unconfirmed" in reason for reason in timing_censored)
    # censored legs contribute NOTHING to totals (the pending trip adds no $)
    assert legs["leg_n"]["timing"] <= legs["n_records"]


def test_write_statement_refuses_prod_paths(seeded_db, tmp_path):
    statement = rp.build_statement(
        seeded_db,
        strategy_config=_strategy_config(tmp_path),
        sleeve_log=tmp_path / "absent.jsonl",
        close_loader=_synthetic_closes(),
        beta_min_obs=20,
    )
    with pytest.raises(ValueError, match="refusing to write"):
        rp.write_statement(statement, Path.home() / "git/github/RenQuant/data/x")
    paths = rp.write_statement(statement, tmp_path / "lake")
    assert paths["markdown"].exists() and paths["json"].exists()


def test_cli_exit_code_matches_status(seeded_db, tmp_path, monkeypatch):
    # route the CLI at a file-backed copy of the fixture
    db_path = tmp_path / "fixture.db"
    disk = sqlite3.connect(db_path)
    seeded_db.backup(disk)
    disk.close()
    monkeypatch.setattr(
        bd, "load_close_series",
        lambda _dir, ticker: _synthetic_closes()(ticker),
    )
    rc = rp.main([
        "--db", str(db_path),
        "--strategy-config", str(_strategy_config(tmp_path)),
        "--sleeve-log", str(tmp_path / "absent.jsonl"),
        "--out-dir", str(tmp_path / "lake"),
    ])
    assert rc == 2  # concentration WARN drives the fixture's exit code


# ---------------------------------------------------------------------------
# 5. Read-only smoke over the REAL run DB (skipped when absent)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not REAL_DB.exists(), reason="live run DB not present")
def test_real_db_smoke_read_only(tmp_path):
    before = os.stat(REAL_DB).st_mtime_ns
    conn = bd.connect(REAL_DB)
    try:
        statement = rp.build_statement(conn)
    finally:
        conn.close()
    assert os.stat(REAL_DB).st_mtime_ns == before  # read-only, byte-for-byte
    dd = statement["readings"]["drawdown"]
    assert dd["n_sessions"] > 0
    assert 0 <= dd["max_drawdown"] < 1
    # the #253 censoring boundary must be visible through the bridge
    legs = statement["leg_decomposition"].get("overall")
    if legs:
        reasons = set()
        for leg in ab.LEG_NAMES:
            reasons.update(legs["leg_censored"][leg])
        assert any("entry_fill_unconfirmed" in r for r in reasons)
    # writer works and refuses nothing about tmp
    paths = rp.write_statement(statement, tmp_path / "lake")
    assert paths["markdown"].exists()
