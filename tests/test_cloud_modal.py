"""Tests for cloud Modal executor — unit tests (no real Modal calls)."""
from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from renquant_orchestrator.cloud.bundle import (
    STRIP_DIRS,
    STRIP_EXTS,
    bundle_subrepos,
    compute_bundle_fingerprint,
)
from renquant_orchestrator.cloud.executor import DataManifest, PreflightReport
from renquant_orchestrator.cloud.modal_executor import (
    ModalExecutor,
    _estimate_cost_usd,
    _request_to_dict,
)
from renquant_orchestrator.cloud.sync_data import build_local_manifest


class TestBundle:
    def test_bundle_creates_manifest(self, tmp_path: Path):
        subrepo_root = tmp_path / "subrepos"
        common_src = subrepo_root / "renquant-common" / "src" / "common"
        common_src.mkdir(parents=True)
        (common_src / "utils.py").write_text("# utils")
        (common_src / "__init__.py").write_text("")

        strategy_dir = tmp_path / "strategy"
        kernel = strategy_dir / "kernel"
        kernel.mkdir(parents=True)
        (kernel / "core.py").write_text("# kernel")

        sim = strategy_dir / "sim"
        sim.mkdir(parents=True)
        (sim / "runner.py").write_text("# runner")

        output = tmp_path / "bundle"
        manifest = bundle_subrepos(subrepo_root, strategy_dir, output)

        assert "subrepos/renquant-common/src/common/utils.py" in manifest
        assert "subrepos/renquant-common/src/common/__init__.py" in manifest
        assert "kernel/core.py" in manifest
        assert "sim/runner.py" in manifest

        assert (output / "subrepos" / "renquant-common" / "src" / "common" / "utils.py").exists()
        assert (output / "kernel" / "core.py").exists()
        assert (output / "sim" / "runner.py").exists()
        assert (output / "bundle_manifest.json").exists()

    def test_bundle_strips_pycache_and_tests(self, tmp_path: Path):
        subrepo_root = tmp_path / "subrepos"
        src = subrepo_root / "renquant-common" / "src"
        (src / "common").mkdir(parents=True)
        (src / "common" / "good.py").write_text("# keep")
        (src / "common" / "__pycache__").mkdir()
        (src / "common" / "__pycache__" / "good.cpython-310.pyc").write_bytes(b"\x00")
        (src / "tests").mkdir()
        (src / "tests" / "test_x.py").write_text("# skip")

        strategy_dir = tmp_path / "strategy"
        strategy_dir.mkdir()

        output = tmp_path / "bundle"
        manifest = bundle_subrepos(subrepo_root, strategy_dir, output)

        assert "subrepos/renquant-common/src/common/good.py" in manifest
        assert not any("__pycache__" in k for k in manifest)
        assert not any("tests" in k for k in manifest)

    def test_fingerprint_deterministic(self):
        m1 = {"a.py": "abc123", "b.py": "def456"}
        m2 = {"b.py": "def456", "a.py": "abc123"}
        assert compute_bundle_fingerprint(m1) == compute_bundle_fingerprint(m2)

    def test_fingerprint_changes_on_content(self):
        m1 = {"a.py": "abc123"}
        m2 = {"a.py": "xyz789"}
        assert compute_bundle_fingerprint(m1) != compute_bundle_fingerprint(m2)


class TestSyncDataLocalManifest:
    def test_build_manifest_file(self, tmp_path: Path):
        f = tmp_path / "data.parquet"
        f.write_bytes(b"parquet data")
        manifest = build_local_manifest({"ohlcv": f})
        assert "ohlcv/data.parquet" in manifest

    def test_build_manifest_dir(self, tmp_path: Path):
        d = tmp_path / "ohlcv"
        d.mkdir()
        (d / "AAPL.parquet").write_bytes(b"aapl")
        (d / "SPY.parquet").write_bytes(b"spy")
        manifest = build_local_manifest({"ohlcv": d})
        assert "ohlcv/AAPL.parquet" in manifest
        assert "ohlcv/SPY.parquet" in manifest

    def test_excludes_sensitive_files(self, tmp_path: Path):
        d = tmp_path / "data"
        d.mkdir()
        (d / "good.parquet").write_bytes(b"ok")
        (d / ".env").write_text("SECRET=x")
        (d / "rawlabel.parquet").write_bytes(b"nope")
        manifest = build_local_manifest({"data": d})
        assert "data/good.parquet" in manifest
        assert not any(".env" in k for k in manifest)
        assert not any("rawlabel" in k for k in manifest)


class TestModalExecutor:
    def test_estimate_cost(self):
        cost = _estimate_cost_usd(60.0)
        assert cost > 0
        assert cost < 1.0

    def test_preflight_no_bundle_dir(self, tmp_path: Path):
        executor = ModalExecutor(
            bundle_dir=str(tmp_path / "nonexistent"),
            volume_name="test-vol",
        )
        manifest = DataManifest(
            commit_id="test",
            timestamp="2026-07-07T00:00:00",
            files={"ohlcv/SPY.parquet": "abc"},
            total_bytes=1000,
        )
        report = executor.preflight(manifest)
        assert not report.passed
        assert report.checks["bundle_exists"] is False

    def test_preflight_passes_with_valid_state(self, tmp_path: Path):
        bundle = tmp_path / "bundle"
        bundle.mkdir()
        executor = ModalExecutor(
            bundle_dir=str(bundle),
            volume_name="test-vol",
        )
        manifest = DataManifest(
            commit_id="test",
            timestamp="2026-07-07T00:00:00",
            files={"ohlcv/SPY.parquet": "abc"},
            total_bytes=1000,
        )
        report = executor.preflight(manifest)
        assert report.checks["bundle_exists"] is True
        assert report.checks["volume_has_data"] is True
        assert report.checks["cost_reasonable"] is True

    def test_request_to_dict_round_trip(self):
        from renquant_orchestrator.cloud.executor import BacktestRequest

        req = BacktestRequest(
            variant_name="cap_0.15_drift_0.04_topup_0.80",
            role="candidate",
            config_json='{"watchlist": ["AAPL"]}',
            volume_commit_id="20260707_120000",
            seeds=[42, 123, 777],
            start="2024-01-01",
            end="2026-03-28",
            initial_cash=100_000.0,
            incumbent_turnover=3.5,
        )
        d = _request_to_dict(req)
        assert d["variant_name"] == "cap_0.15_drift_0.04_topup_0.80"
        assert d["seeds"] == [42, 123, 777]
        assert d["incumbent_turnover"] == 3.5
        assert json.loads(d["config_json"]) == {"watchlist": ["AAPL"]}

    def test_preflight_empty_manifest_fails(self, tmp_path: Path):
        bundle = tmp_path / "bundle"
        bundle.mkdir()
        executor = ModalExecutor(bundle_dir=str(bundle))
        manifest = DataManifest(
            commit_id=None, timestamp="", files={}, total_bytes=0,
        )
        report = executor.preflight(manifest)
        assert not report.passed
        assert report.checks["volume_has_data"] is False
