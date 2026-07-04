"""Mandatory controls: positive plant + true null, first-class.

The founding precedent (S-REL §0): the A-1 λ sweep's round-1 "NULL" was
guaranteed by construction — the harness never armed the mechanism. Nothing
in the process forced the distinction between "no effect" and "a harness that
cannot detect the effect". These controls force it:

- POSITIVE PLANT: inject an effect of DECLARED size into real data and
  assert the harness detects it (RS-5 rank-z(label)+noise at planted
  Pearson ~0.10; D3 0.9*rank(score)+0.1*rank(label); C4 blend-weight solved
  to a 2x-margin target; C2 PC-A z(label)+kappa*noise at 2x the bar).
- TRUE NULL: a permuted / offset-seed / pure-noise arm must NOT be detected
  AND the negative branch must actually fire (RS-5: gate NOT detected AND
  kill_branch_fires on all seeds; D3 offset-seed retrains at seeds+100; C2
  PC-C within-date permutation -> KILL).

The runner refuses to emit a verdict unless BOTH pass (verdict.decide maps
controls_ok False/None to NON-VOTING).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd

from renquant_orchestrator.expkit.verdict import GateDecision, Outcome

__all__ = [
    "ControlResult",
    "ControlsNotPassedError",
    "ControlsReport",
    "plant_mean_shift",
    "plant_rank_blend",
    "run_controls",
    "sign_flip_null",
    "within_date_permutation_null",
]


class ControlsNotPassedError(RuntimeError):
    """Raised when a verdict is demanded from a harness whose mandatory
    controls are missing or failing."""


@dataclass
class ControlResult:
    name: str
    kind: str  # "positive_plant" | "true_null"
    passed: bool
    outcome: str
    requirement: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "passed": self.passed,
            "outcome": self.outcome,
            "requirement": self.requirement,
            "detail": self.detail,
        }


@dataclass
class ControlsReport:
    positive: ControlResult
    null: ControlResult

    @property
    def all_passed(self) -> bool:
        return self.positive.passed and self.null.passed

    def to_dict(self) -> dict[str, Any]:
        return {
            "positive": self.positive.to_dict(),
            "null": self.null.to_dict(),
            "all_passed": self.all_passed,
        }

    def raise_if_failed(self) -> None:
        if not self.all_passed:
            failed = [
                c.name for c in (self.positive, self.null) if not c.passed
            ]
            raise ControlsNotPassedError(
                f"mandatory controls failed: {failed} — no verdict is admissible "
                "(S-REL R2; the lambda-round-1 lesson)"
            )


def run_controls(
    gate_fn: Callable[[Any], GateDecision],
    *,
    positive_input: Any,
    null_input: Any,
    positive_name: str = "positive_plant",
    null_name: str = "true_null",
    declared_effect: float | None = None,
    require_negative_branch: bool = True,
) -> ControlsReport:
    """Run the SAME gate the experiment uses on both control inputs.

    - positive passes iff the gate outcome is GO (detection of the declared
      planted effect);
    - null passes iff the gate outcome is NOT GO, and (by default, the RS-5
      semantics) the negative branch actually fires: KILL or NULL. An
      INCONCLUSIVE read on a true null means the harness cannot classify a
      pure null — set require_negative_branch=False only with a documented
      reason. For the small-n exact branch, non-detection suffices (its
      power limits are already encoded as INCONCLUSIVE-only outcomes).
    """
    pos_decision = gate_fn(positive_input)
    pos_mech = pos_decision.mechanical_outcome
    positive = ControlResult(
        name=positive_name,
        kind="positive_plant",
        passed=pos_mech is Outcome.GO,
        outcome=pos_mech.value,
        requirement="gate must detect the planted effect (mechanical GO)",
        detail={
            "declared_effect": declared_effect,
            "decision": pos_decision.to_dict(),
        },
    )

    null_decision = gate_fn(null_input)
    null_mech = null_decision.mechanical_outcome
    non_detection = null_mech is not Outcome.GO
    if null_decision.method == "exact":
        negative_fired = non_detection
    else:
        negative_fired = null_mech in (Outcome.KILL, Outcome.NULL)
    null_passed = non_detection and (negative_fired or not require_negative_branch)
    null = ControlResult(
        name=null_name,
        kind="true_null",
        passed=null_passed,
        outcome=null_mech.value,
        requirement=(
            "gate must NOT detect the null"
            + (" AND the negative branch must fire (KILL/NULL)" if require_negative_branch else "")
        ),
        detail={"decision": null_decision.to_dict()},
    )
    return ControlsReport(positive=positive, null=null)


# ---------------------------------------------------------------------------
# Injection helpers (the plants and nulls the corpus used, generalized)
# ---------------------------------------------------------------------------
def plant_mean_shift(clean_ic: pd.Series, delta: float) -> pd.Series:
    """IC-series-level plant: shift the per-date clean-IC series by a
    DECLARED delta. Because the block bootstrap's resample mean is linear,
    the planted series' bounds shift by exactly delta — a wiring-level
    detection check when only the IC series (not scores) is available."""
    return clean_ic + float(delta)


def plant_rank_blend(
    score: pd.DataFrame, label: pd.DataFrame, weight: float
) -> pd.DataFrame:
    """Score-level plant (D3 wf_positive_plant / C4 PC-A family): per date,
    blend the rank of the REAL label into the rank of the baseline score at
    a declared weight: (1-w)*rankz(score) + w*rankz(label). The plant rides
    on real data — detecting it proves the whole evaluation path, not just
    the bootstrap."""
    if not 0 < weight < 1:
        raise ValueError("weight must be in (0, 1)")

    def _rankz(frame: pd.DataFrame) -> pd.DataFrame:
        r = frame.rank(axis=1)
        mu = r.mean(axis=1)
        sd = r.std(axis=1).replace(0, np.nan)
        return r.sub(mu, axis=0).div(sd, axis=0)

    planted = (1.0 - weight) * _rankz(score) + weight * _rankz(label)
    return planted.where(score.notna())


def sign_flip_null(clean_ic: pd.Series, seed: int) -> pd.Series:
    """IC-series-level true null: multiply each per-date value by an
    independent random sign (offset-seed convention: pass a seed disjoint
    from the analysis seeds, e.g. seed+100 per D3 NULL_OFFSET). Destroys the
    mean while keeping the marginal scale; the gate must not fire and its
    negative branch must."""
    rng = np.random.default_rng(seed)
    signs = rng.choice([-1.0, 1.0], size=len(clean_ic))
    return clean_ic * signs


def within_date_permutation_null(score: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Score-level true null (C2 PC-C / C4 PC-B): permute the score
    cross-section WITHIN each date — any surviving 'signal' is machinery
    artifact by construction."""
    rng = np.random.default_rng(seed)
    out = score.copy()
    for dt in out.index:
        row = out.loc[dt]
        mask = row.notna()
        if mask.sum() >= 2:
            vals = row[mask].to_numpy()
            out.loc[dt, mask.index[mask]] = rng.permutation(vals)
    return out
