"""Model freshness enforcement — read-only recommendation engine.

Extends the observe-only ``model_freshness_monitor`` with ACTIONABLE fallback
recommendations when the current prod panel is stale (>28d data-cutoff age).

Implements the orchestrator side of governance §4 Pillar 1 (freshness ceiling) and
prepares the recommendation surface for Pillar 3 (best-of-recent fallback, DEFERRED —
auto-promotion is NOT enabled; this module only RECOMMENDS, never mutates).

The enforcement logic:

1. Reads the current prod panel's freshness (data-cutoff-keyed, via the monitor).
2. If the model is NOT stale, returns ``action="none"``.
3. If stale, scans a configurable search path for recent candidate artifacts
   produced within the last ``--window-days`` (default 10).
4. Classifies each candidate's WF-gate metadata:
   - ``gate_passed`` — the candidate passed the strict gate.
   - ``infra_failure`` — the gate failed for an enumerated MECHANICAL/INFRA reason
     (§4.3.1: timeout, artifact-path-not-found, scorer-kind parity).
   - ``substance_failure`` — the gate failed for a QUALITY/SUBSTANCE reason
     (§4.3.1: sub-SPY, placebo, leakage, recipe mismatch, unknown).
5. Picks the best recommendation:
   - ``promote_passing`` — a gate-passing candidate exists; recommend it.
   - ``promote_freshest`` — no gate-passing candidate, but a fresh candidate with
     ONLY infra failures exists (Pillar 3 territory, DEFERRED).
   - ``none`` — no suitable candidates found.

OBSERVE-ONLY: this module reads + classifies + recommends. It NEVER retrains,
promotes, swaps pins, or changes any artifact. The recommendation is a structured
result that an operator (or a future automated Pillar-3 pipeline) acts on.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
import sys
from typing import Optional

from renquant_common import Job, Pipeline, Task

from .model_freshness_monitor import (
    ArtifactFreshness,
    DATA_CUTOFF_FIELDS,
    DEFAULT_BREACH_DAYS,
    FreshnessPolicy,
    PROD_FAST_POLICY,
    TIER_BREACH,
    TIER_ESCALATE,
    TIER_UNKNOWN,
    _TIER_RANK,
    default_prod_panel_path,
    parse_as_of,
    read_artifact_freshness,
    resolve_now,
)
from .runtime_paths import default_repo_root

DEFAULT_REPO_ROOT = default_repo_root()
DEFAULT_WINDOW_DAYS = 10

INFRA_FAILURE_KEYWORDS = frozenset({
    "timeout",
    "paralleltimeouterror",
    "artifact-not-found",
    "filenotfounderror",
    "path-not-found",
    "kind-parity",
    "parity-mismatch",
    "scorer-kind",
    "config-path",
})

ACTION_NONE = "none"
ACTION_PROMOTE_PASSING = "promote_passing"
ACTION_PROMOTE_FRESHEST = "promote_freshest"


def _parse_date_from_artifact(data: dict) -> str | None:
    for field_name in DATA_CUTOFF_FIELDS:
        value = data.get(field_name)
        if value is not None:
            text = str(value).strip()[:10]
            if len(text) >= 10:
                return text
    return None


def _classify_gate_failure(wf_meta: dict | None) -> tuple[bool, str, str]:
    """Classify a WF-gate result.

    Returns ``(gate_passed, failure_class, detail)``:
    - ``failure_class`` is ``"none"`` if passed, ``"infra"`` for mechanical,
      ``"substance"`` for quality, ``"no_gate"`` if no metadata.
    """
    if wf_meta is None or not isinstance(wf_meta, dict):
        return False, "no_gate", "no wf_gate_metadata present"

    if wf_meta.get("passed") is True:
        return True, "none", "gate passed"

    failure_reasons: list[str] = []
    for key in ("failure_reason", "reject_reason", "detail", "error"):
        val = wf_meta.get(key)
        if val:
            failure_reasons.append(str(val).lower())
    reason_text = " ".join(failure_reasons)

    if any(kw in reason_text for kw in INFRA_FAILURE_KEYWORDS):
        return False, "infra", f"infra failure: {reason_text[:200]}"

    gate_error = wf_meta.get("error")
    if gate_error and any(kw in str(gate_error).lower() for kw in INFRA_FAILURE_KEYWORDS):
        return False, "infra", f"infra error: {str(gate_error)[:200]}"

    if wf_meta.get("passed") is False:
        return False, "substance", f"substance failure: {reason_text[:200] or 'gate returned passed=false'}"

    return False, "unknown", f"unclassifiable gate result: {json.dumps(wf_meta)[:200]}"


@dataclass
class CandidateResult:
    """One candidate artifact's freshness + gate classification."""

    path: str
    freshness: ArtifactFreshness
    gate_passed: bool = False
    failure_class: str = "unknown"
    gate_detail: str = ""
    data_cutoff: Optional[str] = None
    trained_date: Optional[str] = None
    age_days: Optional[int] = None

    def as_dict(self) -> dict:
        return {
            "age_days": self.age_days,
            "data_cutoff": self.data_cutoff,
            "failure_class": self.failure_class,
            "gate_detail": self.gate_detail,
            "gate_passed": self.gate_passed,
            "path": self.path,
            "trained_date": self.trained_date,
        }


@dataclass
class EnforcementResult:
    """Structured recommendation from the enforcement check."""

    stale: bool = False
    current_age_days: Optional[int] = None
    current_tier: str = "healthy"
    action: str = ACTION_NONE
    recommended_path: Optional[str] = None
    recommended_age_days: Optional[int] = None
    gate_passed: bool = False
    failure_class: Optional[str] = None
    candidates_scanned: int = 0
    candidates_fresh: int = 0
    candidates_passing: int = 0
    detail: str = ""
    candidates: list[CandidateResult] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "action": self.action,
            "candidates_fresh": self.candidates_fresh,
            "candidates_passing": self.candidates_passing,
            "candidates_scanned": self.candidates_scanned,
            "current_age_days": self.current_age_days,
            "current_tier": self.current_tier,
            "detail": self.detail,
            "failure_class": self.failure_class,
            "gate_passed": self.gate_passed,
            "recommended_age_days": self.recommended_age_days,
            "recommended_path": self.recommended_path,
            "stale": self.stale,
        }


def scan_candidates(
    search_dirs: list[Path],
    now: datetime,
    *,
    window_days: int = DEFAULT_WINDOW_DAYS,
    policy: FreshnessPolicy = PROD_FAST_POLICY,
) -> list[CandidateResult]:
    """Scan directories for candidate panel-ltr artifacts within the time window.

    Looks for ``panel-ltr*.json`` files (excluding ``.staging.json`` and
    ``.metadata.json`` sidecars). Each candidate is read for freshness and
    gate classification.
    """
    seen: set[str] = set()
    candidates: list[CandidateResult] = []

    for search_dir in search_dirs:
        if not search_dir.is_dir():
            continue
        for path in sorted(search_dir.rglob("panel-ltr*.json")):
            if not path.is_file():
                continue
            if path.suffix != ".json":
                continue
            if path.name.endswith(".staging.json"):
                continue
            if path.name.endswith(".metadata.json"):
                continue

            resolved = str(path.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)

            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(data, dict):
                continue

            freshness = read_artifact_freshness(
                f"candidate:{path.name}", path, now, policy=policy,
            )

            if freshness.age_days is None or freshness.age_days > window_days:
                continue

            wf_meta = (
                (data.get("metadata") or {}).get("wf_gate_metadata")
                or data.get("wf_gate_metadata")
            )
            gate_passed, failure_class, gate_detail = _classify_gate_failure(wf_meta)

            candidates.append(CandidateResult(
                path=str(path),
                freshness=freshness,
                gate_passed=gate_passed,
                failure_class=failure_class,
                gate_detail=gate_detail,
                data_cutoff=freshness.binding_cutoff,
                trained_date=freshness.trained_date,
                age_days=freshness.age_days,
            ))

    candidates.sort(key=lambda c: c.age_days if c.age_days is not None else 9999)
    return candidates


def enforce(
    prod_panel_path: Path,
    search_dirs: list[Path],
    now: datetime,
    *,
    breach_days: int = DEFAULT_BREACH_DAYS,
    window_days: int = DEFAULT_WINDOW_DAYS,
    policy: FreshnessPolicy = PROD_FAST_POLICY,
) -> EnforcementResult:
    """Check the prod panel's freshness and recommend a fallback if stale.

    Returns a structured ``EnforcementResult`` with the recommended action.
    Never mutates any artifact.

    ``breach_days`` is the single source of truth for the breach threshold used
    in tiering: it always overrides ``policy.breach_days`` (all of ``policy``'s
    other fields — name/warn_days/escalate_days/require_validated_promote — are
    preserved). This keeps the two parameters from silently disagreeing when
    ``enforce`` is called directly with a non-default ``breach_days`` but the
    default ``policy`` (previously: the reported ``breach_days`` in ``detail``
    had no effect on the actual tiering, which only read ``policy.breach_days``).
    """
    result = EnforcementResult()
    policy = replace(policy, breach_days=breach_days)

    prod_freshness = read_artifact_freshness(
        "prod-panel", prod_panel_path, now, policy=policy,
    )
    result.current_age_days = prod_freshness.age_days
    result.current_tier = prod_freshness.tier

    is_stale = _TIER_RANK.get(prod_freshness.tier, 0) >= _TIER_RANK[TIER_BREACH]
    result.stale = is_stale

    if not is_stale:
        result.action = ACTION_NONE
        result.detail = (
            f"prod panel {prod_freshness.tier} "
            f"(age={prod_freshness.age_days}d, breach={breach_days}d); "
            "no enforcement needed"
        )
        return result

    candidates = scan_candidates(
        search_dirs, now, window_days=window_days, policy=policy,
    )
    result.candidates = candidates
    result.candidates_scanned = len(candidates)

    passing = [c for c in candidates if c.gate_passed]
    infra_only = [c for c in candidates if c.failure_class == "infra"]
    fresh = passing + infra_only
    result.candidates_fresh = len(fresh)
    result.candidates_passing = len(passing)

    if passing:
        best = passing[0]
        result.action = ACTION_PROMOTE_PASSING
        result.recommended_path = best.path
        result.recommended_age_days = best.age_days
        result.gate_passed = True
        result.failure_class = "none"
        result.detail = (
            f"prod panel STALE ({prod_freshness.tier}, age={prod_freshness.age_days}d); "
            f"gate-passing candidate available: {best.path} "
            f"(age={best.age_days}d)"
        )
    elif infra_only:
        best = infra_only[0]
        result.action = ACTION_PROMOTE_FRESHEST
        result.recommended_path = best.path
        result.recommended_age_days = best.age_days
        result.gate_passed = False
        result.failure_class = "infra"
        result.detail = (
            f"prod panel STALE ({prod_freshness.tier}, age={prod_freshness.age_days}d); "
            f"no gate-passing candidate; freshest infra-only-failure: {best.path} "
            f"(age={best.age_days}d) [Pillar 3 DEFERRED — recommend only]"
        )
    else:
        result.action = ACTION_NONE
        result.detail = (
            f"prod panel STALE ({prod_freshness.tier}, age={prod_freshness.age_days}d); "
            f"scanned {len(candidates)} candidates in last {window_days}d, "
            f"none gate-passing or infra-only-failure"
        )

    return result


@dataclass
class EnforcementContext:
    now: datetime
    repo_root: Path
    prod_panel_path: Path
    search_dirs: list[Path]
    breach_days: int = DEFAULT_BREACH_DAYS
    window_days: int = DEFAULT_WINDOW_DAYS
    policy: FreshnessPolicy = PROD_FAST_POLICY
    quiet: bool = False
    result: Optional[EnforcementResult] = None
    exit_code: int = 0


class EnforceTask(Task):
    def run(self, ctx: EnforcementContext) -> bool | None:
        ctx.result = enforce(
            ctx.prod_panel_path,
            ctx.search_dirs,
            ctx.now,
            breach_days=ctx.breach_days,
            window_days=ctx.window_days,
            policy=ctx.policy,
        )
        ctx.exit_code = 0 if not ctx.result.stale else (1 if ctx.result.action != ACTION_NONE else 2)
        return True


class EnforceJob(Job):
    @property
    def tasks(self) -> list[Task]:
        return [EnforceTask()]


def build_pipeline() -> Pipeline:
    return Pipeline([EnforceJob()], name="model-freshness-enforce")


def default_search_dirs(repo_root: Path) -> list[Path]:
    base = repo_root / "backtesting" / "renquant_104" / "artifacts"
    return [
        base / "staging",
        base / "prod",
        base / "sim",
    ]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Model freshness enforcement — recommend fallback when prod panel is stale."
    )
    parser.add_argument(
        "--as-of", default=None,
        help="Inject 'now' (YYYY-MM-DD or ISO datetime); defaults to UTC now.",
    )
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--prod-panel", type=Path, default=None)
    parser.add_argument(
        "--search-dir", type=Path, action="append", default=None,
        help="Directory to scan for candidate artifacts (repeatable).",
    )
    parser.add_argument("--breach-days", type=int, default=DEFAULT_BREACH_DAYS)
    parser.add_argument(
        "--window-days", type=int, default=DEFAULT_WINDOW_DAYS,
        help="Scan window: only consider candidates from the last N days.",
    )
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def build_context(args: argparse.Namespace) -> EnforcementContext:
    repo_root = args.repo_root.expanduser().resolve()
    prod_panel = (
        args.prod_panel or default_prod_panel_path(repo_root)
    ).expanduser().resolve()
    search_dirs = (
        [d.expanduser().resolve() for d in args.search_dir]
        if args.search_dir
        else default_search_dirs(repo_root)
    )
    policy = FreshnessPolicy(
        name="prod-fast-axis",
        breach_days=args.breach_days,
    )
    return EnforcementContext(
        now=resolve_now(parse_as_of(args.as_of)),
        repo_root=repo_root,
        prod_panel_path=prod_panel,
        search_dirs=search_dirs,
        breach_days=args.breach_days,
        window_days=args.window_days,
        policy=policy,
        quiet=args.quiet,
    )


def _render_result(result: EnforcementResult) -> str:
    lines = [
        f"# Model freshness enforcement",
        f"",
        f"Current prod panel: tier={result.current_tier} age={result.current_age_days}d "
        f"stale={result.stale}",
        f"Action: {result.action}",
    ]
    if result.recommended_path:
        lines.append(f"Recommended: {result.recommended_path} (age={result.recommended_age_days}d)")
        lines.append(f"  gate_passed={result.gate_passed} failure_class={result.failure_class}")
    lines.append(f"")
    lines.append(f"Candidates scanned: {result.candidates_scanned}")
    lines.append(f"  passing: {result.candidates_passing}  fresh: {result.candidates_fresh}")
    lines.append(f"")
    lines.append(result.detail)
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ctx = build_context(args)
    build_pipeline().run(ctx)
    if ctx.result is None:
        print("enforcement pipeline did not produce a result", file=sys.stderr)
        return 3
    if args.json:
        print(json.dumps(ctx.result.as_dict(), indent=2, sort_keys=True))
    elif not args.quiet:
        print(_render_result(ctx.result))
    return ctx.exit_code


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
