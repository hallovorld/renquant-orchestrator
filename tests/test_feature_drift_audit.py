"""Tests for feature_drift_audit (#106/#108).

Synthetic panel with a KNOWN drift feature (equals the 120d future-shifted
label) and a KNOWN signal feature (equals the aligned label), so the audit's
ranking is checkable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from renquant_orchestrator.feature_drift_audit import (
    drift_audit,
    family_drift,
    suggest_prune_families,
)


def _panel(n_tickers=30, n_dates=200, shift=120, seed=0):
    rng = np.random.RandomState(seed)
    dates = pd.bdate_range("2020-01-01", periods=n_dates)
    tickers = [f"T{i:02d}" for i in range(n_tickers)]
    frames = []
    for t in tickers:
        lab = rng.randn(n_dates)
        df = pd.DataFrame({
            "ticker": t, "date": dates,
            "fwd_60d_excess": lab,
            "SIGNAL5": lab,                                   # = aligned label
            "DRIFT60": pd.Series(lab).shift(-shift).values,    # = future label
            "NOISE9": rng.randn(n_dates),                     # unrelated
        })
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def test_drift_feature_ranks_top_signal_bottom():
    a = drift_audit(_panel(), shift_days=120, min_names=20)
    order = list(a["feature"])
    assert order[0] == "DRIFT60"          # highest drift_excess
    assert order[-1] == "SIGNAL5"        # signal: aligned >> placebo -> negative
    drift_row = a[a.feature == "DRIFT60"].iloc[0]
    sig_row = a[a.feature == "SIGNAL5"].iloc[0]
    assert drift_row.drift_excess > 0.5
    assert sig_row.drift_excess < -0.5
    assert sig_row.aligned_ic > 0.9      # SIGNALa perfectly aligned


def test_family_drift_groups():
    fam = family_drift(drift_audit(_panel(), min_names=20))
    fams = set(fam["family"])
    assert {"DRIFT", "SIGNAL", "NOISE"} <= fams
    top = fam.iloc[0]["family"]
    assert top == "DRIFT"


def test_suggest_prune_picks_drift_not_signal():
    a = drift_audit(_panel(), min_names=20)
    picks = suggest_prune_families(a, min_drift_excess=0.2, max_abs_aligned=0.2)
    assert "DRIFT" in picks
    assert "SIGNAL" not in picks   # high aligned IC -> kept


def test_collision_guard_drops_prefix_of_keep_family():
    # 'MA' is a prefix of 'MAX'; if MAX is a keep-family, MA must be excluded
    # from the suggestions even if it drifts.
    a = drift_audit(_panel(), min_names=20)
    # inject a synthetic MA family row that drifts
    a = pd.concat([a, pd.DataFrame([{
        "feature": "MA60", "aligned_ic": 0.0, "placebo_ic": 0.5,
        "drift_excess": 0.5, "family": "MA"}])], ignore_index=True)
    picks = suggest_prune_families(a, min_drift_excess=0.2, max_abs_aligned=0.2,
                                   collides_with=["MAX"])
    assert "MA" not in picks


def test_exclude_prefixes_skips_family():
    a = drift_audit(_panel(), exclude_prefixes=("DRIFT",), min_names=20)
    assert "DRIFT60" not in set(a["feature"])
    assert "SIGNAL5" in set(a["feature"])
