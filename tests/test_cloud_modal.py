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
from renquant_orchestrator.cloud.sync_data import (
    build_local_manifest,
    compute_manifest_commit_id,
)


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

    def test_subrepo_names_stays_synced_with_sweep_scripts_own_dependency_list(self):
        """SUBREPO_NAMES is documented as hardcoded to exactly what
        run_concentration_cap_sweep.py::SUBREPO_IMPORT_ORDER needs (see
        bundle.py's module docstring) — not a generic arbitrary repo list.
        This proves that coupling instead of leaving it as a comment nobody
        re-checks when either list changes."""
        import sys as _sys
        from pathlib import Path as _Path

        from renquant_orchestrator.cloud.bundle import SUBREPO_NAMES

        scripts_dir = str(_Path(__file__).parent.parent / "scripts")
        _sys.path.insert(0, scripts_dir)
        try:
            from run_concentration_cap_sweep import SUBREPO_IMPORT_ORDER
        finally:
            _sys.path.remove(scripts_dir)

        assert set(SUBREPO_NAMES) == set(SUBREPO_IMPORT_ORDER)


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

    def test_commit_id_is_content_coupled_not_a_timestamp(self):
        """commit_id must change iff the synced manifest's content changes —
        a wall-clock timestamp (the pre-fix behavior) would pass this only
        by accident, since two syncs of identical content a second apart
        would wrongly report different commit_ids, and unchanged reruns
        would wrongly look like a genuine content change."""
        m1 = {"ohlcv/AAPL.parquet": "sha_a", "artifacts/wf.json": "sha_b"}
        m2 = {"ohlcv/AAPL.parquet": "sha_a", "artifacts/wf.json": "sha_b"}
        m3 = {"ohlcv/AAPL.parquet": "sha_a_changed", "artifacts/wf.json": "sha_b"}

        assert compute_manifest_commit_id(m1) == compute_manifest_commit_id(m2)
        assert compute_manifest_commit_id(m1) != compute_manifest_commit_id(m3)

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


def _install_fake_modal_sdk(monkeypatch):
    """Stub the `modal` package so modal_app.py can be imported without the
    real SDK (not a project dependency — only needed at actual cloud
    runtime). Captures the exact kwargs @app.function is decorated with so
    tests can assert on the real decoration-time values, not a guess."""
    import sys as _sys
    import types

    captured: dict = {}

    fake_modal = types.ModuleType("modal")

    class _FakeApp:
        def __init__(self, name):
            self.name = name

        def function(self, **kwargs):
            captured.update(kwargs)

            def deco(fn):
                fn._modal_function_kwargs = kwargs
                fn.get_build_def = lambda: ""
                return fn

            return deco

    class _FakeVolume:
        @staticmethod
        def from_name(name, create_if_missing=False):
            return object()

    class _FakeImage:
        def pip_install(self, *a, **k):
            return self

        def run_commands(self, *a, **k):
            return self

    class _FakeImageNS:
        @staticmethod
        def debian_slim(python_version=None):
            return _FakeImage()

    fake_modal.App = _FakeApp
    fake_modal.Volume = _FakeVolume
    fake_modal.Image = _FakeImageNS

    monkeypatch.setitem(_sys.modules, "modal", fake_modal)
    return captured


class TestModalTimeoutRetriesConfigurability:
    """Prove timeout/retries genuinely reach the @app.function decorator.

    Modal's @app.function bakes timeout/retries in at decoration time (no
    per-call override exists in the installed SDK — verified against the
    real modal package: no with_options()/options() on modal.Function, and
    app.function()'s signature takes timeout/retries as plain kwargs).
    ModalExecutor.execute_batch sets RENQUANT_MODAL_TIMEOUT_SECONDS /
    RENQUANT_MODAL_RETRIES env vars before importing modal_app so the
    module-level decorator picks up the caller's requested values on that
    process's first (only) import. `modal` itself is not a project
    dependency (only needed at real cloud runtime), so these tests stub it.
    """

    def _fresh_import(self, monkeypatch, captured):
        import sys as _sys

        module_name = "renquant_orchestrator.cloud.modal_app"
        monkeypatch.delitem(_sys.modules, module_name, raising=False)
        import importlib
        return importlib.import_module(module_name)

    def test_env_var_reaches_decorator_kwargs(self, monkeypatch):
        captured = _install_fake_modal_sdk(monkeypatch)
        monkeypatch.setenv("RENQUANT_MODAL_TIMEOUT_SECONDS", "111")
        monkeypatch.setenv("RENQUANT_MODAL_RETRIES", "7")

        self._fresh_import(monkeypatch, captured)

        assert captured["timeout"] == 111
        assert captured["retries"] == 7

    def test_defaults_used_when_env_unset(self, monkeypatch):
        captured = _install_fake_modal_sdk(monkeypatch)
        monkeypatch.delenv("RENQUANT_MODAL_TIMEOUT_SECONDS", raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_RETRIES", raising=False)

        self._fresh_import(monkeypatch, captured)

        assert captured["timeout"] == 3600
        assert captured["retries"] == 1

    def test_execute_batch_sets_env_vars_before_first_import(self, monkeypatch, tmp_path: Path):
        """Proves execute_batch's own env-var-setting side effect fires
        before modal_app import — the real (unpatched) code path under
        test, only the modal SDK itself is stubbed."""
        import sys as _sys

        _install_fake_modal_sdk(monkeypatch)
        module_name = "renquant_orchestrator.cloud.modal_app"
        monkeypatch.delitem(_sys.modules, module_name, raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_TIMEOUT_SECONDS", raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_RETRIES", raising=False)

        executor = ModalExecutor(bundle_dir=str(tmp_path), timeout=222, retries=9)

        try:
            executor.execute_batch([], on_result=lambda r: None, on_error=lambda n, e: None)
        except Exception:
            pass  # fake app.run() / empty request list — irrelevant here

        mod = _sys.modules[module_name]
        assert mod.WORKER_TIMEOUT_SECONDS == 222
        assert mod.WORKER_RETRIES == 9
        assert mod.run_variant_remote._modal_function_kwargs["timeout"] == 222
        assert mod.run_variant_remote._modal_function_kwargs["retries"] == 9

    def test_execute_batch_raises_on_conflicting_reimport(self, monkeypatch, tmp_path: Path):
        """A second ModalExecutor with different timeout/retries in the same
        process cannot silently reuse the first import's baked-in decorator
        values — must raise, not silently ignore, matching the fix's honesty
        requirement (this is exactly the bug class being fixed: a parameter
        that looks accepted but is silently dropped)."""
        import sys as _sys

        _install_fake_modal_sdk(monkeypatch)
        module_name = "renquant_orchestrator.cloud.modal_app"
        monkeypatch.delitem(_sys.modules, module_name, raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_TIMEOUT_SECONDS", raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_RETRIES", raising=False)

        first = ModalExecutor(bundle_dir=str(tmp_path), timeout=100, retries=2)
        try:
            first.execute_batch([], on_result=lambda r: None, on_error=lambda n, e: None)
        except Exception:
            pass

        second = ModalExecutor(bundle_dir=str(tmp_path), timeout=200, retries=3)
        with pytest.raises(RuntimeError, match="cannot be honored without a fresh process"):
            second.execute_batch([], on_result=lambda r: None, on_error=lambda n, e: None)
