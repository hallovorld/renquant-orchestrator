"""Tests for cloud executor protocol and local backend."""
from __future__ import annotations

import json

import pytest

from renquant_orchestrator.cloud.executor import (
    BacktestRequest,
    BacktestResult,
    compute_result_checksum,
)
from renquant_orchestrator.cloud.local_executor import LocalExecutor


class TestComputeResultChecksum:
    def test_deterministic(self):
        d = {"variant_name": "v1", "sharpe": 1.5, "seeds": [42]}
        assert compute_result_checksum(d) == compute_result_checksum(d)

    def test_excludes_checksum_field(self):
        d1 = {"variant_name": "v1", "sharpe": 1.5}
        d2 = {"variant_name": "v1", "sharpe": 1.5, "result_checksum": "junk"}
        assert compute_result_checksum(d1) == compute_result_checksum(d2)

    def test_different_data_different_checksum(self):
        d1 = {"variant_name": "v1", "sharpe": 1.5}
        d2 = {"variant_name": "v1", "sharpe": 1.6}
        assert compute_result_checksum(d1) != compute_result_checksum(d2)


class TestLocalExecutor:
    def test_execute_batch_streams_results(self):
        def mock_execute(req):
            return {
                "variant_name": req.variant_name,
                "role": req.role,
                "config_fingerprint": "fp",
                "started_at": "t0",
                "finished_at": "t1",
                "elapsed_seconds": 0.01,
                "peak_memory_mb": 10.0,
                "seeds": req.seeds,
                "per_seed": [{"seed": s, "sharpe": 1.0} for s in req.seeds],
            }

        executor = LocalExecutor(max_workers=2, use_threads=True)
        requests = [
            BacktestRequest(
                variant_name=f"v{i}", role="candidate",
                config_json="{}", volume_commit_id=None,
                seeds=[42], start="2024-01-01", end="2026-01-01",
                initial_cash=100_000, incumbent_turnover=None,
            )
            for i in range(3)
        ]

        results = []
        errors = []
        summary = executor.execute_batch(
            requests,
            on_result=lambda r: results.append(r),
            on_error=lambda n, e: errors.append((n, e)),
            execute_fn=mock_execute,
        )
        assert len(results) == 3
        assert len(errors) == 0
        assert summary.n_completed == 3
        assert summary.n_failed == 0
        assert {r.variant_name for r in results} == {"v0", "v1", "v2"}

    def test_execute_batch_handles_errors(self):
        call_count = {"n": 0}

        def failing_execute(req):
            call_count["n"] += 1
            if req.variant_name == "v_bad":
                raise RuntimeError("OOM")
            return {
                "variant_name": req.variant_name,
                "role": "candidate",
                "config_fingerprint": "fp",
                "started_at": "t0", "finished_at": "t1",
                "elapsed_seconds": 0.01, "peak_memory_mb": 10.0,
                "seeds": [42], "per_seed": [{"seed": 42, "sharpe": 1.0}],
            }

        executor = LocalExecutor(max_workers=1, use_threads=True)
        requests = [
            BacktestRequest(
                variant_name=name, role="candidate",
                config_json="{}", volume_commit_id=None,
                seeds=[42], start="2024-01-01", end="2026-01-01",
                initial_cash=100_000, incumbent_turnover=None,
            )
            for name in ["v_ok", "v_bad"]
        ]

        results = []
        errors = []
        summary = executor.execute_batch(
            requests,
            on_result=lambda r: results.append(r),
            on_error=lambda n, e: errors.append((n, str(e))),
            execute_fn=failing_execute,
        )
        assert summary.n_completed == 1
        assert summary.n_failed == 1
        assert errors[0][0] == "v_bad"
        assert "OOM" in errors[0][1]

    def test_preflight_passes_for_local(self):
        executor = LocalExecutor()
        from renquant_orchestrator.cloud.executor import DataManifest
        report = executor.preflight(DataManifest(
            commit_id=None, timestamp="now", files={}, total_bytes=0,
        ))
        assert report.passed

    def test_sync_data_computes_checksums(self, tmp_path):
        f = tmp_path / "test.txt"
        f.write_text("hello")
        executor = LocalExecutor()
        manifest = executor.sync_data({"test_file": str(f)})
        assert manifest.commit_id is None
        assert "test_file" in manifest.files
        assert manifest.total_bytes == 5
