"""Synthetic tests for the frozen vol-switch confirmatory runner (prereg orch#1001).

The runner ships REVIEWED but UN-RUN (freeze-then-review-then-run, prereg §6),
so these tests exercise its pure frozen logic only: the vol-state
classification (incl. the 0.135 boundary), block eligibility, the DGTW cell
adjustment, the P1/P2/guard verdict logic (each condition flips the mapped
verdict), and the embargo boundary. No market data is read and no xgboost
training happens.

The refit/embargo/scoring machinery is REUSED from the reviewed tail_q90
runner (2026-08-18-gi-tailq90-derivation.py, #996/#999 lineage) by verbatim
copy; ``test_reused_machinery_byte_identical`` enforces byte-identity so the
reuse cannot silently drift into a rewrite.

The one-shot guard is tested as a MECHANISM on temp paths only (the tail_q90
lesson: a "no outputs committed" repo-state test necessarily breaks at the
one authorized run).
"""
import ast
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "doc" / "research" / "data" / "2026-08-18-vol-switch-derivation.py"
TAILQ90 = ROOT / "doc" / "research" / "data" / "2026-08-18-gi-tailq90-derivation.py"

_spec = importlib.util.spec_from_file_location("vol_switch_runner", RUNNER)
rn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rn)


# ------------------------------------------------------ vol-state (prereg §2)
def test_realized_vol20_hand_computed():
    """21 closes -> 20 returns of +1%/-1% alternating in halves; sample std
    (ddof=1) of ten +0.01 and ten -0.01 is 0.01*sqrt(20/19); annualized by
    sqrt(252). The last rolling window is exactly those 20 returns."""
    rets = [0.01] * 10 + [-0.01] * 10
    closes = [100.0]
    for r in rets:
        closes.append(closes[-1] * (1 + r))
    s = pd.Series(closes, index=pd.bdate_range("2020-01-01", periods=21))
    vol = rn.realized_vol20(s)
    expected = 0.01 * np.sqrt(20 / 19) * np.sqrt(252)
    assert vol.iloc[:-1].isna().all() is np.True_ or vol.iloc[:20].isna().all()
    assert vol.iloc[-1] == pytest.approx(expected, rel=1e-9)


def test_fixed_state_boundary_0135_is_off():
    """Prereg §2: ON <=> vol20 > 13.5% STRICT — exactly 0.135 is OFF; NaN
    (warmup) is OFF fail-closed."""
    vol20 = pd.Series([0.1349, 0.135, 0.1351, np.nan, 0.20],
                      index=pd.bdate_range("2020-01-01", periods=5))
    on = rn.on_state_fixed(vol20)
    assert list(on) == [False, False, True, False, True]
    assert rn.FIXED_ON_THRESHOLD == 0.135


def test_expanding_state_warmup_is_off_fail_closed():
    """The expanding-tercile threshold first exists at the 504th vol20
    observation (CORRECTIONS #4); every earlier day is OFF. On a strictly
    increasing series every post-warmup day is ON (each value exceeds the
    66.7th percentile of its own history)."""
    n = 510
    vol20 = pd.Series(np.linspace(0.05, 0.60, n),
                      index=pd.bdate_range("2016-01-04", periods=n))
    on = rn.on_state_expanding(vol20)
    assert not on.iloc[:rn.EXPANDING_WARMUP_OBS - 1].any()
    assert on.iloc[rn.EXPANDING_WARMUP_OBS - 1:].all()
    assert int(on.sum()) == n - (rn.EXPANDING_WARMUP_OBS - 1)
    thr = rn.expanding_threshold(vol20)
    assert thr.dropna().index[0] == vol20.index[rn.EXPANDING_WARMUP_OBS - 1]


# -------------------------------------------------- block eligibility (§3)
def test_block_on_day_counts_and_eligibility():
    """Three 60-td blocks with 20 / 14 / 15 ON days: the >=15 floor admits
    blocks 0 and 2 and rejects block 1 (14 is below, 15 is exactly at)."""
    flags = ([True] * 20 + [False] * 40          # block 0: 20 ON
             + [True] * 14 + [False] * 46        # block 1: 14 ON
             + [True] * 15 + [False] * 45)       # block 2: 15 ON
    on = pd.Series(flags, index=pd.bdate_range("2017-01-03", periods=180))
    counts = rn.block_on_day_counts(on, 3)
    assert counts == [20, 14, 15]
    eligible = [c >= rn.ELIGIBLE_MIN_ON_DAYS for c in counts]
    assert eligible == [True, False, True]


def test_block_on_day_counts_ignores_trailing_remainder():
    on = pd.Series([True] * 130, index=pd.bdate_range("2017-01-03", periods=130))
    assert rn.block_on_day_counts(on, 2) == [60, 60]  # 10-day remainder dropped


def test_frozen_geometry_assert_passes_on_frozen_and_fails_on_drift():
    good = dict(rn.FROZEN_PRIMARY_GEOMETRY)
    rn.assert_frozen_primary_geometry(good)          # exact match -> passes
    for key in good:
        bad = dict(good)
        bad[key] = 999 if not isinstance(bad[key], str) else "1999-01-01"
        with pytest.raises(AssertionError, match="frozen geometry mismatch"):
            rn.assert_frozen_primary_geometry(bad)
    with pytest.raises(AssertionError, match="missing"):
        rn.assert_frozen_primary_geometry(
            {k: v for k, v in good.items() if k != "corpus_td"})


# ------------------------------------------------------------ DGTW estimand
def _dgtw_fixture():
    """9 names in 3 perfectly aligned cells (all three characteristics share
    one ordering), 3 names per cell — small enough to hand-compute."""
    chars = np.arange(1.0, 10.0)
    return pd.DataFrame({
        "STD60": chars, "ROC60": chars, "BETA60": chars,
        "label": [1.0, 2.0, 3.0, 10.0, 20.0, 30.0, -1.0, -2.0, -3.0],
        "score": np.arange(9.0, 0.0, -1.0),
    }, index=[f"T{i}" for i in range(9)])


def test_dgtw_self_excluded_cell_mean_hand_computed():
    d = rn.dgtw_adjust(_dgtw_fixture(), min_cell=3)
    assert list(d["cell"].values) == [0, 0, 0, 13, 13, 13, 26, 26, 26]
    assert d["adjusted"].all()
    # name T0: cell {1,2,3}, self-excluded bench = (2+3)/2 -> dgtw = 1 - 2.5
    assert d.loc["T0", "dgtw"] == pytest.approx(-1.5)
    assert d.loc["T1", "dgtw"] == pytest.approx(2.0 - 2.0)
    assert d.loc["T4", "dgtw"] == pytest.approx(20.0 - 20.0)
    # self-exclusion, not the full-cell mean (which would give 1 - 2 = -1)
    assert d.loc["T0", "dgtw"] != pytest.approx(-1.0)


def test_dgtw_small_cell_is_flagged_unadjusted():
    """Prereg §3: a cell below the floor keeps the RAW label, flagged."""
    d = rn.dgtw_adjust(_dgtw_fixture(), min_cell=4)   # every cell has 3 < 4
    assert not d["adjusted"].any()
    assert (d["dgtw"] == d["label"]).all()
    assert rn.DGTW_MIN_CELL == 15                     # the frozen default


def test_dgtw_drops_rows_missing_characteristics():
    df = _dgtw_fixture()
    df.loc["T3", "BETA60"] = np.nan
    d = rn.dgtw_adjust(df, min_cell=1)
    assert "T3" not in d.index and len(d) == 8


def test_top_decile_spread_hand_computed():
    df = pd.DataFrame({
        "score": np.arange(20.0, 0.0, -1.0),
        "val": [1.0] * 2 + [0.0] * 18,               # top-2 by score carry 1.0
    }, index=[f"N{i}" for i in range(20)])
    spread, n, ndec = rn.top_decile_spread(df, "val")
    assert (n, ndec) == (20, 2)
    assert spread == pytest.approx(1.0 - 2.0 / 20.0)


def test_top_decile_rounding_is_round_half_even():
    """N = int(round(n/10)) — the formation construction; 25 -> 2 (banker's
    rounding), 26 -> 3. Pinned so the ONE run cannot silently re-interpret."""
    df = pd.DataFrame({"score": np.arange(25.0), "val": np.zeros(25)})
    assert rn.top_decile_spread(df, "val")[2] == 2
    df26 = pd.DataFrame({"score": np.arange(26.0), "val": np.zeros(26)})
    assert rn.top_decile_spread(df26, "val")[2] == 3


# ------------------------------------------------------- block aggregation
def _weekly_fixture():
    return pd.DataFrame({
        "block": [0, 0, 0, 1, 1, 1],
        "on_fixed": [True, True, False, False, False, False],
        "spread_dgtw": [0.4, 0.2, -0.1, 0.5, 0.3, 0.1],
        "spread_dgtw_w50": [0.3, 0.1, -0.1, 0.5, 0.3, 0.1],
    })


def test_aggregate_blocks_on_off_means_hand_computed():
    out = rn.aggregate_blocks(_weekly_fixture(), "on_fixed", [20, 10])
    b0 = out[out["block"] == 0].iloc[0]
    assert b0["on_mean"] == pytest.approx(0.3)       # mean(0.4, 0.2)
    assert b0["off_mean"] == pytest.approx(-0.1)
    assert b0["on_minus_off"] == pytest.approx(0.4)
    assert b0["on_mean_w50"] == pytest.approx(0.2)
    assert bool(b0["eligible"]) and not bool(b0["dominant"])
    b1 = out[out["block"] == 1].iloc[0]
    assert np.isnan(b1["on_mean"]) and np.isnan(b1["on_minus_off"])
    assert b1["off_mean"] == pytest.approx(0.3)
    assert not bool(b1["eligible"])                  # 10 ON days < 15


def test_aggregate_blocks_eligibility_comes_from_day_counts_not_weekly():
    """Eligibility is a DAY-count property (>=15 of 60), independent of how
    many weekly cross-sections happen to be ON."""
    out = rn.aggregate_blocks(_weekly_fixture(), "on_fixed", [15, 45])
    assert bool(out.iloc[0]["eligible"]) and bool(out.iloc[1]["eligible"])
    out2 = rn.aggregate_blocks(_weekly_fixture(), "on_fixed", [14, 46])
    assert not bool(out2.iloc[0]["eligible"])
    assert bool(out2.iloc[1]["dominant"])            # 46 >= 45


# ------------------------------------------------------------ P1 inference
def test_nw_lag1_hand_computed():
    """x = [1,2,3]: mean 2; gamma0 = 2/3, gamma1 = 0 -> var(mean) = 2/9,
    se = sqrt(2)/3, t = 3*sqrt(2) ~ 4.2426, df = 2."""
    r = rn.nw_lag1(np.array([1.0, 2.0, 3.0]))
    assert r["mean"] == pytest.approx(2.0)
    assert r["se"] == pytest.approx(np.sqrt(2.0) / 3.0)
    assert r["t"] == pytest.approx(3.0 * np.sqrt(2.0))
    assert r["df"] == 2
    assert r["t_crit_one_sided_95"] == pytest.approx(2.9200, abs=1e-3)
    assert r["passes"] is (r["ci_lower_one_sided_95"] > 0)
    assert r["passes"]                               # 2 - 2.92*0.4714 > 0


def test_nw_lag1_zero_mean_fails():
    r = rn.nw_lag1(np.array([1.0, -1.0, 1.0, -1.0, 1.0, -1.0]))
    assert r["mean"] == pytest.approx(0.0)
    assert not r["passes"]


def test_stationary_bootstrap_deterministic_and_exact_on_constant():
    x = np.full(10, 0.5)
    m1 = rn.stationary_bootstrap_means(x)
    m2 = rn.stationary_bootstrap_means(x)
    assert len(m1) == rn.BOOT_RESAMPLES == 10_000
    assert np.array_equal(m1, m2)                    # fixed seed 0
    assert np.all(m1 == 0.5)                         # resamples of a constant


def test_stationary_bootstrap_q05_positive_for_solid_series():
    rng = np.random.default_rng(3)
    x = 1.0 + 0.05 * rng.standard_normal(19)
    q05 = float(np.percentile(rn.stationary_bootstrap_means(x), 5))
    assert q05 > 0


def test_ess_lag1_hand_computed():
    """x = [1,2,3,4]: gamma0 = 1.25, gamma1 = 0.3125 -> rho1 = 0.25,
    ESS = 4 * 0.75 / 1.25 = 2.4."""
    rho1, ess = rn.ess_lag1(np.array([1.0, 2.0, 3.0, 4.0]))
    assert rho1 == pytest.approx(0.25)
    assert ess == pytest.approx(2.4)


def test_ess_lag1_negative_rho_clips_to_full_n():
    """rho1 is clipped below at 0 (canon §1.2) — anti-correlation may not
    INFLATE the effective sample."""
    rho1, ess = rn.ess_lag1(np.array([1.0, -1.0, 1.0, -1.0, 1.0, -1.0]))
    assert rho1 < 0
    assert ess == pytest.approx(6.0)                 # N, not more


# ---------------------------------------------------- P1/P2 decision logic
def test_p1_conjunction_each_condition_flips():
    assert rn.p1_conjunction(True, True, True) == (True, False)
    assert rn.p1_conjunction(False, True, True) == (False, True)   # DISAGREEMENT
    assert rn.p1_conjunction(True, False, True) == (False, True)   # DISAGREEMENT
    assert rn.p1_conjunction(True, True, False) == (False, False)  # anti-lottery
    assert rn.p1_conjunction(False, False, True) == (False, False)


def test_p1_decision_passes_on_solid_positive_series():
    rng = np.random.default_rng(11)
    x = 0.8 + 0.05 * rng.standard_normal(19)
    r = rn.p1_decision(x, x)
    assert r["nw"]["passes"] and r["bootstrap"]["passes"]
    assert not r["disagreement"]
    assert r["p1_pass"]


def test_p1_decision_winsorized_guard_flips_the_pass():
    """A raw pass with a NEGATIVE winsorized ON-mean is a lottery pass and
    FAILS (prereg §5 anti-lottery guard)."""
    rng = np.random.default_rng(11)
    x = 0.8 + 0.05 * rng.standard_normal(19)
    r = rn.p1_decision(x, x - 1.0)                   # winsorized mean < 0
    assert not r["winsorized_guard_passes"]
    assert not r["p1_pass"]
    # boundary: winsorized mean exactly 0 is >= 0 -> guard holds
    r0 = rn.p1_decision(x, np.zeros(19))
    assert r0["winsorized_guard_passes"] and r0["p1_pass"]


def test_p1_decision_fails_on_negative_series_without_disagreement():
    rng = np.random.default_rng(12)
    x = -0.5 + 0.05 * rng.standard_normal(19)
    r = rn.p1_decision(x, x)
    assert not r["p1_pass"] and not r["disagreement"]


def _p2_blocks(diffs, on_days=30):
    n = len(diffs)
    return pd.DataFrame({
        "block": range(n),
        "on_days": [on_days] * n,
        "off_days": [60 - on_days] * n,
        "n_on_weekly": [3] * n,
        "n_off_weekly": [3] * n,
        "on_minus_off": diffs,
    })


def test_p2_passes_on_consistent_positive_differences():
    r = rn.p2_decision(_p2_blocks([0.2, 0.3, 0.25, 0.15, 0.1]))
    assert r["n_blocks"] == 5
    assert r["mean_diff"] == pytest.approx(0.2)
    assert r["block_t"] >= rn.P2_BLOCK_T_MIN
    assert r["passes"]


def test_p2_fails_on_negative_differences():
    assert not rn.p2_decision(_p2_blocks([-0.2, -0.3, -0.25, -0.15, -0.1]))["passes"]


def test_p2_fails_below_block_t_floor():
    r = rn.p2_decision(_p2_blocks([0.5, -0.45, 0.48, -0.4, 0.02]))
    assert r["mean_diff"] > 0
    assert r["block_t"] < rn.P2_BLOCK_T_MIN
    assert not r["passes"]


def test_p2_excludes_blocks_without_15_days_in_each_state():
    """Interpretation ledger (i): a block enters P2 only with >=15 ON days
    AND >=15 OFF days (the DEFINITIONS.md cell rule, applied to both cells).
    An ON-dominant block (50 ON / 10 OFF) is excluded."""
    blocks = pd.concat([
        _p2_blocks([0.2, 0.3, 0.25], on_days=30),
        _p2_blocks([-9.9], on_days=50),              # off_days 10 < 15
    ], ignore_index=True)
    blocks["block"] = range(len(blocks))
    r = rn.p2_decision(blocks)
    assert r["n_blocks"] == 3
    assert 3 not in r["contributing_blocks"]
    assert r["passes"]                               # the outlier never enters


def test_p2_fails_closed_below_two_blocks():
    r = rn.p2_decision(_p2_blocks([0.4]))
    assert not r["passes"] and r["block_t"] is None
    assert "fewer than 2" in r["reason"]


# ----------------------------------------------------- verdict mapping (§5)
def test_verdict_mapping_and_consequences():
    v, c = rn.final_verdict(True, True, True, True)
    assert v == "CONFIRMED" and "design PR" in c
    v, c = rn.final_verdict(True, True, True, False)
    assert v == "PARTIAL" and ">=40 live shadow sessions" in c
    v, c = rn.final_verdict(True, True, False, True)   # P1 fails, P2 cannot rescue
    assert v == "REFUTED" and "vol-switch line closes" in c
    v, c = rn.final_verdict(True, True, False, False)
    assert v == "REFUTED"


def test_verdict_guards_take_precedence_over_p1_p2():
    v, c = rn.final_verdict(True, False, True, True)
    assert v == "UNMEASURABLE" and "fail-closed" in c
    v, c = rn.final_verdict(False, True, True, True)
    assert v == "INVALID_INSTRUMENT" and "positive control failed" in c
    # instrument sanity outranks the measurability guard
    assert rn.final_verdict(False, False, True, True)[0] == "INVALID_INSTRUMENT"
    for verdict, consequence in rn.CONSEQUENCE.items():
        assert consequence, f"empty consequence string for {verdict}"


# --------------------------------------------- embargo boundary (V6, reused)
def test_embargo_boundary_c_plus_60_exactly_usable():
    """C at position 100: the first admissible scoring position is 160
    (C + 60 trading days <= d), NOT 159."""
    assert rn.refit_index_for_date([100], 160) == 0
    assert rn.refit_index_for_date([100], 159) is None


def test_embargo_selects_newest_admissible_refit():
    positions = [100, 160]
    assert rn.refit_index_for_date(positions, 219) == 0   # 160+60=220 > 219
    assert rn.refit_index_for_date(positions, 220) == 1   # boundary flips
    assert rn.refit_index_for_date([], 1000) is None


def test_realized_label_boundary_mirrors_embargo():
    assert rn.latest_realized_label_pos(500) == 440
    assert 440 + rn.LABEL_HORIZON_TDAYS <= 500
    assert 441 + rn.LABEL_HORIZON_TDAYS > 500


# ------------------------------------------------------ refit ladder (V5)
def weekday_calendar(start="2016-01-04", end="2026-06-30") -> pd.DatetimeIndex:
    return pd.DatetimeIndex(pd.bdate_range(start, end))


def test_refit_calendar_has_exactly_39_cutoffs_2016q2_to_2025q4():
    cutoffs = rn.build_refit_calendar(weekday_calendar())
    assert len(cutoffs) == 39
    assert rn.EXPECTED_REFITS == 39
    # Last weekday of 2016-Q2 is Thursday 2016-06-30; of 2025-Q4, 2025-12-31.
    assert str(cutoffs[0].date()) == "2016-06-30"
    assert str(cutoffs[-1].date()) == "2025-12-31"
    assert all(a < b for a, b in zip(cutoffs, cutoffs[1:]))


def test_refit_calendar_fails_closed_on_truncated_calendar():
    with pytest.raises(AssertionError, match="FROZEN-GUARD"):
        rn.build_refit_calendar(weekday_calendar(end="2025-06-30"))


# ------------------------------------------------------------- one-shot (V1)
def test_one_shot_guard_fires_when_an_output_already_exists(tmp_path):
    """V1 is a RUNTIME guard tested on temp paths — the repo-state variant
    would necessarily break at the ONE authorized run (the tail_q90 lesson)."""
    absent = tmp_path / "results.json"
    rn.assert_one_shot(outputs=[absent])             # nothing written -> passes
    absent.write_text("{}")
    with pytest.raises(AssertionError, match="one-shot marker"):
        rn.assert_one_shot(outputs=[absent])
    other = tmp_path / "series.csv"
    with pytest.raises(AssertionError, match="one-shot marker"):
        rn.assert_one_shot(outputs=[other, absent])


# --------------------------------------------- reused machinery byte-identity
@pytest.mark.parametrize("name", [
    "_sha256", "_assert", "build_refit_calendar", "refit_index_for_date",
    "latest_realized_label_pos", "ReadersLite", "assert_one_shot",
    "assert_runner_matches_main", "load_trainer_module",
    "load_served_artifact", "fit_booster", "score_frame",
])
def test_reused_machinery_byte_identical(name):
    """The refit/embargo/scoring machinery is REUSED from the reviewed
    tail_q90 runner (#996/#999 lineage) — byte-identity enforced so the reuse
    cannot silently drift into a rewrite (prereg §4: cite-and-reuse)."""
    def source_of(path: Path, target: str) -> str:
        src = path.read_text()
        for node in ast.parse(src).body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) \
                    and node.name == target:
                return ast.get_source_segment(src, node)
        raise AssertionError(f"{target} not found in {path.name}")

    assert source_of(RUNNER, name) == source_of(TAILQ90, name)


# ------------------------------------------------------- frozen-table pins
def test_frozen_constants_match_the_merged_prereg():
    assert rn.PRIMARY_START == "2017-01-03"
    assert rn.PRIMARY_END == "2023-09-29"
    assert rn.SECONDARY_END == "2026-03-31"
    assert rn.SAMPLE_STEP == 5
    assert rn.BLOCK_TD == 60
    assert rn.ELIGIBLE_MIN_ON_DAYS == 15
    assert rn.DOMINANT_MIN_ON_DAYS == 45
    assert rn.VOL_WINDOW == 20
    assert rn.FIXED_ON_THRESHOLD == 0.135
    assert rn.EXPANDING_WARMUP_OBS == 504
    assert rn.EXPANDING_QUANTILE == pytest.approx(2 / 3)
    assert rn.FROZEN_CONFIG_FINGERPRINT == "sha256:f8fb2259b2bf1537"
    assert rn.PRODUCTION_OBJECTIVE == "rank:pairwise"
    assert rn.N_FEATURES == 172
    assert rn.LABEL == "fwd_60d_excess"
    assert rn.LABEL_HORIZON_TDAYS == 60
    assert rn.EMBARGO_TDAYS == 60
    assert rn.EXPECTED_BEST_ITER == 100
    assert rn.TRAIN_DATA_START == "2016-01-04"
    assert rn.REFIT_FIRST_QUARTER == (2016, 2)
    assert rn.REFIT_LAST_QUARTER == (2025, 4)
    assert rn.PRIMARY_LAST_QUARTER == (2023, 3)
    assert rn.EXPECTED_PRIMARY_REFITS == 30
    assert rn.PANEL_N_TICKERS == 292
    assert rn.DGTW_CHARS == ("STD60", "ROC60", "BETA60")
    assert rn.DGTW_MIN_CELL == 15
    assert rn.TOPDEC_DIV == 10
    assert rn.WINSOR_CLIP == 0.5
    assert rn.NW_LAG == 1
    assert rn.ONE_SIDED_ALPHA == 0.05
    assert rn.BOOT_RESAMPLES == 10_000
    assert rn.BOOT_EXPECTED_BLOCK == 2.0
    assert rn.BOOT_SEED == 0
    assert rn.P2_BLOCK_T_MIN == 1.0
    assert rn.MIN_ON_ELIGIBLE_BLOCKS == 15
    assert rn.MIN_ESS == 6.0
    assert rn.MIN_NAMES_PER_DATE == 100


def test_frozen_geometry_table_matches_the_prereg_corrections():
    """Prereg §2/§3 + CORRECTIONS #1/#3/#4: 1,697 td; 821/808 ON; 28 blocks
    (NOT the first draft's 29); 19/19 eligible, 18 under BOTH (NOT 19); 8/8
    dominant; expanding threshold first defined 2018-01-31."""
    g = rn.FROZEN_PRIMARY_GEOMETRY
    assert g["corpus_td"] == 1697
    assert g["on_days_fixed"] == 821
    assert g["on_days_expanding"] == 808
    assert g["complete_blocks"] == 28
    assert g["eligible_fixed"] == 19
    assert g["eligible_expanding"] == 19
    assert g["eligible_both"] == 18
    assert g["dominant_fixed"] == 8
    assert g["dominant_expanding"] == 8
    assert g["expanding_threshold_first"] == "2018-01-31"
    assert g["weekly_grid_n"] == 340
