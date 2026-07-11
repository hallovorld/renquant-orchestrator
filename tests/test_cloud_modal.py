"""Tests for cloud Modal executor — unit tests (no real Modal calls)."""
from __future__ import annotations

import hashlib
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
from renquant_orchestrator.cloud.executor import BacktestRequest, DataManifest, PreflightReport
from renquant_orchestrator.cloud.modal_executor import (
    HARD_COST_SAFETY_GATE_USD,
    IMAGE_SPEC,
    ModalExecutor,
    ModalPreflightReport,
    WorkloadManifest,
    WorkloadManifestError,
    WorkloadMismatchError,
    _estimate_cost_usd,
    _request_to_dict,
    image_spec_fingerprint,
    write_workload_manifest,
)
from renquant_orchestrator.cloud.sync_data import (
    build_local_manifest,
    compute_manifest_commit_id,
)

# ── Shared guardrail fixtures: a mutually-consistent (bundle, workload
# manifest, data manifest) trio so a preflight can genuinely PASS ──

_DEFAULT_FILES = {"ohlcv/SPY.parquet": "abc"}
_DEFAULT_VARIANT = {
    "name": "cap12_driftinf_topup05",
    "role": "candidate",
    "config_sha256": hashlib.sha256(b"{}").hexdigest(),
    "seeds": [42, 43, 44],
}


def _data_sha(files: dict) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def _write_bundle_dir(tmp_path: Path) -> tuple[Path, str]:
    bundle = tmp_path / "bundle"
    bundle.mkdir(exist_ok=True)
    bundle_manifest = {"kernel/core.py": "abc123"}
    (bundle / "bundle_manifest.json").write_text(json.dumps(bundle_manifest))
    return bundle, compute_bundle_fingerprint(bundle_manifest)


def _manifest_payload(*, bundle_fp: str, variants=None, files=None, **overrides):
    payload = {
        "schema_version": 1,
        "region": "us-east",
        "image_spec_sha256": image_spec_fingerprint(),
        "volume_name": "test-vol",
        "volume_commit_id": "vc1",
        "data_manifest_sha256": _data_sha(_DEFAULT_FILES if files is None else files),
        "bundle_fingerprint": bundle_fp,
        "artifact_manifest_sha256": "a" * 64,
        "data_interval": {"start": "2024-01-01", "end": "2026-03-28"},
        "variants": [dict(_DEFAULT_VARIANT)] if variants is None else variants,
    }
    payload.update(overrides)
    return payload


def _load_manifest(tmp_path: Path, payload: dict) -> WorkloadManifest:
    p = tmp_path / "workload_manifest.json"
    p.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return WorkloadManifest.load(p)


def _ensure_modal_importable(monkeypatch):
    """Preflight's modal_sdk check does `import modal`; CI does not install
    the real SDK, so stub an empty module when it's genuinely absent (and
    leave any real/fake one already in place untouched)."""
    import sys as _sys
    import types

    if "modal" in _sys.modules:
        return
    try:
        import modal  # noqa: F401
    except ImportError:
        monkeypatch.setitem(_sys.modules, "modal", types.ModuleType("modal"))


def _passing_preflight(
    tmp_path: Path,
    monkeypatch,
    *,
    approved_cost_cap_usd: float = 10.0,
    variants=None,
    files=None,
    timeout: int | None = None,
    retries: int = 1,
    seconds_per_pod: float = 60.0,
):
    """Build a fully consistent executor/data/manifest trio and run a
    preflight that passes every check. Returns (executor, data_manifest,
    report, workload_manifest)."""
    _ensure_modal_importable(monkeypatch)
    bundle, bundle_fp = _write_bundle_dir(tmp_path)
    files = _DEFAULT_FILES if files is None else files
    wm = _load_manifest(
        tmp_path, _manifest_payload(bundle_fp=bundle_fp, variants=variants, files=files)
    )
    kwargs: dict = {}
    if timeout is not None:
        kwargs["timeout"] = timeout
    executor = ModalExecutor(
        bundle_dir=str(bundle), volume_name="test-vol", region="us-east",
        retries=retries, **kwargs,
    )
    data_manifest = DataManifest(
        commit_id="vc1", timestamp="2026-07-10T00:00:00", files=files,
        total_bytes=1000,
    )
    report = executor.preflight(
        data_manifest,
        n_variants=len(wm.variants),
        n_seeds_per_variant=len(wm.variants[0].seeds),
        approved_cost_cap_usd=approved_cost_cap_usd,
        workload_manifest=wm,
        seconds_per_pod=seconds_per_pod,
    )
    assert report.passed, f"fixture preflight must pass, got {report.checks} {report.details}"
    return executor, data_manifest, report, wm


def _request(
    *,
    name: str = "cap12_driftinf_topup05",
    role: str = "candidate",
    config_json: str = "{}",
    seeds=(42, 43, 44),
    volume_commit: str = "vc1",
    start: str = "2024-01-01",
    end: str = "2026-03-28",
) -> BacktestRequest:
    return BacktestRequest(
        variant_name=name,
        role=role,
        config_json=config_json,
        volume_commit_id=volume_commit,
        seeds=list(seeds),
        start=start,
        end=end,
        initial_cash=100_000.0,
        incumbent_turnover=None,
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
        wm = _load_manifest(tmp_path, _manifest_payload(bundle_fp="deadbeef"))
        executor = ModalExecutor(
            bundle_dir=str(tmp_path / "nonexistent"),
            volume_name="test-vol",
            region="us-east",
        )
        manifest = DataManifest(
            commit_id="vc1",
            timestamp="2026-07-07T00:00:00",
            files=dict(_DEFAULT_FILES),
            total_bytes=1000,
        )
        report = executor.preflight(
            manifest, n_variants=1, n_seeds_per_variant=3,
            approved_cost_cap_usd=10.0, workload_manifest=wm,
        )
        assert not report.passed
        assert report.checks["bundle_exists"] is False
        # No dispatch token from a failed preflight.
        assert report.approval is None

    def test_preflight_passes_with_valid_state(self, tmp_path: Path, monkeypatch):
        executor, data_manifest, report, wm = _passing_preflight(tmp_path, monkeypatch)
        assert isinstance(report, ModalPreflightReport)
        assert isinstance(report, PreflightReport)  # still protocol-compatible
        assert report.passed
        assert report.checks["bundle_exists"] is True
        assert report.checks["volume_has_data"] is True
        assert report.checks["cost_within_effective_gate"] is True
        assert report.checks["region_pinned"] is True
        assert report.checks["bundle_fingerprint_matches_manifest"] is True
        assert report.checks["image_spec_matches_manifest"] is True

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
        bundle, bundle_fp = _write_bundle_dir(tmp_path)
        wm = _load_manifest(tmp_path, _manifest_payload(bundle_fp=bundle_fp))
        executor = ModalExecutor(bundle_dir=str(bundle), region="us-east")
        manifest = DataManifest(
            commit_id=None, timestamp="", files={}, total_bytes=0,
        )
        report = executor.preflight(
            manifest, n_variants=1, n_seeds_per_variant=3,
            approved_cost_cap_usd=10.0, workload_manifest=wm,
        )
        assert not report.passed
        assert report.checks["volume_has_data"] is False
        assert report.approval is None

    def test_preflight_cost_scales_with_actual_pod_count(self, tmp_path: Path):
        """Under per-seed fan-out, pods = n_variants * n_seeds_per_variant.
        The preflight cost projection must scale with that real product, not
        a stale one-pod-per-variant assumption (previously hardcoded as
        `_estimate_cost_usd(30.0) * 75`, which never reflected the actual
        75 variants x 3 seeds = 225-pod fan-out plan)."""
        bundle, bundle_fp = _write_bundle_dir(tmp_path)
        wm = _load_manifest(tmp_path, _manifest_payload(bundle_fp=bundle_fp))
        executor = ModalExecutor(bundle_dir=str(bundle), region="us-east")
        manifest = DataManifest(
            commit_id="vc1", timestamp="2026-07-08T00:00:00",
            files=dict(_DEFAULT_FILES), total_bytes=1000,
        )

        big = executor.preflight(
            manifest, n_variants=1000, n_seeds_per_variant=1,
            approved_cost_cap_usd=10.0, workload_manifest=wm,
        )
        bigger = executor.preflight(
            manifest, n_variants=1000, n_seeds_per_variant=3,
            approved_cost_cap_usd=10.0, workload_manifest=wm,
        )
        assert not big.checks["cost_within_effective_gate"]
        assert not bigger.checks["cost_within_effective_gate"]
        big_cost = float(
            big.details["cost_within_effective_gate"].split("$")[1].split(" ")[0]
        )
        bigger_cost = float(
            bigger.details["cost_within_effective_gate"].split("$")[1].split(" ")[0]
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
            captured["image_pip_packages"] = list(a)
            return self

        def run_commands(self, *a, **k):
            captured["image_run_commands"] = list(a)
            return self

    class _FakeImageNS:
        @staticmethod
        def debian_slim(python_version=None):
            captured["image_python_version"] = python_version
            return _FakeImage()

    fake_modal.App = _FakeApp
    fake_modal.Volume = _FakeVolume
    fake_modal.Image = _FakeImageNS

    monkeypatch.setitem(_sys.modules, "modal", fake_modal)
    return captured


class TestImageSpecCoupling:
    """modal_app's baked image build inputs must match IMAGE_SPEC — the
    single source of truth whose fingerprint gets pre-registered in every
    workload manifest. Literal drift between the two would let a manifest
    record an image identity that is not what actually runs."""

    def test_modal_app_image_is_built_from_image_spec(self, monkeypatch):
        import importlib
        import sys as _sys

        captured = _install_fake_modal_sdk(monkeypatch)
        module_name = "renquant_orchestrator.cloud.modal_app"
        monkeypatch.delitem(_sys.modules, module_name, raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_TIMEOUT_SECONDS", raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_RETRIES", raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_REGION", raising=False)
        importlib.import_module(module_name)

        assert captured["image_python_version"] == IMAGE_SPEC["python_version"]
        assert captured["image_pip_packages"] == list(IMAGE_SPEC["pip_packages"])
        assert captured["image_run_commands"] == list(IMAGE_SPEC["run_commands"])

    def test_image_spec_fingerprint_is_deterministic_sha256(self):
        fp = image_spec_fingerprint()
        assert fp == image_spec_fingerprint()
        assert len(fp) == 64
        int(fp, 16)  # valid hex


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
        monkeypatch.delenv("RENQUANT_MODAL_REGION", raising=False)

        executor, _dm, report, _wm = _passing_preflight(tmp_path, monkeypatch, timeout=222, retries=9)

        try:
            executor.execute_batch(
                [], on_result=lambda r: None, on_error=lambda n, e: None,
                preflight=report,
            )
        except Exception:
            pass  # fake app.run() / empty request list — irrelevant here

        mod = _sys.modules[module_name]
        assert mod.WORKER_TIMEOUT_SECONDS == 222
        assert mod.WORKER_RETRIES == 9
        assert mod.run_variant_remote._modal_function_kwargs["timeout"] == 222
        assert mod.run_variant_remote._modal_function_kwargs["retries"] == 9
        # The pre-registered region genuinely reaches the decorator too —
        # the manifest's REQUIRED region field is requested, not just noted.
        assert mod.WORKER_REGION == "us-east"
        assert mod.run_variant_remote._modal_function_kwargs["region"] == "us-east"

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
        monkeypatch.delenv("RENQUANT_MODAL_REGION", raising=False)

        first, _dm1, report1, _wm1 = _passing_preflight(
            tmp_path, monkeypatch, timeout=100, retries=2
        )
        try:
            first.execute_batch(
                [], on_result=lambda r: None, on_error=lambda n, e: None,
                preflight=report1,
            )
        except Exception:
            pass

        second, _dm2, report2, _wm2 = _passing_preflight(
            tmp_path, monkeypatch, timeout=200, retries=3
        )
        with pytest.raises(RuntimeError, match="cannot be honored without a fresh process"):
            second.execute_batch(
                [], on_result=lambda r: None, on_error=lambda n, e: None,
                preflight=report2,
            )


def _install_fake_modal_sdk_with_map(monkeypatch, per_seed_results_json):
    """Like _install_fake_modal_sdk, but the decorated worker function's
    `.map()` yields the given canned per-pod JSON result strings and
    `app.run()` is a working (no-op) context manager — enough to exercise
    ModalExecutor.execute_batch's real aggregation logic end to end without
    a real Modal dispatch. Returns a list that captures the exact request
    JSON strings dispatched through `.map()`."""
    import sys as _sys
    import types
    from contextlib import contextmanager

    fake_modal = types.ModuleType("modal")
    dispatched: list[str] = []

    class _FakeMappedFn:
        def __init__(self, results):
            self._results = results

        def map(self, requests, kwargs=None, **extra):
            dispatched.extend(list(requests))
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
    return dispatched


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

        module_name = "renquant_orchestrator.cloud.modal_app"
        monkeypatch.delitem(_sys.modules, module_name, raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_TIMEOUT_SECONDS", raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_RETRIES", raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_REGION", raising=False)

        # 3 pods for ONE variant with deliberately DIFFERENT elapsed times —
        # max() would report only the slowest pod's time (600s); sum() must
        # report the true total compute-seconds actually billed (1100s).
        per_seed = [
            self._fake_pod_result("cap12_driftinf_topup05", 42, 300.0, "task-a"),
            self._fake_pod_result("cap12_driftinf_topup05", 43, 600.0, "task-b"),
            self._fake_pod_result("cap12_driftinf_topup05", 44, 200.0, "task-c"),
        ]
        _install_fake_modal_sdk_with_map(monkeypatch, per_seed)

        executor, _dm, report, _wm = _passing_preflight(tmp_path, monkeypatch)
        request = _request()

        results = []
        summary = executor.execute_batch(
            [request],
            on_result=results.append,
            on_error=lambda n, e: (_ for _ in ()).throw(e),
            preflight=report,
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

        module_name = "renquant_orchestrator.cloud.modal_app"
        monkeypatch.delitem(_sys.modules, module_name, raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_TIMEOUT_SECONDS", raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_RETRIES", raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_REGION", raising=False)

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

        executor, _dm, report, _wm = _passing_preflight(tmp_path, monkeypatch)
        request = _request()

        results = []
        errors = []
        # No lambda-that-raises here (unlike the sibling test above) —
        # proving execute_batch itself must not propagate the pod's
        # exception; on_error is just a recording callback.
        summary = executor.execute_batch(
            [request],
            on_result=results.append,
            on_error=lambda name, exc: errors.append((name, exc)),
            preflight=report,
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


class TestSpendCapEnforcement:
    """Codex #450 (03:21Z) point 1: the operator-approved cap must be a
    REQUIRED preflight input, enforced as min(hard safety gate, cap) — the
    tighter bound always governs, and a missing/unresolved cap fails closed
    rather than silently falling back to the fixed gate."""

    def _fixture(self, tmp_path, monkeypatch):
        _ensure_modal_importable(monkeypatch)
        bundle, bundle_fp = _write_bundle_dir(tmp_path)
        wm = _load_manifest(tmp_path, _manifest_payload(bundle_fp=bundle_fp))
        executor = ModalExecutor(
            bundle_dir=str(bundle), volume_name="test-vol", region="us-east",
        )
        dm = DataManifest(
            commit_id="vc1", timestamp="2026-07-10T00:00:00",
            files=dict(_DEFAULT_FILES), total_bytes=1000,
        )
        return executor, dm, wm

    def test_cap_is_required_with_no_default(self, tmp_path, monkeypatch):
        executor, dm, wm = self._fixture(tmp_path, monkeypatch)
        with pytest.raises(TypeError):
            executor.preflight(
                dm, n_variants=1, n_seeds_per_variant=3, workload_manifest=wm,
            )

    def test_workload_manifest_is_required_with_no_default(self, tmp_path, monkeypatch):
        executor, dm, _wm = self._fixture(tmp_path, monkeypatch)
        with pytest.raises(TypeError):
            executor.preflight(
                dm, n_variants=1, n_seeds_per_variant=3,
                approved_cost_cap_usd=10.0,
            )

    def test_unresolved_cap_fails_closed_not_fallback(self, tmp_path, monkeypatch):
        executor, dm, wm = self._fixture(tmp_path, monkeypatch)
        for bad in (0.0, -5.0, float("nan"), float("inf")):
            with pytest.raises(ValueError, match="fails\\s+closed"):
                executor.preflight(
                    dm, n_variants=1, n_seeds_per_variant=3,
                    approved_cost_cap_usd=bad, workload_manifest=wm,
                )
        for bad in (None, "10", True):
            with pytest.raises(TypeError):
                executor.preflight(
                    dm, n_variants=1, n_seeds_per_variant=3,
                    approved_cost_cap_usd=bad, workload_manifest=wm,
                )

    def test_hard_gate_binds_when_cap_is_higher(self, tmp_path, monkeypatch):
        """An enormous approved cap can never RAISE the gate above the hard
        $20 safety literal — min() must bind at the hard gate."""
        executor, dm, wm = self._fixture(tmp_path, monkeypatch)
        # 15 variants × 3 seeds × 5558s/pod ≈ $22 projected — above the hard
        # gate but far below the approved cap.
        report = executor.preflight(
            dm, n_variants=15, n_seeds_per_variant=3,
            approved_cost_cap_usd=1_000_000.0, workload_manifest=wm,
        )
        assert report.checks["cost_within_effective_gate"] is False
        assert (
            f"${HARD_COST_SAFETY_GATE_USD:.2f}"
            in report.details["cost_within_effective_gate"]
        )
        assert report.approval is None

    def test_approved_cap_binds_when_below_hard_gate(self, tmp_path, monkeypatch):
        """A cap tighter than the hard gate must govern: the same projection
        that clears $20 fails a $1 operator cap."""
        executor, dm, wm = self._fixture(tmp_path, monkeypatch)
        # 1 variant × 3 seeds at the default 5558s/pod ≈ $1.47 projected.
        tight = executor.preflight(
            dm, n_variants=1, n_seeds_per_variant=3,
            approved_cost_cap_usd=1.0, workload_manifest=wm,
        )
        assert tight.checks["cost_within_effective_gate"] is False
        assert tight.approval is None

        loose = executor.preflight(
            dm, n_variants=1, n_seeds_per_variant=3,
            approved_cost_cap_usd=2.0, workload_manifest=wm,
        )
        assert loose.checks["cost_within_effective_gate"] is True

    def test_effective_gate_recorded_as_min_of_both_bounds(self, tmp_path, monkeypatch):
        executor, dm, wm = self._fixture(tmp_path, monkeypatch)
        below = executor.preflight(
            dm, n_variants=1, n_seeds_per_variant=3,
            approved_cost_cap_usd=5.0, workload_manifest=wm,
        )
        assert below.passed
        assert below.approval.effective_cost_gate_usd == pytest.approx(5.0)
        assert below.approval.approved_cost_cap_usd == pytest.approx(5.0)

        above = executor.preflight(
            dm, n_variants=1, n_seeds_per_variant=3,
            approved_cost_cap_usd=50.0, workload_manifest=wm,
        )
        assert above.passed
        assert above.approval.effective_cost_gate_usd == pytest.approx(
            HARD_COST_SAFETY_GATE_USD
        )
        assert above.approval.approved_cost_cap_usd == pytest.approx(50.0)

    def test_projected_over_cap_fails_whole_preflight(self, tmp_path, monkeypatch):
        executor, dm, wm = self._fixture(tmp_path, monkeypatch)
        report = executor.preflight(
            dm, n_variants=1, n_seeds_per_variant=3,
            approved_cost_cap_usd=0.50, workload_manifest=wm,
        )
        assert report.passed is False
        assert report.approval is None
        # The cap is still recorded in the report on failure — part of the
        # immutable evidence trail either way.
        assert "$0.50" in report.details["cost_within_effective_gate"]


class TestWorkloadManifestValidation:
    """Codex #450 (03:21Z) point 2: region/image/Volume are REQUIRED
    recorded fields — unknown region or unresolved image/Volume identity is
    an abort, not a post-hoc note; a bare variant count is not a workload."""

    def test_unknown_region_rejected(self, tmp_path):
        for bad_region in ("unknown", "", "TBD"):
            with pytest.raises(WorkloadManifestError, match="region"):
                _load_manifest(
                    tmp_path,
                    _manifest_payload(bundle_fp="fp", region=bad_region),
                )
        payload = _manifest_payload(bundle_fp="fp")
        del payload["region"]
        with pytest.raises(WorkloadManifestError, match="region"):
            _load_manifest(tmp_path, payload)

    def test_unresolved_image_identity_rejected(self, tmp_path):
        with pytest.raises(WorkloadManifestError, match="image_spec_sha256"):
            _load_manifest(
                tmp_path,
                _manifest_payload(bundle_fp="fp", image_spec_sha256="unknown"),
            )

    def test_unresolved_volume_identity_rejected(self, tmp_path):
        with pytest.raises(WorkloadManifestError, match="volume_commit_id"):
            _load_manifest(
                tmp_path,
                _manifest_payload(bundle_fp="fp", volume_commit_id=""),
            )
        with pytest.raises(WorkloadManifestError, match="volume_name"):
            _load_manifest(
                tmp_path,
                _manifest_payload(bundle_fp="fp", volume_name="none"),
            )

    def test_missing_data_interval_rejected(self, tmp_path):
        payload = _manifest_payload(bundle_fp="fp")
        del payload["data_interval"]
        with pytest.raises(WorkloadManifestError, match="data_interval"):
            _load_manifest(tmp_path, payload)

    def test_empty_or_countlike_variants_rejected(self, tmp_path):
        with pytest.raises(WorkloadManifestError, match="variants"):
            _load_manifest(tmp_path, _manifest_payload(bundle_fp="fp", variants=[]))
        # "3 variants" as a count is not a pre-registered workload.
        with pytest.raises(WorkloadManifestError):
            _load_manifest(tmp_path, _manifest_payload(bundle_fp="fp", variants=3))

    def test_duplicate_variant_names_rejected(self, tmp_path):
        with pytest.raises(WorkloadManifestError, match="duplicate"):
            _load_manifest(
                tmp_path,
                _manifest_payload(
                    bundle_fp="fp",
                    variants=[dict(_DEFAULT_VARIANT), dict(_DEFAULT_VARIANT)],
                ),
            )

    def test_non_integer_seeds_rejected(self, tmp_path):
        for bad_seeds in ([], ["42"], [True], None):
            variant = dict(_DEFAULT_VARIANT, seeds=bad_seeds)
            with pytest.raises(WorkloadManifestError, match="seeds"):
                _load_manifest(
                    tmp_path, _manifest_payload(bundle_fp="fp", variants=[variant]),
                )

    def test_manifest_sha_is_digest_of_approved_file_bytes(self, tmp_path):
        payload = _manifest_payload(bundle_fp="fp")
        p = tmp_path / "wm.json"
        p.write_text(json.dumps(payload, indent=2, sort_keys=True))
        wm = WorkloadManifest.load(p)
        assert wm.sha256 == hashlib.sha256(p.read_bytes()).hexdigest()
        # Any byte-level change to the approved file is a different identity.
        p.write_text(json.dumps(payload, indent=4, sort_keys=True))
        assert WorkloadManifest.load(p).sha256 != wm.sha256

    def test_write_workload_manifest_round_trips_and_validates(self, tmp_path):
        out = tmp_path / "captured.json"
        wm = write_workload_manifest(
            out,
            region="us-east",
            volume_name="test-vol",
            volume_commit_id="vc42",
            data_manifest_sha256="d" * 64,
            bundle_fingerprint="b" * 64,
            artifact_manifest_sha256="a" * 64,
            start="2024-01-02",
            end="2026-03-28",
            variants=[dict(_DEFAULT_VARIANT)],
        )
        loaded = WorkloadManifest.load(out)
        assert loaded == wm
        assert loaded.image_spec_sha256 == image_spec_fingerprint()
        assert loaded.variants[0].seeds == (42, 43, 44)

    def test_write_workload_manifest_refuses_unresolved_plan(self, tmp_path):
        out = tmp_path / "captured.json"
        with pytest.raises(WorkloadManifestError, match="region"):
            write_workload_manifest(
                out,
                region="unknown",
                volume_name="test-vol",
                volume_commit_id="vc42",
                data_manifest_sha256="d" * 64,
                bundle_fingerprint="b" * 64,
                artifact_manifest_sha256="a" * 64,
                start="2024-01-02",
                end="2026-03-28",
                variants=[dict(_DEFAULT_VARIANT)],
            )
        assert not out.exists(), "an unresolvable plan must never be written"


class TestDispatchGuard:
    """execute_batch refuses to dispatch without a PASSING preflight run
    with an approved cap (token threaded through, not an honor-system
    flag), and fails on ANY workload/manifest mismatch BEFORE dispatch."""

    def test_execute_without_preflight_is_refused(self, tmp_path, monkeypatch):
        executor, _dm, _report, _wm = _passing_preflight(tmp_path, monkeypatch)
        with pytest.raises(RuntimeError, match="no preflight report"):
            executor.execute_batch(
                [_request()], on_result=lambda r: None, on_error=lambda n, e: None,
            )

    def test_failed_preflight_report_is_not_a_dispatch_token(self, tmp_path):
        bundle, bundle_fp = _write_bundle_dir(tmp_path)
        wm = _load_manifest(tmp_path, _manifest_payload(bundle_fp=bundle_fp))
        executor = ModalExecutor(
            bundle_dir=str(bundle), volume_name="test-vol", region="us-east",
        )
        dm = DataManifest(
            commit_id="vc1", timestamp="2026-07-10T00:00:00",
            files=dict(_DEFAULT_FILES), total_bytes=1000,
        )
        # Cap below projection → preflight FAILS (no approval issued).
        failed = executor.preflight(
            dm, n_variants=1, n_seeds_per_variant=3,
            approved_cost_cap_usd=0.01, workload_manifest=wm,
        )
        assert not failed.passed
        with pytest.raises(RuntimeError, match="did not\\s+PASS"):
            executor.execute_batch(
                [_request()], on_result=lambda r: None,
                on_error=lambda n, e: None, preflight=failed,
            )

    def test_report_from_another_executor_is_refused(self, tmp_path, monkeypatch):
        _issuer, _dm, report, _wm = _passing_preflight(tmp_path, monkeypatch)
        other = ModalExecutor(
            bundle_dir=str(tmp_path / "bundle"), volume_name="test-vol",
            region="us-east",
        )
        with pytest.raises(RuntimeError, match="not issued by this"):
            other.execute_batch(
                [_request()], on_result=lambda r: None,
                on_error=lambda n, e: None, preflight=report,
            )

    def test_unregistered_variant_fails_before_dispatch(self, tmp_path, monkeypatch):
        executor, _dm, report, _wm = _passing_preflight(tmp_path, monkeypatch)
        rogue = _request(name="cap99_rogue_variant")
        with pytest.raises(WorkloadMismatchError, match="not pre-registered"):
            executor.execute_batch(
                [_request(), rogue], on_result=lambda r: None,
                on_error=lambda n, e: None, preflight=report,
            )

    def test_changed_seed_fails_before_dispatch(self, tmp_path, monkeypatch):
        executor, _dm, report, _wm = _passing_preflight(tmp_path, monkeypatch)
        with pytest.raises(WorkloadMismatchError, match="seeds"):
            executor.execute_batch(
                [_request(seeds=(42, 43, 45))], on_result=lambda r: None,
                on_error=lambda n, e: None, preflight=report,
            )

    def test_config_fingerprint_drift_fails_before_dispatch(self, tmp_path, monkeypatch):
        executor, _dm, report, _wm = _passing_preflight(tmp_path, monkeypatch)
        with pytest.raises(WorkloadMismatchError, match="config fingerprint"):
            executor.execute_batch(
                [_request(config_json='{"tampered": true}')],
                on_result=lambda r: None, on_error=lambda n, e: None,
                preflight=report,
            )

    def test_bundle_fingerprint_drift_fails_before_dispatch(self, tmp_path, monkeypatch):
        executor, _dm, report, _wm = _passing_preflight(tmp_path, monkeypatch)
        # Mutate the bundle AFTER the passing preflight — the dispatch-time
        # re-check must catch it (preflight alone is not enough).
        (tmp_path / "bundle" / "bundle_manifest.json").write_text(
            json.dumps({"kernel/core.py": "tampered"})
        )
        with pytest.raises(WorkloadMismatchError, match="bundle fingerprint"):
            executor.execute_batch(
                [_request()], on_result=lambda r: None,
                on_error=lambda n, e: None, preflight=report,
            )

    def test_off_interval_or_wrong_volume_commit_fails(self, tmp_path, monkeypatch):
        executor, _dm, report, _wm = _passing_preflight(tmp_path, monkeypatch)
        with pytest.raises(WorkloadMismatchError, match="data interval"):
            executor.execute_batch(
                [_request(start="2023-01-01")], on_result=lambda r: None,
                on_error=lambda n, e: None, preflight=report,
            )
        with pytest.raises(WorkloadMismatchError, match="volume commit"):
            executor.execute_batch(
                [_request(volume_commit="vc-drifted")], on_result=lambda r: None,
                on_error=lambda n, e: None, preflight=report,
            )

    def test_happy_path_records_cap_and_manifest_sha(self, monkeypatch, tmp_path):
        """A conforming batch dispatches, and the run's evidence carries
        the approved cap + manifest sha: echoed into every pod's dispatch
        metadata AND stamped onto the aggregated results."""
        import sys as _sys

        module_name = "renquant_orchestrator.cloud.modal_app"
        monkeypatch.delitem(_sys.modules, module_name, raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_TIMEOUT_SECONDS", raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_RETRIES", raising=False)
        monkeypatch.delenv("RENQUANT_MODAL_REGION", raising=False)

        pod_json = json.dumps({
            "variant_name": "cap12_driftinf_topup05",
            "role": "candidate",
            "config_fingerprint": "fp",
            "worker_id": "task-a",
            "volume_commit_id": "vc1",
            "code_image_id": "img1",
            "started_at": "2026-07-10T00:00:00+00:00",
            "finished_at": "2026-07-10T00:10:00+00:00",
            "elapsed_seconds": 300.0,
            "peak_memory_mb": 1000.0,
            "seeds": [42],
            "per_seed": [{"seed": 42, "apy": 0.1, "sharpe": 1.0}],
            "equity_curves": None,
            "trade_logs": None,
            "result_checksum": "chk42",
        })
        dispatched = _install_fake_modal_sdk_with_map(
            monkeypatch, [pod_json, pod_json, pod_json]
        )

        executor, _dm, report, wm = _passing_preflight(tmp_path, monkeypatch)
        results = []
        summary = executor.execute_batch(
            [_request()], on_result=results.append,
            on_error=lambda n, e: (_ for _ in ()).throw(e),
            preflight=report,
        )

        assert summary.n_completed == 1
        # Every dispatched pod request carries the approval evidence.
        assert len(dispatched) == 3
        for raw in dispatched:
            meta = json.loads(raw)["dispatch_metadata"]
            assert meta["workload_manifest_sha256"] == wm.sha256
            assert meta["approved_cost_cap_usd"] == pytest.approx(10.0)
            assert meta["effective_cost_gate_usd"] == pytest.approx(10.0)
            assert meta["region"] == "us-east"
        # ...and the aggregated result is stamped with the manifest sha.
        assert results[0].workload_manifest_sha256 == wm.sha256
        # The pre-registered region genuinely reached the decorator.
        mod = _sys.modules[module_name]
        assert mod.run_variant_remote._modal_function_kwargs["region"] == "us-east"
