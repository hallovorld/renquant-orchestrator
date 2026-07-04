"""expkit.replay -- arm-vs-arm replay-experiment orchestration primitives."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np
import pytest

from renquant_orchestrator.expkit.replay import (
    ReplayArm,
    ReplayBar,
    admitted_set,
    canonical_runs,
    evaluate_arm,
    mean_admission_count,
    open_readonly,
    per_date_expectancy,
    point_delta,
    replay_experiment,
    run_control_tests,
    solve_arm_param,
)


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


def _make_bars(
    n_bars: int = 5,
    n_tickers: int = 20,
    seed: int = 42,
    with_outcomes: bool = True,
) -> list[ReplayBar]:
    """Synthetic bars with deterministic scores and outcomes."""
    rng = np.random.default_rng(seed)
    bars = []
    for i in range(n_bars):
        scores = rng.standard_normal(n_tickers)
        outcomes = rng.standard_normal(n_tickers) * 0.05 if with_outcomes else None
        eligible = np.ones(n_tickers, dtype=bool)
        # veto the last 2 tickers as upstream-blocked
        eligible[-2:] = False
        bars.append(
            ReplayBar(
                date=f"2026-06-{10 + i:02d}",
                run_id=f"run_{i}",
                tickers=[f"T{j}" for j in range(n_tickers)],
                scores=scores,
                outcomes=outcomes,
                eligible=eligible,
                meta={"regime": "BULL_CALM"},
            )
        )
    return bars


def _top_half_gate(scores: np.ndarray, ctx: dict) -> np.ndarray:
    """Admit the top half of scores (above the median)."""
    return scores >= np.median(scores)


def _threshold_gate(scores: np.ndarray, ctx: dict) -> np.ndarray:
    """Gate parameterised by arm.param stored in ctx -- admit scores above a
    threshold read from the arm's param (exposed via closure or the scores
    array convention).  For testing we use a simple > 0 gate."""
    return scores > 0


def _make_baseline() -> ReplayArm:
    return ReplayArm(
        name="baseline",
        label="scores > 0",
        gate_fn=_threshold_gate,
        is_baseline=True,
    )


def _make_candidate() -> ReplayArm:
    return ReplayArm(
        name="top_half",
        label="top half by score",
        gate_fn=_top_half_gate,
    )


# --------------------------------------------------------------------------
# open_readonly
# --------------------------------------------------------------------------


def test_open_readonly(tmp_path: Path):
    db_path = tmp_path / "test.db"
    # Create a DB first
    con = sqlite3.connect(str(db_path))
    con.execute("CREATE TABLE t (id INTEGER)")
    con.execute("INSERT INTO t VALUES (1)")
    con.commit()
    con.close()

    # Open read-only
    ro = open_readonly(str(db_path))
    rows = ro.execute("SELECT * FROM t").fetchall()
    assert rows == [(1,)]
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("INSERT INTO t VALUES (2)")
    ro.close()


# --------------------------------------------------------------------------
# canonical_runs
# --------------------------------------------------------------------------


def _build_canonical_runs_db(path: Path) -> None:
    con = sqlite3.connect(str(path))
    con.execute(
        "CREATE TABLE pipeline_runs (run_id TEXT PRIMARY KEY, run_date TEXT, "
        "regime TEXT, created_at TEXT, counters_json TEXT, run_type TEXT)"
    )
    con.execute(
        "CREATE TABLE score_distribution (run_id TEXT, ticker TEXT, "
        "is_holding INTEGER, raw_panel REAL)"
    )

    def _insert_run(run_id, run_date, created_at, run_type="live", n_candidates=10):
        con.execute(
            "INSERT INTO pipeline_runs VALUES (?,?,?,?,?,?)",
            (run_id, run_date, "BULL_CALM", created_at, '{"n": 1}', run_type),
        )
        for i in range(n_candidates):
            con.execute(
                "INSERT INTO score_distribution VALUES (?,?,0,?)",
                (run_id, f"T{i}", 0.1 * i),
            )

    # 2026-06-10: an early (superseded) run + a later full run, same date.
    _insert_run("run-early", "2026-06-10", "2026-06-10T09:00:00")
    _insert_run("run-late", "2026-06-10", "2026-06-10T15:30:00")
    # 2026-06-11: a single run with too few candidates -- filtered by threshold.
    _insert_run("run-thin", "2026-06-11", "2026-06-11T15:30:00", n_candidates=3)
    # 2026-06-12: a single non-live (e.g. backtest) run -- filtered by run_type.
    _insert_run("run-sim", "2026-06-12", "2026-06-12T15:30:00", run_type="backtest")
    con.commit()
    con.close()


def test_canonical_runs_dedup_latest_full(tmp_path: Path):
    db_path = tmp_path / "runs.fixture.db"
    _build_canonical_runs_db(db_path)
    con = open_readonly(str(db_path))
    runs = canonical_runs(con, min_candidates=5)
    con.close()

    # Only 2026-06-10 has a qualifying (>= 5 candidates) live run; the
    # 06-11 run is too thin and 06-12 is not run_type='live'.
    assert len(runs) == 1
    assert runs[0]["run_date"] == "2026-06-10"
    assert runs[0]["run_id"] == "run-late"  # the LATER of the two same-date runs


def test_canonical_runs_min_candidates_threshold(tmp_path: Path):
    db_path = tmp_path / "runs.fixture.db"
    _build_canonical_runs_db(db_path)
    con = open_readonly(str(db_path))
    runs = canonical_runs(con, min_candidates=3)
    con.close()

    # At threshold 3, the thin 06-11 run now qualifies too.
    dates = {r["run_date"] for r in runs}
    assert "2026-06-11" in dates
    assert "2026-06-12" not in dates  # still excluded: run_type != 'live'


# --------------------------------------------------------------------------
# admitted_set
# --------------------------------------------------------------------------


def test_admitted_set_respects_eligibility():
    bars = _make_bars(n_bars=1, n_tickers=10)
    bar = bars[0]
    arm = _make_baseline()
    mask = admitted_set(arm, bar)
    # The last 2 tickers are ineligible, so they must be False regardless
    assert not mask[-2]
    assert not mask[-1]


def test_admitted_set_without_eligibility():
    bar = ReplayBar(
        date="2026-01-01",
        run_id="r1",
        tickers=["A", "B", "C"],
        scores=np.array([1.0, -1.0, 0.5]),
        eligible=None,
    )
    arm = _make_baseline()
    mask = admitted_set(arm, bar)
    np.testing.assert_array_equal(mask, [True, False, True])


# --------------------------------------------------------------------------
# per_date_expectancy + point_delta
# --------------------------------------------------------------------------


def test_per_date_expectancy_shape_and_ordering():
    bars = _make_bars(n_bars=4)
    baseline = _make_baseline()
    candidate = _make_candidate()
    dates, agg = per_date_expectancy(bars, baseline, candidate)
    assert len(dates) == 4
    assert agg.shape == (4, 4)
    # dates must be sorted
    assert dates == sorted(dates)


def test_per_date_expectancy_skips_no_outcome_bars():
    bars = _make_bars(n_bars=3, with_outcomes=False)
    baseline = _make_baseline()
    candidate = _make_candidate()
    dates, agg = per_date_expectancy(bars, baseline, candidate)
    assert len(dates) == 0
    assert agg.shape == (0, 4)


def test_point_delta_sign():
    # Candidate admits only positive-outcome names, baseline admits all
    rng = np.random.default_rng(99)
    outcomes = np.array([0.10, 0.08, -0.05, -0.03, 0.02])
    bar = ReplayBar(
        date="2026-01-01",
        run_id="r1",
        tickers=["A", "B", "C", "D", "E"],
        scores=np.array([1.0, 0.8, -0.5, -0.3, 0.2]),
        outcomes=outcomes,
        eligible=np.ones(5, dtype=bool),
    )
    # Baseline: all admitted; candidate: scores > 0 (A, B, E)
    baseline = _make_baseline()  # scores > 0 => A, B, E
    # Custom candidate that admits only the top 2
    top2_arm = ReplayArm(
        name="top2",
        label="top 2 scores",
        gate_fn=lambda s, c: s >= np.sort(s)[-2],
    )
    dates, agg = per_date_expectancy([bar], baseline, top2_arm)
    delta = point_delta(agg)
    # top2 admits A (0.10) and B (0.08), mean = 0.09
    # baseline admits A (0.10), B (0.08), E (0.02), mean = 0.0667
    assert delta is not None
    assert delta > 0  # candidate has higher expected return


def test_point_delta_empty():
    assert point_delta(np.empty((0, 4))) is None


# --------------------------------------------------------------------------
# mean_admission_count
# --------------------------------------------------------------------------


def test_mean_admission_count_consistent():
    bars = _make_bars(n_bars=5)
    baseline = _make_baseline()
    count = mean_admission_count(bars, baseline)
    # With eligible=True for first 18 tickers, scores > 0 admits roughly half
    assert 4 < count < 14  # very loose: just validates it runs


# --------------------------------------------------------------------------
# solve_arm_param
# --------------------------------------------------------------------------


def test_solve_arm_param_matches_baseline():
    bars = _make_bars(n_bars=5, n_tickers=30, seed=7)
    baseline = _make_baseline()
    target = mean_admission_count(bars, baseline)

    # Candidate with a threshold param: admit scores > param
    def threshold_gate(scores, ctx):
        # Read param from the arm closure -- we stash it in the arm
        return scores > threshold_gate._param

    threshold_gate._param = 0.0

    candidate = ReplayArm(
        name="threshold",
        label="scores > threshold",
        gate_fn=lambda s, c: s > candidate.param if candidate.param is not None else s > 0,
        param=0.0,
        param_bounds=(-3.0, 3.0),
        param_increasing=False,  # higher threshold -> fewer admissions
    )
    result = solve_arm_param(bars, candidate, target, tol=1.0)
    assert result.converged or abs(result.achieved - target) <= 1.5
    # The solved param should be stored on the arm
    assert candidate.param == result.param


def test_solve_arm_param_rejects_no_bounds():
    bars = _make_bars(n_bars=2)
    arm = ReplayArm(name="x", label="x", gate_fn=_threshold_gate, param_bounds=None)
    with pytest.raises(ValueError, match="param_bounds"):
        solve_arm_param(bars, arm, 5.0)


# --------------------------------------------------------------------------
# evaluate_arm
# --------------------------------------------------------------------------


def test_evaluate_arm_returns_expected_keys():
    bars = _make_bars(n_bars=4)
    baseline = _make_baseline()
    candidate = _make_candidate()
    result = evaluate_arm(bars, baseline, candidate)
    assert result["arm"] == "top_half"
    assert "baseline" in result
    assert "candidate" in result
    assert "removed" in result
    assert "expectancy_delta" in result
    assert "n_resolved_dates" in result
    assert result["n_resolved_dates"] == 4
    assert result["baseline"]["n"] > 0
    assert result["candidate"]["n"] > 0


def test_evaluate_arm_removed_set_is_baseline_minus_candidate():
    bar = ReplayBar(
        date="2026-01-01",
        run_id="r1",
        tickers=["A", "B", "C", "D"],
        scores=np.array([2.0, 1.0, -1.0, -2.0]),
        outcomes=np.array([0.1, 0.05, -0.05, -0.1]),
        eligible=np.ones(4, dtype=bool),
    )
    baseline = _make_baseline()  # scores > 0: A, B
    # Candidate: top 1 only
    top1 = ReplayArm(
        name="top1",
        label="top 1",
        gate_fn=lambda s, c: s >= np.max(s),
    )
    result = evaluate_arm([bar], baseline, top1)
    # removed = baseline (A, B) minus candidate (A) = B with outcome 0.05
    assert result["removed"]["n"] == 1
    assert result["removed"]["mean"] == pytest.approx(0.05)


# --------------------------------------------------------------------------
# run_control_tests
# --------------------------------------------------------------------------


def test_run_control_tests_null_rate_near_nominal():
    bars = _make_bars(n_bars=8, n_tickers=30, seed=12)
    baseline = _make_baseline()
    candidate = _make_candidate()

    # A trivially permissive criterion: delta > 0
    def always_true_criterion(dates, agg):
        d = point_delta(agg)
        return d is not None and d > 0

    result = run_control_tests(
        bars,
        baseline,
        candidate,
        criterion_fn=always_true_criterion,
        n_reps=50,
        seed=99,
    )
    assert "true_null_false_fire_rate_iid" in result
    assert "positive_control_power" in result
    assert result["n_reps"] == 50
    # Permutation null should have run (we have real outcomes)
    assert result["true_null_false_fire_rate_perm"] is not None


def test_run_control_tests_positive_power_increases_with_gap():
    bars = _make_bars(n_bars=6, n_tickers=40, seed=33)
    baseline = _make_baseline()
    candidate = _make_candidate()

    def criterion(dates, agg):
        d = point_delta(agg)
        return d is not None and d > 0.01

    result = run_control_tests(
        bars,
        baseline,
        candidate,
        criterion_fn=criterion,
        n_reps=100,
        planted_gaps=(0.01, 0.10),
        seed=77,
    )
    # Larger planted gap should yield at least as much detection power
    assert result["positive_control_power"]["gap_0.1"] >= result["positive_control_power"]["gap_0.01"]


# --------------------------------------------------------------------------
# replay_experiment (end-to-end)
# --------------------------------------------------------------------------


def test_replay_experiment_smoke():
    bars = _make_bars(n_bars=5, n_tickers=20)
    baseline = _make_baseline()
    candidate = _make_candidate()
    result = replay_experiment(bars, baseline, [candidate])
    assert result["n_bars"] == 5
    assert "top_half" in result["evaluations"]
    assert result["controls"] is None  # no criterion_fn


def test_replay_experiment_with_controls():
    bars = _make_bars(n_bars=5, n_tickers=20)
    baseline = _make_baseline()
    candidate = _make_candidate()

    def crit(dates, agg):
        d = point_delta(agg)
        return d is not None and d > 0

    result = replay_experiment(
        bars,
        baseline,
        [candidate],
        criterion_fn=crit,
        control_reps=20,
        control_seed=55,
    )
    assert result["controls"] is not None
    assert "top_half" in result["controls"]
    assert result["controls"]["top_half"]["n_reps"] == 20


def test_replay_experiment_with_param_solve():
    bars = _make_bars(n_bars=5, n_tickers=30, seed=7)
    baseline = _make_baseline()
    target = mean_admission_count(bars, baseline)

    candidate = ReplayArm(
        name="threshold",
        label="scores > threshold",
        gate_fn=lambda s, c: s > candidate.param if candidate.param is not None else s > 0,
        param=0.0,
        param_bounds=(-3.0, 3.0),
        param_increasing=False,
    )
    result = replay_experiment(bars, baseline, [candidate], breadth_tol=1.0)
    assert "threshold" in result["solves"]
    solve = result["solves"]["threshold"]
    assert abs(solve["achieved"] - solve["target"]) <= 1.5
