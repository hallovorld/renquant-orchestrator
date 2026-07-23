"""GOAL-4 two-expert (XGB + PatchTST) ensemble — pre-registered, tiered,
power-first evaluation.

This package holds the *method* (a composition of the codex-reviewed
``expkit`` prereg primitives plus a power/MDE calculator) and the frozen spec.
It deliberately does NOT wire the expensive real-model scoring: that is the
compute-gated follow-up, unlocked only after the cheap Tier-0/Tier-1 gates in
the frozen spec are met.

See ``doc/research/2026-07-23-g4-ensemble-prereg.md`` for the design.
"""

from renquant_orchestrator.g4_ensemble.harness import (
    ExistenceResult,
    IncrementResult,
    evaluate_existence,
    evaluate_increment,
    positive_control_recovery,
)
from renquant_orchestrator.g4_ensemble.power import (
    achieved_power,
    effective_blocks,
    min_detectable_ic,
    required_blocks,
)
from renquant_orchestrator.g4_ensemble.spec import build_spec

__all__ = [
    "ExistenceResult",
    "IncrementResult",
    "evaluate_existence",
    "evaluate_increment",
    "positive_control_recovery",
    "achieved_power",
    "effective_blocks",
    "min_detectable_ic",
    "required_blocks",
    "build_spec",
]
