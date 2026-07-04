"""expkit.evaluation — IC/placebo/label primitives + matched admission."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from renquant_orchestrator.expkit.evaluation import (
    fwd_excess,
    gate_shift_sessions,
    paired_deltas,
    per_date_ic,
    shifted_label_placebo,
    shifted_label_placebo_long,
    solve_matched_admission,
    spearman,
)


# ---------------------------------------------------------------------------
# spearman
# ---------------------------------------------------------------------------
def test_spearman_perfect_and_inverse():
    a = np.array([1.0, 2.0, 3.0, 4.0])
    assert spearman(a, a * 10) == pytest.approx(1.0)
    assert spearman(a, -a) == pytest.approx(-1.0)


def test_spearman_monotone_transform_invariant():
    rng = np.random.default_rng(0)
    a = rng.standard_normal(50)
    assert spearman(a, np.exp(a)) == pytest.approx(1.0)


def test_spearman_degenerate_is_nan():
    assert math.isnan(spearman(np.ones(5), np.arange(5.0)))


# ---------------------------------------------------------------------------
# per_date_ic
# ---------------------------------------------------------------------------
def _wide(vals: np.ndarray, dates, names) -> pd.DataFrame:
    return pd.DataFrame(vals, index=dates, columns=names)


def test_per_date_ic_clean_is_real_minus_placebo():
    rng = np.random.default_rng(1)
    dates = pd.date_range("2024-01-01", periods=6, freq="B")
    names = [f"T{i}" for i in range(8)]
    score = _wide(rng.standard_normal((6, 8)), dates, names)
    label = _wide(rng.standard_normal((6, 8)), dates, names)
    placebo = _wide(rng.standard_normal((6, 8)), dates, names)
    out = per_date_ic(score, label, placebo, min_names=5)
    assert len(out) == 6
    assert np.allclose(out["clean_ic"], out["real_ic"] - out["placebo_ic"])
    # spot-check one date against a direct computation
    dt = dates[2]
    assert out.loc[dt, "real_ic"] == pytest.approx(
        spearman(score.loc[dt].to_numpy(), label.loc[dt].to_numpy())
    )


def test_per_date_ic_min_names_gate():
    dates = pd.date_range("2024-01-01", periods=2, freq="B")
    names = [f"T{i}" for i in range(10)]
    rng = np.random.default_rng(2)
    score = _wide(rng.standard_normal((2, 10)), dates, names)
    label = score * 2.0
    placebo = score * 0.5
    # kill the label cross-section on date 0 below the floor
    label.iloc[0, 3:] = np.nan
    out = per_date_ic(score, label, placebo, min_names=5)
    assert "real_ic" not in out.columns or pd.isna(out.iloc[0].get("real_ic"))
    assert out.iloc[1]["clean_ic"] == pytest.approx(0.0)  # both legs IC=1


# ---------------------------------------------------------------------------
# labels + placebo conventions
# ---------------------------------------------------------------------------
def test_fwd_excess_values_and_clip():
    dates = pd.date_range("2024-01-01", periods=4, freq="B")
    close = pd.DataFrame({"A": [10.0, 10.0, 40.0, 40.0]}, index=dates)
    bench = pd.Series([100.0, 100.0, 110.0, 110.0], index=dates)
    out = fwd_excess(close, bench, horizon=2)
    # A: 40/10-1 = 3.0; bench: 0.10 -> excess 2.9 clipped to 0.5
    assert out.loc[dates[0], "A"] == pytest.approx(0.5)
    assert np.isnan(out.loc[dates[2], "A"])  # horizon runs off the end
    unclipped = fwd_excess(close, bench, horizon=2, clip=10.0)
    assert unclipped.loc[dates[0], "A"] == pytest.approx(2.9)


def test_gate_shift_sessions_is_twice_horizon():
    # the repaired-WF-gate S2 convention: _gate_shift_days = 2 * label horizon
    assert gate_shift_sessions(60) == 120
    assert gate_shift_sessions(20) == 40


def test_shifted_label_placebo_wide():
    dates = pd.date_range("2024-01-01", periods=5, freq="B")
    label = pd.DataFrame({"A": np.arange(5.0)}, index=dates)
    out = shifted_label_placebo(label, 2)
    assert out.loc[dates[0], "A"] == pytest.approx(2.0)  # label from t+2
    assert np.isnan(out.loc[dates[3], "A"])
    with pytest.raises(ValueError):
        shifted_label_placebo(label, 0)


def test_shifted_label_placebo_long_per_ticker():
    df = pd.DataFrame(
        {
            "ticker": ["A", "A", "A", "B", "B", "B"],
            "date": list(pd.date_range("2024-01-01", periods=3)) * 2,
            "y": [0.01, 0.02, 0.03, 0.10, 0.20, 0.30],
        }
    )
    out = shifted_label_placebo_long(df, label_col="y", shift_sessions=1)
    # per-ticker shift: A row0 gets A's t+1 value, never B's
    assert out.iloc[0] == pytest.approx(0.02)
    assert np.isnan(out.iloc[2])  # last A row has no t+1
    assert out.iloc[3] == pytest.approx(0.20)
    # clip applies (repo label convention)
    df2 = df.assign(y=[0.0, 5.0, 0.0, 0.0, -5.0, 0.0])
    out2 = shifted_label_placebo_long(df2, label_col="y", shift_sessions=1)
    assert out2.iloc[0] == pytest.approx(0.5)
    assert out2.iloc[3] == pytest.approx(-0.5)


# ---------------------------------------------------------------------------
# paired deltas
# ---------------------------------------------------------------------------
def test_paired_deltas_common_dates_only():
    d = pd.date_range("2024-01-01", periods=5, freq="B")
    a = pd.Series([0.1, 0.2, np.nan, 0.4, 0.5], index=d)
    b = pd.Series([0.05, np.nan, 0.3, 0.1, 0.2], index=d)
    out = paired_deltas(a, b)
    assert list(out.index) == [d[0], d[3], d[4]]
    assert out.loc[d[3]] == pytest.approx(0.3)


# ---------------------------------------------------------------------------
# matched-admission solve (the M4-b matched-breadth protocol)
# ---------------------------------------------------------------------------
def test_solve_matched_admission_monotone_increasing():
    # admission count rises with the parameter (integer step function)
    fn = lambda p: float(int(p * 10))  # noqa: E731
    out = solve_matched_admission(fn, target=7.0, lo=0.0, hi=1.0)
    assert out.converged
    assert out.achieved == pytest.approx(7.0)
    assert 0.7 <= out.param < 0.8


def test_solve_matched_admission_decreasing():
    # a floor: higher floor admits fewer names
    fn = lambda p: float(int((1.0 - p) * 10))  # noqa: E731
    out = solve_matched_admission(fn, target=3.0, lo=0.0, hi=1.0)
    assert out.converged
    assert out.achieved == pytest.approx(3.0)


def test_solve_matched_admission_target_outside_bracket_is_honest():
    fn = lambda p: p  # noqa: E731
    out = solve_matched_admission(fn, target=5.0, lo=0.0, hi=1.0)
    assert not out.converged
    assert out.achieved == pytest.approx(1.0)  # closest edge, honestly marked
