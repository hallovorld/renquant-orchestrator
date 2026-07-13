"""CI lint: cross-repo import boundaries (V-018 remediation).

Ensures that importing the orchestrator package does not eagerly pull in
modules that belong to other layers (broker runtime, heavy ML frameworks,
or pipeline kernel internals).

Known V-005 violations (deferred kernel imports in specific modules) are
tested separately to verify they remain deferred.
"""
from __future__ import annotations

import importlib
import sys

import pytest


def test_orchestrator_import_does_not_pull_live_broker_runtime() -> None:
    """Top-level import must not eagerly load broker/ML/kernel modules."""
    before = set(sys.modules)
    importlib.import_module("renquant_orchestrator")
    imported = set(sys.modules) - before

    forbidden_prefixes = (
        "alpaca",
        "ib_insync",
        "live",
        "renquant_pipeline.kernel",
        "torch",
        "xgboost",
    )
    offenders = sorted(
        name
        for name in imported
        if name in forbidden_prefixes
        or any(name.startswith(p + ".") for p in forbidden_prefixes)
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
    before = set(sys.modules)
    try:
        importlib.import_module(f"renquant_orchestrator.{submodule}")
    except ImportError:
        pytest.skip(f"renquant_orchestrator.{submodule} not importable in test env")
    imported = set(sys.modules) - before

    kernel_leaks = sorted(
        name
        for name in imported
        if name == "renquant_pipeline.kernel"
        or name.startswith("renquant_pipeline.kernel.")
    )
    assert kernel_leaks == [], (
        f"V-005: {submodule} leaked kernel imports at module level: {kernel_leaks}"
    )
