"""The frozen GOAL-4 pre-registration spec (commit-1 of expkit's three-commit
prereg pattern). Building it in code — rather than hand-writing JSON — means
the R3/R4 invariants in ``expkit.prereg.FrozenSpec.__post_init__`` are enforced
and the hash is reproducible.

Run ``python -m renquant_orchestrator.g4_ensemble.spec <out.json>`` to (re)write
the committed spec; the committed bytes' sha256 is what governs once frozen.
"""

from __future__ import annotations

import sys

from renquant_orchestrator.expkit.prereg import Criterion, FrozenSpec, write_frozen_spec

# Screen horizons for the Tier-1 existence sweep. The 60-day horizon is the
# strategy's operating label; 5/20 are where statistical power actually exists.
SCREEN_HORIZONS = (5, 20, 60)

# Bonferroni family: 2 experts (XGB, PatchTST) x 3 horizons = 6 existence
# looks. Tier-2 increment is a single pre-registered follow-up CONDITIONAL on
# Tier-1 passing, evaluated at the same corrected alpha (documented in
# extra_frozen); seeds are unanimity checks, not counted (expkit #264 lesson).
FAMILY_SIZE_K = 6

SEEDS = (44, 7, 123)


def build_spec() -> FrozenSpec:
    return FrozenSpec(
        experiment_id="g4-ensemble-2expert-2026-07-23",
        hypothesis=(
            "H1 (existence): at least one of {XGB, PatchTST} has a placebo-clean "
            "cross-sectional rank-IC strictly above its shifted-label leakage "
            "floor at some horizon in {5,20,60}d. H2 (increment): the 2-expert "
            "ensemble out-ranks the BEST single expert on identical dates/names, "
            "measured as a paired clean-IC delta whose one-sided lower bound > 0. "
            "H0 default: no existence at any horizon (=> KILL) or no positive "
            "increment (=> defer to forward test, NOT a go)."
        ),
        criteria=(
            Criterion(
                name="tier1_existence_clean_ic_lb",
                threshold=0.0,
                direction="gt",
                units="rank_ic",
                description=(
                    "Tier-1 PASS: one-sided lower bound of the block-bootstrap "
                    "CI of mean(clean_ic = real - shifted-label placebo) > 0 for "
                    "some (expert, horizon). If FALSE for every cell => KILL G4."
                ),
            ),
            Criterion(
                name="tier2_increment_paired_lb",
                threshold=0.0,
                direction="gt",
                units="rank_ic_delta",
                description=(
                    "Tier-2 PASS: one-sided lower bound of the paired "
                    "block-bootstrap CI of mean(ensemble_clean_ic - "
                    "best_single_clean_ic) > 0. CI containing 0 => historical "
                    "increment unproven => decision deferred to Tier-3 forward "
                    "test (neither go nor kill)."
                ),
            ),
            Criterion(
                name="tier0_positive_control_real_ic",
                threshold=0.5,
                direction="gt",
                units="rank_ic",
                description=(
                    "Tier-0 harness sanity: a synthetic score injected at "
                    "rank-correlation rho>=0.6 must recover a real_ic > 0.5. "
                    "If it does not, the harness is broken and NO result on "
                    "this substrate is admissible."
                ),
            ),
        ),
        family_size_k=FAMILY_SIZE_K,
        seeds=SEEDS,
        horizon=60,
        block=60,
        n_boot=2000,
        base_alpha=0.05,
        min_decision_dates=600,
        min_names=30,
        evidence_boundary={
            "window": (
                "walk-forward as-of cutoffs 2023-10 .. 2026-03 (~600 trading "
                "days); each fold trained only on data <= its cutoff, "
                "horizon-matched embargo."
            ),
            "cells": (
                "2 experts (XGB, PatchTST) x 3 horizons (5,20,60d) x 3 seeds; "
                "104-145 name cross-section per date."
            ),
            "outcome_era": (
                "forward EXCESS return vs benchmark, repo label convention "
                "(clipped); demeaned per-date."
            ),
            "cost_model": (
                "Tier-1/2 are gross rank-IC (frictionless). Net-of-cost "
                "portfolio Sharpe/APY is a SEPARATE downstream stage, only "
                "entered if Tier-2 shows a positive increment."
            ),
            "substrate": (
                "renquant panel (alpha158-family features), PIT / train-only "
                "clipping quantiles; CSRankNorm per-date."
            ),
            "multiplicity": (
                "Bonferroni k=6 over the existence family; one-sided "
                "alpha=0.05/6; seeds enforced as unanimity, not extra looks."
            ),
            "not_covered": (
                "The 60-day operating-horizon go/no-go CANNOT be settled at "
                "adequate power from history (K~10 blocks, MDE~0.09); that "
                "verdict is explicitly reserved for the Tier-3 forward "
                "sequential test."
            ),
        },
        reopening_conditions=(
            "A fresh expert family outside {XGB, PatchTST} is proposed.",
            "A materially different label horizon or objective is adopted.",
            "The Tier-3 forward shadow test accrues its pre-registered number "
            "of admissible non-overlapping sessions.",
        ),
        extra_frozen={
            "screen_horizons": list(SCREEN_HORIZONS),
            "placebo": "shifted-label at gate_shift_sessions(horizon) = 2*horizon",
            "inference": "gap-respecting block bootstrap, block = horizon",
            "tier2_conditional_on": "tier1_existence_clean_ic_lb met",
            "tier3_forward": (
                "if Tier-2 CI contains 0, prereg a live shadow forward test "
                "with a sequential (alpha-spending) stopping rule; $0 compute."
            ),
            "compute_gate": (
                "the expensive full walk-forward PatchTST corpus is unlocked "
                "ONLY after Tier-1 shows a 60d-relevant lead; XGB tiers are "
                "near-free."
            ),
        },
    )


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: python -m renquant_orchestrator.g4_ensemble.spec <out.json>")
        return 2
    spec = build_spec()
    digest = write_frozen_spec(spec, argv[1])
    print(f"wrote {argv[1]}  sha256={digest}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv))
