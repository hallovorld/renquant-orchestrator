"""Best-of-last-10-days fallback — SHADOW-LOGGING mode (#210, design
``doc/design/2026-06-30-model-freshness-governance.md`` §5.6 + rollout Phase 4).

This decides which model the best-of-recent fallback **WOULD** select — and logs
that decision — WITHOUT promoting anything. It is the honest §5.6 path: build the
prospective point-in-time record going forward so a later held-out confirmation
(§5.2) can authorize the real auto-promote. Flipping to real promotion needs that
shadow evidence + a point-in-time replay + Codex/operator sign-off; nothing here
touches a pin, model, config, broker, risk cap, or sizing.

The fallback would fire **only** if ALL of these hold (design §3, §4.3, §7):

  1. the prod model **breached** the fast-axis freshness ceiling (or a slow axis
     is off-SLA);
  2. the **newest** retrain within the window **failed for an ENUMERATED
     INFRASTRUCTURE reason** (timeout / config-path / artifact-not-found /
     recipe-mismatch) — NOT substance / leakage / placebo / unknown, which stay
     FAIL-CLOSED;
  3. among the recent (≤ N-day) candidates there is one that is point-in-time
     available (§5.0-i-a), failed only for an infra reason, clears the
     basic-integrity floor (§4.3.2) AND the recomputed OOS economic floor
     (§4.3.3), and has a computable pre-registered selection score (§4.3.4).

The winner is the highest selection score, tie-broken by freshest data cutoff then
artifact id. If any condition fails, the decision is ``would_promote=False`` with an
explicit ``would_NOT_because``. Every decision is appended (idempotently) to a
JSONL log.
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

SCHEMA_VERSION = 1
DEFAULT_CEILING_DAYS = 28   # fast-axis ceiling (design §3; candidate, gated by §5)
DEFAULT_WINDOW_DAYS = 10    # best-of-recent window (design §4.3.4; candidate)


@dataclass(frozen=True)
class ProdModelState:
    """The live model's freshness, as the monitor would observe it (§2, §3)."""

    data_cutoff: date | None
    as_of: date
    ceiling_days: int = DEFAULT_CEILING_DAYS
    slow_axis_off_sla: bool = False  # any actually-used slow source off its SLA (§2)

    @property
    def fast_axis_age_days(self) -> int | None:
        if self.data_cutoff is None:
            return None
        return (self.as_of - self.data_cutoff).days

    @property
    def breached(self) -> bool:
        """Breached iff the fast axis is older than the ceiling OR a slow axis is
        off-SLA. An UNKNOWN prod cutoff is treated as breached (can't confirm
        fresh → fail toward the fallback path, which itself stays fail-closed
        unless a clean infra candidate exists)."""
        age = self.fast_axis_age_days
        if age is None:
            return True
        return age > self.ceiling_days or self.slow_axis_off_sla


def clears_oos_floor(quality: Mapping[str, Any] | None) -> bool:
    """Independent OOS economic floor (design §4.3.3): OOS Sharpe must exist and be
    ``>= SPY`` Sharpe (when a SPY comparator is present), and net-of-cost return —
    when present — must be non-negative. Placebo/leakage contamination is handled
    upstream by the failure classification (those categories fail closed)."""
    if not quality:
        return False
    oos = quality.get("oos_sharpe")
    if isinstance(oos, bool) or not isinstance(oos, (int, float)):
        return False
    spy = quality.get("spy_sharpe")
    if isinstance(spy, (int, float)) and not isinstance(spy, bool):
        if float(oos) < float(spy):
            return False
    net = quality.get("net_return")
    if isinstance(net, (int, float)) and not isinstance(net, bool):
        if float(net) < 0:
            return False
    return True


def candidate_ineligibility(cand: StagingCandidate, as_of: date | datetime) -> str | None:
    """Return ``None`` if ``cand`` is eligible for the best-of-recent fallback,
    else a short machine reason token. Order matters: the first failing check wins.
    """
    if cand.parse_error is not None:
        return "parse_error"
    if not cand.is_available_at(as_of):
        return "not_point_in_time_available"  # §5.0-i-a: missing/future availability
    if cand.failure_category != CATEGORY_INFRA:
        # substance / leakage / placebo / unknown → fail-closed (§4.3.1); a
        # gate-passing candidate ("none") is handled by the normal promote path,
        # not by the fallback pool.
        return f"failure_class_fail_closed:{cand.failure_category}"
    if not cand.passes_integrity_floor:
        return "integrity_floor_failed"  # §4.3.2
    if not clears_oos_floor(cand.quality):
        return "oos_floor_not_cleared"  # §4.3.3
    if cand.selection_score is None:
        return "no_selection_score"  # §4.3.4 — unscoreable
    return None


@dataclass(frozen=True)
class ShadowDecision:
    """One shadow decision. The first seven fields are the pre-registered log
    schema; the rest is audit context. PROMOTES NOTHING."""

    as_of: str
    would_promote: bool
    candidate: str | None
    reason: str
    failure_class: str
    selection_score: float | None
    would_NOT_because: str | None
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
        window_days=window_days,
        ceiling_days=prod.ceiling_days,
        prod={
            "data_cutoff": prod.data_cutoff.isoformat() if prod.data_cutoff else None,
            "fast_axis_age_days": prod.fast_axis_age_days,
            "slow_axis_off_sla": prod.slow_axis_off_sla,
            "breached": prod.breached,
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

    # (4) Newest failed infra → build the eligible pool (infra-only + integrity +
    #     OOS floor + scoreable), select the best.
    pool: list[StagingCandidate] = []
    rejected: dict[str, str] = {}
    for c in recent:
        why = candidate_ineligibility(c, as_of)
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

    # Highest selection score, tie-broken by freshest data cutoff then artifact id.
    pool.sort(key=lambda c: c.artifact_id)
    pool.sort(
        key=lambda c: (c.selection_score, c.data_cutoff or date.min),
        reverse=True,
    )
    winner = pool[0]
    return _decision(
        prod, window_days,
        would_promote=True, candidate=winner.artifact_id,
        reason=f"best_of_{window_days}d_infra_fallback",
        failure_class=CATEGORY_INFRA,
        selection_score=winner.selection_score,
        would_NOT_because=None,
        meta={
            "newest_candidate": newest.artifact_id,
            "winner": {
                "artifact_id": winner.artifact_id,
                "artifact_path": winner.artifact_path,
                "data_cutoff": winner.data_cutoff.isoformat() if winner.data_cutoff else None,
                "trained_date": winner.trained_date.isoformat() if winner.trained_date else None,
                "raw_failure_class": winner.raw_failure_class,
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
                   help="prod model fast-axis data cutoff (YYYY-MM-DD); omit if unknown")
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
    )
    decision = run_shadow(
        args.staging_dir, prod, log_path=args.log_path,
        window_days=args.window_days, family=args.family,
    )
    print(json.dumps(decision.to_record(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
