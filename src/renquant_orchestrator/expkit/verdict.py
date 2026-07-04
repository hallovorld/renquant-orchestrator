"""Verdict taxonomy: GO / KILL / NULL / INCONCLUSIVE / NON-VOTING.

Mechanizes the outcome vocabulary the corpus converged on, with the
power-aware distinction the M3 verification made canonical: a
significant-looking negative on an uninformative sample is INCONCLUSIVE,
not NULL — and the call is MECHANICAL (MDE vs observed), not judgment.

Definitions (the frozen rule family, C2/C4/D3 semantics):
- GO           unanimous across seeds: one-sided LB > bar, AND the
               decision-date floor is met, AND controls passed.
- KILL         unanimous across seeds: one-sided UB < bar (the effect is
               confidently below the decision bar), AND controls passed.
               (C2 semantics: KILL is CI-driven and carries its own power —
               a wide CI cannot produce it.)
- NULL         neither GO nor KILL, the harness was POWERED at decision
               scale (z*SE_max <= bar, i.e. a bar-sized effect is within the
               harness's resolution), the floor was met, and controls
               passed. "Powered, found nothing."
- INCONCLUSIVE neither GO nor KILL and the harness was NOT powered at
               decision scale (or the floor was unmet, or the small-n exact
               branch was in effect). The MDE is reported next to the
               observed effect so the NULL-vs-INCONCLUSIVE boundary is
               checkable (C4 power note: detecting an effect at one-sided
               (1-alpha) needs roughly mean >= bar + z*SE).
- NON-VOTING   the mechanical rule output is recorded but does NOT stand as
               a vote: controls missing/failed (S-REL R2 admissibility) or a
               declared substrate/precondition disqualifier (the C2/C3
               EXPLORATORY_NON_VOTING pattern).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from statistics import NormalDist
from typing import Any, Mapping, Sequence

from renquant_orchestrator.expkit.stats import SmallNExactResult, multi_seed_unanimity

__all__ = [
    "GateDecision",
    "Outcome",
    "decide",
    "mde_one_sided",
    "verdicts_md_row",
]


class Outcome(str, Enum):
    GO = "GO"
    KILL = "KILL"
    NULL = "NULL"
    INCONCLUSIVE = "INCONCLUSIVE"
    NON_VOTING = "NON-VOTING"

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


def mde_one_sided(se: float, *, threshold: float, alpha_one_sided: float) -> float:
    """Minimum detectable effect: the smallest true mean that would clear the
    one-sided GO bar in expectation — bar + z_(1-alpha) * SE (the C4 power
    note, generalized). Reported in every decision so INCONCLUSIVE-vs-NULL is
    mechanical."""
    z = NormalDist().inv_cdf(1.0 - alpha_one_sided)
    return float(threshold + z * se)


@dataclass
class GateDecision:
    outcome: Outcome
    mechanical_outcome: Outcome
    rule: str
    n_dates: int
    floor_met: bool
    observed_mean: float | None
    mde: float | None
    power: dict[str, Any]
    unanimity_go: dict[str, Any]
    unanimity_kill: dict[str, Any]
    method: str
    requires_null_control: bool
    controls_ok: bool | None
    non_voting_reasons: tuple[str, ...] = ()
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "mechanical_outcome": self.mechanical_outcome.value,
            "rule": self.rule,
            "n_dates": self.n_dates,
            "floor_met": self.floor_met,
            "observed_mean": self.observed_mean,
            "mde": self.mde,
            "power": self.power,
            "unanimity_go": self.unanimity_go,
            "unanimity_kill": self.unanimity_kill,
            "method": self.method,
            "requires_null_control": self.requires_null_control,
            "controls_ok": self.controls_ok,
            "non_voting_reasons": list(self.non_voting_reasons),
            "detail": self.detail,
        }


def _mechanical_from_bootstrap(
    stats_result: Mapping[str, Any],
    *,
    threshold: float,
    kill_threshold: float,
    min_decision_dates: int,
    alpha_one_sided: float,
    observed_mean: float | None,
) -> tuple[Outcome, dict[str, Any], dict[str, Any], dict[str, Any], float | None, bool]:
    by_seed = stats_result["by_seed"]
    n_dates = int(stats_result["n_dates"])
    floor_met = n_dates >= min_decision_dates
    u_go = multi_seed_unanimity(by_seed, lambda b: b["lb_one_sided"] > threshold)
    u_kill = multi_seed_unanimity(by_seed, lambda b: b["ub_one_sided"] < kill_threshold)
    ses = [b["boot_se"] for b in by_seed.values() if b is not None]
    se_max = max(ses) if ses else None
    z = NormalDist().inv_cdf(1.0 - alpha_one_sided)
    mde = (
        mde_one_sided(se_max, threshold=threshold, alpha_one_sided=alpha_one_sided)
        if se_max is not None
        else None
    )
    powered = se_max is not None and (z * se_max) <= threshold
    power = {
        "z_one_sided": float(z),
        "boot_se_max": se_max,
        "z_times_se": (float(z * se_max) if se_max is not None else None),
        "powered_at_decision_scale": bool(powered),
        "criterion": "z*SE_max <= bar",
    }
    if u_go["unanimous_true"] and floor_met:
        mech = Outcome.GO
    elif u_kill["unanimous_true"]:
        mech = Outcome.KILL
    elif powered and floor_met:
        mech = Outcome.NULL
    else:
        mech = Outcome.INCONCLUSIVE
    return mech, power, u_go, u_kill, mde, floor_met


def _mechanical_from_exact(
    stats_result: Mapping[str, Any],
    *,
    threshold: float,
    alpha_one_sided: float,
) -> tuple[Outcome, dict[str, Any], dict[str, Any], dict[str, Any], float | None, bool]:
    exact: SmallNExactResult = stats_result["exact"]
    # read the EXPLICITLY oriented p-values, never the raw tail masses —
    # exact_block_tail_masses and exact_sign_test define p_ge/p_le with
    # opposite GO/KILL orientation (see SmallNExactResult docstring)
    go_fired = exact.go_evidence_p <= alpha_one_sided
    kill_fired = exact.kill_evidence_p <= alpha_one_sided
    u_go = {"per_seed": {"exact": go_fired}, "unanimous_true": go_fired,
            "unanimous_false": not go_fired, "split": False, "n_seeds": 0}
    u_kill = {"per_seed": {"exact": kill_fired}, "unanimous_true": kill_fired,
              "unanimous_false": not kill_fired, "split": False, "n_seeds": 0}
    power = {
        "z_one_sided": None,
        "boot_se_max": None,
        "z_times_se": None,
        "powered_at_decision_scale": False,
        "criterion": (
            "small-n exact branch: never powered at decision scale; a "
            "non-detection here is INCONCLUSIVE, never NULL (V3 method note)"
        ),
    }
    if go_fired and not kill_fired:
        mech = Outcome.GO
    elif kill_fired and not go_fired:
        mech = Outcome.KILL
    else:
        mech = Outcome.INCONCLUSIVE
    return mech, power, u_go, u_kill, None, False


def decide(
    stats_result: Mapping[str, Any],
    *,
    threshold: float,
    min_decision_dates: int,
    alpha_one_sided: float,
    controls_ok: bool | None,
    kill_threshold: float | None = None,
    observed_mean: float | None = None,
    non_voting_reasons: Sequence[str] = (),
) -> GateDecision:
    """The frozen mechanical rule + the admissibility overlay.

    `stats_result` is the output of `stats.bootstrap_or_exact`. The
    mechanical outcome is always computed and recorded; the GOVERNING
    outcome is NON-VOTING whenever (a) controls were not run
    (controls_ok=None), (b) controls failed (S-REL R2: a negative verdict
    from a harness with no passing controls is inadmissible), (c) a declared
    non-voting reason exists (substrate disqualifier / unmet precondition —
    the C2 EXPLORATORY_NON_VOTING pattern), or (d) the small-n exact branch
    is in effect and its mandatory null control has not passed.
    """
    kill_threshold = threshold if kill_threshold is None else kill_threshold
    method = stats_result.get("method", "block_bootstrap")
    if method == "block_bootstrap":
        mech, power, u_go, u_kill, mde, floor_met = _mechanical_from_bootstrap(
            stats_result,
            threshold=threshold,
            kill_threshold=kill_threshold,
            min_decision_dates=min_decision_dates,
            alpha_one_sided=alpha_one_sided,
            observed_mean=observed_mean,
        )
    elif method == "exact":
        mech, power, u_go, u_kill, mde, floor_met = _mechanical_from_exact(
            stats_result, threshold=threshold, alpha_one_sided=alpha_one_sided
        )
    else:  # pragma: no cover - defensive
        raise ValueError(f"unknown stats method {method!r}")

    reasons = list(non_voting_reasons)
    if controls_ok is None:
        reasons.append("controls_not_run: no verdict without a positive plant AND a true null")
    elif not controls_ok:
        reasons.append("controls_failed: verdict inadmissible per S-REL R2")
    requires_null = bool(stats_result.get("requires_null_control", False))
    governing = Outcome.NON_VOTING if reasons else mech

    rule = (
        f"GO iff one-sided(1-{alpha_one_sided:.6f}) LB > {threshold} on ALL seeds "
        f"AND n >= {min_decision_dates}; KILL iff UB < {kill_threshold} on ALL seeds; "
        "else NULL if powered at decision scale (z*SE_max <= bar) and floor met, "
        "else INCONCLUSIVE; NON-VOTING overlay if controls/preconditions unmet"
    )
    return GateDecision(
        outcome=governing,
        mechanical_outcome=mech,
        rule=rule,
        n_dates=int(stats_result["n_dates"]),
        floor_met=bool(floor_met),
        observed_mean=observed_mean,
        mde=mde,
        power=power,
        unanimity_go=u_go,
        unanimity_kill=u_kill,
        method=method,
        requires_null_control=requires_null,
        controls_ok=controls_ok,
        non_voting_reasons=tuple(reasons),
        detail={k: v for k, v in stats_result.items() if k != "exact"},
    )


def _cell(text: str) -> str:
    return " ".join(str(text).replace("|", r"\|").split())


def verdicts_md_row(
    *,
    date: str,
    id_source: str,
    verdict: str,
    rationale: str,
    evidence_boundary: str,
    verification: str = "PROVISIONAL",
    verification_note: str = "(R1 default)",
    reopening_condition: str,
) -> str:
    """One `doc/research/VERDICTS.md` ledger row, matching the seeded format:

    | Date | ID / source | Verdict | Evidence boundary (one phrase) |
      Verification | Reopening condition |

    Verdict cell = `**<VERDICT>** — <one-line rationale with the load-bearing
    numbers>`; Verification cell = `**<STATUS>** (<note>)`.
    """
    verdict_cell = f"**{_cell(verdict)}** — {_cell(rationale)}"
    verification_cell = f"**{_cell(verification)}**"
    if verification_note:
        verification_cell += f" {_cell(verification_note)}"
    return (
        f"| {_cell(date)} | {_cell(id_source)} | {verdict_cell} | "
        f"{_cell(evidence_boundary)} | {verification_cell} | {_cell(reopening_condition)} |"
    )
