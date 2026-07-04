"""expkit — the reusable pre-registered experiment framework.

Consolidates the proven machinery of the 2026-07-02/03 measurement burst
(C2/C3/C4, M3/M8, S9, RS-5, D3 and their independent verifications) into one
importable, tested library, mechanizing the S-REL reliability contract
(doc/design/2026-07-03-s-rel-experiment-reliability.md).

An experiment is a frozen spec + a few callbacks:

    prereg.py     freeze-first spec (hash + committed-before-results check)
    evaluation.py per-date Spearman IC, shifted-label placebo, paired deltas,
                  matched-admission-rate solve
    stats.py      gap-respecting block bootstrap with the automatic small-n
                  exact-tail branch; multi-seed unanimity
    controls.py   mandatory positive-plant + true-null controls
    evidence.py   content-hash manifests, verified on re-read
    verdict.py    GO/KILL/NULL/INCONCLUSIVE/NON-VOTING with the power-aware
                  (MDE vs observed) NULL-vs-INCONCLUSIVE distinction
    runner.py     spec -> substrate -> controls gate -> evaluation -> stats ->
                  verdict + evidence bundle

See doc/design/2026-07-03-expkit.md for the plug-in guide.
"""

from renquant_orchestrator.expkit.controls import (
    ControlResult,
    ControlsNotPassedError,
    ControlsReport,
    plant_mean_shift,
    plant_rank_blend,
    run_controls,
    sign_flip_null,
    within_date_permutation_null,
)
from renquant_orchestrator.expkit.evaluation import (
    fwd_excess,
    gate_shift_sessions,
    paired_deltas,
    per_date_ic,
    shifted_label_placebo,
    shifted_label_placebo_long,
    solve_matched_admission,
    spearman,
)
from renquant_orchestrator.expkit.evidence import (
    ManifestVerification,
    build_manifest,
    canonical_json,
    load_and_verify_evidence,
    sha256_bytes,
    sha256_file,
    verify_manifest,
    write_evidence,
)
from renquant_orchestrator.expkit.prereg import (
    Criterion,
    FreezeCheck,
    FrozenSpec,
    SpecNotFrozenError,
    assert_spec_frozen_before_results,
    check_spec_frozen_before_results,
    load_frozen_spec,
    write_frozen_spec,
)
from renquant_orchestrator.expkit.runner import (
    ExperimentPlugin,
    ExperimentResult,
    gate_per_date,
    run_experiment,
)
from renquant_orchestrator.expkit.stats import (
    SMALL_N_MIN_USABLE_BLOCKS,
    block_bootstrap_conditional_mean,
    block_bootstrap_diff,
    bootstrap_admissible,
    bootstrap_or_exact,
    exact_sign_test,
    multi_seed_unanimity,
    summarize_boot,
    usable_blocks,
)
from renquant_orchestrator.expkit.verdict import (
    GateDecision,
    Outcome,
    decide,
    mde_one_sided,
    verdicts_md_row,
)

__all__ = [
    "SMALL_N_MIN_USABLE_BLOCKS",
    "ControlResult",
    "ControlsNotPassedError",
    "ControlsReport",
    "Criterion",
    "ExperimentPlugin",
    "ExperimentResult",
    "FreezeCheck",
    "FrozenSpec",
    "GateDecision",
    "ManifestVerification",
    "Outcome",
    "SpecNotFrozenError",
    "assert_spec_frozen_before_results",
    "block_bootstrap_conditional_mean",
    "block_bootstrap_diff",
    "bootstrap_admissible",
    "bootstrap_or_exact",
    "build_manifest",
    "canonical_json",
    "check_spec_frozen_before_results",
    "decide",
    "exact_sign_test",
    "fwd_excess",
    "gate_per_date",
    "gate_shift_sessions",
    "load_and_verify_evidence",
    "load_frozen_spec",
    "mde_one_sided",
    "multi_seed_unanimity",
    "paired_deltas",
    "per_date_ic",
    "plant_mean_shift",
    "plant_rank_blend",
    "run_controls",
    "run_experiment",
    "sha256_bytes",
    "sha256_file",
    "shifted_label_placebo",
    "shifted_label_placebo_long",
    "sign_flip_null",
    "solve_matched_admission",
    "spearman",
    "summarize_boot",
    "usable_blocks",
    "verdicts_md_row",
    "within_date_permutation_null",
    "write_evidence",
    "write_frozen_spec",
]
