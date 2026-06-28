"""Finite-value guards for the read-only PEAD cheap-screen IC/HAC path (PR #203 review fix 3).

The cheap screen (scripts/pead_test.py) computed its Newey-West HAC t-stat with a bare ``@``
matmul, whose NumPy 2.x BLAS path emits spurious overflow/invalid/divide warnings even on
bounded IC inputs and could let a NaN/inf propagate into the statistic. These tests assert the
finite-guarded helpers:

  * produce FINITE outputs (no NaN/inf) on clean inputs and emit NO NumPy RuntimeWarnings,
  * FAIL LOUDLY (raise) on non-finite inputs instead of silently writing a NaN statistic,
  * keep ``spearman_ic`` finite-or-NaN and degenerate-safe,
  * leave the HAC point estimate numerically equivalent to the old bare-matmul formula,
  * keep the SUE z-score finite-or-NaN (a zero trailing-std denominator must NOT become +inf
    and silently corrupt the qcut quintile binning).
"""
from __future__ import annotations

import importlib.util
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_SPEC = importlib.util.spec_from_file_location(
    "pead_test", Path(__file__).resolve().parent.parent / "scripts" / "pead_test.py")
pead = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(pead)


def _ic_series(n: int = 2006, seed: int = 7) -> np.ndarray:
    """A realistic bounded rank-IC series in [-1, 1] (the kind that triggered the warnings)."""
    rng = np.random.default_rng(seed)
    return rng.uniform(-1.0, 1.0, size=n).astype(np.float64)


def test_nw_tstat_finite_and_no_numpy_warnings() -> None:
    x = _ic_series()
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)  # any spurious matmul warning -> failure
        t = pead.nw_tstat(x, lag=20)
    assert np.isfinite(t)


def test_safe_dot_matches_matmul_and_is_finite() -> None:
    x = _ic_series()
    xd = x - x.mean()
    # numerically equivalent to the old `xd @ xd`, but warning-free + finite-guarded
    assert pead._safe_dot(xd, xd, "lag0") == pytest.approx(float(np.dot(xd, xd)))
    assert np.isfinite(pead._safe_dot(xd[5:], xd[:-5], "lag5"))


def test_nw_tstat_raises_on_nonfinite_input() -> None:
    x = _ic_series(n=50)
    x[3] = np.inf  # a non-NaN, non-finite value must NOT be silently absorbed
    with pytest.raises(ValueError):
        pead.nw_tstat(x, lag=10)


def test_safe_dot_raises_on_nonfinite_input() -> None:
    u = np.array([1.0, 2.0, np.inf], dtype=np.float64)
    v = np.ones(3, dtype=np.float64)
    with pytest.raises(ValueError):
        pead._safe_dot(u, v, "lag0")


def test_nw_tstat_short_series_returns_nan_not_error() -> None:
    assert np.isnan(pead.nw_tstat(np.array([0.1, 0.2, 0.3]), lag=2))


def test_spearman_ic_finite_on_monotone_signal() -> None:
    sig = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0])
    ret = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    ic, n = pead.spearman_ic(sig, ret)
    assert n == 6
    assert np.isfinite(ic)
    assert ic == pytest.approx(1.0)


def test_spearman_ic_degenerate_constant_is_nan_not_inf() -> None:
    sig = pd.Series([1.0, 1.0, 1.0, 1.0, 1.0, 1.0])  # zero variance -> corrcoef undefined
    ret = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5, 0.6])
    ic, _ = pead.spearman_ic(sig, ret)
    assert np.isnan(ic)  # NaN (skipped upstream), never inf


def test_spearman_ic_too_few_pairs_returns_nan() -> None:
    sig = pd.Series([1.0, 2.0, np.nan, np.nan])
    ret = pd.Series([0.1, 0.2, 0.3, 0.4])
    ic, n = pead.spearman_ic(sig, ret)
    assert np.isnan(ic)
    assert n < 5


def test_sue_zscore_never_infinite_on_zero_std() -> None:
    # 8 identical prior surprises -> trailing std == 0; the next surprise must NOT become +inf
    # (the real NVDA 2020-02-13 case). It must be NaN so it is excluded, not poisoning qcut.
    surp = pd.Series([0.5] * 8 + [0.01])
    z = pead.sue_zscore(surp).to_numpy(dtype=float)
    assert not np.isinf(z).any()              # never +/-inf — that was the bug
    assert np.isnan(z[-1])                     # the zero-std denominator row is masked to NaN


def test_sue_zscore_output_is_finite_or_nan_only() -> None:
    rng = np.random.default_rng(3)
    surp = pd.Series(rng.normal(size=40))
    z = pead.sue_zscore(surp).to_numpy(dtype=float)
    assert not np.isinf(z).any()  # finite-or-NaN, never inf
    finite = z[np.isfinite(z)]
    assert finite.size > 0


def test_qcut_path_runs_without_runtime_warning_on_inf_row() -> None:
    # End-to-end-ish: a frame whose raw SUE would contain an inf must bin cleanly after the
    # guard, emitting NO NumPy RuntimeWarning from the percentile/qcut path.
    surp = pd.Series([0.5] * 8 + [0.01] + list(np.linspace(-2, 2, 30)))
    sue = pead.sue_zscore(surp)
    df = pd.DataFrame({"sue": sue}).dropna()
    df = df[np.isfinite(df["sue"].to_numpy(dtype=float))]
    with warnings.catch_warnings():
        warnings.simplefilter("error", RuntimeWarning)
        q = pd.qcut(df["sue"], 5, labels=False, duplicates="drop")
    assert q.notna().all()
