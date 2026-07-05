"""Direct unit tests for risk_budget/budget.py — DB-facing functions,
equity curve loading, position extraction, close series, and SPY returns.

Complements test_risk_budget.py (which covers the pure arithmetic
functions exhaustively) by testing the SQL / IO seams that only the
existing integration test touched indirectly.
"""
from __future__ import annotations

import json
import sqlite3

import pandas as pd
import pytest

from renquant_orchestrator.risk_budget import budget as bd

# ---------------------------------------------------------------------------
# Shared DDL — matches the production schema subset budget.py queries
# ---------------------------------------------------------------------------

DDL = """
CREATE TABLE pipeline_runs (
  run_id TEXT PRIMARY KEY, run_date DATE, run_type TEXT, strategy TEXT,
  regime TEXT, portfolio_value REAL, cash REAL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE portfolio_daily_metrics (
  as_of_date DATE, run_type TEXT, strategy TEXT, portfolio_value REAL,
  daily_return REAL, beta_spy_252d REAL,
  PRIMARY KEY (as_of_date, run_type, strategy));
CREATE TABLE ticker_daily_state (
  run_id TEXT, date TEXT, ticker TEXT, has_position INTEGER,
  position_pct REAL, sector TEXT, PRIMARY KEY (run_id, ticker));
CREATE TABLE ticker_forward_returns (
  as_of_date DATE, ticker TEXT, close_price REAL, fwd_1d REAL, fwd_5d REAL,
  fwd_10d REAL, fwd_20d REAL, fwd_60d REAL, PRIMARY KEY (as_of_date, ticker));
CREATE TABLE live_state_snapshots (
  run_id TEXT PRIMARY KEY, run_date DATE, high_water_mark REAL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
"""


@pytest.fixture()
def mem_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(DDL)
    return conn


# ---------------------------------------------------------------------------
# connect() — read-only mode
# ---------------------------------------------------------------------------

def test_connect_opens_readonly(tmp_path):
    db_path = tmp_path / "test.db"
    setup = sqlite3.connect(str(db_path))
    setup.execute("CREATE TABLE t (x INTEGER)")
    setup.execute("INSERT INTO t VALUES (1)")
    setup.commit()
    setup.close()

    conn = bd.connect(db_path)
    rows = conn.execute("SELECT x FROM t").fetchall()
    assert rows == [(1,)]
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("INSERT INTO t VALUES (2)")
    conn.close()


# ---------------------------------------------------------------------------
# load_equity_curve() — SQL extraction
# ---------------------------------------------------------------------------

def test_load_equity_curve_basic(mem_db):
    mem_db.executemany(
        "INSERT INTO portfolio_daily_metrics VALUES (?,?,?,?,?,?)",
        [
            ("2026-06-01", "live", "s104", 10000, None, None),
            ("2026-06-02", "live", "s104", 10100, 0.01, None),
            ("2026-06-03", "live", "s104", 10050, -0.005, None),
        ],
    )
    mem_db.commit()
    df = bd.load_equity_curve(mem_db)
    assert len(df) == 3
    assert list(df.columns) == ["date", "portfolio_value", "daily_return", "strategy"]
    assert df["portfolio_value"].iloc[-1] == 10050


def test_load_equity_curve_filters_run_type(mem_db):
    mem_db.executemany(
        "INSERT INTO portfolio_daily_metrics VALUES (?,?,?,?,?,?)",
        [
            ("2026-06-01", "live", "s104", 10000, None, None),
            ("2026-06-01", "sim", "s104", 50000, None, None),
        ],
    )
    mem_db.commit()
    live = bd.load_equity_curve(mem_db, run_type="live")
    assert len(live) == 1
    assert live["portfolio_value"].iloc[0] == 10000
    sim = bd.load_equity_curve(mem_db, run_type="sim")
    assert len(sim) == 1
    assert sim["portfolio_value"].iloc[0] == 50000


def test_load_equity_curve_filters_strategy(mem_db):
    mem_db.executemany(
        "INSERT INTO portfolio_daily_metrics VALUES (?,?,?,?,?,?)",
        [
            ("2026-06-01", "live", "s104", 10000, None, None),
            ("2026-06-01", "live", "s105", 20000, None, None),
        ],
    )
    mem_db.commit()
    df = bd.load_equity_curve(mem_db, strategy="s105")
    assert len(df) == 1
    assert df["portfolio_value"].iloc[0] == 20000


def test_load_equity_curve_drops_null_pv(mem_db):
    mem_db.executemany(
        "INSERT INTO portfolio_daily_metrics VALUES (?,?,?,?,?,?)",
        [
            ("2026-06-01", "live", "s104", 10000, None, None),
            ("2026-06-02", "live", "s104", None, None, None),
            ("2026-06-03", "live", "s104", 10200, 0.02, None),
        ],
    )
    mem_db.commit()
    df = bd.load_equity_curve(mem_db)
    assert len(df) == 2
    assert df.index.tolist() == [0, 1]


def test_load_equity_curve_empty_table(mem_db):
    df = bd.load_equity_curve(mem_db)
    assert df.empty


def test_load_equity_curve_ordered_by_date(mem_db):
    mem_db.executemany(
        "INSERT INTO portfolio_daily_metrics VALUES (?,?,?,?,?,?)",
        [
            ("2026-06-03", "live", "s104", 10200, None, None),
            ("2026-06-01", "live", "s104", 10000, None, None),
            ("2026-06-02", "live", "s104", 10100, None, None),
        ],
    )
    mem_db.commit()
    df = bd.load_equity_curve(mem_db)
    assert df["date"].tolist() == ["2026-06-01", "2026-06-02", "2026-06-03"]


# ---------------------------------------------------------------------------
# stamped_high_water_mark()
# ---------------------------------------------------------------------------

def test_stamped_hwm_normal(mem_db):
    mem_db.execute(
        "INSERT INTO live_state_snapshots (run_id, run_date, high_water_mark)"
        " VALUES (?,?,?)",
        ("run-1", "2026-06-01", 10500.0),
    )
    mem_db.commit()
    assert bd.stamped_high_water_mark(mem_db) == 10500.0


def test_stamped_hwm_returns_latest(mem_db):
    mem_db.executemany(
        "INSERT INTO live_state_snapshots (run_id, run_date, high_water_mark)"
        " VALUES (?,?,?)",
        [("run-1", "2026-06-01", 10000.0), ("run-2", "2026-06-02", 10500.0)],
    )
    mem_db.commit()
    assert bd.stamped_high_water_mark(mem_db) == 10500.0


def test_stamped_hwm_null_value(mem_db):
    mem_db.execute(
        "INSERT INTO live_state_snapshots (run_id, run_date, high_water_mark)"
        " VALUES (?,?,?)",
        ("run-1", "2026-06-01", None),
    )
    mem_db.commit()
    assert bd.stamped_high_water_mark(mem_db) is None


def test_stamped_hwm_empty_table(mem_db):
    assert bd.stamped_high_water_mark(mem_db) is None


def test_stamped_hwm_missing_table():
    conn = sqlite3.connect(":memory:")
    assert bd.stamped_high_water_mark(conn) is None
    conn.close()


# ---------------------------------------------------------------------------
# latest_positions()
# ---------------------------------------------------------------------------

def test_latest_positions_basic(mem_db):
    mem_db.execute(
        "INSERT INTO pipeline_runs (run_id, run_date, run_type, strategy, regime,"
        " portfolio_value, cash) VALUES (?,?,?,?,?,?,?)",
        ("run-1", "2026-06-10", "live", "s104", "BULL_CALM", 10000.0, 8500.0),
    )
    mem_db.executemany(
        "INSERT INTO ticker_daily_state VALUES (?,?,?,?,?,?)",
        [
            ("run-1", "2026-06-10", "AAPL", 1, 0.10, "tech"),
            ("run-1", "2026-06-10", "GOOG", 1, 0.05, "tech"),
            ("run-1", "2026-06-10", "ZZZ", 0, None, "fin"),
        ],
    )
    mem_db.commit()
    out = bd.latest_positions(mem_db)
    assert out["run_id"] == "run-1"
    assert out["regime"] == "BULL_CALM"
    assert len(out["positions"]) == 2
    assert out["positions"][0]["ticker"] == "AAPL"
    assert out["positions"][0]["weight"] == 0.10
    assert out["invested_weight"] == pytest.approx(0.15)
    assert out["cash_weight"] == pytest.approx(0.85)
    assert out["censored"] is None


def test_latest_positions_cash_identity_gap(mem_db):
    mem_db.execute(
        "INSERT INTO pipeline_runs (run_id, run_date, run_type, strategy, regime,"
        " portfolio_value, cash) VALUES (?,?,?,?,?,?,?)",
        ("run-1", "2026-06-10", "live", "s104", "BULL_CALM", 10000.0, 9500.0),
    )
    mem_db.executemany(
        "INSERT INTO ticker_daily_state VALUES (?,?,?,?,?,?)",
        [("run-1", "2026-06-10", "AAPL", 1, 0.10, "tech")],
    )
    mem_db.commit()
    out = bd.latest_positions(mem_db)
    assert out["recorded_cash_weight"] == pytest.approx(0.95)
    assert out["cash_identity_gap"] == pytest.approx(0.95 + 0.10 - 1.0)


def test_latest_positions_no_runs(mem_db):
    out = bd.latest_positions(mem_db)
    assert out["positions"] == []
    assert "no_runs" in out["censored"]


def test_latest_positions_no_held(mem_db):
    mem_db.execute(
        "INSERT INTO pipeline_runs (run_id, run_date, run_type, strategy, regime,"
        " portfolio_value, cash) VALUES (?,?,?,?,?,?,?)",
        ("run-1", "2026-06-10", "live", "s104", "BULL_CALM", 10000.0, 10000.0),
    )
    mem_db.executemany(
        "INSERT INTO ticker_daily_state VALUES (?,?,?,?,?,?)",
        [("run-1", "2026-06-10", "ZZZ", 0, None, "tech")],
    )
    mem_db.commit()
    out = bd.latest_positions(mem_db)
    assert out["positions"] == []
    assert out["cash_weight"] == pytest.approx(1.0)
    assert out["invested_weight"] == pytest.approx(0.0)


def test_latest_positions_picks_latest_run(mem_db):
    mem_db.executemany(
        "INSERT INTO pipeline_runs (run_id, run_date, run_type, strategy, regime,"
        " portfolio_value, cash) VALUES (?,?,?,?,?,?,?)",
        [
            ("run-1", "2026-06-09", "live", "s104", "BULL_CALM", 9000.0, 8000.0),
            ("run-2", "2026-06-10", "live", "s104", "CHOPPY", 10000.0, 9000.0),
        ],
    )
    mem_db.executemany(
        "INSERT INTO ticker_daily_state VALUES (?,?,?,?,?,?)",
        [
            ("run-1", "2026-06-09", "AAA", 1, 0.05, "tech"),
            ("run-2", "2026-06-10", "BBB", 1, 0.08, "fin"),
        ],
    )
    mem_db.commit()
    out = bd.latest_positions(mem_db)
    assert out["run_id"] == "run-2"
    assert out["regime"] == "CHOPPY"
    assert out["positions"][0]["ticker"] == "BBB"


def test_latest_positions_ordered_desc(mem_db):
    mem_db.execute(
        "INSERT INTO pipeline_runs (run_id, run_date, run_type, strategy, regime,"
        " portfolio_value, cash) VALUES (?,?,?,?,?,?,?)",
        ("run-1", "2026-06-10", "live", "s104", "BULL_CALM", 10000.0, 8000.0),
    )
    mem_db.executemany(
        "INSERT INTO ticker_daily_state VALUES (?,?,?,?,?,?)",
        [
            ("run-1", "2026-06-10", "AAA", 1, 0.05, "tech"),
            ("run-1", "2026-06-10", "BBB", 1, 0.10, "fin"),
        ],
    )
    mem_db.commit()
    out = bd.latest_positions(mem_db)
    assert out["positions"][0]["ticker"] == "BBB"
    assert out["positions"][1]["ticker"] == "AAA"


# ---------------------------------------------------------------------------
# spy_return_series()
# ---------------------------------------------------------------------------

def test_spy_return_series_basic(mem_db):
    mem_db.executemany(
        "INSERT INTO ticker_forward_returns VALUES (?,?,?,?,?,?,?,?)",
        [
            ("2026-06-01", "SPY", 500.0, None, None, None, None, None),
            ("2026-06-02", "SPY", 505.0, None, None, None, None, None),
            ("2026-06-03", "SPY", 500.0, None, None, None, None, None),
        ],
    )
    mem_db.commit()
    s = bd.spy_return_series(mem_db)
    assert len(s) == 2
    assert s.iloc[0] == pytest.approx(0.01)
    assert s.iloc[1] == pytest.approx(-0.00990099, rel=1e-4)
    assert s.index[0] == "2026-06-02"


def test_spy_return_series_empty(mem_db):
    s = bd.spy_return_series(mem_db)
    assert s.empty


def test_spy_return_series_skips_null_prices(mem_db):
    mem_db.executemany(
        "INSERT INTO ticker_forward_returns VALUES (?,?,?,?,?,?,?,?)",
        [
            ("2026-06-01", "SPY", 500.0, None, None, None, None, None),
            ("2026-06-02", "SPY", None, None, None, None, None, None),
            ("2026-06-03", "SPY", 510.0, None, None, None, None, None),
        ],
    )
    mem_db.commit()
    s = bd.spy_return_series(mem_db)
    assert len(s) == 1
    assert s.index[0] == "2026-06-03"


def test_spy_return_series_ignores_other_tickers(mem_db):
    mem_db.executemany(
        "INSERT INTO ticker_forward_returns VALUES (?,?,?,?,?,?,?,?)",
        [
            ("2026-06-01", "SPY", 500.0, None, None, None, None, None),
            ("2026-06-02", "SPY", 505.0, None, None, None, None, None),
            ("2026-06-01", "AAPL", 150.0, None, None, None, None, None),
            ("2026-06-02", "AAPL", 155.0, None, None, None, None, None),
        ],
    )
    mem_db.commit()
    s = bd.spy_return_series(mem_db)
    assert len(s) == 1
    assert s.name == "spy_return"


# ---------------------------------------------------------------------------
# load_close_series()
# ---------------------------------------------------------------------------

def test_load_close_series_missing_dir(tmp_path):
    result = bd.load_close_series(tmp_path / "nonexistent", "AAPL")
    assert result is None


def test_load_close_series_missing_ticker(tmp_path):
    (tmp_path / "SPY").mkdir()
    result = bd.load_close_series(tmp_path, "AAPL")
    assert result is None


def test_load_close_series_reads_parquet(tmp_path):
    ticker_dir = tmp_path / "AAPL"
    ticker_dir.mkdir()
    dates = pd.date_range("2026-06-01", periods=5)
    df = pd.DataFrame({"close": [100.0, 101.0, 102.0, 103.0, 104.0]}, index=dates)
    df.to_parquet(ticker_dir / "1d.parquet")
    s = bd.load_close_series(tmp_path, "AAPL")
    assert s is not None
    assert len(s) == 5
    assert s.iloc[0] == 100.0
    assert s.index[0] == "2026-06-01"


# ---------------------------------------------------------------------------
# load_strategy_risk_controls() — non-dict regime params skipped
# ---------------------------------------------------------------------------

def test_load_controls_non_dict_regime_params_skipped(tmp_path):
    cfg = {
        "regime_params": {
            "BULL_CALM": {"max_position_pct": 0.12},
            "BAD_REGIME": "not_a_dict",
            "ALSO_BAD": 42,
        },
    }
    path = tmp_path / "cfg.json"
    path.write_text(json.dumps(cfg))
    out = bd.load_strategy_risk_controls(path)
    assert "BULL_CALM" in out["regime_params"]
    assert "BAD_REGIME" not in out["regime_params"]
    assert "ALSO_BAD" not in out["regime_params"]


def test_load_controls_pinned_path_detection(tmp_path):
    cfg_path = tmp_path / ".subrepo_runtime" / "repos" / "cfg.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(json.dumps({"regime_params": {}}))
    out = bd.load_strategy_risk_controls(cfg_path)
    assert out["pinned"] is True


def test_load_controls_non_pinned_path(tmp_path):
    cfg_path = tmp_path / "some" / "other" / "cfg.json"
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(json.dumps({"regime_params": {}}))
    out = bd.load_strategy_risk_controls(cfg_path)
    assert out["pinned"] is False


# ---------------------------------------------------------------------------
# read_sleeve_shadow() — edge cases
# ---------------------------------------------------------------------------

def test_sleeve_reversal_threshold_boundary(tmp_path):
    """reversal_dd_threshold=0.5: exactly 0.5 should NOT trigger."""
    log = tmp_path / "sleeve.jsonl"
    rec = {
        "book_state": {
            "sleeve_contribution_pct": -0.01,
            "max_dd_budget_consumption_pct": 0.5,
        }
    }
    log.write_text(json.dumps(rec))
    out = bd.read_sleeve_shadow(log)
    assert out["reversal_metrics"]["triggered"] is False


def test_sleeve_reversal_threshold_just_above(tmp_path):
    log = tmp_path / "sleeve.jsonl"
    rec = {
        "book_state": {
            "sleeve_contribution_pct": -0.01,
            "max_dd_budget_consumption_pct": 0.501,
        }
    }
    log.write_text(json.dumps(rec))
    out = bd.read_sleeve_shadow(log)
    assert out["reversal_metrics"]["triggered"] is True


def test_sleeve_custom_reversal_sessions(tmp_path):
    log = tmp_path / "sleeve.jsonl"
    records = [
        {"book_state": {"sleeve_contribution_pct": -0.01, "max_dd_budget_consumption_pct": 0.6}}
        for _ in range(20)
    ]
    log.write_text("\n".join(json.dumps(r) for r in records))
    out = bd.read_sleeve_shadow(log, reversal_sessions=5)
    assert out["reversal_metrics"]["window_sessions"] == 5
    assert out["reversal_metrics"]["contribution_sum_pct"] == pytest.approx(-0.05)


def test_sleeve_no_book_state_wrapper(tmp_path):
    """Records without book_state wrapper — fields at top level."""
    log = tmp_path / "sleeve.jsonl"
    rec = {
        "sleeve_contribution_pct": -0.01,
        "max_dd_budget_consumption_pct": 0.7,
        "dd_budget_pct": 0.15,
        "dd_budget_consumption_pct": 0.45,
        "spy_notional": 1000.0,
    }
    log.write_text(json.dumps(rec))
    out = bd.read_sleeve_shadow(log)
    assert out["present"] is True
    assert out["reversal_metrics"]["triggered"] is True


# ---------------------------------------------------------------------------
# dd_budget_consumption() with censored input
# ---------------------------------------------------------------------------

def test_dd_budget_consumption_censored_input():
    dd = {"censored": "no_equity_curve(portfolio_daily_metrics empty for run_type)"}
    out = bd.dd_budget_consumption(dd, limit=0.15)
    assert out["censored"] == dd["censored"]
    assert out["limit"] == 0.15
    assert "max_consumption" not in out


# ---------------------------------------------------------------------------
# running_drawdown() — additional edge cases
# ---------------------------------------------------------------------------

def test_running_drawdown_all_same_value():
    curve = pd.DataFrame({
        "date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "portfolio_value": [100.0, 100.0, 100.0],
        "daily_return": [None, 0.0, 0.0],
    })
    out = bd.running_drawdown(curve)
    assert out["max_drawdown"] == 0.0
    assert out["current_drawdown"] == 0.0
    assert out["peak_value"] == 100.0


def test_running_drawdown_two_peaks():
    curve = pd.DataFrame({
        "date": ["2026-01-01", "2026-01-02", "2026-01-03",
                 "2026-01-04", "2026-01-05"],
        "portfolio_value": [100.0, 110.0, 90.0, 120.0, 96.0],
        "daily_return": [None, 0.1, -0.182, 0.333, -0.2],
    })
    out = bd.running_drawdown(curve)
    assert out["max_drawdown"] == pytest.approx(0.2)
    assert out["max_drawdown_date"] == "2026-01-05"
    assert out["peak_value"] == 120.0


# ---------------------------------------------------------------------------
# per_name_betas() — empty benchmark
# ---------------------------------------------------------------------------

def test_per_name_betas_empty_benchmark():
    closes = {"SPY": pd.Series(dtype=float), "AAPL": pd.Series([100, 101, 102], dtype=float)}
    out = bd.per_name_betas(closes, window=63, min_obs=20)
    assert out["AAPL"]["censored"] == bd.CENSOR_NO_SPY


def test_per_name_betas_name_with_empty_series():
    n = 80
    dates = [f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}" for i in range(n)]
    spy = pd.Series([100 + i * 0.5 for i in range(n)], index=dates, dtype=float)
    closes = {"SPY": spy, "EMPTY": pd.Series(dtype=float)}
    out = bd.per_name_betas(closes, window=63, min_obs=20)
    assert "no_price_series" in out["EMPTY"]["censored"]


# ---------------------------------------------------------------------------
# beta_composition() — sleeve without spy_notional
# ---------------------------------------------------------------------------

def test_beta_composition_sleeve_no_spy_notional():
    pos = {
        "portfolio_value": 10000.0,
        "positions": [{"ticker": "AAA", "weight": 0.3, "sector": "tech"}],
    }
    betas = {"AAA": {"beta": 1.5, "n_obs": 60, "censored": None}}
    sleeve = {"present": True, "last": {}}
    out = bd.beta_composition(pos, betas, sleeve)
    assert out["sleeve_leg"] is None
    assert out["book_beta_measured_names"] == pytest.approx(0.45)


def test_beta_composition_sleeve_no_pv():
    pos = {
        "portfolio_value": None,
        "positions": [{"ticker": "AAA", "weight": 0.3, "sector": "tech"}],
    }
    betas = {"AAA": {"beta": 1.5, "n_obs": 60, "censored": None}}
    sleeve = {"present": True, "last": {"spy_notional": 1000.0}}
    out = bd.beta_composition(pos, betas, sleeve)
    assert out["sleeve_leg"] is None
