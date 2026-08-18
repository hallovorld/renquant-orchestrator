"""Synthetic tests for the frozen tail_q90_60d screen runner (spec orch#994).

The runner ships REVIEWED but UN-RUN (freeze-then-review-then-run, spec §6),
so these tests exercise its pure frozen logic only: the refit calendar, the
embargo/realized-label boundaries, the single-delta params construction, the
triage rule, and the G7-class paired machinery. No market data is read, no
xgboost training happens, and no runner outputs may exist on this branch.

The paired-cross-section / block-t / placebo machinery is REUSED from the
merged corrected runner (2026-08-17-gi-moe-screen-derivation.py, the #990
pairing correction) by verbatim copy; ``test_reused_machinery_byte_identical``
enforces byte-identity so the reuse cannot silently drift into a rewrite.
"""
import ast
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "doc" / "research" / "data" / "2026-08-18-gi-tailq90-derivation.py"
MOE = ROOT / "doc" / "research" / "data" / "2026-08-17-gi-moe-screen-derivation.py"

_spec = importlib.util.spec_from_file_location("tailq90_runner", RUNNER)
rn = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rn)


def weekday_calendar(start="2016-01-04", end="2026-06-30") -> pd.DatetimeIndex:
    """Synthetic trading calendar: all weekdays (no holiday table needed —
    the tested properties are calendar-shape properties)."""
    return pd.DatetimeIndex(pd.bdate_range(start, end))


# ---------------------------------------------------------- refit calendar
def test_refit_calendar_has_exactly_31_cutoffs():
    cal = weekday_calendar()
    cutoffs = rn.build_refit_calendar(cal)
    assert len(cutoffs) == 31
    assert rn.EXPECTED_REFITS == 31


def test_refit_calendar_spans_2018q2_to_2025q4():
    cutoffs = rn.build_refit_calendar(weekday_calendar())
    # Last weekday of 2018-Q2 is Friday 2018-06-29 (the 30th is a Saturday);
    # last weekday of 2025-Q4 is Wednesday 2025-12-31.
    assert str(cutoffs[0].date()) == "2018-06-29"
    assert str(cutoffs[-1].date()) == "2025-12-31"


def test_refit_calendar_cutoffs_are_quarter_end_trading_days():
    cal = weekday_calendar()
    cutoffs = rn.build_refit_calendar(cal)
    assert all(c in cal for c in cutoffs)
    assert all(a < b for a, b in zip(cutoffs, cutoffs[1:]))
    for c in cutoffs:
        q_end = c + pd.offsets.QuarterEnd(0)
        # Independent re-derivation: no trading day of the same quarter may
        # come after the chosen cutoff.
        later_same_quarter = cal[(cal > c) & (cal <= q_end)]
        assert len(later_same_quarter) == 0, f"{c} is not the last trading day"


def test_refit_calendar_fails_closed_on_truncated_calendar():
    with pytest.raises(AssertionError, match="FROZEN-GUARD"):
        rn.build_refit_calendar(weekday_calendar(end="2025-06-30"))


# ------------------------------------------------- embargo / refit selection
def test_embargo_boundary_c_plus_60_exactly_usable():
    # C at position 100: the first admissible scoring position is 160
    # (C + 60 trading days <= d), NOT 159.
    assert rn.refit_index_for_date([100], 160) == 0
    assert rn.refit_index_for_date([100], 159) is None


def test_embargo_selects_newest_admissible_refit():
    positions = [100, 160]
    assert rn.refit_index_for_date(positions, 219) == 0   # 160+60=220 > 219
    assert rn.refit_index_for_date(positions, 220) == 1   # boundary flips
    assert rn.refit_index_for_date(positions, 500) == 1


def test_embargo_none_before_first_refit_matures():
    assert rn.refit_index_for_date([100, 160], 99) is None
    assert rn.refit_index_for_date([], 1000) is None


def test_realized_label_boundary_mirrors_embargo():
    # A row at position t is trainable at cutoff position c iff t + 60 <= c.
    assert rn.latest_realized_label_pos(500) == 440
    # Row exactly at the boundary is usable; one later is not.
    assert 440 + rn.LABEL_HORIZON_TDAYS <= 500
    assert 441 + rn.LABEL_HORIZON_TDAYS > 500


# ------------------------------------------------------- single-delta params
ARTIFACT_PARAMS_FIXTURE = {
    "objective": "rank:pairwise", "eta": 0.05, "max_depth": 5,
    "min_child_weight": 50, "subsample": 0.7, "colsample_bytree": 0.7,
    "verbosity": 0, "seed": 42,
}


def test_single_delta_params_changes_objective_only():
    out = rn.single_delta_params(dict(ARTIFACT_PARAMS_FIXTURE))
    assert out["objective"] == "reg:quantileerror"
    assert out["quantile_alpha"] == 0.90
    for k, v in ARTIFACT_PARAMS_FIXTURE.items():
        if k != "objective":
            assert out[k] == v, f"non-objective param {k} drifted"
    assert set(out) == set(ARTIFACT_PARAMS_FIXTURE) | {"quantile_alpha"}


def test_single_delta_params_does_not_mutate_input():
    src = dict(ARTIFACT_PARAMS_FIXTURE)
    rn.single_delta_params(src)
    assert src == ARTIFACT_PARAMS_FIXTURE


def test_single_delta_params_rejects_wrong_base_objective():
    bad = dict(ARTIFACT_PARAMS_FIXTURE, objective="reg:quantileerror")
    with pytest.raises(AssertionError, match="rank:pairwise"):
        rn.single_delta_params(bad)


def test_single_delta_params_rejects_preexisting_quantile_alpha():
    bad = dict(ARTIFACT_PARAMS_FIXTURE, quantile_alpha=0.5)
    with pytest.raises(AssertionError, match="quantile_alpha"):
        rn.single_delta_params(bad)


def test_single_delta_params_rejects_missing_seed():
    bad = {k: v for k, v in ARTIFACT_PARAMS_FIXTURE.items() if k != "seed"}
    with pytest.raises(AssertionError, match="seed"):
        rn.single_delta_params(bad)


def test_single_delta_params_rejects_empty():
    with pytest.raises(AssertionError):
        rn.single_delta_params({})


# ------------------------------------------------------------- triage rule
PASSING = dict(delta=0.01, block_t=1.5, pos_frac=0.6,
               n_blocks_with_data=29, min_blocks=15)


def _verdict(**overrides):
    kw = dict(PASSING, **overrides)
    return rn.triage_verdict(kw["delta"], kw["block_t"], kw["pos_frac"],
                             kw["n_blocks_with_data"], kw["min_blocks"])


def test_verdict_all_criteria_met_not_flagged():
    verdict, reason = _verdict()
    assert verdict == "NOT FLAGGED"
    assert reason == "all three criteria met"


def test_verdict_flips_on_nonpositive_delta():
    assert _verdict(delta=-0.001)[0] == "FLAGGED"
    assert _verdict(delta=0.0)[0] == "FLAGGED"          # strictly > 0


def test_verdict_flips_on_low_block_t():
    assert _verdict(block_t=0.999)[0] == "FLAGGED"
    assert _verdict(block_t=1.0)[0] == "NOT FLAGGED"    # >= 1.0 inclusive


def test_verdict_flips_on_pos_block_frac():
    assert _verdict(pos_frac=0.5)[0] == "FLAGGED"       # strictly > 0.5
    assert _verdict(pos_frac=0.49)[0] == "FLAGGED"
    assert _verdict(pos_frac=0.51)[0] == "NOT FLAGGED"


def test_verdict_insufficient_blocks_fails_closed():
    verdict, reason = _verdict(n_blocks_with_data=14)
    assert verdict == "FLAGGED"
    assert reason == "insufficient_blocks"
    # ... even when every statistical criterion would pass.
    assert _verdict(n_blocks_with_data=15)[0] == "NOT FLAGGED"


def test_verdict_reason_names_every_failed_criterion():
    _, reason = _verdict(delta=-0.01, block_t=0.2, pos_frac=0.3)
    assert "delta" in reason and "block_t" in reason and "pos_block_frac" in reason


# --------------------------------------------- reused machinery (G7-class)
@pytest.mark.parametrize("name", [
    "_sha256", "_assert", "build_grid", "close_panel",
    "spearman_ic", "paired_spearman_ic", "MomReaders",
])
def test_reused_machinery_byte_identical(name):
    """The paired/placebo/grid machinery is REUSED from the merged corrected
    moe runner (#990 pairing correction) — byte-identity enforced so the
    reuse cannot silently drift into a rewrite."""
    def source_of(path: Path, target: str) -> str:
        src = path.read_text()
        for node in ast.parse(src).body:
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)) \
                    and node.name == target:
                return ast.get_source_segment(src, node)
        raise AssertionError(f"{target} not found in {path.name}")

    assert source_of(RUNNER, name) == source_of(MOE, name)


def test_paired_ic_shares_one_cross_section():
    """Functional G7 check: names missing from EITHER leg are excluded from
    BOTH, and the returned identities are exactly the shared set."""
    rng = np.random.default_rng(7)
    shared = [f"S{i:03d}" for i in range(55)]
    gen_only = [f"G{i:03d}" for i in range(10)]
    pla_only = [f"P{i:03d}" for i in range(10)]
    gen = pd.Series(rng.standard_normal(65), index=shared + gen_only)
    pla = pd.Series(rng.standard_normal(65), index=shared + pla_only)
    lab = pd.Series(rng.standard_normal(75), index=shared + gen_only + pla_only)
    ic_g, ic_p, n, names = rn.paired_spearman_ic(gen, pla, lab)
    assert n == 55
    assert sorted(names) == sorted(shared)
    assert np.isfinite(ic_g) and np.isfinite(ic_p)


def test_paired_ic_below_floor_returns_nan():
    rng = np.random.default_rng(8)
    names = [f"S{i:03d}" for i in range(49)]  # floor is 50
    s = pd.Series(rng.standard_normal(49), index=names)
    ic_g, ic_p, n, _ = rn.paired_spearman_ic(s, s, s)
    assert n == 49
    assert np.isnan(ic_g) and np.isnan(ic_p)


# ------------------------------------------------------------- one-shot (T1)
def test_one_shot_passes_when_no_outputs_exist(tmp_path):
    rn.assert_one_shot(outputs=(tmp_path / "results.json",))


def test_one_shot_refuses_when_any_output_exists(tmp_path):
    marker = tmp_path / "results.json"
    marker.write_text("{}")
    with pytest.raises(AssertionError, match="one-shot"):
        rn.assert_one_shot(outputs=(marker, tmp_path / "absent.csv"))


def test_this_pr_ships_unrun_no_outputs_committed():
    """The runner PR must not carry any run outputs (spec §6)."""
    rn.assert_one_shot()


# ------------------------------------------------------- frozen-table pins
def test_frozen_constants_match_the_merged_spec():
    assert rn.PRIMARY_H == 60                       # spec §4 REVISED
    assert rn.HORIZONS == (20, 60)
    assert rn.EXPECTED_BLOCKS == {20: 89, 60: 29}
    assert rn.MIN_BLOCKS_WITH_DATA == {60: 15, 20: 45}
    assert rn.QUANTILE_ALPHA == 0.90
    assert rn.EMBARGO_TDAYS == 60
    assert rn.LABEL == "fwd_60d_excess"
    assert rn.LABEL_HORIZON_TDAYS == 60
    assert rn.TRAIN_DATA_START == "2016-01-04"
    assert rn.N_FEATURES == 172
    assert rn.EXPECTED_BEST_ITER == 100
    assert rn.FROZEN_CONFIG_FINGERPRINT == "sha256:f8fb2259b2bf1537"
    assert rn.CORPUS_START == "2019-01-14"
    assert rn.CORPUS_END == "2026-03-02"
    assert rn.WATCHLIST_N == 145
    assert rn.NAMES_PER_DATE_FLOOR == 50
    assert rn.BLOCK_T_MIN == 1.0
    assert rn.POS_BLOCK_FRAC_MIN == 0.5
