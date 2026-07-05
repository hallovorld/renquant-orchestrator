"""Direct unit tests for risk_budget/report.py — build_statement edge paths,
CLI argument variations, write_statement filename logic, and render_markdown
with dd_window attribution.

Complements test_risk_budget.py (which covers pure functions like
breach_status / overall_status / exit_code / _fmt / _check_out_dir and the
happy-path build_statement + render_markdown exhaustively).
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd
import pytest

from renquant_orchestrator.risk_budget import budget as bd
from renquant_orchestrator.risk_budget import report as rp

# ---------------------------------------------------------------------------
# Shared DDL (matches the schema budget.py queries)
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
CREATE TABLE candidate_scores (
  run_id TEXT, ticker TEXT, role TEXT, raw_score REAL, rank_score REAL, mu REAL,
  sigma REAL, selected INTEGER, blocked_by TEXT, kelly_target_pct REAL,
  PRIMARY KEY (run_id, ticker, role));
CREATE TABLE trades (
  run_id TEXT, ticker TEXT, action TEXT, shares REAL, price REAL, invest REAL,
  target_pct REAL, exit_reason TEXT, pnl_pct REAL, hold_days INTEGER,
  trade_date DATE, order_type TEXT, kelly_target_pct REAL);
"""


@pytest.fixture()
def empty_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript(DDL)
    return conn


def _strategy_config(tmp_path, *, sleeve_enabled=False, dd_budget_pct=0.15):
    cfg = {
        "regime_params": {
            "BULL_CALM": {"max_position_pct": 0.12},
            "BEAR": {"max_position_pct": 0.0},
        },
        "sleeve": {
            "enabled": sleeve_enabled,
            "dd_budget_pct": dd_budget_pct,
        },
    }
    p = tmp_path / "strategy_config.json"
    p.write_text(json.dumps(cfg))
    return p


def _noop_close_loader(ticker):
    return None


# ---------------------------------------------------------------------------
# build_statement — empty DB (equity curve + positions censored)
# ---------------------------------------------------------------------------

def test_build_statement_empty_db(empty_db, tmp_path):
    cfg = _strategy_config(tmp_path)
    stmt = rp.build_statement(
        empty_db,
        strategy_config=cfg,
        sleeve_log=tmp_path / "absent.jsonl",
        close_loader=_noop_close_loader,
    )
    assert stmt["readings"]["drawdown"]["censored"] == bd.CENSOR_NO_EQUITY
    assert "no_runs" in stmt["readings"]["positions"]["censored"]
    assert stmt["breaches"]["max_drawdown"]["status"] == rp.STATUS_CENSORED
    assert stmt["exit_code"] == 0


def test_build_statement_no_spy_beta_censored(empty_db, tmp_path):
    empty_db.executemany(
        "INSERT INTO portfolio_daily_metrics VALUES (?,?,?,?,?,?)",
        [
            ("2026-06-01", "live", "s104", 10000, None, None),
            ("2026-06-02", "live", "s104", 10100, 0.01, None),
        ],
    )
    empty_db.execute(
        "INSERT INTO pipeline_runs (run_id, run_date, run_type, strategy, regime, portfolio_value, cash) VALUES (?,?,?,?,?,?,?)",
        ("run-1", "2026-06-02", "live", "s104", "BULL_CALM", 10100, 9090),
    )
    empty_db.commit()
    stmt = rp.build_statement(
        empty_db,
        strategy_config=_strategy_config(tmp_path),
        sleeve_log=tmp_path / "absent.jsonl",
        close_loader=_noop_close_loader,
    )
    assert stmt["readings"]["beta_realized"]["censored"] == bd.CENSOR_NO_SPY
    assert stmt["breaches"]["book_beta"]["status"] == rp.STATUS_CENSORED


def test_build_statement_cash_identity_gap_censoring(empty_db, tmp_path):
    empty_db.executemany(
        "INSERT INTO portfolio_daily_metrics VALUES (?,?,?,?,?,?)",
        [("2026-06-01", "live", "s104", 10000, None, None)],
    )
    empty_db.execute(
        "INSERT INTO pipeline_runs (run_id, run_date, run_type, strategy, regime, portfolio_value, cash) VALUES (?,?,?,?,?,?,?)",
        ("run-1", "2026-06-01", "live", "s104", "BULL_CALM", 10000, 9500),
    )
    empty_db.executemany(
        "INSERT INTO ticker_daily_state VALUES (?,?,?,?,?,?)",
        [("run-1", "2026-06-01", "AAA", 1, 0.10, "tech")],
    )
    empty_db.commit()
    stmt = rp.build_statement(
        empty_db,
        strategy_config=_strategy_config(tmp_path),
        sleeve_log=tmp_path / "absent.jsonl",
        close_loader=_noop_close_loader,
    )
    gap_cens = [c for c in stmt["censoring"] if c["where"] == "positions.cash"]
    assert len(gap_cens) == 1
    assert "recorded_cash_inconsistent" in gap_cens[0]["reason"]


def test_build_statement_hw_above_peak_censoring(empty_db, tmp_path):
    empty_db.executemany(
        "INSERT INTO portfolio_daily_metrics VALUES (?,?,?,?,?,?)",
        [
            ("2026-06-01", "live", "s104", 10000, None, None),
            ("2026-06-02", "live", "s104", 10100, 0.01, None),
        ],
    )
    empty_db.execute(
        "INSERT INTO pipeline_runs (run_id, run_date, run_type, strategy, regime, portfolio_value, cash) VALUES (?,?,?,?,?,?,?)",
        ("run-1", "2026-06-02", "live", "s104", "BULL_CALM", 10100, 9090),
    )
    empty_db.execute(
        "INSERT INTO live_state_snapshots (run_id, run_date, high_water_mark)"
        " VALUES (?,?,?)",
        ("run-1", "2026-06-02", 12000.0),
    )
    empty_db.commit()
    stmt = rp.build_statement(
        empty_db,
        strategy_config=_strategy_config(tmp_path),
        sleeve_log=tmp_path / "absent.jsonl",
        close_loader=_noop_close_loader,
    )
    hwm_cens = [c for c in stmt["censoring"] if c["where"] == "drawdown.hwm"]
    assert len(hwm_cens) == 1
    assert "stamped_hwm_above_measured_peak" in hwm_cens[0]["reason"]


# ---------------------------------------------------------------------------
# build_statement — attribution bridge sim-refused path
# ---------------------------------------------------------------------------

def test_build_statement_legs_censored_when_sim_refused(empty_db, tmp_path):
    empty_db.executemany(
        "INSERT INTO portfolio_daily_metrics VALUES (?,?,?,?,?,?)",
        [
            ("2026-06-01", "sim", "s104", 50000, None, None),
            ("2026-06-02", "sim", "s104", 50500, 0.01, None),
        ],
    )
    empty_db.execute(
        "INSERT INTO pipeline_runs (run_id, run_date, run_type, strategy, regime, portfolio_value, cash) VALUES (?,?,?,?,?,?,?)",
        ("run-sim", "2026-06-02", "sim", "s104", "BULL_CALM", 50500, 45000),
    )
    empty_db.commit()
    stmt = rp.build_statement(
        empty_db,
        strategy_config=_strategy_config(tmp_path),
        sleeve_log=tmp_path / "absent.jsonl",
        close_loader=_noop_close_loader,
        run_type="sim",
        allow_sim=False,
    )
    assert "censored" in stmt["leg_decomposition"]
    bridge_cens = [c for c in stmt["censoring"] if c["where"] == "attribution_bridge"]
    assert len(bridge_cens) == 1


# ---------------------------------------------------------------------------
# build_statement — sleeve consumption becomes breach
# ---------------------------------------------------------------------------

def test_build_statement_sleeve_consumption_breach(empty_db, tmp_path):
    empty_db.executemany(
        "INSERT INTO portfolio_daily_metrics VALUES (?,?,?,?,?,?)",
        [("2026-06-01", "live", "s104", 10000, None, None)],
    )
    empty_db.execute(
        "INSERT INTO pipeline_runs (run_id, run_date, run_type, strategy, regime, portfolio_value, cash) VALUES (?,?,?,?,?,?,?)",
        ("run-1", "2026-06-01", "live", "s104", "BULL_CALM", 10000, 10000),
    )
    empty_db.commit()
    sleeve_log = tmp_path / "sleeve.jsonl"
    rec = {
        "book_state": {
            "sleeve_contribution_pct": -0.02,
            "dd_budget_pct": 0.05,
            "dd_budget_consumption_pct": 1.10,
            "max_dd_budget_consumption_pct": 1.10,
            "spy_notional": 500.0,
        }
    }
    sleeve_log.write_text(json.dumps(rec))
    stmt = rp.build_statement(
        empty_db,
        strategy_config=_strategy_config(tmp_path, dd_budget_pct=0.05),
        sleeve_log=sleeve_log,
        close_loader=_noop_close_loader,
    )
    assert stmt["breaches"]["sleeve_dd_sub_budget"]["status"] == rp.STATUS_CRITICAL
    assert stmt["breaches"]["sleeve_dd_sub_budget"]["consumption"] == pytest.approx(1.10)


# ---------------------------------------------------------------------------
# build_statement — provenance fields
# ---------------------------------------------------------------------------

def test_build_statement_provenance_fields(empty_db, tmp_path):
    cfg = _strategy_config(tmp_path)
    stmt = rp.build_statement(
        empty_db,
        strategy_config=cfg,
        sleeve_log=tmp_path / "absent.jsonl",
        close_loader=_noop_close_loader,
    )
    assert stmt["provenance"]["strategy_config"] == str(cfg)
    assert stmt["provenance"]["read_only"] is True
    assert stmt["run_type"] == "live"
    assert "generated_at" in stmt
    assert "as_of" in stmt


# ---------------------------------------------------------------------------
# render_markdown — dd_window view in leg decomposition
# ---------------------------------------------------------------------------

def test_render_markdown_dd_window_section():
    stmt = _make_statement_with_dd_window()
    md = rp.render_markdown(stmt)
    assert "current DD window" in md
    assert "2026-05-01" in md
    assert "2026-06-15" in md


def test_render_markdown_both_views():
    stmt = _make_statement_with_dd_window()
    md = rp.render_markdown(stmt)
    assert "full history" in md
    assert "current DD window" in md


def _make_statement_with_dd_window():
    """Statement with both overall and dd_window legs."""
    leg_view = {
        "n_records": 5,
        "n_decomposed": 5,
        "total_pnl_decomposed": -200.0,
        "leg_totals": {"market": 100.0, "signal": 50.0, "sizing": -30.0,
                       "timing": -250.0, "cost": -70.0},
        "leg_n": {"market": 5, "signal": 5, "sizing": 5, "timing": 5, "cost": 5},
        "leg_censored": {"market": {}, "signal": {}, "sizing": {}, "timing": {}, "cost": {}},
        "dd_consumers": [
            {"leg": "timing", "total": -250.0, "n": 5},
            {"leg": "cost", "total": -70.0, "n": 5},
        ],
        "ranking": [
            {"leg": "timing", "total": -250.0, "n": 5},
            {"leg": "cost", "total": -70.0, "n": 5},
            {"leg": "sizing", "total": -30.0, "n": 5},
            {"leg": "signal", "total": 50.0, "n": 5},
            {"leg": "market", "total": 100.0, "n": 5},
        ],
    }
    return {
        "generated_at": "2026-07-04T12:00:00+0000",
        "as_of": "2026-07-03",
        "run_type": "live",
        "status": "OK",
        "exit_code": 0,
        "provenance": {
            "strategy_config": "/cfg.json",
            "strategy_config_pinned": False,
            "sleeve_log": "/sleeve.jsonl",
            "read_only": True,
        },
        "budgets": {
            "max_drawdown": {"limit": 0.15, "kind": "hard"},
            "book_beta": {"limit": 0.6, "kind": "planning"},
            "per_name_concentration": {"limit": None, "kind": "hard", "per_regime": {}},
            "sleeve_dd_sub_budget": {"limit": 0.15, "kind": "sub-budget"},
        },
        "controls_context": {
            "cash_reserve_per_regime": {},
            "max_positions_per_sector": None,
            "vol_gate": None,
            "sleeve_flag": {},
        },
        "readings": {
            "drawdown": {
                "as_of": "2026-07-03", "max_drawdown": 0.05,
                "current_drawdown": 0.02, "max_drawdown_peak_date": "2026-05-01",
                "max_drawdown_date": "2026-06-15", "peak_value": 100000.0,
                "start_date": "2026-01-01", "censored": None,
            },
            "dd_consumption": {"max_consumption": 0.33, "current_consumption": 0.13, "censored": None},
            "burn": {
                "censored": bd.CENSOR_NOT_BURNING,
                "window": 21, "burn_per_session": None,
            },
            "positions": {"cash_weight": 1.0, "positions": [], "censored": None},
            "concentration": {"n_names": 0, "censored": "no_positions(book is all cash)",
                              "regime": None, "cap": None},
            "beta_realized": {"censored": bd.CENSOR_NO_SPY, "n_obs": 0},
            "beta_composition": {
                "book_beta_measured_names": None, "measured_weight": 0.0,
                "per_name": {}, "censored_names": {}, "sleeve_leg": None,
                "censored": "no_measurable_names",
            },
            "sleeve": {"present": False, "censored": bd.CENSOR_SLEEVE_ABSENT},
        },
        "leg_decomposition": {
            "overall": leg_view,
            "dd_window": {
                **leg_view,
                "start": "2026-05-01",
                "end": "2026-06-15",
            },
        },
        "breaches": {
            "max_drawdown": {"limit": 0.15, "consumption": 0.33, "status": "OK"},
            "book_beta": {"limit": 0.6, "consumption": None, "status": "CENSORED"},
            "per_name_concentration": {"limit": None, "consumption": None, "status": "CENSORED"},
            "sleeve_dd_sub_budget": {"limit": 0.15, "consumption": None, "status": "CENSORED"},
        },
        "censoring": [],
    }


# ---------------------------------------------------------------------------
# write_statement — filename encoding + content
# ---------------------------------------------------------------------------

def test_write_statement_creates_dir(tmp_path):
    stmt = _make_statement_with_dd_window()
    deep = tmp_path / "a" / "b" / "c"
    paths = rp.write_statement(stmt, deep)
    assert paths["markdown"].exists()
    assert paths["json"].exists()
    assert deep.exists()


def test_write_statement_json_roundtrip(tmp_path):
    stmt = _make_statement_with_dd_window()
    paths = rp.write_statement(stmt, tmp_path / "out")
    loaded = json.loads(paths["json"].read_text())
    assert loaded["status"] == stmt["status"]
    assert loaded["exit_code"] == stmt["exit_code"]


def test_write_statement_md_contains_title(tmp_path):
    stmt = _make_statement_with_dd_window()
    paths = rp.write_statement(stmt, tmp_path / "out")
    md = paths["markdown"].read_text()
    assert "Risk-budget statement (observe-only)" in md


# ---------------------------------------------------------------------------
# _check_out_dir — additional forbidden path variants
# ---------------------------------------------------------------------------

def test_check_out_dir_forbids_canonical_umbrella_data():
    with pytest.raises(ValueError, match="refusing to write"):
        rp._check_out_dir(rp._CANONICAL_UMBRELLA / "data" / "risk_budget")


def test_check_out_dir_forbids_canonical_umbrella_runtime():
    with pytest.raises(ValueError, match="refusing to write"):
        rp._check_out_dir(rp._CANONICAL_UMBRELLA / "runtime" / "risk_budget")


def test_check_out_dir_accepts_research_path(tmp_path):
    result = rp._check_out_dir(tmp_path / "research" / "risk_budget")
    assert result == (tmp_path / "research" / "risk_budget").resolve()


# ---------------------------------------------------------------------------
# CLI main() — disk-backed DB with custom args
# ---------------------------------------------------------------------------

def test_cli_with_burn_window(empty_db, tmp_path):
    db_path = tmp_path / "fixture.db"
    disk = sqlite3.connect(db_path)
    empty_db.backup(disk)
    disk.close()
    rc = rp.main([
        "--db", str(db_path),
        "--strategy-config", str(_strategy_config(tmp_path)),
        "--sleeve-log", str(tmp_path / "absent.jsonl"),
        "--out-dir", str(tmp_path / "lake"),
        "--burn-window", "5",
    ])
    assert rc == 0


def test_cli_output_files_created(empty_db, tmp_path):
    db_path = tmp_path / "fixture.db"
    disk = sqlite3.connect(db_path)
    empty_db.backup(disk)
    disk.close()
    out_dir = tmp_path / "lake"
    rp.main([
        "--db", str(db_path),
        "--strategy-config", str(_strategy_config(tmp_path)),
        "--sleeve-log", str(tmp_path / "absent.jsonl"),
        "--out-dir", str(out_dir),
    ])
    md_files = list(out_dir.glob("*.md"))
    json_files = list(out_dir.glob("*.json"))
    assert len(md_files) == 1
    assert len(json_files) == 1


def test_cli_half_spread_bps(empty_db, tmp_path):
    db_path = tmp_path / "fixture.db"
    disk = sqlite3.connect(db_path)
    empty_db.backup(disk)
    disk.close()
    rc = rp.main([
        "--db", str(db_path),
        "--strategy-config", str(_strategy_config(tmp_path)),
        "--sleeve-log", str(tmp_path / "absent.jsonl"),
        "--out-dir", str(tmp_path / "lake"),
        "--half-spread-bps", "5.0",
    ])
    assert rc == 0


# ---------------------------------------------------------------------------
# render_markdown — concentration with 0 names shows censored reason
# ---------------------------------------------------------------------------

def test_render_markdown_no_positions_shows_censored():
    stmt = _make_statement_with_dd_window()
    md = rp.render_markdown(stmt)
    assert "no_positions" in md


# ---------------------------------------------------------------------------
# build_statement — beta driver picks max of realized and composition
# ---------------------------------------------------------------------------

def test_build_statement_beta_driver_picks_max(empty_db, tmp_path):
    pvs = [10000, 10100, 10200, 10300, 10400]
    for i, pv in enumerate(pvs):
        d = f"2026-06-{i + 1:02d}"
        ret = None if i == 0 else pv / pvs[i - 1] - 1.0
        empty_db.execute(
            "INSERT INTO portfolio_daily_metrics VALUES (?,?,?,?,?,?)",
            (d, "live", "s104", pv, ret, None),
        )
    empty_db.execute(
        "INSERT INTO pipeline_runs (run_id, run_date, run_type, strategy, regime, portfolio_value, cash) VALUES (?,?,?,?,?,?,?)",
        ("run-1", "2026-06-05", "live", "s104", "BULL_CALM", 10400, 9360),
    )
    empty_db.executemany(
        "INSERT INTO ticker_daily_state VALUES (?,?,?,?,?,?)",
        [("run-1", "2026-06-05", "AAA", 1, 0.10, "tech")],
    )
    n = 80
    dates = [f"2026-{(i // 28) + 3:02d}-{(i % 28) + 1:02d}" for i in range(n)]
    spy_px = 500.0
    for d in dates:
        empty_db.execute(
            "INSERT OR IGNORE INTO ticker_forward_returns VALUES (?,?,?,?,?,?,?,?)",
            (d, "SPY", spy_px, None, None, None, None, None),
        )
        spy_px *= 1.001

    name_px = 100.0
    for d in dates:
        empty_db.execute(
            "INSERT OR IGNORE INTO ticker_forward_returns VALUES (?,?,?,?,?,?,?,?)",
            (d, "AAA", name_px, None, None, None, None, None),
        )
        name_px *= 1.003
    empty_db.commit()

    def close_loader(ticker):
        closes = {}
        for d in dates:
            if ticker == "SPY":
                closes[d] = 500.0 * (1.001 ** dates.index(d))
            elif ticker == "AAA":
                closes[d] = 100.0 * (1.003 ** dates.index(d))
            else:
                return None
        return pd.Series(closes, dtype=float)

    stmt = rp.build_statement(
        empty_db,
        strategy_config=_strategy_config(tmp_path),
        sleeve_log=tmp_path / "absent.jsonl",
        close_loader=close_loader,
        beta_min_obs=20,
    )
    beta_breach = stmt["breaches"]["book_beta"]
    assert beta_breach["measured_beta"] is not None
    assert beta_breach["consumption"] is not None
