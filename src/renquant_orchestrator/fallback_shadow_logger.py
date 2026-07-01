"""Best-of-last-10-days fallback — SHADOW-LOGGING mode (#210, design
``doc/design/2026-06-30-model-freshness-governance.md`` §5.6 + rollout Phase 4).

This decides which model the best-of-recent fallback **WOULD** select — and logs
that decision — WITHOUT promoting anything. It is the honest §5.6 path: build the
prospective point-in-time record going forward so a later held-out confirmation
(§5.2) can authorize the real auto-promote. Flipping to real promotion needs that
shadow evidence + a point-in-time replay + Codex/operator sign-off; nothing here
touches a pin, model, config, broker, risk cap, or sizing.

The fallback would fire **only** if ALL of these hold (design §3, §4.3, §7):

  0. the prod model's fast-axis freshness is **DETERMINATE** — an UNKNOWN prod
     data cutoff yields a separate ``indeterminate`` decision that authorizes
     NOTHING (Codex r7): unknown freshness must not justify a replacement;
  1. the prod model **breached** the fast-axis freshness ceiling (or a slow axis
     is off-SLA);
  2. the **newest** retrain within the window **failed for an ENUMERATED
     INFRASTRUCTURE reason** (timeout / config-path / artifact-not-found) — NOT
     substance / leakage / placebo / recipe-mismatch / unknown, which stay
     FAIL-CLOSED;
  3. among the recent (≤ N-day) candidates there is one that is point-in-time
     available (§5.0-i-a), failed only for an infra reason, is comparable to the
     production recipe contract (§4.3.1), clears the basic-integrity floor
     (§4.3.2) AND the recomputed OOS economic floor (§4.3.3, SPY-benchmark
     REQUIRED), and has a computable selection score (§4.3.4).

**Selection is OUTCOME-INDEPENDENT (Codex r7).** The winner is the **NEWEST
ELIGIBLE** candidate (freshest recency date, tie-broken by freshest data cutoff
then artifact id) — a rule fixed BEFORE the evaluation outcome is seen. It is
explicitly **not** the maximum OOS Sharpe: picking the max over N noisy,
dependent (overlapping-retrain) candidates is winner's-curse / multiple-testing
bias that would overstate what a pre-registered fallback could realize. The OOS
floor stays a per-candidate PASS/FAIL eligibility gate, never a ranker.

If any condition fails, the decision is ``would_promote=False`` with an explicit
``would_NOT_because``. Every decision is appended (idempotently) to a JSONL log.

**These logs are OBSERVE-ONLY EVIDENCE, not policy-authorizing.** Before they may
choose policy, a pre-registration must fix the candidate-generation count, a
common untouched evaluation window, the primary net endpoint, the cost model,
dependence-aware resampling, and a one-time acceptance rule (design §5). Shadow
containment prevents capital impact; it does not make biased evidence useful.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

from renquant_orchestrator.model_staging_registry import (
    CATEGORY_INFRA,
    CATEGORY_NONE,
    ModelStagingRegistry,
    StagingCandidate,
    _as_of_date,
)

# Schema v2 (Codex r7): outcome-independent (newest-eligible) selection; SPY-
# required OOS floor; recipe-mismatch fail-closed; indeterminate-cutoff decision.
SCHEMA_VERSION = 2
DEFAULT_CEILING_DAYS = 28   # fast-axis ceiling (design §3; candidate, gated by §5)
DEFAULT_WINDOW_DAYS = 10    # best-of-recent window (design §4.3.4; candidate)

# The pre-registered, outcome-INDEPENDENT selection rule (Codex r7): pick the
# newest eligible candidate, NOT the maximum score. Recorded on every decision.
SELECTION_RULE = "newest_eligible_outcome_independent"


@dataclass(frozen=True)
class ProdModelState:
    """The live model's freshness, as the monitor would observe it (§2, §3)."""

    data_cutoff: date | None
    as_of: date
    ceiling_days: int = DEFAULT_CEILING_DAYS
    slow_axis_off_sla: bool = False  # any actually-used slow source off its SLA (§2)
    recipe_fingerprint: str | None = None  # prod recipe contract, for comparability (§4.3.1)

    @property
    def fast_axis_age_days(self) -> int | None:
        if self.data_cutoff is None:
            return None
        return (self.as_of - self.data_cutoff).days

    @property
    def indeterminate(self) -> bool:
        """Prod freshness is INDETERMINATE when the fast-axis data cutoff is
        UNKNOWN (Codex r7). An unknown cutoff must NOT be treated as a breach and
        must NOT authorize a hypothetical replacement — it is reported as its own
        decision (``would_promote=False``, ``reason="indeterminate"``). Fail-safe:
        we never promote on an unknown."""
        return self.data_cutoff is None

    @property
    def breached(self) -> bool:
        """Breached iff a DETERMINATE staleness signal fires: the KNOWN fast-axis
        age exceeds the ceiling, OR a slow axis is off its SLA. An UNKNOWN
        fast-axis cutoff is NOT a breach — it is :attr:`indeterminate` and is
        handled separately, because unknown freshness cannot authorize a
        replacement."""
        age = self.fast_axis_age_days
        if age is not None and age > self.ceiling_days:
            return True
        return self.slow_axis_off_sla


def clears_oos_floor(quality: Mapping[str, Any] | None) -> bool:
    """Independent OOS economic floor (design §4.3.3). The **SPY benchmark
    comparator is REQUIRED** (Codex r7): OOS Sharpe must exist, a SPY Sharpe
    comparator must exist, AND OOS Sharpe ``>= SPY`` Sharpe. A candidate with **no
    SPY comparator FAILS CLOSED** — an unbenchmarked OOS Sharpe cannot clear a
    benchmark-required gate (the earlier "no comparator → passes" behaviour
    contradicted the gate and is removed). Net-of-cost return, when present, must
    be non-negative. Placebo/leakage contamination is handled upstream by the
    failure classification (those categories fail closed)."""
    if not quality:
        return False
    oos = quality.get("oos_sharpe")
    if isinstance(oos, bool) or not isinstance(oos, (int, float)):
        return False
    spy = quality.get("spy_sharpe")
    if isinstance(spy, bool) or not isinstance(spy, (int, float)):
        return False  # benchmark REQUIRED — no comparator → fail closed
    if float(oos) < float(spy):
        return False
    net = quality.get("net_return")
    if isinstance(net, (int, float)) and not isinstance(net, bool):
        if float(net) < 0:
            return False
    return True


def candidate_ineligibility(
    cand: StagingCandidate,
    as_of: date | datetime,
    *,
    prod_recipe_fingerprint: str | None = None,
) -> str | None:
    """Return ``None`` if ``cand`` is eligible for the best-of-recent fallback,
    else a short machine reason token. Order matters: the first failing check wins.
    """
    if cand.parse_error is not None:
        return "parse_error"
    if not cand.is_available_at(as_of):
        return "not_point_in_time_available"  # §5.0-i-a: missing/future availability
    if cand.failure_category != CATEGORY_INFRA:
        # substance / leakage / placebo / recipe-mismatch / unknown → fail-closed
        # (§4.3.1); a gate-passing candidate ("none") is handled by the normal
        # promote path, not by the fallback pool.
        return f"failure_class_fail_closed:{cand.failure_category}"
    if prod_recipe_fingerprint is not None:
        # Codex r7 comparability gate: when the production recipe contract is
        # known, an infra-failed candidate must carry a recipe fingerprint that
        # MATCHES it. A missing or divergent fingerprint means the candidate is
        # not comparable to the production contract → ineligible (never rescued).
        if not cand.recipe_fingerprint or cand.recipe_fingerprint != prod_recipe_fingerprint:
            return "recipe_not_comparable"
    if not cand.passes_integrity_floor:
        return "integrity_floor_failed"  # §4.3.2
    if not clears_oos_floor(cand.quality):
        return "oos_floor_not_cleared"  # §4.3.3 (SPY comparator required)
    if cand.selection_score is None:
        return "no_selection_score"  # §4.3.4 — unscoreable
    return None


@dataclass(frozen=True)
class ShadowDecision:
    """One shadow decision. The first eight fields (through ``selection_rule``,
    the outcome-independent selection rule fixed before the outcome is seen) are
    the pre-registered log schema; the rest is audit context. PROMOTES NOTHING."""

    as_of: str
    would_promote: bool
    candidate: str | None
    reason: str
    failure_class: str
    selection_score: float | None
    would_NOT_because: str | None
    selection_rule: str = SELECTION_RULE
    schema_version: int = SCHEMA_VERSION
    window_days: int = DEFAULT_WINDOW_DAYS
    ceiling_days: int = DEFAULT_CEILING_DAYS
    prod: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)

    def to_record(self) -> dict:
        return asdict(self)


def _decision(
    prod: ProdModelState,
    window_days: int,
    *,
    would_promote: bool,
    candidate: str | None,
    reason: str,
    failure_class: str,
    selection_score: float | None,
    would_NOT_because: str | None,
    meta: dict | None = None,
) -> ShadowDecision:
    return ShadowDecision(
        as_of=prod.as_of.isoformat(),
        would_promote=would_promote,
        candidate=candidate,
        reason=reason,
        failure_class=failure_class,
        selection_score=selection_score,
        would_NOT_because=would_NOT_because,
        selection_rule=SELECTION_RULE,
        window_days=window_days,
        ceiling_days=prod.ceiling_days,
        prod={
            "data_cutoff": prod.data_cutoff.isoformat() if prod.data_cutoff else None,
            "fast_axis_age_days": prod.fast_axis_age_days,
            "slow_axis_off_sla": prod.slow_axis_off_sla,
            "breached": prod.breached,
            "indeterminate": prod.indeterminate,
            "recipe_fingerprint": prod.recipe_fingerprint,
        },
        meta=meta or {},
    )


def shadow_decision(
    registry: ModelStagingRegistry,
    prod: ProdModelState,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    family: str | None = None,
) -> ShadowDecision:
    """Compute the shadow decision. Promotes nothing; returns a
    :class:`ShadowDecision` describing what the fallback WOULD do."""
    as_of = prod.as_of

    # (0) Prod freshness INDETERMINATE (unknown fast-axis cutoff) → authorize
    #     nothing. An unknown cutoff is NOT a breach and cannot justify a
    #     hypothetical replacement (Codex r7); it is reported separately.
    if prod.indeterminate:
        return _decision(
            prod, window_days,
            would_promote=False, candidate=None,
            reason="indeterminate", failure_class=CATEGORY_NONE,
            selection_score=None,
            would_NOT_because="prod_cutoff_unknown",
        )

    # (1) Prod still fresh → no fallback needed.
    if not prod.breached:
        return _decision(
            prod, window_days,
            would_promote=False, candidate=None,
            reason="fallback_not_needed", failure_class=CATEGORY_NONE,
            selection_score=None,
            would_NOT_because="prod_model_within_ceiling",
        )

    recent = registry.within_last_days(
        window_days, as_of=as_of, family=family, require_available=True
    )

    # (2) No candidate within the window (e.g. newest retrain > N days old).
    if not recent:
        return _decision(
            prod, window_days,
            would_promote=False, candidate=None,
            reason="fallback_declined", failure_class=CATEGORY_NONE,
            selection_score=None,
            would_NOT_because=f"no_candidate_within_{window_days}d",
        )

    newest = recent[0]
    newest_cat = newest.failure_category

    # (3) The newest retrain must have failed for an ENUMERATED INFRA reason for
    #     the fallback to even consider firing.
    if newest_cat == CATEGORY_NONE:
        return _decision(
            prod, window_days,
            would_promote=False, candidate=None,
            reason="fallback_not_needed", failure_class=CATEGORY_NONE,
            selection_score=None,
            would_NOT_because="newest_retrain_passed_gate_use_normal_promote",
            meta={"newest_candidate": newest.artifact_id},
        )
    if newest_cat != CATEGORY_INFRA:
        # substance / leakage / placebo / unknown → fail closed.
        return _decision(
            prod, window_days,
            would_promote=False, candidate=None,
            reason="fallback_declined", failure_class=newest_cat,
            selection_score=None,
            would_NOT_because=f"newest_retrain_failed_{newest_cat}_fail_closed",
            meta={
                "newest_candidate": newest.artifact_id,
                "newest_raw_failure_class": newest.raw_failure_class,
            },
        )

    # (4) Newest failed infra → build the eligible pool (infra-only + comparable
    #     recipe + integrity + OOS floor + scoreable), then select.
    pool: list[StagingCandidate] = []
    rejected: dict[str, str] = {}
    for c in recent:
        why = candidate_ineligibility(
            c, as_of, prod_recipe_fingerprint=prod.recipe_fingerprint
        )
        if why is None:
            pool.append(c)
        else:
            rejected[c.artifact_id] = why

    if not pool:
        return _decision(
            prod, window_days,
            would_promote=False, candidate=None,
            reason="fallback_declined", failure_class=CATEGORY_INFRA,
            selection_score=None,
            would_NOT_because="no_eligible_candidate_cleared_floors",
            meta={"newest_candidate": newest.artifact_id, "rejected": rejected},
        )

    # OUTCOME-INDEPENDENT selection (Codex r7): pick the NEWEST eligible candidate,
    # NOT the maximum selection score. Ranking N noisy, dependent (overlapping-
    # retrain) candidates by the same OOS metric that declares the winner is
    # winner's-curse / multiple-testing bias. The rule is fixed before the outcome
    # is seen: freshest recency date, tie-broken by freshest data cutoff then
    # artifact id. The OOS floor remains a per-candidate PASS/FAIL gate, not a
    # ranker. Stable sorts applied in reverse priority order.
    pool.sort(key=lambda c: c.artifact_id)
    pool.sort(key=lambda c: c.data_cutoff or date.min, reverse=True)
    pool.sort(key=lambda c: c.recency_date() or date.min, reverse=True)
    winner = pool[0]
    return _decision(
        prod, window_days,
        would_promote=True, candidate=winner.artifact_id,
        reason=f"newest_eligible_within_{window_days}d_infra_fallback",
        failure_class=CATEGORY_INFRA,
        selection_score=winner.selection_score,
        would_NOT_because=None,
        meta={
            "newest_candidate": newest.artifact_id,
            "selection_rule": SELECTION_RULE,
            # Multiplicity context for a later pre-registered analysis: these
            # candidates are DEPENDENT (overlapping retrains), not independent
            # draws, and the raw would_promote rate is NOT policy-authorizing
            # until §5's pre-registration (candidate-generation count, common
            # untouched window, primary net endpoint, cost model, dependence-aware
            # resampling, one-time acceptance rule) lands.
            "n_candidates_considered": len(pool),
            "n_recent_in_window": len(recent),
            "candidates_are_dependent": True,
            "not_policy_authorizing": (
                "shadow evidence only — see design §5 pre-registration before "
                "using these logs to choose policy"
            ),
            "winner": {
                "artifact_id": winner.artifact_id,
                "artifact_path": winner.artifact_path,
                "data_cutoff": winner.data_cutoff.isoformat() if winner.data_cutoff else None,
                "trained_date": winner.trained_date.isoformat() if winner.trained_date else None,
                "raw_failure_class": winner.raw_failure_class,
                "recipe_fingerprint": winner.recipe_fingerprint,
                "selection_score": winner.selection_score,
            },
            "pool": [c.artifact_id for c in pool],
            "rejected": rejected,
            "note": "SHADOW ONLY — nothing promoted",
        },
    )


def append_shadow_decision(log_path: str | Path, decision: ShadowDecision) -> bool:
    """Append ``decision`` to the JSONL ``log_path``. Idempotent on
    ``(as_of, would_promote, candidate)``: re-logging the same decision for the
    same day is a no-op. Returns ``True`` if a new line was appended, ``False`` if
    an identical decision already existed. Writes ONLY this log file.
    """
    path = Path(log_path)
    record = decision.to_record()
    key = (record["as_of"], record["would_promote"], record["candidate"])
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                existing = json.loads(line)
            except json.JSONDecodeError:
                continue
            if (
                existing.get("as_of"),
                existing.get("would_promote"),
                existing.get("candidate"),
            ) == key:
                return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return True


def run_shadow(
    staging_dir: str | Path,
    prod: ProdModelState,
    *,
    log_path: str | Path,
    window_days: int = DEFAULT_WINDOW_DAYS,
    family: str | None = None,
) -> ShadowDecision:
    """Scan → decide → append. Observe-only end to end."""
    registry = ModelStagingRegistry.scan(staging_dir, family=family)
    decision = shadow_decision(registry, prod, window_days=window_days, family=family)
    append_shadow_decision(log_path, decision)
    return decision


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--staging-dir", required=True, help="dir holding *.staging.json sidecars")
    p.add_argument("--prod-cutoff", default=None,
                   help="prod model fast-axis data cutoff (YYYY-MM-DD); omit if unknown "
                        "(unknown → an 'indeterminate' decision that promotes nothing)")
    p.add_argument("--prod-recipe-fingerprint", default=None,
                   help="prod recipe-contract fingerprint; when set, candidates must match "
                        "it to be comparable (§4.3.1)")
    p.add_argument("--as-of", default=None, help="decision date (YYYY-MM-DD); default today")
    p.add_argument("--log-path", required=True, help="JSONL shadow-decision log to append to")
    p.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    p.add_argument("--ceiling-days", type=int, default=DEFAULT_CEILING_DAYS)
    p.add_argument("--slow-axis-off-sla", action="store_true",
                   help="mark a slow-axis (quarterly) source as off its SLA (§2)")
    p.add_argument("--family", default=None, help="restrict to one model family")
    args = p.parse_args(argv)

    as_of = date.fromisoformat(args.as_of) if args.as_of else datetime.now().date()
    prod = ProdModelState(
        data_cutoff=date.fromisoformat(args.prod_cutoff) if args.prod_cutoff else None,
        as_of=as_of,
        ceiling_days=args.ceiling_days,
        slow_axis_off_sla=args.slow_axis_off_sla,
        recipe_fingerprint=args.prod_recipe_fingerprint,
    )
    decision = run_shadow(
        args.staging_dir, prod, log_path=args.log_path,
        window_days=args.window_days, family=args.family,
    )
    print(json.dumps(decision.to_record(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
