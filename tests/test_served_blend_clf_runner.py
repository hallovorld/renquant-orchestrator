"""Tests for the served-blend + clf paired backtest runner.

The runner answers a deployment question by BACKTEST (operator policy
2026-08-18), so unlike the vol-switch confirmatory it is not under a
freeze-then-review-then-run protocol. What these tests hold are the two
things that keep the result honest:

1. BYTE-IDENTITY of the reused machinery. The refit/embargo/scoring/
   estimand/inference machinery is copied VERBATIM from the reviewed
   vol-switch runner (orch#1002/#1003) and the momentum readers from the
   reviewed tail_q90 runner (#996/#999). ``test_reused_*_byte_identical``
   fails the moment a copy drifts into a rewrite.
2. The runner's OWN logic — the served z-sum contract, the arm wiring, the
   clf label construction, block aggregation and the frozen verdict
   mapping — exercised on synthetic data. No market data is read and no
   xgboost training happens here.

The one-shot guard is tested as a MECHANISM on temp paths only (the
tail_q90 lesson: a "no outputs committed" repo-state test necessarily
breaks once the authorized run has landed its results).
"""
import ast
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "doc" / "research" / "data" / "2026-08-18-served-blend-plus-clf-derivation.py"
VOL_SWITCH = ROOT / "doc" / "research" / "data" / "2026-08-18-vol-switch-derivation.py"
TAILQ90 = ROOT / "doc" / "research" / "data" / "2026-08-18-gi-tailq90-derivation.py"

_spec = importlib.util.spec_from_file_location("served_blend_clf_runner", RUNNER)
rn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rn)


# --------------------------------------------- reused machinery byte-identity
def source_of(path: Path, target: str) -> str:
    src = path.read_text()
    for node in ast.parse(src).body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)) \
                and node.name == target:
            return ast.get_source_segment(src, node)
    raise AssertionError(f"{target} not found in {path.name}")


@pytest.mark.parametrize("name", [
    "_sha256", "_assert", "build_refit_calendar", "refit_index_for_date",
    "latest_realized_label_pos", "ReadersLite", "assert_one_shot",
    "load_trainer_module", "load_served_artifact", "fit_booster", "score_frame",
    "realized_vol20", "on_state_fixed", "block_on_day_counts",
    "dgtw_adjust", "top_decile_spread",
    "nw_lag1", "stationary_bootstrap_means", "ess_lag1",
])
def test_reused_vol_switch_machinery_byte_identical(name):
    """Refit ladder, embargo, scoring, state, estimand and inference are
    REUSED from the reviewed vol-switch runner — cite-and-reuse, not
    rewrite."""
    assert source_of(RUNNER, name) == source_of(VOL_SWITCH, name)


def test_reused_momentum_readers_byte_identical():
    """The momentum reader surface is REUSED from the reviewed tail_q90
    runner, which mirrors the production LiveReaders construction."""
    assert source_of(RUNNER, "MomReaders") == source_of(TAILQ90, "MomReaders")


def test_reused_names_are_not_silently_dropped():
    """A copied definition that is deleted from the runner would make the
    parametrized byte-identity test vanish rather than fail. Pin the count
    of reused vol-switch definitions the runner is expected to carry."""
    reused = [n for n in (
        "_sha256", "_assert", "build_refit_calendar", "refit_index_for_date",
        "latest_realized_label_pos", "ReadersLite", "assert_one_shot",
        "load_trainer_module", "load_served_artifact", "fit_booster",
        "score_frame", "realized_vol20", "on_state_fixed",
        "block_on_day_counts", "dgtw_adjust", "top_decile_spread", "nw_lag1",
        "stationary_bootstrap_means", "ess_lag1") if hasattr(rn, n)]
    assert len(reused) == 19


# --------------------------------------------------- the served z-sum contract
def test_zscore_leg_is_ddof0_over_finite_values():
    s = pd.Series([1.0, 2.0, 3.0, 4.0], index=list("abcd"))
    z = rn.zscore_leg(s)
    assert z.mean() == pytest.approx(0.0, abs=1e-12)
    assert float(np.std(z.to_numpy(), ddof=0)) == pytest.approx(1.0)
    assert rn.Z_DDOF == 0


def test_zscore_leg_ignores_nan_when_computing_moments():
    s = pd.Series([1.0, 2.0, 3.0, np.nan], index=list("abcd"))
    z = rn.zscore_leg(s)
    assert np.isnan(z["d"])
    finite = z.dropna().to_numpy()
    assert finite.mean() == pytest.approx(0.0, abs=1e-12)
    assert float(np.std(finite, ddof=0)) == pytest.approx(1.0)


def test_degenerate_leg_contributes_zero_like_the_served_scorer():
    """blend_scorer: a leg with n_finite < 2 or sd <= 0 contributes 0 and
    stamps degraded_reason — it does not poison the composite."""
    assert list(rn.zscore_leg(pd.Series([5.0, 5.0, 5.0]))) == [0.0, 0.0, 0.0]
    assert list(rn.zscore_leg(pd.Series([7.0]))) == [0.0]


def test_blend_is_an_unweighted_sum_of_leg_zscores():
    idx = list("abcde")
    legs = {"xgb": pd.Series([1.0, 2, 3, 4, 5], index=idx),
            "mom": pd.Series([5.0, 4, 3, 2, 1], index=idx),
            "clf": pd.Series([0.0, 1, 0, 1, 0], index=idx)}
    got = rn.blend_scores(legs, ("xgb", "mom", "clf"))
    want = (rn.zscore_leg(legs["xgb"]) + rn.zscore_leg(legs["mom"])
            + rn.zscore_leg(legs["clf"]))
    pd.testing.assert_series_equal(got, want)
    # two exactly-opposing legs cancel: no hidden weighting
    assert rn.blend_scores(legs, ("xgb", "mom")).abs().max() == pytest.approx(0.0, abs=1e-12)


def test_blend_nan_propagates_to_the_intersection():
    idx = list("abc")
    legs = {"xgb": pd.Series([1.0, 2.0, 3.0], index=idx),
            "mom": pd.Series([1.0, 2.0, np.nan], index=idx)}
    out = rn.blend_scores(legs, ("xgb", "mom"))
    assert np.isnan(out["c"]) and np.isfinite(out["a"])


def test_solo_arm_is_just_the_leg_zscore():
    s = pd.Series([3.0, 1.0, 2.0], index=list("abc"))
    pd.testing.assert_series_equal(
        rn.blend_scores({"xgb": s}, ("xgb",)), rn.zscore_leg(s))


def test_arm_wiring_matches_the_served_and_certified_constructions():
    assert rn.ARM_LEGS["A_prod"] == ("xgb", "mom")
    assert rn.ARM_LEGS["B_3leg"] == ("xgb", "mom", "clf")
    assert rn.ARM_LEGS["C_2leg_certified"] == ("xgb", "clf")
    assert rn.ARM_LEGS["D_solo_xgb"] == ("xgb",)
    assert rn.PRIMARY_CONTRAST == ("B_3leg", "A_prod")
    assert rn.CONTROL_CONTRAST == ("C_2leg_certified", "D_solo_xgb")


# ------------------------------------------------- the clf label construction
def test_top_decile_label_is_per_date_and_inclusive_at_the_threshold():
    """The frozen construction: 1{row's fwd_60d_excess is in its DATE's top
    decile}, threshold >= 0.9 on the per-date percentile rank pct = rank/n.
    Boundary behaviour is INCLUSIVE and pinned here rather than assumed: at
    n = 10 the positives are ranks 9 and 10 (pct 0.9 and 1.0), i.e. TWO
    names, not one. This is the construction model#76 certified and the
    deployed shadow artifact stamps; it is recorded, not corrected."""
    dates = ["2020-01-02"] * 10 + ["2020-01-03"] * 10
    lab = list(range(10)) + list(range(100, 110))
    df = pd.DataFrame({"date": pd.to_datetime(dates), rn.LABEL: lab})
    y = rn.top_decile_label(df)
    assert list(y.iloc[:10]) == [0.0] * 8 + [1.0, 1.0]
    assert list(y.iloc[10:]) == [0.0] * 8 + [1.0, 1.0]
    assert set(y.unique()) <= {0.0, 1.0}
    assert rn.CLF_TOP_DECILE == 0.9


def test_top_decile_label_positive_rate_tracks_the_decile_at_scale():
    """At a realistic cross-section width the positive rate is ~10%."""
    n = 200
    df = pd.DataFrame({"date": pd.to_datetime(["2020-01-02"] * n),
                       rn.LABEL: np.arange(n, dtype=float)})
    assert rn.top_decile_label(df).mean() == pytest.approx(0.105, abs=0.01)


def test_top_decile_label_is_not_a_pooled_threshold():
    """A pooled (cross-date) threshold would put every winner on the
    high-label date — the per-date groupby is the whole point."""
    dates = ["2020-01-02"] * 10 + ["2020-01-03"] * 10
    df = pd.DataFrame({"date": pd.to_datetime(dates),
                       rn.LABEL: list(range(10)) + list(range(100, 110))})
    y = rn.top_decile_label(df)
    assert y.iloc[:10].sum() == 2 and y.iloc[10:].sum() == 2


# --------------------------------------------------------- block aggregation
def _weekly(n_blocks=3, per_block=4, value=1.0, on=True):
    rows = []
    for b in range(n_blocks):
        for j in range(per_block):
            rows.append({"block": b, "diff_primary": value * (b + 1),
                         "on_fixed": on or (j % 2 == 0)})
    return pd.DataFrame(rows)


def test_block_series_means_per_block_and_counts_dates():
    w = _weekly()
    vals, rows = rn.block_series(w, "diff_primary", 3)
    assert list(vals) == [1.0, 2.0, 3.0]
    assert [r["n_dates"] for r in rows] == [4, 4, 4]


def test_block_series_mask_restricts_contributing_dates_and_drops_empty_blocks():
    w = _weekly(on=False)          # only even j are ON
    mask = w["on_fixed"].astype(bool)
    vals, rows = rn.block_series(w, "diff_primary", 3, mask=mask)
    assert list(vals) == [1.0, 2.0, 3.0]
    assert [r["n_dates"] for r in rows] == [2, 2, 2]
    empty, erows = rn.block_series(w, "diff_primary", 3,
                                   mask=pd.Series([False] * len(w)))
    assert len(empty) == 0
    assert all(r["value"] is None and r["n_dates"] == 0 for r in erows)


# ------------------------------------------------------- the frozen verdict
def _res(**kw):
    base = {"measurable": True, "mean": 0.1, "disagreement": False,
            "both_legs_pass": True, "n_blocks": 28, "ess": 20.0}
    base.update(kw)
    return base


def test_verdict_beats_only_when_both_legs_clear_the_inherited_bar():
    assert rn.verdict_of(_res())[0] == "BEATS"
    assert rn.verdict_of(_res(both_legs_pass=False))[0] == "NOT DISTINGUISHABLE"


def test_verdict_split_between_inference_legs_is_not_a_pass():
    v, why = rn.verdict_of(_res(disagreement=True, both_legs_pass=False))
    assert v == "NOT DISTINGUISHABLE" and "SPLIT" in why


def test_verdict_worse_on_a_nonpositive_point_estimate():
    assert rn.verdict_of(_res(mean=0.0, both_legs_pass=False))[0] == "WORSE"
    assert rn.verdict_of(_res(mean=-0.2, both_legs_pass=False))[0] == "WORSE"


def test_guards_precede_the_verdict_and_fail_closed():
    """n_blocks / ESS floors are checked FIRST: a would-be BEATS on too few
    or too dependent blocks is UNMEASURABLE, never a pass."""
    assert rn.verdict_of(_res(measurable=False))[0] == "UNMEASURABLE"
    assert rn.MIN_BLOCKS == 15 and rn.MIN_ESS == 6.0


def test_infer_reports_guards_and_both_inference_legs():
    rng = np.random.default_rng(7)
    x = rng.normal(0.5, 1.0, 28)
    r = rn.infer(x)
    assert r["n_blocks"] == 28
    assert r["mean"] == pytest.approx(float(x.mean()))
    assert set(("nw", "bootstrap", "rho1", "ess", "measurable")) <= set(r)
    assert r["bootstrap"]["n_resamples"] == rn.BOOT_RESAMPLES
    assert r["bootstrap"]["seed"] == rn.BOOT_SEED
    assert r["disagreement"] == (r["nw"]["passes"] != r["bootstrap"]["passes"])


def test_infer_is_deterministic_given_the_pinned_seed():
    x = np.linspace(-0.2, 0.9, 28)
    assert rn.infer(x)["bootstrap"]["q05"] == rn.infer(x)["bootstrap"]["q05"]


def test_a_zero_difference_series_is_never_a_pass():
    """The paired B-A series is identically zero when the clf leg changes no
    ranking; the bar must not manufacture a win from noiseless zeros."""
    x = np.full(28, 1e-18)
    r = rn.infer(x)
    assert rn.verdict_of(r)[0] in {"UNMEASURABLE", "NOT DISTINGUISHABLE", "WORSE"}


# ------------------------------------------------------------- one-shot guard
def test_one_shot_guard_refuses_when_any_output_exists(tmp_path):
    absent = tmp_path / "results.json"
    rn.assert_one_shot(outputs=[absent])
    absent.write_text("{}")
    with pytest.raises(AssertionError, match="one-shot marker"):
        rn.assert_one_shot(outputs=[absent])
    with pytest.raises(AssertionError, match="one-shot marker"):
        rn.assert_one_shot(outputs=[tmp_path / "series.csv", absent])


# ---------------------------------------------------------- frozen constants
def test_frozen_corpus_and_recipe_constants():
    assert rn.PRIMARY_START == "2017-01-03" and rn.PRIMARY_END == "2023-09-29"
    assert rn.BLOCK_TD == 60 and rn.SAMPLE_STEP == 5
    assert rn.EMBARGO_TDAYS == 60 and rn.LABEL_HORIZON_TDAYS == 60
    assert rn.EXPECTED_REFITS == 30
    assert rn.REFIT_FIRST_QUARTER == (2016, 2) and rn.REFIT_LAST_QUARTER == (2023, 3)
    assert rn.FROZEN_CONFIG_FINGERPRINT == "sha256:f8fb2259b2bf1537"
    assert rn.PRODUCTION_OBJECTIVE == "rank:pairwise"
    assert rn.CLF_OBJECTIVE == "binary:logistic"
    assert rn.FROZEN_MOMENTUM_FINGERPRINT == "momentum-v0-fd65161a20b29314"
    assert rn.FROZEN_PRIMARY_GEOMETRY == {
        "corpus_td": 1697, "on_days_fixed": 821,
        "complete_blocks": 28, "weekly_grid_n": 340}
