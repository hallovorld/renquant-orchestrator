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

    def test_bundles_adapters_and_training_panel_dirs(self, tmp_path: Path):
        """sim/runner.py::run_backtest unconditionally does
        `from adapters.sim import SimAdapter` on its default (non-snapshot)
        path — these dirs are not optional to bundle."""
        strategy_dir = tmp_path / "strategy"
        for subdir in ("kernel", "sim", "adapters", "training_panel"):
            d = strategy_dir / subdir
            d.mkdir(parents=True)
            (d / "__init__.py").write_text("")

        subrepo_root = tmp_path / "subrepos"
        output = tmp_path / "bundle"
        manifest = bundle_subrepos(subrepo_root, strategy_dir, output)

        assert "adapters/__init__.py" in manifest
        assert "training_panel/__init__.py" in manifest
        assert (output / "adapters" / "__init__.py").exists()
        assert (output / "training_panel" / "__init__.py").exists()

    def test_worker_sys_path_setup_resolves_top_level_bundled_packages(self, tmp_path: Path):
        """Regression test: the worker in modal_app.py inserts only
        app_root (plus subrepo src dirs) onto sys.path, NOT
        app_root/adapters or app_root/training_panel individually —
        `from adapters.sim import X` requires adapters' PARENT directory
        on sys.path to resolve `adapters` as a top-level package.
        Inserting app_root/adapters itself does NOT make `adapters`
        importable; it was a real bug caught by exercising a built bundle
        with the exact sys.path strategy the worker uses, rather than
        only unit-testing bundle_subrepos() and the worker in isolation."""
        strategy_dir = tmp_path / "strategy"
        for subdir, module_name, class_name in (
            ("adapters", "sim", "SimAdapter"),
            ("training_panel", "panel", "TrainingPanel"),
        ):
            pkg = strategy_dir / subdir
            pkg.mkdir(parents=True)
            (pkg / "__init__.py").write_text("")
            (pkg / f"{module_name}.py").write_text(
                f"class {class_name}:\n    pass\n"
            )
        (strategy_dir / "kernel").mkdir()
        (strategy_dir / "sim").mkdir()
        (strategy_dir / "sim" / "__init__.py").write_text("")
        (strategy_dir / "sim" / "runner.py").write_text(
            "def run_backtest():\n"
            "    from adapters.sim import SimAdapter\n"
            "    return SimAdapter\n"
        )

        subrepo_root = tmp_path / "subrepos"
        output = tmp_path / "bundle"
        bundle_subrepos(subrepo_root, strategy_dir, output)

        import subprocess
        import sys as _sys

        # Exactly what the worker does: app_root itself on sys.path, no
        # per-subdirectory insertion for adapters/training_panel.
        code = (
            f"import sys; sys.path.insert(0, {str(output)!r}); "
            "from adapters.sim import SimAdapter; "
            "from sim.runner import run_backtest; "
            "assert run_backtest() is SimAdapter; "
            "print('OK')"
        )
        result = subprocess.run(
            [_sys.executable, "-c", code], capture_output=True, text=True
        )
        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout


class TestSyncDataLocalManifest:
    def test_build_manifest_file(self, tmp_path: Path):
        f = tmp_path / "data.parquet"
        f.write_bytes(b"parquet data")
        manifest, _sources = build_local_manifest({"ohlcv": f})
        assert "ohlcv/data.parquet" in manifest

    def test_build_manifest_dir(self, tmp_path: Path):
        d = tmp_path / "ohlcv"
        d.mkdir()
        (d / "AAPL.parquet").write_bytes(b"aapl")
        (d / "SPY.parquet").write_bytes(b"spy")
        manifest, _sources = build_local_manifest({"ohlcv": d})
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
        manifest, _sources = build_local_manifest({"data": d})
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
        report = executor.preflight(manifest, n_variants=1, n_seeds_per_variant=1)
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
        report = executor.preflight(manifest, n_variants=1, n_seeds_per_variant=1)
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
        report = executor.preflight(manifest, n_variants=1, n_seeds_per_variant=1)
        assert not report.passed
        assert report.checks["volume_has_data"] is False

    def test_preflight_cost_scales_with_actual_pod_count(self, tmp_path: Path):
        """Under per-seed fan-out, pods = n_variants * n_seeds_per_variant.
        The preflight cost projection must scale with that real product, not
        a stale one-pod-per-variant assumption (previously hardcoded as
        `_estimate_cost_usd(30.0) * 75`, which never reflected the actual
        75 variants x 3 seeds = 225-pod fan-out plan)."""
        bundle = tmp_path / "bundle"
        bundle.mkdir()
        executor = ModalExecutor(bundle_dir=str(bundle))
        manifest = DataManifest(
            commit_id="test", timestamp="2026-07-08T00:00:00",
            files={"ohlcv/SPY.parquet": "abc"}, total_bytes=1000,
        )

        # Force a scale where the $20 gate fires so the projected dollar
        # figure is actually reported (and thus comparable) in `details`.
        big = executor.preflight(manifest, n_variants=1000, n_seeds_per_variant=1)
        bigger = executor.preflight(manifest, n_variants=1000, n_seeds_per_variant=3)
        assert not big.checks["cost_reasonable"]
        assert not bigger.checks["cost_reasonable"]
        big_cost = float(big.details["cost_reasonable"].split("$")[1].split(" ")[0])
        bigger_cost = float(
            bigger.details["cost_reasonable"].split("$")[1].split(" ")[0]
        )
        assert bigger_cost == pytest.approx(big_cost * 3, rel=1e-6)


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


def _install_fake_modal_sdk_with_map(monkeypatch, per_seed_results_json):
    """Like _install_fake_modal_sdk, but the decorated worker function's
    `.map()` yields the given canned per-pod JSON result strings and
    `app.run()` is a working (no-op) context manager — enough to exercise
    ModalExecutor.execute_batch's real aggregation logic end to end without
    a real Modal dispatch."""
    import sys as _sys
    import types
    from contextlib import contextmanager

    fake_modal = types.ModuleType("modal")

    class _FakeMappedFn:
        def __init__(self, results):
            self._results = results

        def map(self, requests, kwargs=None, **extra):
            return iter(self._results)

    class _FakeApp:
        def __init__(self, name):
            self.name = name

        def function(self, **kwargs):
            def deco(fn):
                wrapped = _FakeMappedFn(per_seed_results_json)
                wrapped._modal_function_kwargs = kwargs
                wrapped.get_build_def = lambda: ""
                return wrapped

            return deco

        @contextmanager
        def run(self):
            yield self

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


class TestPerSeedCostAggregation:
    """Prove variant-level cost/elapsed reflects the SUM of every dispatched
    pod's compute time under per-seed fan-out, not just the slowest pod's
    wall-clock duration (which would undercount real spend by roughly
    seeds_per_variant x — the bug Codex's r1 review on #435 blocked on)."""

    def _fake_pod_result(self, variant_name, seed, elapsed_seconds, worker_id):
        return json.dumps({
            "variant_name": variant_name,
            "role": "candidate",
            "config_fingerprint": "fp",
            "worker_id": worker_id,
            "volume_commit_id": "vc1",
            "code_image_id": "img1",
            "started_at": "2026-07-08T00:00:00+00:00",
            "finished_at": "2026-07-08T00:10:00+00:00",
            "elapsed_seconds": elapsed_seconds,
            "peak_memory_mb": 1000.0 + seed,
            "seeds": [seed],
            "per_seed": [{"seed": seed, "apy": 0.1, "sharpe": 1.0}],
            "equity_curves": None,
            "trade_logs": None,
            "result_checksum": f"chk{seed}",
        })

    def test_variant_cost_is_sum_not_max_of_per_seed_pods(self, monkeypatch, tmp_path):
        import sys as _sys
        from renquant_orchestrator.cloud.executor import BacktestRequest

        module_name = "renquant_orchestrator.cloud.modal_app"
        monkeypatch.delitem(_sys.modules, module_name, raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_TIMEOUT_SECONDS", raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_RETRIES", raising=False)

        # 3 pods for ONE variant with deliberately DIFFERENT elapsed times —
        # max() would report only the slowest pod's time (600s); sum() must
        # report the true total compute-seconds actually billed (1100s).
        per_seed = [
            self._fake_pod_result("cap12_driftinf_topup05", 42, 300.0, "task-a"),
            self._fake_pod_result("cap12_driftinf_topup05", 43, 600.0, "task-b"),
            self._fake_pod_result("cap12_driftinf_topup05", 44, 200.0, "task-c"),
        ]
        _install_fake_modal_sdk_with_map(monkeypatch, per_seed)

        executor = ModalExecutor(bundle_dir=str(tmp_path))
        request = BacktestRequest(
            variant_name="cap12_driftinf_topup05",
            role="candidate",
            config_json="{}",
            volume_commit_id="vc1",
            seeds=[42, 43, 44],
            start="2024-01-01",
            end="2026-03-28",
            initial_cash=100_000.0,
            incumbent_turnover=None,
        )

        results = []
        summary = executor.execute_batch(
            [request],
            on_result=results.append,
            on_error=lambda n, e: (_ for _ in ()).throw(e),
        )

        assert len(results) == 1
        result = results[0]

        # The bug: max(300, 600, 200) == 600 (undercounts by ~1.83x here,
        # and by ~seeds_per_variant x in the general case where all pods
        # take similar time). The fix: sum == 1100.
        assert result.elapsed_seconds == pytest.approx(1100.0)
        assert result.elapsed_seconds != pytest.approx(600.0)

        assert summary.cost_usd == pytest.approx(_estimate_cost_usd(1100.0))
        assert summary.cost_usd != pytest.approx(_estimate_cost_usd(600.0))

        # peak_memory_mb legitimately IS a max (independent pods, memory
        # doesn't add across machines) — must NOT have been changed to a sum.
        assert result.peak_memory_mb == pytest.approx(max(1042.0, 1043.0, 1044.0))

        # Per-pod provenance must survive per-seed, not just collapse to
        # whichever pod happened to report first.
        assert len(result.per_seed) == 3
        assert {s["seed"] for s in result.per_seed} == {42, 43, 44}


class TestPartialFailureHandling:
    """Prove `return_exceptions=True` actually protects the batch: when
    Modal's real `.map(..., return_exceptions=True)` hits a dead/failed pod,
    it yields the raised exception object in place of a JSON string rather
    than raising it into the iterator — codex's #438 review blocked on this
    path being unverified. `execute_batch` must not crash, must report the
    failure via `on_error`/`n_failed`, and must keep draining the remaining
    (successful) pods rather than abandoning the batch."""

    def _fake_pod_result(self, variant_name, seed, worker_id):
        return json.dumps({
            "variant_name": variant_name,
            "role": "candidate",
            "config_fingerprint": "fp",
            "worker_id": worker_id,
            "volume_commit_id": "vc1",
            "code_image_id": "img1",
            "started_at": "2026-07-08T00:00:00+00:00",
            "finished_at": "2026-07-08T00:10:00+00:00",
            "elapsed_seconds": 300.0,
            "peak_memory_mb": 1000.0 + seed,
            "seeds": [seed],
            "per_seed": [{"seed": seed, "apy": 0.1, "sharpe": 1.0}],
            "equity_curves": None,
            "trade_logs": None,
            "result_checksum": f"chk{seed}",
        })

    def test_exception_item_is_reported_not_raised_and_batch_keeps_draining(
        self, monkeypatch, tmp_path
    ):
        import sys as _sys
        from renquant_orchestrator.cloud.executor import BacktestRequest

        module_name = "renquant_orchestrator.cloud.modal_app"
        monkeypatch.delitem(_sys.modules, module_name, raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_TIMEOUT_SECONDS", raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_RETRIES", raising=False)

        pod_failure = RuntimeError("pod task-b died: OOMKilled")
        # Modal's own map(return_exceptions=True) yields the raw Exception
        # object interleaved with normal results — not a JSON string, not a
        # wrapper. The fake here mirrors that exactly.
        per_seed = [
            self._fake_pod_result("cap12_driftinf_topup05", 42, "task-a"),
            pod_failure,
            self._fake_pod_result("cap12_driftinf_topup05", 44, "task-c"),
        ]
        _install_fake_modal_sdk_with_map(monkeypatch, per_seed)

        executor = ModalExecutor(bundle_dir=str(tmp_path))
        request = BacktestRequest(
            variant_name="cap12_driftinf_topup05",
            role="candidate",
            config_json="{}",
            volume_commit_id="vc1",
            seeds=[42, 43, 44],
            start="2024-01-01",
            end="2026-03-28",
            initial_cash=100_000.0,
            incumbent_turnover=None,
        )

        results = []
        errors = []
        # No lambda-that-raises here (unlike the sibling test above) —
        # proving execute_batch itself must not propagate the pod's
        # exception; on_error is just a recording callback.
        summary = executor.execute_batch(
            [request],
            on_result=results.append,
            on_error=lambda name, exc: errors.append((name, exc)),
        )

        # The failed pod must be reported, not swallowed silently and not
        # allowed to crash execute_batch.
        assert len(errors) == 1
        assert errors[0][1] is pod_failure
        assert summary.n_failed == 1

        # The batch must keep draining: seeds 42 and 44 (the two pods that
        # did NOT fail) still reach the final aggregated result. A batch
        # that aborted on the first exception would lose seed 44 entirely.
        assert len(results) == 1
        result = results[0]
        assert {s["seed"] for s in result.per_seed} == {42, 44}
        assert len(result.per_seed) == 2
