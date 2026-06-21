from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from renquant_orchestrator import weekly_apy_monitor as mod


def _write_audit(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def _recent_date(days_ago: int) -> str:
    """A date `days_ago` before *now*, so audit fixtures stay inside the
    rolling window regardless of when the test runs. Using hard-coded calendar
    dates made `read_recent_rows`' wall-clock cutoff drop boundary rows once the
    fixtures aged past `window_days`, so the test rotted over time."""
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def test_pipeline_shape() -> None:
    pipeline = mod.build_pipeline()

    assert pipeline.name == "weekly-apy-monitor"
    assert [type(job).__name__ for job in pipeline.jobs] == [
        "LoadAuditRowsJob",
        "ComputeWeeklyHealthJob",
        "AlertDecisionJob",
    ]


def test_compute_rolling_apy_uses_first_and_last_equity() -> None:
    apy, n = mod.compute_rolling_apy([
        {"date": "2026-01-01", "equity": 100.0},
        {"date": "2026-01-31", "equity": 110.0},
    ])

    assert n == 2
    assert apy == pytest.approx((1.1 ** (365.0 / 30)) - 1.0)


def test_read_recent_rows_accepts_timezone_aware_dates(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"
    _write_audit(audit, [
        {"date": "2026-05-01T00:00:00+00:00", "equity": 100.0},
        {"date": "2026-06-01T17:00:00+00:00", "equity": 110.0},
    ])

    rows = mod.read_recent_rows(
        audit,
        7,
        now=datetime(2026, 6, 2, 0, 0, tzinfo=timezone.utc),
    )

    assert [row["equity"] for row in rows] == [110.0]


def test_pipeline_alerts_on_low_apy(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"
    _write_audit(audit, [
        {"date": "2026-05-01", "equity": 100.0, "drawdown_pct": 0.01},
        {"date": "2026-05-31", "equity": 101.0, "drawdown_pct": 0.01},
    ])
    ctx = mod.WeeklyApyContext(
        repo_root=tmp_path,
        audit_log=audit,
        window_days=60,
        alert_threshold=0.25,
        quiet=True,
    )

    result = mod.build_pipeline().run(ctx)

    assert result.ok is True
    assert ctx.exit_code == 2
    assert ctx.alert_title == "RenQuant 104 WATCH"
    assert "APY" in ctx.alert_body


def test_pipeline_alerts_on_persistent_drawdown(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"
    # dates relative to now (5 consecutive recent days) so all stay inside the
    # default rolling window — fixes the previous wall-clock-dependent failure.
    _write_audit(audit, [
        {"date": _recent_date(5 - i), "equity": 100.0 + i, "drawdown_pct": 0.25}
        for i in range(5)
    ])
    ctx = mod.WeeklyApyContext(
        repo_root=tmp_path,
        audit_log=audit,
        alert_threshold=-1.0,
        drawdown_days=5,
        quiet=True,
    )

    mod.build_pipeline().run(ctx)

    assert ctx.exit_code == 3
    assert "drawdown" in ctx.alert_body


def test_latest_sharpe_reads_newest_live_row(tmp_path: Path) -> None:
    db = tmp_path / "runs.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "create table portfolio_daily_metrics("
            "run_type text, strategy text, as_of_date text, sharpe_21d real, sharpe_63d real)"
        )
        conn.execute(
            "insert into portfolio_daily_metrics values ('live', 'renquant-104', '2026-01-01', 1.0, 2.0)"
        )
        conn.execute(
            "insert into portfolio_daily_metrics values ('live', 'renquant-104', '2026-01-02', 1.5, 2.5)"
        )

    assert mod.latest_sharpe(db) == (1.5, 2.5)


def test_main_json_outputs_summary(tmp_path: Path, capsys) -> None:
    audit = tmp_path / "audit.jsonl"
    _write_audit(audit, [
        {"date": "2026-05-01", "equity": 100.0, "drawdown_pct": 0.0},
        {"date": "2026-05-31", "equity": 120.0, "drawdown_pct": 0.0},
    ])

    rc = mod.main([
        "--repo-root",
        str(tmp_path),
        "--audit-log",
        str(audit),
        "--window-days",
        "60",
        "--quiet",
        "--json",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert rc == payload["exit_code"]
    assert payload["n_rows"] == 2
    assert payload["apy"] is not None
