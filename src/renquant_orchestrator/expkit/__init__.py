"""expkit — the load-bearing primitives of the pre-registered experiment
discipline, consolidated where real duplication was found.

Scope (2026-07-04 narrowing, codex review round 2 on PR #287): shipped surface
is the four modules with CONCRETE, verified evidence of repeated independent
reimplementation across the 2026-07-02/03 measurement burst's scripts —
not the full speculative runner/verdict/plugin framework originally proposed.
See doc/progress/2026-07-03-expkit.md for the evidence trail and
doc/design/2026-07-03-expkit.md for the deferred full design (a documented
sketch, not current scope).

    prereg.py     freeze-first spec (hash + committed-before-results check).
                  The frozen_spec.json write/read/hash convention was
                  independently hand-rolled in scripts/d3_core_shrink_check.py,
                  scripts/m8_cluster_wave1.py, scripts/m8_independent_verification.py,
                  scripts/s9_track_a_conditional.py.
    evaluation.py per-date Spearman IC, shifted-label placebo, forward-excess
                  labels, paired deltas, matched-admission-rate solve.
                  fwd_excess/per_date_ic reimplemented in both
                  scripts/c3_residual_momentum.py and
                  scripts/rs5_downcap_measurement.py; scripts/msig_c2_quality.py
                  reaches for the c3 versions via a raw importlib.util
                  file-path load rather than a real import.
    stats.py      gap-respecting block bootstrap (block_bootstrap_conditional_mean
                  in scripts/c3_residual_momentum.py, re-implemented as
                  carried_mask_block_bootstrap in scripts/msig_c4_trendscan.py
                  and bootstrap_mask_removed_mean in
                  scripts/rs5_downcap_measurement.py) plus the automatic
                  small-n exact-tail branch and multi-seed unanimity.
    evidence.py   content-hash manifests, verified on re-read. sha256_file/
                  _json_default originate in scripts/c3_residual_momentum.py;
                  scripts/msig_c2_quality.py already reaches back into c3 for
                  them via the same importlib.util hack.

    replay.py     Replay-experiment orchestration: the reusable arm-vs-arm
                  evaluation pattern.  The load -> match -> evaluate ->
                  control -> stamp pipeline extracted from
                  scripts/m4b_floor_replay.py: score loading (read-only DB),
                  per-arm evaluation with per-date expectancy aggregation,
                  and control tests (iid-noise null, permutation null,
                  positive-control planted-effect).

NOT shipped in this narrowing (no duplication evidence found — each
experiment's verdict/controls logic differs in its specific formulas, not
just its wiring): verdict.py (GO/KILL/NULL/INCONCLUSIVE/NON-VOTING decision
engine), runner.py (the full spec -> controls -> evaluation -> stats ->
verdict -> evidence pipeline), plugins/ (runner's plugin registration).
These remain a documented design sketch pending real, repeated,
evidence-justified need.
"""

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
from renquant_orchestrator.expkit.replay import (
    ReplayArm,
    ReplayBar,
    admitted_set,
    evaluate_arm,
    mean_admission_count,
    open_readonly,
    per_date_expectancy,
    point_delta,
    replay_experiment,
    run_control_tests,
    solve_arm_param,
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

__all__ = [
    "ReplayArm",
    "ReplayBar",
    "SMALL_N_MIN_USABLE_BLOCKS",
    "Criterion",
    "FreezeCheck",
    "FrozenSpec",
    "ManifestVerification",
    "SpecNotFrozenError",
    "admitted_set",
    "assert_spec_frozen_before_results",
    "block_bootstrap_conditional_mean",
    "block_bootstrap_diff",
    "bootstrap_admissible",
    "bootstrap_or_exact",
    "build_manifest",
    "canonical_json",
    "check_spec_frozen_before_results",
    "evaluate_arm",
    "exact_sign_test",
    "fwd_excess",
    "gate_shift_sessions",
    "load_and_verify_evidence",
    "load_frozen_spec",
    "mean_admission_count",
    "multi_seed_unanimity",
    "open_readonly",
    "paired_deltas",
    "per_date_ic",
    "per_date_expectancy",
    "point_delta",
    "replay_experiment",
    "run_control_tests",
    "sha256_bytes",
    "sha256_file",
    "shifted_label_placebo",
    "shifted_label_placebo_long",
    "solve_arm_param",
    "solve_matched_admission",
    "spearman",
    "summarize_boot",
    "usable_blocks",
    "verify_manifest",
    "write_evidence",
    "write_frozen_spec",
]
