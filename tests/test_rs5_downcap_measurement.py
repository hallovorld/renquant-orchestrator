"""Unit tests for scripts/rs5_downcap_measurement.py (RS-5/M7 fallback run).

Hermetic: synthetic frames only — no umbrella data, no network. Covers the
S-REL P0 duties: the contract validate-or-refuse branch, the positive-control
detection path, the true-null no-effect branch, and the frozen §1/§3 mechanics
(monthly floors, cost buckets, placebo construction).
"""
from __future__ import annotations

import importlib.util
import json
import os

import numpy as np
import pandas as pd
import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD_PATH = os.path.join(REPO_ROOT, "scripts", "rs5_downcap_measurement.py")


def _load_module():
    spec = importlib.util.spec_from_file_location("rs5_downcap_measurement", MOD_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def m():
    return _load_module()


@pytest.fixture(scope="module")
def contract():
    p = os.path.join(
        REPO_ROOT, "doc/research/evidence/2026-07-02-rs5-m7-prereg/prereg_contract.json")
    with open(p) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Contract validate-or-refuse (spec §7)
# ---------------------------------------------------------------------------
def test_runner_matches_committed_contract(m, contract):
    assert m.validate_against_contract(contract) == []


def test_runner_refuses_on_tampered_threshold(m, contract):
    bad = json.loads(json.dumps(contract))
    bad["verdict_logic"]["gate_a_net_relevant_placebo_clean_ic"][
        "point_estimate_threshold"] = 0.015  # the large-cap bar, NOT the frozen 0.02
    errs = m.validate_against_contract(bad)
    assert errs and any("gate_a_threshold" in e for e in errs)


def test_runner_refuses_on_tampered_cost_bucket(m, contract):
    bad = json.loads(json.dumps(contract))
    bad["cost_model"]["buckets"][2]["round_trip_bps"] = 40  # soften bucket C
    errs = m.validate_against_contract(bad)
    assert errs and any("cost_buckets" in e for e in errs)


# ---------------------------------------------------------------------------
# Frozen mechanics
# ---------------------------------------------------------------------------
def test_cost_bucket_assignment(m):
    assert m.adv_bucket_rt_bps(30_000_000) == 25.0
    assert m.adv_bucket_rt_bps(25_000_000) == 25.0
    assert m.adv_bucket_rt_bps(15_000_000) == 40.0
    assert m.adv_bucket_rt_bps(7_000_000) == 60.0
    # drift below the $5M floor between monthly evaluations => bucket C
    assert m.adv_bucket_rt_bps(3_000_000) == 60.0
    assert m.adv_bucket_rt_bps(15_000_000, shift_bps=10.0) == 50.0


def test_factor_formulas_match_sighunt_convention(m):
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2020-01-01", periods=400)
    px = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0, 0.01, (400, 3)), axis=0)),
        index=idx, columns=list("ABC"))
    f = m.compute_factors(px)
    expected_mom = px.shift(21) / px.shift(252) - 1.0
    pd.testing.assert_frame_equal(f["mom_12_1"], expected_mom)
    expected_rev = -1.0 * (px / px.shift(21) - 1.0)
    pd.testing.assert_frame_equal(f["st_rev_21"], expected_rev)


def test_placebo_is_label_shifted_plus_horizon(m):
    idx = pd.bdate_range("2020-01-01", periods=200)
    rng = np.random.default_rng(1)
    close = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0, 0.01, (200, 2)), axis=0)),
        index=idx, columns=["X", "Y"])
    spy = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.008, 200))), index=idx)
    lab = m.fwd_excess(close, spy, 60)
    placebo = lab.shift(-60)
    # placebo at t equals the label evaluated at t+60 (within ticker)
    assert placebo.iloc[0]["X"] == pytest.approx(lab.iloc[60]["X"])
    # clean series defined only where both exist: last 2*60 dates drop out
    both = lab["X"].notna() & placebo["X"].notna()
    assert both.sum() == 200 - 120


def test_monthly_membership_applies_next_session(m):
    # 6 months of sessions; one name crosses the ADV floor only in month 4+
    idx = pd.bdate_range("2020-01-01", "2020-06-30")
    n = len(idx)
    raw = pd.DataFrame({"LOW": 10.0, "HIGH": 50.0}, index=idx)
    dv = pd.DataFrame({"LOW": 1e6, "HIGH": 1e8}, index=idx)  # LOW under $5M ADV
    # give both >=252 sessions of history by prepending
    pre = pd.bdate_range("2018-01-01", periods=300)
    raw = pd.concat([pd.DataFrame({"LOW": 10.0, "HIGH": 50.0}, index=pre), raw])
    dv = pd.concat([pd.DataFrame({"LOW": 1e6, "HIGH": 1e8}, index=pre), dv])
    member = m.monthly_membership(raw, dv)
    # after the first full evaluation, HIGH is a member and LOW never is
    tail = member.loc[idx[-40]:]
    assert tail["HIGH"].all()
    assert not member["LOW"].any()
    # applied NEXT session: on the first session after a month-end evaluation,
    # membership reflects that evaluation
    month_ends = [d for i, d in enumerate(raw.index[:-1])
                  if raw.index[i + 1].month != d.month]
    e = month_ends[-2]
    nxt = raw.index[raw.index.get_loc(e) + 1]
    assert bool(member.loc[nxt, "HIGH"])


# ---------------------------------------------------------------------------
# Harness controls: planted effect must be detected; true null must not be
# ---------------------------------------------------------------------------
def _mini_panel(m, seed=7, n_dates=420, n_names=260):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2019-01-01", periods=n_dates)
    cols = [f"T{i}" for i in range(n_names)]
    close = pd.DataFrame(
        50 * np.exp(np.cumsum(rng.normal(0, 0.02, (n_dates, n_names)), axis=0)),
        index=idx, columns=cols)
    spy = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, n_dates))), index=idx)
    lab = m.fwd_excess(close, spy, 60)
    placebo = lab.shift(-60)
    base = pd.DataFrame(rng.standard_normal((n_dates, n_names)), index=idx, columns=cols)
    return lab, placebo, base


def test_positive_control_detected(m):
    lab, placebo, base = _mini_panel(m)
    f = m.build_control_factor(lab, base, "positive", seed=42)
    ic = m.per_date_ic(f, lab, placebo, min_names=200)
    ser = ic["clean_ic"].dropna()
    assert len(ser) > 100
    b = m.block_bootstrap_stats(ser.to_numpy(), block=60, n_boot=300, seed=42)
    assert ser.mean() >= m.GATE_A_IC          # planted ~0.1 clears the 0.02 bar
    assert b["onesided_lb_98_75"] > 0          # CI lower bound clears zero


def test_true_null_not_detected_and_kill_branch_fires(m):
    lab, placebo, base = _mini_panel(m)
    f = m.build_control_factor(lab, base, "null", seed=42)
    ic = m.per_date_ic(f, lab, placebo, min_names=200)
    ser = ic["clean_ic"].dropna()
    assert len(ser) > 100
    b = m.block_bootstrap_stats(ser.to_numpy(), block=60, n_boot=300, seed=42)
    detected = ser.mean() >= m.GATE_A_IC and b["onesided_lb_98_75"] > 0
    assert not detected                        # the no-effect branch fires
    assert b["onesided_ub_98_75"] < m.GATE_A_IC  # per-family KILL leg fires on null


def test_per_date_ic_enforces_min_names(m):
    lab, placebo, base = _mini_panel(m, n_names=150)  # below the 200 floor
    ic = m.per_date_ic(base, lab, placebo, min_names=200)
    assert len(ic) == 0
