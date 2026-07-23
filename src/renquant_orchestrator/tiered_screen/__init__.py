"""tiered_screen — generic power-first, tiered signal-screening primitives.

A composition of the codex-reviewed ``expkit`` prereg primitives (``per_date_ic``,
``shifted_label_placebo``, ``paired_deltas``, the gap-respecting block bootstrap)
plus a power/MDE calculator (the one primitive ``expkit`` did not yet carry).
Carries no model-family, expert, or experiment-specific policy: callers supply
their own scores, close/bench frames, horizons, and (family-corrected) alpha.

  Tier 0  harness validation — positive control (inject a known-rho signal,
          the pipeline must recover it) + negative control (the shifted-label
          placebo IS the leakage floor). :func:`positive_control_recovery`.
  Tier 1  signal EXISTENCE at a given horizon. :func:`evaluate_existence`.
  Tier 2  paired INCREMENT of one score over another on identical dates/names
          (the common leakage floor cancels). :func:`evaluate_increment`.

Any concrete experiment (which experts, which horizons, which frozen alpha)
is the caller's pre-registered spec — this module does not define one.
"""

from renquant_orchestrator.tiered_screen.harness import (
    ExistenceResult,
    IncrementResult,
    evaluate_existence,
    evaluate_increment,
    positive_control_recovery,
)
from renquant_orchestrator.tiered_screen.power import (
    achieved_power,
    effective_blocks,
    min_detectable_ic,
    required_blocks,
)

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
]
