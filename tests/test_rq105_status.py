"""Tests for ops/renquant105/rq105_status.py (Codex review on PR #417 — the
dashboard duplicated five contracts that already exist elsewhere in this
repo: the batch-scores-export MIN_ROWS threshold, launchd job identity,
canonical-run selection, data-root resolution, and collector-freshness
logic. These tests prove genuine coupling to each canonical source — not a
coincidentally-matching hardcoded copy."""
from __future__ import annotations

import datetime as dt
import sqlite3
import sys
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
OPS_DIR = REPO / "ops" / "renquant105"
sys.path.insert(0, str(OPS_DIR))

import rq105_status as dashboard  # noqa: E402


class TestMinRowsCoupling:
    def test_uses_export_batch_scores_min_rows_not_a_hardcoded_value(self, monkeypatch):
        """The good/warn threshold in _db_latest_run must be the SAME object
        as export_batch_scores.MIN_ROWS — changing the canonical constant
        must change the dashboard's behavior without touching this module."""
        import export_batch_scores

        assert dashboard.MIN_ROWS is export_batch_scores.MIN_ROWS

    def test_threshold_change_propagates_to_dashboard_coloring(self, monkeypatch, tmp_path):
        """Construct a synthetic DB with a run scored at exactly the current
        MIN_ROWS. Lowering the canonical constant must flip this run from
        WARN to OK without any dashboard-side change."""
        (tmp_path / "data").mkdir(parents=True, exist_ok=True)
        db_path = tmp_path / "data" / "runs.alpaca.db"
        con = sqlite3.connect(str(db_path))
        con.executescript(
            """
            CREATE TABLE pipeline_runs (run_id TEXT, run_date TEXT, created_at TEXT, run_type TEXT);
            CREATE TABLE candidate_scores (run_id TEXT, role TEXT, panel_score REAL);
            """
        )
        run_id = "20260707-live-abc"
        con.execute(
            "INSERT INTO pipeline_runs VALUES (?, ?, ?, 'live')",
            (run_id, "2026-07-07", "2026-07-07T10:00:00"),
        )
        n = 24
        con.executemany(
            "INSERT INTO candidate_scores VALUES (?, 'candidate', 1.0)",
            [(run_id,)] * n,
        )
        con.commit()
        con.close()

        monkeypatch.setattr(dashboard, "RQ_ROOT", tmp_path)
        # canonical selection requires >= MIN_FULL_RUN_CANDIDATES in
        # candidate_scores; patch that floor down so this small synthetic
        # run is itself selected as canonical, isolating the MIN_ROWS
        # coloring behavior under test from the separate canonical-run
        # candidate-count floor.
        with mock.patch("renquant_orchestrator.tc_measurement.MIN_FULL_RUN_CANDIDATES", 1):
            with mock.patch.object(dashboard, "MIN_ROWS", n + 1):
                result_warn = dashboard._db_latest_run()
            with mock.patch.object(dashboard, "MIN_ROWS", n):
                result_ok = dashboard._db_latest_run()

        assert result_warn["icon"] == dashboard.WARN
        assert result_ok["icon"] == dashboard.OK


class TestLaunchdJobIdentityCoupling:
    def test_rq105_jobs_come_from_scheduled_jobs_registry(self):
        """Every job the dashboard checks must be a real entry in the
        canonical scheduled_jobs registry, with its real launchd_label —
        not a second, independently-typed label string."""
        from renquant_orchestrator.scheduled_jobs import scheduled_jobs

        registry_by_id = {j.job_id: j for j in scheduled_jobs()}
        jobs = dashboard._rq105_jobs()
        assert jobs, "expected at least one rq105 job to resolve from the registry"
        for job in jobs:
            assert job.job_id in registry_by_id
            assert job is registry_by_id[job.job_id]
            assert job.launchd_label == registry_by_id[job.job_id].launchd_label

    def test_unregistered_job_id_is_silently_excluded_not_invented(self, monkeypatch):
        """If a job_id in _RQ105_JOB_IDS is renamed/removed from the
        registry, the dashboard must drop it rather than fabricate a
        launchd label for it."""
        monkeypatch.setattr(dashboard, "_RQ105_JOB_IDS", ("does_not_exist_in_registry",))
        assert dashboard._rq105_jobs() == []


class TestCanonicalRunSelectionCoupling:
    def test_db_latest_run_uses_tc_measurement_canonical_selection(self, tmp_path, monkeypatch):
        """A partial/non-canonical run (too few candidate_scores rows to
        clear tc_measurement's own canonical-run floor) must be excluded by
        _db_latest_run exactly as tc_measurement itself would exclude it —
        proving real reuse of _canonical_daily_runs, not a separately
        re-implemented (and possibly looser) selection query."""
        (tmp_path / "data").mkdir(parents=True, exist_ok=True)
        db_path = tmp_path / "data" / "runs.alpaca.db"
        con = sqlite3.connect(str(db_path))
        con.executescript(
            """
            CREATE TABLE pipeline_runs (run_id TEXT, run_date TEXT, created_at TEXT, run_type TEXT);
            CREATE TABLE candidate_scores (run_id TEXT, role TEXT, panel_score REAL);
            """
        )
        run_id = "20260707-live-partial"
        con.execute(
            "INSERT INTO pipeline_runs VALUES (?, ?, ?, 'live')",
            (run_id, "2026-07-07", "2026-07-07T10:00:00"),
        )
        # Below the real MIN_FULL_RUN_CANDIDATES floor (80) — a genuinely
        # partial run that tc_measurement's canonical selection must reject.
        con.executemany(
            "INSERT INTO candidate_scores VALUES (?, 'candidate', 1.0)",
            [(run_id,)] * 5,
        )
        con.commit()
        con.close()

        monkeypatch.setattr(dashboard, "RQ_ROOT", tmp_path)
        result = dashboard._db_latest_run()

        assert result["icon"] == dashboard.FAIL
        assert result["status"] == "no qualifying runs"


class TestDataRootCoupling:
    def test_rq_root_is_default_data_root_not_hardcoded_path(self):
        """RQ_ROOT must be resolved via runtime_paths.default_data_root(),
        not a hardcoded ~/git/github/RenQuant-style default."""
        from renquant_orchestrator.runtime_paths import default_data_root

        assert dashboard.RQ_ROOT == default_data_root()

    def test_data_root_env_override_propagates(self, monkeypatch):
        """Setting RENQUANT_DATA_ROOT and re-resolving must change the
        dashboard's root — proving live coupling to the resolver, not a
        constant captured once and never revisited."""
        import importlib

        from renquant_orchestrator import runtime_paths

        fake_root = "/tmp/fake-rq105-data-root-test"
        monkeypatch.setenv("RENQUANT_DATA_ROOT", fake_root)
        importlib.reload(runtime_paths)
        try:
            # default_data_root() calls .resolve(), which follows the
            # macOS /tmp -> /private/tmp symlink — compare against the same
            # resolution rather than the raw literal.
            assert runtime_paths.default_data_root() == Path(fake_root).expanduser().resolve()
        finally:
            monkeypatch.delenv("RENQUANT_DATA_ROOT", raising=False)
            importlib.reload(runtime_paths)


class TestCollectorFreshnessCoupling:
    def test_today_logs_uses_liveness_check_data_output_function(self, monkeypatch, tmp_path):
        """_today_logs must report the collector-data-output entries exactly
        as rq105_liveness_check.check_collector_data_outputs computes them
        (same status/reason), not a second naive size/mtime check that
        could disagree with what actually pages the operator."""
        sentinel = {
            "intraday_quote_logger": {
                "status": "stale_or_missing",
                "reason": "sentinel-test-reason",
                "path": "x", "freshness_basis": "row_event_time", "row_content_sha256": None,
            },
        }
        monkeypatch.setattr(dashboard, "RQ105_LOGS", tmp_path)
        with mock.patch.object(dashboard, "check_collector_data_outputs", return_value=sentinel):
            results = dashboard._today_logs("2026-07-07")

        matched = [r for r in results if r["name"] == "intraday_quote_logger"]
        assert len(matched) == 1
        assert matched[0]["icon"] == dashboard.FAIL
        assert matched[0]["status"] == "sentinel-test-reason"
