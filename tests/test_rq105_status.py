"""Tests for ops/renquant105/rq105_status.py (Codex review on PR #419 —
round 2 of the same split-brain-duplication class of finding as PR #417:
root resolution, launchd job discovery, and DB run-selection each had a
dashboard-local approximation instead of reusing the canonical primitive.
This file proves genuine coupling to each — patching the canonical source
and confirming the dashboard's own output changes to match, not just a
coincidentally-matching hardcoded value."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
OPS_DIR = REPO / "ops" / "renquant105"
sys.path.insert(0, str(OPS_DIR))

import rq105_status as dashboard  # noqa: E402


class TestRootResolutionUsesDefaultDataRoot:
    def test_repo_root_calls_default_data_root_not_default_repo_root(self, tmp_path, monkeypatch):
        """_repo_root() must resolve via default_data_root() (the
        RENQUANT_DATA_ROOT-aware resolver this repo's migration uses for
        operator state), not default_repo_root() (the umbrella-checkout
        resolver) — the two are deliberately decoupled elsewhere in this
        repo and the dashboard must follow the same convention."""
        monkeypatch.delenv("RENQUANT_DATA_ROOT", raising=False)
        fake_root = tmp_path / "fake_data_root"
        with mock.patch.object(dashboard, "default_data_root", return_value=fake_root) as mocked:
            result = dashboard._repo_root()
        mocked.assert_called_once()
        assert result == fake_root

    def test_repo_root_honors_renquant_data_root_env(self, tmp_path, monkeypatch):
        explicit = tmp_path / "explicit_data_root"
        monkeypatch.setenv("RENQUANT_DATA_ROOT", str(explicit))
        result = dashboard._repo_root()
        assert result == explicit


class TestLaunchdJobDiscoveryUsesRegistry:
    def test_job_labels_come_from_scheduled_jobs_registry(self):
        """_rq105_job_labels() must derive job_id -> label from the
        scheduled_jobs registry, not a hardcoded com.renquant.rq105- prefix
        scan (the wrapper-era naming that predates the native multirepo
        launchd labels this repo has migrated to)."""
        labels = dashboard._rq105_job_labels()
        # Real native labels from the registry (not the old rq105- prefix scheme).
        assert labels.get("intraday_quote_logger") == "com.renquant.intraday-quote-logger"
        assert labels.get("intraday_session_scheduler") == "com.renquant.intraday-session-scheduler"
        assert labels.get("shadow_realtime_serving") == "com.renquant.shadow-realtime-serving"
        # None of the old-scheme "rq105-" prefixed labels should appear.
        assert not any(v.startswith("com.renquant.rq105-") for v in labels.values())

    def test_job_labels_reflect_registry_changes(self):
        """Prove genuine coupling: if the registry's rq105 job set changes,
        the dashboard's expected-job list changes with it (not a hardcoded
        list that would silently drift from a modified registry)."""
        from renquant_orchestrator.scheduled_jobs import ScheduledJob

        fake_job = ScheduledJob(
            job_id="fake_intraday_job",
            kind="ops",
            cadence="intraday_session",
            command=["renquant-orchestrator", "run-job", "fake_intraday_job"],
            owner_repo="renquant-orchestrator",
            migration_state="native_multirepo",
            production_safe=True,
            launchd_label="com.renquant.fake-intraday-job",
        )
        with mock.patch.object(dashboard, "scheduled_jobs", return_value=(fake_job,)):
            labels = dashboard._rq105_job_labels()
        assert labels == {"fake_intraday_job": "com.renquant.fake-intraday-job"}

    def test_launchd_status_reports_not_loaded_for_registry_jobs_absent_from_launchctl(self):
        """A registry-listed rq105 job that launchctl doesn't report must
        show as 'not loaded', not be silently omitted (the old prefix-scan
        version only ever showed jobs launchctl reported, so a job that
        failed to load at all was invisible)."""
        with mock.patch("subprocess.check_output", return_value="PID\tStatus\tLabel\n"):
            results = dashboard._launchd_status()
        names = {r["name"] for r in results}
        assert "intraday_quote_logger" in names
        matching = [r for r in results if r["name"] == "intraday_quote_logger"]
        assert matching[0]["status"] == "not loaded"
        assert matching[0]["icon"] == dashboard.FAIL


class TestDbRunSelectionUsesCanonicalExporterContract:
    def test_db_latest_run_calls_select_source_run_with_expected_previous_session(self, tmp_path):
        """_db_latest_run() must call export_batch_scores._select_source_run
        against the exporter's own expected_previous_session date, not a
        dashboard-local 'latest live run with non-null panel_score' query
        that could disagree with the real qualifying-run contract."""
        db_path = tmp_path / "data" / "runs.alpaca.db"
        db_path.parent.mkdir(parents=True)
        db_path.touch()

        with mock.patch.object(
            dashboard, "expected_previous_session", return_value="2026-07-06"
        ) as mocked_session, mock.patch.object(
            dashboard, "_select_source_run",
            return_value=("run-abc-live-1", "2026-07-06", {}),
        ) as mocked_select:
            result = dashboard._db_latest_run(tmp_path)

        mocked_session.assert_called_once()
        mocked_select.assert_called_once()
        assert result["icon"] == dashboard.OK
        assert "2026-07-06" in result["status"]
        assert result["detail"] == "run-abc-live-1"

    def test_db_latest_run_reports_failure_when_no_qualifying_run_for_expected_date(self, tmp_path):
        """If the real exporter contract finds no qualifying run for the
        expected prior session, the dashboard must fail closed too — not
        fall back to approximating with a different, looser query."""
        db_path = tmp_path / "data" / "runs.alpaca.db"
        db_path.parent.mkdir(parents=True)
        db_path.touch()

        with mock.patch.object(
            dashboard, "expected_previous_session", return_value="2026-07-06"
        ), mock.patch.object(dashboard, "_select_source_run", return_value=None):
            result = dashboard._db_latest_run(tmp_path)

        assert result["icon"] == dashboard.FAIL
        assert "2026-07-06" in result["status"]
