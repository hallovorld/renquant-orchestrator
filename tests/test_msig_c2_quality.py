"""Committed positive-control fixture for scripts/msig_c2_quality.py (S-REL R2).

S-REL (PR #265) R2: positive controls are mandatory in every negative-result
harness — a committed pytest fixture where the effect is PLANTED at decision
scale and the harness must detect it; a NULL without a passing positive
control is inadmissible as a verdict.  These tests plant (a) a horizon-decaying
effect the full IC->placebo->bootstrap->rule path MUST flag GO, and (b) a null
the path must NOT flag; plus unit tests of the frozen PIT availability rule
(strictly-after-acceptance, anomaly guard, staleness cap) and the spec 1.2
missingness rule (a name missing ANY leg is excluded from that date).
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))

import msig_c2_quality as c2  # noqa: E402

C3 = c2.c3  # the shared committed harness machinery


def _synthetic_ic_frames(n_dates=900, n_names=40, horizon=5, kappa=9.95, seed=1234):
    """Label = iid noise; planted score = zscore_t(label) + kappa*noise
    (planted per-date Spearman IC ~= 0.10, decaying past the horizon by
    construction so it survives the shifted-label placebo)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2019-01-01", periods=n_dates)
    names = [f"N{i:02d}" for i in range(n_names)]
    label = pd.DataFrame(rng.standard_normal((n_dates, n_names)), index=dates, columns=names)
    z = label.sub(label.mean(axis=1), axis=0).div(label.std(axis=1), axis=0)
    planted = z + kappa * pd.DataFrame(
        rng.standard_normal((n_dates, n_names)), index=dates, columns=names)
    null_score = pd.DataFrame(
        rng.standard_normal((n_dates, n_names)), index=dates, columns=names)
    placebo = label.shift(-horizon)
    return planted, null_score, label, placebo


def test_positive_control_planted_decaying_effect_is_detected():
    planted, _, label, placebo = _synthetic_ic_frames()
    ic = C3.per_date_ic(planted, label, placebo)
    gate = c2.run_gate(ic, block=5, seeds=(42,), n_boot=300)
    assert gate["mean_clean_ic"] > 0.05  # planted at ~0.10, well above the bar
    assert gate["mechanical_rule_output"] == "GO"


def test_specificity_null_feature_is_not_flagged():
    _, null_score, label, placebo = _synthetic_ic_frames()
    ic = C3.per_date_ic(null_score, label, placebo)
    gate = c2.run_gate(ic, block=5, seeds=(42,), n_boot=300)
    assert abs(gate["mean_clean_ic"]) < 0.02
    assert gate["mechanical_rule_output"] != "GO"


def _mk_obs(period_end, accepted):
    return pd.DataFrame({
        "symbol": ["AAA"],
        "period_end": [pd.Timestamp(period_end)],
        "gp_a": [0.5], "accruals": [0.0], "net_issuance": [0.0],
        "acceptedDate": [pd.Timestamp(accepted) if accepted else pd.NaT],
        "filingDate": [pd.NaT],
    })


def test_availability_is_strictly_after_accepted_date():
    cal = pd.bdate_range("2020-01-01", "2020-03-01")
    obs, _ = c2.resolve_availability(_mk_obs("2019-12-31", "2020-01-15 17:30:00"), cal)
    # 2020-01-15 is a Wednesday trading day; first day STRICTLY after = Jan 16
    assert obs["avail_day"].iloc[0] == pd.Timestamp("2020-01-16")
    assert obs["avail_field"].iloc[0] == "acceptedDate"


def test_anomaly_guard_accepted_on_or_before_period_end_is_inadmissible():
    cal = pd.bdate_range("2020-01-01", "2020-03-01")
    obs, stats = c2.resolve_availability(_mk_obs("2020-01-31", "2020-01-31"), cal)
    assert pd.isna(obs["avail_day"].iloc[0])
    assert stats["n_anomalous_inadmissible"] == 1


def test_no_timestamp_is_inadmissible_never_proxy_dated():
    cal = pd.bdate_range("2020-01-01", "2020-03-01")
    obs, _ = c2.resolve_availability(_mk_obs("2019-12-31", None), cal)
    assert pd.isna(obs["avail_day"].iloc[0])
    assert obs["avail_field"].iloc[0] == "INADMISSIBLE_no_timestamp"


def test_staleness_cap_drops_observation_after_400_calendar_days():
    cal = pd.bdate_range("2020-01-01", "2021-06-30")
    obs, _ = c2.resolve_availability(_mk_obs("2019-12-31", "2020-01-15"), cal)
    panels = c2.build_asof_panels(obs, cal, ["AAA"])
    s = panels["gp_a"]["AAA"]
    assert s.loc[pd.Timestamp("2020-06-01")] == 0.5          # fresh
    assert pd.isna(s.loc[pd.Timestamp("2021-06-01")])        # > 400 cal days stale


def test_missing_any_leg_excludes_name_from_that_date():
    cal = pd.bdate_range("2020-06-01", periods=5)
    names = [f"N{i:02d}" for i in range(c2.MIN_NAMES + 1)]
    full = pd.DataFrame(1.0, index=cal, columns=names)
    rng = np.random.default_rng(0)
    panels = {
        "gp_a": full + rng.standard_normal(full.shape),
        "accruals": full + rng.standard_normal(full.shape),
        "net_issuance": full + rng.standard_normal(full.shape),
    }
    panels["accruals"].loc[cal[2], names[0]] = np.nan  # one leg missing
    comp = c2.composite_from_panels(panels)
    assert pd.isna(comp.loc[cal[2], names[0]])
    assert comp.loc[cal[2], names[1:]].notna().all()
    assert comp.loc[cal[1], names[0]] == comp.loc[cal[1], names[0]]  # present elsewhere
