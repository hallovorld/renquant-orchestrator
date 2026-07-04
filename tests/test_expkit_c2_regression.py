"""Migration proof: the C2 quality measurement (#275) as an expkit plugin.

The regression fixture: run the committed per-date evidence
(doc/research/evidence/2026-07-03-c2/) through the library's generic runner
and assert the committed c2_results.json gate values REPRODUCE — same
bootstrap draws, same per-seed bounds, same mechanical rule output, same
governing adjudication.

Tolerance: the per-date JSON was serialized at pandas' default 10-digit
precision, so recomputed floats agree to ~1e-13; asserted at 1e-9. The
bootstrap indices themselves are seed-exact (identical resamples), so any
implementation drift in the carried-mask bootstrap or the quantile
convention would blow far past that tolerance.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from renquant_orchestrator.expkit.plugins.c2_quality import (
    C2_NON_VOTING_REASONS,
    build_c2_spec,
    build_replay_plugin,
    load_committed_per_date,
    load_committed_results,
)
from renquant_orchestrator.expkit.runner import run_experiment
from renquant_orchestrator.expkit.verdict import Outcome

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_DIR = REPO_ROOT / "doc" / "research" / "evidence" / "2026-07-03-c2"

ATOL = 1e-9

pytestmark = pytest.mark.skipif(
    not (EVIDENCE_DIR / "c2_results.json").exists(),
    reason="committed C2 evidence not present",
)


@pytest.fixture(scope="module")
def committed() -> dict:
    return load_committed_results(EVIDENCE_DIR)


@pytest.fixture(scope="module")
def replay():
    plugin = build_replay_plugin(REPO_ROOT)
    return run_experiment(plugin, repo_root=REPO_ROOT, freeze_check=_git_history_ok())


def _git_history_ok() -> bool:
    """The freeze-first leg needs real git history (a shallow clone breaks
    `git log --diff-filter=A`); the numeric regression must not."""
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO_ROOT), "log", "--diff-filter=A", "--format=%H",
             "--", "doc/research/evidence/2026-07-03-c2/c2_frozen_addendum.json"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return bool(out)
    except (OSError, subprocess.CalledProcessError):
        return False


# ---------------------------------------------------------------------------
# the committed gate values reproduce
# ---------------------------------------------------------------------------
def test_n_dates_reproduces(replay, committed):
    assert replay.decision.n_dates == committed["gate_fwd60_unconditional"]["n_dates"]
    assert replay.decision.n_dates == 2241


def test_mean_ics_reproduce(replay, committed):
    g = committed["gate_fwd60_unconditional"]
    gs = replay.gate_summary
    assert gs["mean_clean_ic"] == pytest.approx(g["mean_clean_ic"], abs=ATOL)
    assert gs["mean_real_ic"] == pytest.approx(g["mean_real_ic"], abs=ATOL)
    assert gs["mean_placebo_ic"] == pytest.approx(g["mean_placebo_ic"], abs=ATOL)
    assert gs["clean_hit_rate"] == pytest.approx(g["clean_hit_rate"], abs=ATOL)


def test_bootstrap_bounds_reproduce_per_seed(replay, committed):
    g = committed["gate_fwd60_unconditional"]["bootstrap_by_seed"]
    by_seed = replay.gate_summary["stats"]["by_seed"]
    assert set(by_seed) == {"42", "43", "44"}
    for seed, c in g.items():
        b = by_seed[seed]
        assert b["boot_se"] == pytest.approx(c["boot_se"], abs=ATOL)
        assert b["lb_one_sided"] == pytest.approx(c["lb_one_sided_9833"], abs=ATOL)
        assert b["ub_one_sided"] == pytest.approx(c["ub_one_sided_9833"], abs=ATOL)
        assert b["ci95_two_sided"][0] == pytest.approx(c["ci95_two_sided"][0], abs=ATOL)
        assert b["ci95_two_sided"][1] == pytest.approx(c["ci95_two_sided"][1], abs=ATOL)
        assert b["n_boot_effective"] == c["n_boot_effective"]


def test_mechanical_outcome_reproduces(replay, committed):
    # committed: INCONCLUSIVE (CI spans the 0.015 bar on all seeds)
    assert (
        replay.decision.mechanical_outcome.value
        == committed["gate_fwd60_unconditional"]["mechanical_rule_output"]
    )
    assert replay.decision.mechanical_outcome is Outcome.INCONCLUSIVE


def test_governing_adjudication_reproduces(replay, committed):
    # committed adjudication_status: EXPLORATORY_NON_VOTING — the declared
    # substrate disqualifiers force NON-VOTING while the mechanical output
    # is still recorded
    assert committed["adjudication_status"] == "EXPLORATORY_NON_VOTING"
    assert replay.outcome == "NON-VOTING"
    assert set(C2_NON_VOTING_REASONS) <= set(replay.decision.non_voting_reasons)


def test_replay_controls_pass(replay):
    assert replay.controls.positive.passed
    assert replay.controls.positive.outcome == "GO"
    assert replay.controls.null.passed
    assert replay.controls.null.outcome != "GO"
    assert "under-powered" in replay.controls.null.detail["negative_branch_waiver"]


def test_freeze_first_against_real_history(replay):
    if replay.freeze_check is None:
        pytest.skip("git history unavailable (shallow clone)")
    assert replay.freeze_check.ok
    # the addendum commit strictly precedes the results commit (the M8
    # three-commit pattern, verified against real history)
    statuses = [e["status"] for e in replay.freeze_check.results.values()]
    assert all("ok" in s for s in statuses)


# ---------------------------------------------------------------------------
# spec restatement stays glued to the committed frozen constants
# ---------------------------------------------------------------------------
def test_spec_matches_committed_frozen_thresholds(committed):
    spec = build_c2_spec()
    frozen = committed["frozen_thresholds"]
    bar = spec.criteria[0]
    assert bar.threshold == frozen["ic_threshold_placebo_clean"]
    assert spec.alpha_one_sided == pytest.approx(1 - frozen["ci_level_one_sided"])
    assert spec.block == frozen["block"]
    assert spec.n_boot == frozen["n_boot"]
    assert list(spec.seeds) == frozen["seeds"]
    assert spec.min_decision_dates == frozen["min_decision_dates"]
    assert spec.horizon == frozen["verdict_horizon"]
    assert spec.family_size_k == 3


def test_committed_per_date_shape():
    per = load_committed_per_date(EVIDENCE_DIR)
    assert per.index.is_monotonic_increasing
    assert {"real_ic", "placebo_ic", "clean_ic"} <= set(per.columns)
    assert per["clean_ic"].notna().sum() == 2241
