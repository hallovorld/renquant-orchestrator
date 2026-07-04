"""C2 quality composite (#275) re-expressed as an expkit plugin — the
migration proof.

The merged measurement (scripts/msig_c2_quality.py, evidence
doc/research/evidence/2026-07-03-c2/) ran the M-SIG frozen gate on the
quality composite's per-date placebo-clean fwd_60d IC series. This plugin
replays the SAME frozen gate through the library's generic runner on the
COMMITTED per-date evidence, and the regression fixture
(tests/test_expkit_c2_regression.py) asserts the committed
`c2_results.json` gate values reproduce:

- identical bootstrap draws (the library's carried-mask block bootstrap is
  bit-identical to the c3 machinery C2 imported), so every per-seed
  LB/UB/SE/CI reproduces to the per-date JSON's serialization precision
  (~1e-13; asserted at 1e-9);
- the same mechanical rule output (INCONCLUSIVE — CI spans the 0.015 bar);
- the same governing adjudication (NON-VOTING: C2's five declared substrate
  disqualifiers, the EXPLORATORY_NON_VOTING pattern);
- the freeze-first check passes against the REAL repo history (the frozen
  addendum commit is an ancestor of the results commit).

Replay-mode controls (documented deviation from the original run): the
original PC-A/PC-B/PC-C were SCORE-level plants requiring the full FMP +
OHLCV substrate. Replay mode has only the committed per-date IC series, so
its controls are IC-SERIES-level wiring checks: a mean-shift plant at
~1.25x the harness's own MDE (the resample mean is linear, so bounds shift
by exactly delta — detection proves the gate wiring end to end) and the
D3 offset-seed sign-flip null. The null uses the C2 PC-C semantics
(specificity only — no false GO): this harness's boot SE (~0.023) makes it
honestly under-powered to actively KILL a true null at the 0.015 bar, the
same reason the original PC-C only asserted "not GO".

Full-substrate mode is intentionally NOT re-implemented here: the original
script remains the committed generator of record for the heavy path; the
plugin proves the library reproduces its adjudication pipeline exactly.

Usage (from the repo root):

    python -m renquant_orchestrator.expkit.plugins.c2_quality --dry-run
    python -m renquant_orchestrator.expkit.plugins.c2_quality --out /tmp/c2-replay
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from renquant_orchestrator.expkit.controls import plant_mean_shift, sign_flip_null
from renquant_orchestrator.expkit.prereg import Criterion, FrozenSpec
from renquant_orchestrator.expkit.runner import ExperimentPlugin, run_experiment

__all__ = [
    "C2_EVIDENCE_DIR",
    "C2_NON_VOTING_REASONS",
    "REPLAY_NULL_SEED",
    "REPLAY_PLANT_DELTA",
    "build_c2_spec",
    "build_replay_plugin",
    "load_committed_per_date",
]

#: Committed evidence of the original run (repo-relative).
C2_EVIDENCE_DIR = Path("doc/research/evidence/2026-07-03-c2")

#: The frozen addendum was committed BEFORE the results (the M8 three-commit
#: pattern) — the freeze-first check runs against this real history.
C2_SPEC_PATH = C2_EVIDENCE_DIR / "c2_frozen_addendum.json"
C2_RESULTS_PATHS = (
    C2_EVIDENCE_DIR / "c2_results.json",
    C2_EVIDENCE_DIR / "c2_per_date_ic_fwd60.json",
)

#: Replay-mode wiring plant: bounds shift by exactly delta (linearity), so
#: detection needs delta > bar + z*SE_max ~= 0.064 on this series. 0.08 is
#: ~1.25x that MDE — the smallest honest detectable scale for an IC-level
#: plant riding the real series' dispersion (the original 2x-bar plant was
#: SCORE-level with near-zero dispersion; different scale, same purpose).
REPLAY_PLANT_DELTA = 0.08

#: D3 NULL_OFFSET convention: null seed disjoint from the analysis seeds.
REPLAY_NULL_SEED = 142

#: The five declared substrate disqualifiers (c2_results.json
#: adjudication_note) — the mechanical rule output is recorded but does NOT
#: stand as C2's formal vote.
C2_NON_VOTING_REASONS = (
    "spec coverage-delta precondition NOT MET (spec section 1.2, >=20% bar)",
    "harvest manifest pins research_descriptive_only (restated current values, "
    "no revision identity): no confirmatory claim may rest on it",
    "survivorship-backfilled 134-name universe",
    "annual-only cadence vs the frozen quarterly estimand",
    "earliest-test date deviation (Q3 vs frozen Q4)",
)


def build_c2_spec() -> FrozenSpec:
    """The C2 frozen spec, restated 1:1 from scripts/msig_c2_quality.py's
    frozen constants (M-SIG spec section 0/1.2/2a + the committed addendum).
    Nothing here may be tuned — it mirrors an already-frozen, already-run
    experiment."""
    return FrozenSpec(
        experiment_id="msig_c2_quality",
        hypothesis=(
            "Cross-sectional rank of the quality composite "
            "{GP/A, -accruals, -net issuance} (acceptedDate-lagged, "
            "equal-weight z-scores) predicts fwd_60d SPY-excess returns: "
            "placebo-clean IC one-sided LB > 0.015 on all seeds"
        ),
        criteria=(
            Criterion(
                name="placebo_clean_ic",
                threshold=0.015,
                direction="gt",
                units="Spearman IC",
                description=(
                    "GO iff moving-block-bootstrap 98.33% one-sided CI lower "
                    "bound of the mean per-date placebo-clean fwd_60d IC > "
                    "0.015 on ALL seeds AND n >= 600 decision dates; KILL iff "
                    "UB < 0.015 on all seeds; else INCONCLUSIVE"
                ),
            ),
        ),
        family_size_k=3,  # M-SIG voting family {C2, C3, C4}
        seeds=(42, 43, 44),
        evidence_boundary={
            "window": "2017-02-09 -> 2026-01-08; n=2,241 daily decision dates",
            "cells": (
                "BULL_CALM 1,637; BEAR 327; BULL_VOLATILE 171 (thin); "
                "CHOPPY 106 (thin)"
            ),
            "outcome_era": (
                "fwd_60d/fwd_20d price-return excess vs SPY, split-adjusted, "
                "NOT dividend-adjusted, clipped +/-0.5"
            ),
            "cost_model": "none — IC-level reading only",
            "substrate": (
                "CURRENT-VINTAGE fundamentals (research_descriptive_only, no "
                "revision identity); survivorship-backfilled 134-name "
                "universe; regime labels replayed backward (C3 caveat "
                "inherited)"
            ),
            "multiplicity": "M-SIG family k=3, one-sided alpha=0.05/3 (98.33%)",
            "not_covered": (
                "incremental value over the production alpha158 stack; "
                "quarterly-refresh estimand (annual-only was measured)"
            ),
        },
        reopening_conditions=(
            "(a) PIT accrual: as-received fundamentals snapshotter (N2/N3) "
            "collects quarterly statements forward to >=600 clean dates",
            "(b) purchased as-filed vintage fundamentals (revision identity) "
            "covering 2016->present for the production universe",
            "(c) operator-amended protocol explicitly accepting the "
            "current-vintage substrate (#268 option-(b) route)",
            "absent (a)/(b)/(c) by 2027-Q3: INCONCLUSIVE per spec section 3; "
            "no coverage-delta re-run can reopen C2",
        ),
        horizon=60,
        block=60,
        n_boot=2000,
        base_alpha=0.05,
        min_decision_dates=600,
        min_names=30,
        extra_frozen={
            "spec_source": (
                "doc/design/2026-07-02-m-sig-signal-stack-spec.md "
                "(merged PR #243 r4) sections 0/1.2/2a"
            ),
            "frozen_addendum": str(C2_SPEC_PATH),
            "original_script": "scripts/msig_c2_quality.py",
            "original_evidence": str(C2_EVIDENCE_DIR),
        },
    )


def load_committed_per_date(evidence_dir: Path | str = C2_EVIDENCE_DIR) -> pd.DataFrame:
    """Load the committed per-date IC frame (date-indexed, ascending) — the
    replay substrate. Read-only."""
    path = Path(evidence_dir) / "c2_per_date_ic_fwd60.json"
    per = pd.read_json(path, orient="records")
    per["date"] = pd.to_datetime(per["date"])
    return per.set_index("date").sort_index()


def load_committed_results(evidence_dir: Path | str = C2_EVIDENCE_DIR) -> dict:
    """The committed c2_results.json — the regression fixture's target."""
    return json.loads((Path(evidence_dir) / "c2_results.json").read_text())


def build_replay_plugin(
    repo_root: Path | str,
    *,
    evidence_dir: Path | str | None = None,
) -> ExperimentPlugin:
    """The C2 replay plugin: committed per-date evidence in, the frozen gate
    + controls + adjudication through the generic runner."""
    repo_root = Path(repo_root)
    evidence_dir = (
        repo_root / C2_EVIDENCE_DIR if evidence_dir is None else Path(evidence_dir)
    )
    spec = build_c2_spec()

    def _load() -> pd.DataFrame:
        return load_committed_per_date(evidence_dir)

    def _evaluate(substrate: pd.DataFrame) -> pd.DataFrame:
        return substrate

    def _clean(substrate: pd.DataFrame) -> pd.Series:
        return substrate.dropna(subset=["clean_ic"]).sort_index()["clean_ic"]

    def _positive(substrate: pd.DataFrame) -> pd.Series:
        return plant_mean_shift(_clean(substrate), REPLAY_PLANT_DELTA)

    def _null(substrate: pd.DataFrame) -> pd.Series:
        return sign_flip_null(_clean(substrate), REPLAY_NULL_SEED)

    return ExperimentPlugin(
        spec=spec,
        load_substrate=_load,
        evaluate=_evaluate,
        positive_control=_positive,
        null_control=_null,
        declared_plant_effect=REPLAY_PLANT_DELTA,
        non_voting_reasons=C2_NON_VOTING_REASONS,
        require_negative_branch=False,
        negative_branch_waiver=(
            "C2 PC-C semantics (specificity only): boot SE ~0.023 makes this "
            "harness honestly under-powered to actively KILL a true null at "
            "the 0.015 bar — the original committed PC-C likewise asserted "
            "only 'no false GO'"
        ),
        inputs={
            "c2_per_date_ic_fwd60": evidence_dir / "c2_per_date_ic_fwd60.json",
            "c2_frozen_addendum": evidence_dir / "c2_frozen_addendum.json",
            "c2_results_committed": evidence_dir / "c2_results.json",
        },
        spec_path=evidence_dir / "c2_frozen_addendum.json",
        results_paths=(
            evidence_dir / "c2_results.json",
            evidence_dir / "c2_per_date_ic_fwd60.json",
        ),
        script="src/renquant_orchestrator/expkit/plugins/c2_quality.py",
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-root", default=".", help="renquant-orchestrator repo root")
    ap.add_argument("--out", default=None, help="evidence output directory")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    plugin = build_replay_plugin(args.repo_root)
    result = run_experiment(
        plugin,
        out_dir=args.out,
        repo_root=args.repo_root,
        dry_run=args.dry_run,
    )
    if result.dry_run:
        print(json.dumps(result.dry_run_plan, indent=2, default=str))
        return
    print(
        json.dumps(
            {
                "experiment_id": result.experiment_id,
                "outcome": result.outcome,
                "mechanical_outcome": result.decision.mechanical_outcome.value,
                "controls_all_passed": result.controls.all_passed,
                "n_dates": result.decision.n_dates,
                "mean_clean_ic": result.gate_summary["mean_clean_ic"],
                "spec_sha256": result.spec_sha256,
                "evidence_path": str(result.evidence_path),
            },
            indent=2,
            default=str,
        )
    )


if __name__ == "__main__":
    main()
