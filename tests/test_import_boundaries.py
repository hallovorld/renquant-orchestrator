"""CI lint: cross-repo import boundaries (V-018 remediation).

Ensures that importing the orchestrator package does not eagerly pull in
modules that belong to other layers (broker runtime, heavy ML frameworks,
or pipeline kernel internals).

Known V-005 violations (deferred kernel imports in specific modules) are
tested separately to verify they remain deferred.

Isolation note (codex review on this PR, 2026-07-13): every import check
below runs in a FRESH subprocess rather than doing an in-process
``sys.modules`` before/after diff. A same-process diff is unsound in this
suite specifically: several other test files import real
``renquant_pipeline.kernel`` submodules directly from inside their test
bodies (``test_d6_freeze_record.py::test_session_parity_with_pipeline_loader``,
``test_native_context_hydration.py``, ``test_live_bridge.py``,
``test_train_gbdt.py``, ...). Whichever of those runs first in the shared
pytest process leaves ``renquant_pipeline.kernel`` cached in ``sys.modules``
for the rest of the run, so a later before/after diff here would see no
*new* kernel modules even if the target eagerly imports kernel -- the
"before" snapshot already contains it. This was verified to reproduce with
the file ordering pytest actually uses under `make test`/`pytest -q`
(``test_d6_freeze_record.py`` sorts and runs before this file). A fresh
interpreter always starts with an empty ``sys.modules``, so the diff is
meaningful no matter what ran earlier in the session or in what order.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import types
from collections.abc import Sequence
from pathlib import Path

import pytest

_FORBIDDEN_PREFIXES = (
    "alpaca",
    "ib_insync",
    "live",
    "renquant_pipeline.kernel",
    "torch",
    "xgboost",
)

# Executed with `python -c SCRIPT <module_name>` in a brand-new interpreter.
# Reports either the set of module names that newly appeared in sys.modules,
# or the ImportError message -- as the last line of stdout, JSON-encoded.
_ISOLATED_IMPORT_SCRIPT = """
import importlib
import json
import sys

module_name = sys.argv[1]
before = set(sys.modules)
try:
    importlib.import_module(module_name)
except ImportError as exc:
    print(json.dumps({"error": str(exc)}))
    raise SystemExit(0)
imported = sorted(set(sys.modules) - before)
print(json.dumps({"imported": imported}))
"""


def _run_isolated_import(
    module_name: str, *, extra_syspath: Sequence[str] = ()
) -> dict[str, object]:
    """Import ``module_name`` in a fresh interpreter; report what it pulled in.

    ``extra_syspath`` entries are searched *before* the current process's own
    ``sys.path`` (which is forwarded via ``PYTHONPATH`` so the subprocess sees
    whatever sibling repos/pytest ``pythonpath`` config are already active).
    """
    env = dict(os.environ)
    search_path = [*extra_syspath, *sys.path]
    env["PYTHONPATH"] = os.pathsep.join(p for p in search_path if p)
    completed = subprocess.run(
        [sys.executable, "-c", _ISOLATED_IMPORT_SCRIPT, module_name],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError(
            f"isolated import of {module_name!r} produced no output "
            f"(exit={completed.returncode}):\n{completed.stderr}"
        )
    return json.loads(lines[-1])


def _kernel_leaks(report: dict[str, object]) -> list[str]:
    imported = report.get("imported", [])
    return sorted(
        name
        for name in imported  # type: ignore[union-attr]
        if name == "renquant_pipeline.kernel" or name.startswith("renquant_pipeline.kernel.")
    )


def _full_environment_available() -> bool:
    """Whether the fully-provisioned multirepo environment is present.

    ``.github/workflows/ci.yml`` only checks out the sibling repos (and only
    then runs `make test`, which is the only job that collects this file) when
    ``RENQUANT_HAS_CI_TOKEN`` is set; its token-less "focused test" job runs a
    hand-picked list of three unrelated test files and never touches this one.
    So in practice, whenever this file *does* run, the sibling repos are
    supposed to be on the path. Probe via ``renquant_common``, the one shared
    substrate every sibling repo depends on: if it imports, we are in that
    expected environment and an ImportError on a V-005 module below is a real
    regression that must fail loudly -- not a documented, silently-skippable
    environment gap.
    """
    return "error" not in _run_isolated_import("renquant_common")


def test_orchestrator_import_does_not_pull_live_broker_runtime() -> None:
    """Top-level import must not eagerly load broker/ML/kernel modules."""
    report = _run_isolated_import("renquant_orchestrator")
    assert "error" not in report, f"renquant_orchestrator itself failed to import: {report}"
    imported = report["imported"]
    offenders = sorted(
        name
        for name in imported  # type: ignore[union-attr]
        if name in _FORBIDDEN_PREFIXES
        or any(name.startswith(p + ".") for p in _FORBIDDEN_PREFIXES)
    )
    assert offenders == [], f"Top-level import leaked forbidden modules: {offenders}"


# ---------------------------------------------------------------------------
# V-005 known violations: modules with deferred kernel imports
#
# These modules import from renquant_pipeline.kernel inside functions (not at
# module level).  The tests below verify that *importing the module itself*
# does not leak kernel into sys.modules.  When V-005 is fully remediated
# (kernel dependency removed or wrapped behind an adapter), remove the
# corresponding parametrize entry.
# ---------------------------------------------------------------------------

_V005_MODULES = [
    "native_context_hydration",
    "live_bridge",
    "train_gbdt",
]


@pytest.mark.parametrize("submodule", _V005_MODULES)
def test_v005_kernel_dependency_stays_deferred(submodule: str) -> None:
    """Importing a V-005 module must not eagerly pull renquant_pipeline.kernel.

    If this fails, a deferred import was accidentally promoted to module level.
    V-005 tracks full remediation (replace kernel imports with an adapter).
    """
    module_name = f"renquant_orchestrator.{submodule}"
    report = _run_isolated_import(module_name)
    if "error" in report:
        if _full_environment_available():
            pytest.fail(
                f"{module_name} failed to import even though the full "
                "multirepo environment (renquant_common et al.) is present -- "
                "this is a real regression, not a documented environment gap "
                f"(this is the only CI job that ever collects this test): "
                f"{report['error']}"
            )
        pytest.skip(
            f"{module_name} not importable: sibling repos not on path "
            f"(documented, environment-only exception): {report['error']}"
        )
    kernel_leaks = _kernel_leaks(report)
    assert kernel_leaks == [], (
        f"V-005: {submodule} leaked kernel imports at module level: {kernel_leaks}"
    )


# ---------------------------------------------------------------------------
# Regression tests for the isolation harness itself (codex review on this PR).
#
# These prove the harness actually has teeth: it must flag a module that
# eagerly imports the forbidden kernel package, it must not be fooled by
# renquant_pipeline.kernel already sitting in the CALLING process's
# sys.modules (the exact false-negative mechanism a same-process diff had),
# and it must not flag a module that only imports kernel inside a function
# body (the legitimate, documented V-005 pattern).
# ---------------------------------------------------------------------------


def _write_fake_pipeline_stub(fake_root: Path) -> None:
    kernel_pkg = fake_root / "renquant_pipeline" / "kernel"
    kernel_pkg.mkdir(parents=True)
    (fake_root / "renquant_pipeline" / "__init__.py").write_text("")
    (kernel_pkg / "__init__.py").write_text("")


def test_isolated_harness_flags_eager_kernel_import(tmp_path: Path) -> None:
    """The harness must FAIL a module that imports kernel at module level."""
    fake_root = tmp_path / "fake_pkgs"
    _write_fake_pipeline_stub(fake_root)
    broken_pkg = fake_root / "broken_v005_module"
    broken_pkg.mkdir()
    (broken_pkg / "__init__.py").write_text("import renquant_pipeline.kernel\n")

    report = _run_isolated_import("broken_v005_module", extra_syspath=[str(fake_root)])
    assert "error" not in report, report
    leaks = _kernel_leaks(report)
    assert leaks == ["renquant_pipeline.kernel"], (
        "regression: the isolated import harness failed to catch an eager "
        f"top-level `import renquant_pipeline.kernel` (got {leaks!r})"
    )


def test_isolated_harness_ignores_deferred_kernel_import(tmp_path: Path) -> None:
    """The harness must NOT flag a module that only imports kernel inside a
    function body -- the same pattern the real V-005 modules use."""
    fake_root = tmp_path / "fake_pkgs"
    _write_fake_pipeline_stub(fake_root)
    good_pkg = fake_root / "good_v005_module"
    good_pkg.mkdir()
    (good_pkg / "__init__.py").write_text(
        "def use_kernel():\n"
        "    import renquant_pipeline.kernel\n"
        "    return renquant_pipeline.kernel\n"
    )

    report = _run_isolated_import("good_v005_module", extra_syspath=[str(fake_root)])
    assert "error" not in report, report
    assert _kernel_leaks(report) == []


def test_isolated_harness_ignores_same_process_kernel_pollution(tmp_path: Path) -> None:
    """Regression for the reviewed bug: poison *this* (parent) process's
    sys.modules with a stand-in kernel package first -- simulating what
    genuinely happens today once any earlier-sorted test file in the shared
    pytest session imports a real kernel submodule -- then prove the
    subprocess-isolated harness still detects a real violation. A
    same-process ``set(sys.modules)`` diff would go blind here, because its
    "before" snapshot would already contain the poisoned name.
    """
    poisoned = ("renquant_pipeline", "renquant_pipeline.kernel")
    already_present = {name: name in sys.modules for name in poisoned}
    try:
        sys.modules.setdefault("renquant_pipeline", types.ModuleType("renquant_pipeline"))
        sys.modules.setdefault(
            "renquant_pipeline.kernel", types.ModuleType("renquant_pipeline.kernel")
        )
        assert "renquant_pipeline.kernel" in sys.modules  # sanity: poisoned

        fake_root = tmp_path / "fake_pkgs"
        _write_fake_pipeline_stub(fake_root)
        broken_pkg = fake_root / "broken_v005_module_poisoned"
        broken_pkg.mkdir()
        (broken_pkg / "__init__.py").write_text("import renquant_pipeline.kernel\n")

        report = _run_isolated_import(
            "broken_v005_module_poisoned", extra_syspath=[str(fake_root)]
        )
        assert "error" not in report, report
        leaks = _kernel_leaks(report)
        assert leaks == ["renquant_pipeline.kernel"], (
            "regression: a same-process cached renquant_pipeline.kernel must "
            f"not hide a real violation from the isolated harness (got {leaks!r})"
        )
    finally:
        for name, was_present in already_present.items():
            if not was_present:
                sys.modules.pop(name, None)
