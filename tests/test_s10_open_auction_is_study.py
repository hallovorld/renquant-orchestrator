"""Tests for scripts/s10_open_auction_is_study.py's pure analysis functions.

Covers the R2 fixes: mixed-reference cohort separation, empty/single-day
handling, DST-correct RTH bar selection, and deterministic cluster
resampling. Network/filesystem-dependent fetch functions (_fills, _daily,
_true_vwap's parquet read) are not exercised here — `analyze()` is a pure
function of an already-built fills DataFrame, which is what these tests
target.
"""
import importlib.util
import os
import sys

import numpy as np
import pandas as pd
import pytest

_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts", "s10_open_auction_is_study.py",
)
_spec = importlib.util.spec_from_file_location("s10_open_auction_is_study", _SCRIPT)
s10 = importlib.util.module_from_spec(_spec)
sys.modules["s10_open_auction_is_study"] = s10
_spec.loader.exec_module(s10)


def _fill_row(symbol, date, ref_kind, vwap_bps, open_bps=0.0, close_bps=0.0):
    return {
        "symbol": symbol, "date": date, "ref_kind": ref_kind,
        "fill_vs_open_bps": open_bps,
        "fill_vs_vwap_bps": vwap_bps,
        "fill_vs_close_bps": close_bps,
    }


def test_mixed_reference_cohorts_reported_separately_and_proxy_does_not_move_verdict():
    """A synthetic case where the true-VWAP cohort is clearly material
    (tight CI, well above the bar) and the proxy cohort is clearly NOT
    material (tight CI, near zero) — pooling them would blur both signals.
    The fix must report them separately and the verdict must be driven only
    by the true-VWAP cohort."""
    rows = []
    # true-VWAP cohort: consistently ~50bps across many days -> tight CI, material.
    for i in range(12):
        rows.append(_fill_row("AAA", f"2026-01-{i+1:02d}", "true_vwap_10min", 50.0 + (i % 3)))
    # proxy cohort: consistently ~0bps across many days -> tight CI, not material.
    for i in range(12):
        rows.append(_fill_row("BBB", f"2026-02-{i+1:02d}", "ohlc4_proxy", 0.0 + (i % 3) - 1))
    df = pd.DataFrame(rows)

    out = s10.analyze(df)

    assert set(out["vwap_cohorts"].keys()) == {"true_vwap_10min", "ohlc4_proxy"}
    true_stat = out["vwap_cohorts"]["true_vwap_10min"]
    proxy_stat = out["vwap_cohorts"]["ohlc4_proxy"]
    assert true_stat["n_fills"] == 12
    assert proxy_stat["n_fills"] == 12
    # The two cohorts must have distinct stats -- proof they were not pooled.
    assert true_stat["mean"] != proxy_stat["mean"]
    assert true_stat["ci95"][0] > s10.MATERIALITY_BPS  # material on its own
    assert proxy_stat["ci95"][1] < s10.MATERIALITY_BPS  # not material on its own

    # Verdict must be driven by the true-VWAP cohort only.
    assert out["verdict"]["vs_day_vwap_true"] == "MATERIAL"
    assert out["verdict"]["vwap_proxy_cohort_is_descriptive_only"] is True


def test_empty_data_does_not_crash_and_reports_no_data():
    df = pd.DataFrame(columns=["symbol", "date", "ref_kind",
                                "fill_vs_open_bps", "fill_vs_vwap_bps", "fill_vs_close_bps"])
    out = s10.analyze(df)
    assert out["fills"] == []
    assert out["verdict"]["vs_day_vwap_true"] == "NO_DATA"
    assert out["verdict"]["vs_close"] == "NO_DATA"
    assert out["stats_date_clustered_bootstrap"] == {}


def test_single_day_data_flagged_unreliable_not_silently_confident():
    """A single independent day cannot support a cluster-bootstrap CI --
    every resample just repeats that one day. The fix must flag this
    explicitly rather than report a falsely tight/confident interval."""
    rows = [_fill_row("AAA", "2026-01-01", "true_vwap_10min", 50.0 + i) for i in range(5)]
    df = pd.DataFrame(rows)

    stat = s10._cluster_boot(df, "fill_vs_vwap_bps")
    assert stat["n_days"] == 1
    assert stat["reliable_ci"] is False

    verdict = s10._materiality_verdict(stat)
    assert verdict == "INCONCLUSIVE_TOO_FEW_DAYS"

    power = s10._cluster_robust_prospective_n_days(df, "fill_vs_vwap_bps")
    assert power is None  # cannot estimate day-level sigma from one day


def test_true_vwap_dst_correct_rth_selection(tmp_path, monkeypatch):
    """_true_vwap must select 09:30-16:00 ET bars correctly across a DST
    transition, using UTC-stamped input (as the real parquet files are)."""
    monkeypatch.setattr(s10, "RQ", str(tmp_path))
    symbol = "AAA"
    intraday_dir = tmp_path / "data" / "intraday" / symbol
    intraday_dir.mkdir(parents=True)

    # 2026-01-15 (EST, UTC-5): RTH 09:30-16:00 ET = 14:30-21:00 UTC.
    # 2026-07-15 (EDT, UTC-4): RTH 09:30-16:00 ET = 13:30-20:00 UTC.
    # 12 RTH bars per day (>= the function's len(g) < 10 floor) plus 2
    # pre/after-hours bars per day that must be EXCLUDED.
    winter_rth = pd.date_range("2026-01-15 14:30:00", periods=12, freq="10min", tz="UTC")
    winter_ext = pd.to_datetime(["2026-01-15 13:00:00", "2026-01-15 21:30:00"], utc=True)
    summer_rth = pd.date_range("2026-07-15 13:30:00", periods=12, freq="10min", tz="UTC")
    summer_ext = pd.to_datetime(["2026-07-15 12:00:00", "2026-07-15 20:30:00"], utc=True)
    idx = winter_rth.append(winter_ext).append(summer_rth).append(summer_ext)
    df = pd.DataFrame({
        "vwap": [100.0] * 12 + [999.0] * 2 + [200.0] * 12 + [999.0] * 2,
        "volume": [1000] * 12 + [1000] * 2 + [1000] * 12 + [1000] * 2,
    }, index=idx)
    df.to_parquet(intraday_dir / "10min.parquet")

    winter_day = pd.Timestamp("2026-01-15")
    summer_day = pd.Timestamp("2026-07-15")

    winter_vwap = s10._true_vwap(symbol, winter_day)
    summer_vwap = s10._true_vwap(symbol, summer_day)

    # Only the 12 in-RTH bars (vwap=100/200) must be used; the extended-hours
    # bars (vwap=999) must be excluded, proving the DST-correct ET window.
    assert winter_vwap == pytest.approx(100.0)
    assert summer_vwap == pytest.approx(200.0)


def test_cluster_bootstrap_is_deterministic_given_fixed_seed():
    # 25 days with a wide, non-repeating spread so two different seeds are
    # (with overwhelming probability) not going to collide on the same
    # rounded percentile boundary by chance -- a small/degenerate fixture
    # made this flaky in an earlier version of this test.
    rows = [_fill_row("AAA", f"2026-{(i % 12) + 1:02d}-{(i % 27) + 1:02d}", "true_vwap_10min",
                       np.sin(i) * 137.0 + i * 3.3)
            for i in range(25)]
    df = pd.DataFrame(rows)
    a = s10._cluster_boot(df, "fill_vs_vwap_bps", seed=42, n_boot=2000)
    b = s10._cluster_boot(df, "fill_vs_vwap_bps", seed=42, n_boot=2000)
    assert a["ci95"] == b["ci95"]
    c = s10._cluster_boot(df, "fill_vs_vwap_bps", seed=99, n_boot=2000)
    assert a["ci95"] != c["ci95"]


def test_materiality_verdict_uses_ci_lower_bound_not_point_estimate():
    """A point estimate above the bar with a CI that includes the bar must be
    INCONCLUSIVE, not MATERIAL -- this is the core bug the review flagged."""
    stat_inconclusive = {"mean": 40.1, "ci95": [-15.6, 99.2], "reliable_ci": True}
    assert s10._materiality_verdict(stat_inconclusive) == "INCONCLUSIVE"

    stat_material = {"mean": 40.1, "ci95": [15.0, 99.2], "reliable_ci": True}
    assert s10._materiality_verdict(stat_material) == "MATERIAL"

    stat_not_material = {"mean": 2.0, "ci95": [-5.0, 8.0], "reliable_ci": True}
    assert s10._materiality_verdict(stat_not_material) == "NOT_MATERIAL"


def test_prospective_power_reports_sensitivity_not_post_hoc_point_estimate():
    """The required-n_days estimate must be a sensitivity table powered
    against stated alternatives above the materiality bar, not the
    (possibly inflated) observed point estimate or the materiality bar
    treated as a null of zero -- confirms the fix no longer does post-hoc
    power calculation."""
    rows = [_fill_row("AAA", f"2026-01-{i+1:02d}", "true_vwap_10min", 40.0 + (i % 5) * 20)
            for i in range(10)]
    df = pd.DataFrame(rows)
    power = s10._cluster_robust_prospective_n_days(df, "fill_vs_vwap_bps")
    assert power is not None
    assert "materiality_bar_bps" in power and power["materiality_bar_bps"] == 10.0
    assert "assumptions" in power and "autocorrelation" in power["assumptions"]
    sens = power["sensitivity_by_alternative"]
    assert [row["mu_alternative_bps"] for row in sens] == [20.0, 30.0, 50.0]
    for row in sens:
        assert isinstance(row["required_n_days_80pct_power"], int)
        assert row["required_n_days_80pct_power"] > 0


def test_power_denominator_uses_gap_to_alternative_not_bar_alone():
    """Hand-computed sanity check: with sigma=100bps, materiality=10bps,
    mu_alternative=30bps, required n = ((1.96+0.84)*100/(30-10))**2 -- NOT
    ((1.96+0.84)*100/10)**2, which is what the old (buggy) formula computed."""
    sigma = 100.0
    n = s10._n_days_for_alternative(sigma, materiality_bps=10.0, mu_alternative_bps=30.0)
    expected = ((1.96 + 0.84) * sigma / (30.0 - 10.0)) ** 2
    assert n == pytest.approx(expected)
    buggy_old_formula = ((1.96 + 0.84) * sigma / 10.0) ** 2
    assert n != pytest.approx(buggy_old_formula)


def test_power_at_or_below_materiality_bar_is_infinite_not_silently_finite():
    """mu_alternative <= materiality_bps means zero gap to detect -- must
    return math.inf explicitly, never a finite (silently wrong) number."""
    assert s10._n_days_for_alternative(100.0, materiality_bps=10.0, mu_alternative_bps=10.0) == float("inf")
    assert s10._n_days_for_alternative(100.0, materiality_bps=10.0, mu_alternative_bps=5.0) == float("inf")

    rows = [_fill_row("AAA", f"2026-01-{i+1:02d}", "true_vwap_10min", 40.0 + (i % 5) * 20)
            for i in range(10)]
    df = pd.DataFrame(rows)
    power = s10._cluster_robust_prospective_n_days(
        df, "fill_vs_vwap_bps", alternatives_bps=(10.0,))
    assert power["sensitivity_by_alternative"][0]["required_n_days_80pct_power"] is None


def test_power_sensitivity_n_decreases_as_alternative_grows():
    """Basic sanity property of the correct formula: as the assumed true
    effect moves further above the materiality bar, the required sample
    size to detect it shrinks monotonically."""
    rows = [_fill_row("AAA", f"2026-01-{i+1:02d}", "true_vwap_10min", 40.0 + (i % 5) * 20)
            for i in range(10)]
    df = pd.DataFrame(rows)
    power = s10._cluster_robust_prospective_n_days(
        df, "fill_vs_vwap_bps", alternatives_bps=(20.0, 30.0, 50.0))
    ns = [row["required_n_days_80pct_power"] for row in power["sensitivity_by_alternative"]]
    assert ns == sorted(ns, reverse=True)
    assert len(set(ns)) == len(ns)
