"""Unit tests for the weekly model-promote chain monitor.

All tests use synthetic temp artifact/log dirs and a mocked clock + alert sink.
None touch the real ``artifacts/prod`` dir, a real broker, or live state.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from renquant_orchestrator import weekly_promote_monitor as wpm
from renquant_orchestrator.cli import main


# --- helpers ----------------------------------------------------------------

NOW = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)


def _staging_name(family: str, ts: datetime) -> str:
    stamp = ts.strftime("%Y%m%dT%H%M%SZ")
    return f"{family}.weekly_{stamp}.staging.json"


def _write_staging(prod_dir, family: str, ts: datetime) -> None:
    (prod_dir / _staging_name(family, ts)).write_text("{}", encoding="utf-8")


def _build(prod_dir, log_dir, *, now=NOW, stale_after_days=wpm.STALE_AFTER_DAYS):
    return wpm.build_weekly_promote_health(
        prod_artifacts_dir=prod_dir,
        promote_log_dir=log_dir,
        stale_after_days=stale_after_days,
        now=now,
    )


@pytest.fixture
def dirs(tmp_path):
    prod = tmp_path / "prod"
    logs = tmp_path / "logs"
    prod.mkdir()
    logs.mkdir()
    return prod, logs


# --- record shape -----------------------------------------------------------

def test_record_has_expected_fields(dirs):
    prod, logs = dirs
    _write_staging(prod, "panel-ltr.alpha158_fund", NOW - timedelta(days=1))
    health = _build(prod, logs)
    for field in (
        "schema_version",
        "owner_repo",
        "as_of",
        "prod_artifacts_dir",
        "promote_log_dir",
        "expected_cadence_days",
        "stale_after_days",
        "newest_staging_artifact",
        "newest_staging_timestamp",
        "staging_age_days",
        "newest_promote_log",
        "last_run_status",
        "health_verdict",
        "alert",
        "summary",
    ):
        assert field in health, f"missing field: {field}"
    assert health["schema_version"] == wpm.SCHEMA_VERSION
    assert health["owner_repo"] == "renquant-orchestrator"


# --- fresh / on-schedule does NOT alert -------------------------------------

def test_fresh_chain_does_not_alert(dirs):
    prod, logs = dirs
    _write_staging(prod, "panel-ltr.alpha158_fund", NOW - timedelta(days=2))
    _write_staging(prod, "panel-rank-calibration", NOW - timedelta(days=2))
    (logs / "2026-06-20.log").write_text(
        "=== weekly_wf_promote started ===\nVERDICT: PASS\n", encoding="utf-8"
    )
    health = _build(prod, logs)
    assert health["health_verdict"] == "ok"
    assert health["alert"] is False
    assert wpm.emit_alert(health, quiet=True) is False


def test_clean_gate_reject_is_healthy_not_alerting(dirs):
    # The gate refusing a bad model is a HEALTHY outcome: the chain ran.
    prod, logs = dirs
    _write_staging(prod, "panel-ltr.alpha158_fund", NOW - timedelta(days=1))
    (logs / "2026-06-21.log").write_text(
        "WF result: 3/3 sim cuts failed\nVERDICT: FAIL\n"
        "WF gate REJECTED staged model — production unchanged.\n",
        encoding="utf-8",
    )
    health = _build(prod, logs)
    assert health["last_run_status"] == "reject"
    assert health["health_verdict"] == "ok"
    assert health["alert"] is False


# --- stale chain DOES alert -------------------------------------------------

def test_stale_chain_alerts(dirs):
    prod, logs = dirs
    # Newest staging artifact is older than the staleness tolerance.
    _write_staging(
        prod, "panel-ltr.alpha158_fund", NOW - timedelta(days=wpm.STALE_AFTER_DAYS + 3)
    )
    health = _build(prod, logs)
    assert health["health_verdict"] == "stale"
    assert health["alert"] is True
    assert health["staging_age_days"] > wpm.STALE_AFTER_DAYS


def test_stale_boundary_just_within_tolerance_is_ok(dirs):
    prod, logs = dirs
    _write_staging(
        prod, "panel-ltr.alpha158_fund", NOW - timedelta(days=wpm.STALE_AFTER_DAYS - 1)
    )
    health = _build(prod, logs)
    assert health["health_verdict"] == "ok"
    assert health["alert"] is False


def test_stale_chain_emits_alert_through_sink(dirs, monkeypatch):
    prod, logs = dirs
    _write_staging(
        prod, "panel-ltr.alpha158_fund", NOW - timedelta(days=wpm.STALE_AFTER_DAYS + 5)
    )
    posted = {}

    def fake_post(title, body, topic):
        posted["title"] = title
        posted["body"] = body
        posted["topic"] = topic

    monkeypatch.setattr(wpm, "post_ntfy", fake_post)
    health = _build(prod, logs)
    assert wpm.emit_alert(health, topic="renquant") is True
    assert posted["topic"] == "renquant"
    assert "stale" in posted["body"] or "did not run" in posted["body"]


# --- errored / partial chain DOES alert -------------------------------------

def test_errored_chain_alerts(dirs):
    prod, logs = dirs
    # Fresh staging artifact, but the promote log left a crash traceback and no
    # clean verdict -> errored run.
    _write_staging(prod, "panel-ltr.alpha158_fund", NOW - timedelta(days=1))
    (logs / "2026-06-21.log").write_text(
        "=== weekly_wf_promote started ===\n"
        "Traceback (most recent call last):\n"
        '  File "loader.py", line 388, in _assert\n'
        "ValueError: calibrator/scorer fingerprint mismatch\n",
        encoding="utf-8",
    )
    health = _build(prod, logs)
    assert health["last_run_status"] == "error"
    assert health["health_verdict"] == "error"
    assert health["alert"] is True


# --- graceful degradation ---------------------------------------------------

def test_empty_artifact_dir_is_unknown_not_raising(dirs):
    prod, logs = dirs  # both empty
    health = _build(prod, logs)
    assert health["health_verdict"] == "unknown"
    assert health["alert"] is False
    assert health["newest_staging_artifact"] is None


def test_missing_dirs_are_unknown_not_raising(tmp_path):
    health = _build(tmp_path / "nope-prod", tmp_path / "nope-logs")
    assert health["health_verdict"] == "unknown"
    assert health["alert"] is False


def test_rollback_markers_are_not_counted_as_fresh_runs(dirs):
    prod, logs = dirs
    # Only a recent ROLLBACK file plus an old real staging artifact: the chain
    # is still stale because rollback markers are not fresh promote runs.
    (prod / "panel-ltr.alpha158_fund.weekly_rollback_2026-06-21.json").write_text(
        "{}", encoding="utf-8"
    )
    _write_staging(
        prod, "panel-ltr.alpha158_fund", NOW - timedelta(days=wpm.STALE_AFTER_DAYS + 2)
    )
    health = _build(prod, logs)
    assert health["health_verdict"] == "stale"
    chosen = health["newest_staging_artifact"] or ""
    assert "rollback" not in chosen.rsplit("/", 1)[-1]
    assert chosen.endswith(".staging.json")


def test_newest_staging_artifact_picks_latest_timestamp(dirs):
    prod, logs = dirs
    _write_staging(prod, "panel-ltr.alpha158_fund", NOW - timedelta(days=9))
    _write_staging(prod, "panel-ltr.alpha158_fund", NOW - timedelta(days=2))
    path, ts = wpm.newest_staging_artifact(prod)
    assert ts == (NOW - timedelta(days=2)).replace(microsecond=0)
    assert "20260620" in path.name


# --- log classification -----------------------------------------------------

def test_classify_promote_log_variants(tmp_path):
    pass_log = tmp_path / "pass.log"
    pass_log.write_text("VERDICT: PASS\n", encoding="utf-8")
    assert wpm.classify_promote_log(pass_log)[0] == "pass"

    fail_log = tmp_path / "fail.log"
    fail_log.write_text("VERDICT: FAIL\n", encoding="utf-8")
    assert wpm.classify_promote_log(fail_log)[0] == "reject"

    err_log = tmp_path / "err.log"
    err_log.write_text("Traceback (most recent call last):\nKeyError\n", encoding="utf-8")
    assert wpm.classify_promote_log(err_log)[0] == "error"

    assert wpm.classify_promote_log(None)[0] == "unknown"


# --- CLI --------------------------------------------------------------------

def test_cli_weekly_promote_health_exit_codes(dirs, monkeypatch, capsys):
    prod, logs = dirs
    monkeypatch.setattr(wpm, "post_ntfy", lambda *a, **k: None)

    # Fresh -> exit 0.
    _write_staging(prod, "panel-ltr.alpha158_fund", datetime.now(timezone.utc) - timedelta(days=1))
    rc = main([
        "weekly-promote-health",
        "--prod-artifacts-dir",
        str(prod),
        "--promote-log-dir",
        str(logs),
        "--quiet",
    ])
    out = capsys.readouterr().out
    assert rc == 0
    assert '"health_verdict": "ok"' in out

    # Stale -> exit 2.
    for f in prod.glob("*.json"):
        f.unlink()
    _write_staging(
        prod,
        "panel-ltr.alpha158_fund",
        datetime.now(timezone.utc) - timedelta(days=wpm.STALE_AFTER_DAYS + 4),
    )
    rc = main([
        "weekly-promote-health",
        "--prod-artifacts-dir",
        str(prod),
        "--promote-log-dir",
        str(logs),
        "--quiet",
    ])
    out = capsys.readouterr().out
    assert rc == 2
    assert '"health_verdict": "stale"' in out
