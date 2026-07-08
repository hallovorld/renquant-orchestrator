from __future__ import annotations

import json
from pathlib import Path

from renquant_orchestrator.intraday_cash_drag_scorecard import build_scorecard
from renquant_orchestrator.intraday_session_scheduler import (
    RECORD_KIND_TICK,
    SCHEDULER_SCHEMA_VERSION,
)


def _tick(
    session_date: str,
    tick_index: int,
    *,
    cash: float,
    equity: float,
    skipped: list[dict] | None = None,
    counters: dict | None = None,
    tick_at: str | None = None,
) -> dict:
    return {
        "schema_version": SCHEDULER_SCHEMA_VERSION,
        "kind": RECORD_KIND_TICK,
        "session_date": session_date,
        "tick_index": tick_index,
        "tick_at": tick_at or f"{session_date}T10:0{tick_index}:00-04:00",
        "inputs": {
            "live_state": {
                "cash": cash,
                "equity": equity,
            }
        },
        "decisions": {
            "skipped": skipped or [],
            "counters": counters or {},
        },
    }


def _write(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def test_build_scorecard_summarizes_sessions_and_medians(tmp_path: Path) -> None:
    shadow_log = tmp_path / "intraday_decisions_shadow.jsonl"
    _write(
        shadow_log,
        [
            _tick(
                "2026-07-01",
                0,
                cash=700.0,
                equity=1000.0,
                skipped=[
                    {"reasons": ["zero_quantity_after_whole_share_floor"]},
                ],
                counters={"entries_count": 1, "deployed_notional": 50.0, "turnover_notional": 50.0},
            ),
            _tick(
                "2026-07-01",
                1,
                cash=600.0,
                equity=1000.0,
                skipped=[
                    {"reasons": ["insufficient_available_cash"]},
                ],
                counters={"entries_count": 2, "deployed_notional": 80.0, "turnover_notional": 110.0},
            ),
            _tick(
                "2026-07-02",
                0,
                cash=200.0,
                equity=1000.0,
                skipped=[],
                counters={"entries_count": 3, "deployed_notional": 300.0, "turnover_notional": 330.0},
            ),
        ],
    )

    scorecard = build_scorecard(shadow_log)

    assert scorecard["schema_version"] == "rq105-cash-drag-scorecard-v1"
    assert scorecard["n_sessions"] == 2
    assert [s["session_date"] for s in scorecard["sessions"]] == ["2026-07-01", "2026-07-02"]
    assert scorecard["summary"]["median_close_idle_cash_fraction"] == 0.4
    assert scorecard["summary"]["total_whole_share_floor_skip_count"] == 1
    assert scorecard["summary"]["total_insufficient_available_cash_skip_count"] == 1
    assert "target_notional" in scorecard["pending_contract_fields_unavailable"]


def test_build_scorecard_uses_latest_tick_for_close_state_and_counters(tmp_path: Path) -> None:
    shadow_log = tmp_path / "intraday_decisions_shadow.jsonl"
    _write(
        shadow_log,
        [
            _tick(
                "2026-07-03",
                0,
                cash=900.0,
                equity=1000.0,
                counters={"entries_count": 0, "deployed_notional": 0.0, "turnover_notional": 0.0},
            ),
            _tick(
                "2026-07-03",
                2,
                cash=250.0,
                equity=1250.0,
                counters={"entries_count": 4, "deployed_notional": 400.0, "turnover_notional": 450.0},
            ),
        ],
    )

    session = build_scorecard(shadow_log)["sessions"][0]

    assert session["close_cash"] == 250.0
    assert session["close_equity"] == 1250.0
    assert session["close_idle_cash_fraction"] == 0.2
    assert session["entries_count"] == 4
    assert session["deployed_notional"] == 400.0
    assert session["turnover_notional"] == 450.0


def test_build_scorecard_accumulates_skip_reasons_across_ticks(tmp_path: Path) -> None:
    shadow_log = tmp_path / "intraday_decisions_shadow.jsonl"
    _write(
        shadow_log,
        [
            _tick(
                "2026-07-04",
                0,
                cash=500.0,
                equity=1000.0,
                skipped=[
                    {"reasons": ["zero_quantity_after_whole_share_floor", "insufficient_available_cash"]},
                ],
            ),
            _tick(
                "2026-07-04",
                1,
                cash=500.0,
                equity=1000.0,
                skipped=[
                    {"reasons": ["zero_quantity_after_whole_share_floor"]},
                ],
            ),
        ],
    )

    session = build_scorecard(shadow_log)["sessions"][0]

    assert session["whole_share_floor_skip_count"] == 2
    assert session["insufficient_available_cash_skip_count"] == 1
    assert session["skip_reason_counts"] == {
        "insufficient_available_cash": 1,
        "zero_quantity_after_whole_share_floor": 2,
    }


def test_build_scorecard_ignores_non_tick_rows_and_filters_session_dates(tmp_path: Path) -> None:
    shadow_log = tmp_path / "intraday_decisions_shadow.jsonl"
    rows = [
        {
            "schema_version": SCHEDULER_SCHEMA_VERSION,
            "kind": "intraday_session_manifest",
            "session_date": "2026-07-05",
        },
        _tick("2026-07-05", 0, cash=100.0, equity=1000.0),
        _tick("2026-07-06", 0, cash=300.0, equity=1000.0),
    ]
    _write(shadow_log, rows)

    scorecard = build_scorecard(shadow_log, session_dates=["2026-07-06"])

    assert scorecard["n_sessions"] == 1
    assert scorecard["sessions"][0]["session_date"] == "2026-07-06"


def test_build_scorecard_rejects_unknown_schema_version(tmp_path: Path) -> None:
    shadow_log = tmp_path / "intraday_decisions_shadow.jsonl"
    _write(
        shadow_log,
        [
            {
                **_tick("2026-07-07", 0, cash=100.0, equity=1000.0),
                "schema_version": "bad-schema",
            }
        ],
    )

    try:
        build_scorecard(shadow_log)
    except ValueError as exc:
        assert "unsupported schema_version" in str(exc)
    else:
        raise AssertionError("expected ValueError")

