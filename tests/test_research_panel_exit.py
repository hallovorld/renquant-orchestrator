"""Test the importable bootstrap-CI helper of the panel-exit predictiveness study."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

_SPEC = importlib.util.spec_from_file_location(
    "rpe", Path(__file__).resolve().parent.parent / "scripts" / "research_panel_exit_predictiveness.py")
rpe = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rpe)


def test_boot_ci_positive_series_excludes_zero():
    rng = np.random.default_rng(0)
    x = rng.normal(0.05, 0.01, size=200)
    m, lo, hi = rpe.boot_ci(x)
    assert lo <= m <= hi and lo > 0


def test_boot_ci_zero_mean_series_includes_zero():
    rng = np.random.default_rng(1)
    x = rng.normal(0.0, 0.05, size=200)
    _, lo, hi = rpe.boot_ci(x)
    assert lo <= 0 <= hi


def test_boot_ci_tiny_input_returns_nan_ci():
    m, lo, hi = rpe.boot_ci([0.01, 0.02, 0.03])
    assert np.isfinite(m) and np.isnan(lo) and np.isnan(hi)


def test_boot_ci_ignores_nonfinite():
    m, lo, hi = rpe.boot_ci([0.01] * 50 + [float("nan"), float("inf")])
    assert abs(m - 0.01) < 1e-9 and np.isfinite(lo)
