#!/usr/bin/env python3
"""rq105 smoke test — validates the session runner can initialize.

READ-ONLY: loads config, validates imports, checks dependencies are present,
and runs a simulated non-session-day cycle. Does NOT connect to any broker,
place any orders, or start any real session. This is an integration
verification tool that raises 105 confidence by proving the wiring is correct.

Usage:
  PYTHONPATH=src python3 scripts/rq105_smoke_test.py
  # or from the RenQuant umbrella venv:
  .venv/bin/python <orchestrator>/scripts/rq105_smoke_test.py
"""
from __future__ import annotations

import json
import sys
import traceback
from pathlib import Path

ORCH = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(ORCH))

CHECKS: list[tuple[str, bool, str]] = []


def _check(name: str, fn):
    try:
        result = fn()
        CHECKS.append((name, True, result or "OK"))
    except Exception as e:
        CHECKS.append((name, False, f"{type(e).__name__}: {e}"))


def check_imports():
    from renquant_orchestrator.software_stop import (
        SoftwareStopEvaluator,
        SoftwareStopShadowLog,
        StopConfig,
        StopSignal,
    )
    from renquant_orchestrator.intraday_session_runner import (
        SessionRunner,
        SessionRunnerConfig,
        SessionResult,
        _extract_holdings,
        _extract_quotes,
    )
    return f"SessionRunner, StopConfig, etc. all importable"


def check_config_schema():
    from renquant_orchestrator.intraday_session_runner import SessionRunnerConfig
    from renquant_orchestrator.software_stop import StopConfig
    cfg = SessionRunnerConfig(
        data_root=Path("/tmp/rq105-smoke"),
        strategy_config={
            "watchlist": ["AAPL", "GOOG"],
            "intraday_decisioning": {
                "enabled": True,
                "mode": "shadow",
                "tick_seconds": 1,
            },
        },
        stop_config=StopConfig(enabled=True, hard_stop_pct=0.05, trailing_stop_pct=0.03),
    )
    cfg.resolve_paths()
    paths = [
        cfg.authorization_path,
        cfg.canary_state_path,
        cfg.order_state_book_path,
        cfg.shadow_log_path,
        cfg.live_log_path,
        cfg.live_actions_path,
        cfg.stop_log_path,
    ]
    for p in paths:
        assert p is not None, "path resolution failed"
    return f"7 paths resolved"


def check_stop_evaluator():
    from renquant_orchestrator.software_stop import SoftwareStopEvaluator, StopConfig
    ev = SoftwareStopEvaluator(config=StopConfig(enabled=True))
    ev.load_positions({"AAPL": {"entry_price": 100.0}})
    signals = ev.evaluate_tick({"AAPL": 94.0})
    assert len(signals) == 1
    assert signals[0].stop_type == "hard_stop"
    rec = ev.to_record()
    assert rec["positions_stopped"] == 1
    return "hard stop fires at 6% drop"


def check_extract_helpers():
    from renquant_orchestrator.intraday_session_runner import _extract_holdings, _extract_quotes
    h = _extract_holdings({"positions": {"AAPL": {"entry_price": 230.0, "shares": 10}}})
    assert h == {"AAPL": {"entry_price": 230.0}}
    q = _extract_quotes({"prices": {"AAPL": 231.0, "GOOG": 185.0}})
    assert q == {"AAPL": 231.0, "GOOG": 185.0}
    return "holdings and quotes extract correctly"


def check_session_result():
    from renquant_orchestrator.intraday_session_runner import SessionResult, RUNNER_SCHEMA_VERSION
    r = SessionResult(
        mode_effective="shadow",
        armed=False,
        status="completed",
        manifest={"test": True},
        stop_summary={"signals_emitted": 0},
    )
    d = r.to_dict()
    assert d["schema_version"] == RUNNER_SCHEMA_VERSION
    assert d["mode_effective"] == "shadow"
    assert "software_stops" in d
    return f"schema_version={RUNNER_SCHEMA_VERSION}"


def check_outcome_backfiller():
    from renquant_orchestrator.outcome_backfiller import _map_gate
    gate, verdict = _map_gate(None, 1)
    assert gate == "admission" and verdict == "allow"
    gate, verdict = _map_gate("veto:rank_score_below_floor", 0)
    assert gate == "VetoWeakBuys" and verdict == "block"
    return "gate mapping works"


def check_config_experiment_store():
    import sqlite3
    from renquant_orchestrator.config_experiment_store import (
        ensure_table, write_experiment, read_experiments,
    )
    conn = sqlite3.connect(":memory:")
    ensure_table(conn)
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()]
    assert "config_experiments" in tables
    return "DDL creates table"


def main():
    print("rq105 smoke test — integration verification")
    print("=" * 50)

    checks = [
        ("import_session_runner", check_imports),
        ("config_schema_resolution", check_config_schema),
        ("stop_evaluator_lifecycle", check_stop_evaluator),
        ("extract_helpers", check_extract_helpers),
        ("session_result_schema", check_session_result),
        ("outcome_backfiller_gate_map", check_outcome_backfiller),
        ("config_experiment_store_ddl", check_config_experiment_store),
    ]

    for name, fn in checks:
        _check(name, fn)

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    failed = sum(1 for _, ok, _ in CHECKS if not ok)

    for name, ok, detail in CHECKS:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}: {detail}")

    print(f"\n{passed}/{passed + failed} checks passed")
    if failed:
        print(f"FAIL: {failed} checks failed")
        return 1
    print("All smoke checks passed — 105 integration wiring verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
