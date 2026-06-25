"""Tests for the pure helpers of the vol-gate exploratory diagnostic — fold
non-overlap/embargo, bootstrap CI sanity, and metric computation. (The full
backtest needs data + xgboost and is run manually; these cover the testable logic.)"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

_SPEC = importlib.util.spec_from_file_location(
    "rvg", Path(__file__).resolve().parent.parent / "scripts" / "research_vol_gate_opportunity_cost.py")
rvg = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(rvg)


def test_purged_windows_nonoverlapping_and_embargoed():
    dates = pd.to_datetime(pd.date_range("2016-01-01", "2024-12-31", freq="B")).values
    wins = rvg.purged_test_windows(dates, n_folds=5, embargo_days=60)
    assert len(wins) == 5
    prev_hi = None
    for train_end, lo, hi in wins:
        assert lo <= hi
        # train ends at least `embargo` before the test starts (no leakage)
        assert pd.Timestamp(train_end) <= pd.Timestamp(lo) - pd.Timedelta(days=60)
        # test folds do NOT share a boundary with the previous fold
        if prev_hi is not None:
            assert pd.Timestamp(lo) > pd.Timestamp(prev_hi)
        prev_hi = hi


def test_annualize_basic_and_small_sample():
    assert rvg.annualize(pd.Series([0.01, 0.02])) == {"n": 2, "sharpe": float("nan")} or \
        rvg.annualize(pd.Series([0.01, 0.02]))["n"] == 2          # <6 → no full metrics
    s = pd.Series([0.01] * 12)
    m = rvg.annualize(s)
    assert m["n"] == 12 and m["ann_ret"] > 0 and m["hit"] == 1.0
    assert m["maxDD"] == 0.0                                      # all-positive → no drawdown


def test_block_bootstrap_ci_brackets_mean_and_flags_zero():
    rng = np.random.default_rng(1)
    # a clearly-positive series: CI should exclude 0
    pos = rng.normal(0.02, 0.005, size=120)
    mean, lo, hi = rvg.block_bootstrap_ci(pos, block=3, n_boot=1000)
    assert lo <= mean <= hi and lo > 0
    # a zero-mean noisy series: CI should include 0
    noise = rng.normal(0.0, 0.05, size=120)
    _, lo2, hi2 = rvg.block_bootstrap_ci(noise, block=3, n_boot=1000)
    assert lo2 <= 0 <= hi2


def test_block_bootstrap_ci_handles_tiny_input():
    mean, lo, hi = rvg.block_bootstrap_ci(np.array([0.01, 0.02]), block=3)
    assert np.isfinite(mean) and np.isnan(lo) and np.isnan(hi)   # too short for blocks
