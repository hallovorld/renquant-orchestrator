"""S-REL R2 committed positive-control fixture for scripts/msig_c4_trendscan.py.

Synthetic-data tests of the C4 measurement machinery (no real panel required):
label construction, repaired-gate per-date delta-genuine series, the carried-mask
block bootstrap, the frozen verdict rule, and an end-to-end synthetic positive/
negative control pair (planted effect detected as GO; permuted scores never GO).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import msig_c4_trendscan as c4  # noqa: E402


# ------------------------------------------------------------------ label construction
def test_trendscan_label_sign_and_missing():
    df = pd.DataFrame({
        # steady uptrend, steady downtrend, missing horizon
        "fwd_5d_excess_raw": [0.01, -0.01, 0.01],
        "fwd_10d_excess_raw": [0.02, -0.02, 0.02],
        "fwd_20d_excess_raw": [0.04, -0.04, np.nan],
        "fwd_60d_excess_raw": [0.12, -0.12, 0.12],
    })
    lab = c4.build_trendscan_label(df)
    assert lab[0] > 0, "clean uptrend must get a positive signed t-stat"
    assert lab[1] < 0, "clean downtrend must get a negative signed t-stat"
    assert np.isnan(lab[2]), "missing horizon must yield NaN (dropped downstream)"
    assert np.isclose(lab[0], -lab[1]), "symmetric paths must get symmetric t-stats"


def test_trendscan_label_rewards_persistence_over_magnitude():
    df = pd.DataFrame({
        # A: clean linear trend to +6%; B: noisy path ending at +12%
        "fwd_5d_excess_raw": [0.005, 0.06],
        "fwd_10d_excess_raw": [0.01, -0.04],
        "fwd_20d_excess_raw": [0.02, 0.10],
        "fwd_60d_excess_raw": [0.06, 0.12],
    })
    lab = c4.build_trendscan_label(df)
    assert lab[0] > lab[1], "persistent clean trend must out-score noisy larger move"


# ---------------------------------------------------------------- carried-mask bootstrap
def test_carried_mask_bootstrap_respects_calendar_gaps():
    # two in-cell episodes of constant value separated by a long NaN gap: every
    # bootstrap mean must equal that constant (no off-cell contamination), and the
    # NaN gap must not crash or splice.
    vals = np.full(400, np.nan)
    vals[10:80] = 0.03
    vals[300:380] = 0.03
    boots = c4.carried_mask_block_bootstrap(vals, block=60, n_boot=200, seed=1)
    assert boots is not None
    assert np.allclose(boots, 0.03)


def test_carried_mask_bootstrap_refuses_thin_series():
    assert c4.carried_mask_block_bootstrap(np.ones(30), block=60, n_boot=50,
                                           seed=1) is None
    empty = np.full(200, np.nan)
    assert c4.carried_mask_block_bootstrap(empty, block=60, n_boot=50, seed=1) is None


# ------------------------------------------------------------------------- verdict rule
def test_verdict_rule_frozen_semantics():
    n_ok = c4.N_FLOOR + 1
    assert c4.verdict_from_bounds(0.021, 0.08, 0.02, n_ok) == "GO"
    assert c4.verdict_from_bounds(-0.05, 0.019, 0.02, n_ok) == "KILL"
    assert c4.verdict_from_bounds(0.001, 0.05, 0.02, n_ok) == "INCONCLUSIVE"
    assert c4.verdict_from_bounds(0.05, 0.08, 0.02, 10).startswith("INCONCLUSIVE")


def test_aggregate_verdict_requires_all_seeds():
    assert c4.aggregate_verdict(["GO", "GO", "GO"]) == "GO"
    assert c4.aggregate_verdict(["GO", "GO", "INCONCLUSIVE"]) == "INCONCLUSIVE"
    assert c4.aggregate_verdict(["KILL", "KILL", "KILL"]) == "KILL"
    assert c4.aggregate_verdict(["KILL", "GO", "KILL"]) == "INCONCLUSIVE"


# ------------------------------------------------- synthetic end-to-end positive control
def _synthetic_scores(n_dates=800, n_names=40, plant=0.0, seed=0):
    """Candidate score = plant * z(y_real) + noise; base score = independent noise.

    With plant=0 the true delta_genuine is 0; with a large plant the candidate
    gains genuine (non-placebo) IC the machinery must detect as GO.
    """
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", periods=n_dates, freq="B")
    rows = []
    for d in dates:
        y = rng.normal(size=n_names)
        yp = rng.normal(size=n_names)  # placebo label independent of y
        cand = plant * y + rng.normal(size=n_names)
        base = rng.normal(size=n_names)
        rows.append(pd.DataFrame({
            "date": d, "ticker": [f"T{i}" for i in range(n_names)],
            "regime": "BULL_CALM", c4.RAW: y, "y_placebo": yp,
            "score_ts": cand, "score_raw": base}))
    return pd.concat(rows, ignore_index=True), pd.DatetimeIndex(dates)


def test_synthetic_planted_effect_reads_go(monkeypatch):
    monkeypatch.setattr(c4, "N_BOOT", 200)
    scores, axis = _synthetic_scores(plant=0.6, seed=3)
    series = c4.per_date_delta_series(scores)
    cell = c4.evaluate_cell(series, axis, "BULL_CALM", boot_seed=42)
    assert cell["n_dates"] >= c4.N_FLOOR
    assert cell["mean_delta_genuine"] > 0.02
    assert cell["verdict_frozen_margin"] == "GO"


def test_synthetic_null_never_reads_go(monkeypatch):
    monkeypatch.setattr(c4, "N_BOOT", 200)
    scores, axis = _synthetic_scores(plant=0.0, seed=4)
    series = c4.per_date_delta_series(scores)
    cell = c4.evaluate_cell(series, axis, "BULL_CALM", boot_seed=42)
    assert abs(cell["mean_delta_genuine"]) < 0.02
    # the frozen acceptance criterion: a true-zero effect must NEVER read GO
    # (whether it reads KILL or INCONCLUSIVE depends on the CI width, which the
    # block=60 bootstrap keeps honestly wide on iid synthetic noise)
    assert cell["verdict_frozen_margin"] != "GO"


def test_per_date_delta_series_pairs_legs():
    scores, _ = _synthetic_scores(n_dates=30, plant=0.6, seed=5)
    series = c4.per_date_delta_series(scores)
    sub = series[series["cell"] == "BULL_CALM"]
    assert len(sub) == 30
    lhs = sub["delta_genuine"].to_numpy()
    rhs = (sub["genuine_cand"] - sub["genuine_base"]).to_numpy()
    assert np.allclose(lhs, rhs), "delta must be the paired per-date difference"
