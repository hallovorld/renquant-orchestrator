#!/usr/bin/env python3
"""GOAL-4 Phase-0: which ensemble MEMBERS have per-regime evidence, and what does it say?

WHY (measured 2026-08-05, orch#805): the WF gate stamps a full per-regime
placebo profile on every verdict and nothing reads it. Reading it reframed the
whole ensemble question. The primary panel recipe's genuine IC is:

    BEAR       +0.335   (50 dates)   — and the strategy places ZERO buys there
    BULL_CALM  -0.029  (363 dates)   — where 136 of its 154 buys land

An ensemble is a weighting over MEMBERS. Before asking whether a weighting
helps, GOAL-4 has to answer a prior question this census exists to make cheap:
**does any member have positive genuine IC in the regime the book actually
trades?** A member that is negatively informative in BULL_CALM does not stop
being negatively informative because it is averaged with others; it has to earn
its weight, and "the pooled number is positive" is not that evidence — the
pooled number is a regime-mix artifact (BEAR's +0.335 over 50 dates drags a pool
that is 80% BULL_CALM into positive territory).

READ-ONLY. Walks stamped artifacts, prints a census, writes nothing.

    python scripts/goal4_regime_member_census.py [--artifacts DIR] [--json]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

DEFAULT_ARTIFACTS = pathlib.Path(
    "/Users/renhao/git/github/RenQuant/backtesting/renquant_104/artifacts")

# The shift the ENFORCED placebo leg itself uses (2 x the 60-session horizon).
# A census on a different shift would describe a different experiment than the
# verdicts it sits beside.
SHIFT = "2x"
REGIMES = ("BULL_CALM", "BEAR", "BULL_VOLATILE", "CHOPPY")

# The member list is DERIVED FROM THE PINNED CONFIG, never frozen in code.
# [codex on orch#807] The first version hardcoded panel + clf + momentum and
# presented it as "the live blend". It is not: PROD is panel + slow momentum;
# the clf leg is a SHADOW blend member (the RC/RCS lanes). Freezing a member
# list is the same error one level up from the one this census exists to find —
# a claim about a configuration that has moved.
DEFAULT_CONFIG = pathlib.Path(
    "/Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/"
    "renquant-strategy-104/configs/strategy_config.json")

# artifact_path -> the filename stem the stamped artifacts are found under, plus
# a human label. A component whose path is not recognised still becomes a row
# (labelled by its path) so it cannot vanish from the census silently.
_KNOWN_STEMS = {
    "artifacts/prod/panel-ltr.alpha158_fund.json":
        ("panel primary (XGB recipe)", "panel-ltr.alpha158_fund"),
    "artifacts/shadow/panel-clf.top-decile.fwd60.json":
        ("clf top-decile fwd60", "panel-clf.top-decile.fwd60"),
    "artifacts/momentum/momentum_artifact_ledger.jsonl":
        ("momentum residual v0 (ledger-served)", "momentum_residual_v0"),
}


def members_from_config(config_path: pathlib.Path) -> list[tuple[str, str]]:
    """(label, artifact stem) for each component the PINNED config declares.

    Raises rather than guessing: a census that silently reported an empty
    member list would read as "nothing to measure" instead of "the config could
    not be read", which is the failure mode this whole line of work is about.
    """
    payload = json.loads(config_path.read_text())
    panel = ((payload.get("ranking") or {}).get("panel_scoring") or {})
    components = panel.get("components")
    if not isinstance(components, list) or not components:
        raise SystemExit(
            f"{config_path} declares no blend components "
            f"(kind={panel.get('kind')!r}) — nothing to census; this is a "
            f"config-read failure, not an empty result")
    out: list[tuple[str, str]] = []
    for component in components:
        path = str((component or {}).get("artifact_path") or "")
        known = _KNOWN_STEMS.get(path)
        if known:
            out.append(known)
        else:
            out.append((f"UNRECOGNISED component ({path or 'no artifact_path'})",
                        pathlib.Path(path).stem or "__none__"))
    return out


def _profiles(artifacts: pathlib.Path, stem: str) -> dict[str, dict]:
    """Distinct per-regime profiles stamped on artifacts matching `stem`.

    Deduplicated by profile digest: the corpus holds many byte-copies of the
    same verdict (one artifact has 23 copies), and counting those as separate
    vintages would inflate any claim made from this census.
    """
    out: dict[str, dict] = {}
    if not artifacts.exists():
        return out
    for path in sorted(artifacts.rglob(f"*{stem}*.json")):
        if ".claude" in str(path):
            continue
        try:
            payload = json.loads(path.read_text())
        except Exception:            # noqa: BLE001 - an unreadable file is not evidence
            continue
        if not isinstance(payload, dict):
            continue
        meta = (payload.get("metadata") or {}).get("wf_gate_metadata")
        if not isinstance(meta, dict):
            continue
        profile = meta.get("model_placebo_profile")
        if not isinstance(profile, dict) or not (profile.get("per_regime") or {}):
            continue
        digest = hashlib.sha256(
            json.dumps(profile, sort_keys=True, default=str).encode()).hexdigest()[:10]
        out.setdefault(digest, {
            "run_at": meta.get("run_at"),
            "recipe_fingerprint": meta.get("candidate_recipe_fingerprint"),
            "profile": profile,
        })
    return out


def _genuine(profile: dict, regime: str):
    cell = ((profile.get("per_regime") or {}).get(regime) or {}).get(SHIFT) or {}
    value = cell.get("genuine_ic")
    return value if isinstance(value, (int, float)) else None


def census(artifacts: pathlib.Path = DEFAULT_ARTIFACTS,
           config: pathlib.Path = DEFAULT_CONFIG) -> dict:
    declared = members_from_config(config)
    members = []
    for label, stem in declared:
        found = _profiles(artifacts, stem)
        vintages = []
        for digest, rec in sorted(found.items(), key=lambda kv: str(kv[1]["run_at"])):
            vintages.append({
                "run_at": rec["run_at"],
                "recipe_fingerprint": rec["recipe_fingerprint"],
                **{r: _genuine(rec["profile"], r) for r in REGIMES},
            })
        members.append({"member": label, "stem": stem,
                        "n_vintages": len(vintages), "vintages": vintages})
    return {"shift": SHIFT, "regimes": list(REGIMES), "config": str(config),
            "members": members}


def _fmt(value) -> str:
    return f"{value:+.4f}" if isinstance(value, (int, float)) else "  n/a "


def render(result: dict) -> str:
    lines = [f"GOAL-4 per-regime member census (genuine_ic at {result['shift']} shift)",
             f"members DERIVED FROM: {result['config']}", ""]
    for m in result["members"]:
        lines.append(f"— {m['member']}  [{m['n_vintages']} distinct vintage(s)]")
        if not m["vintages"]:
            lines.append("    NO per-regime evidence stamped on any artifact. "
                         "This member is unmeasured on the axis that decides.")
            lines.append("")
            continue
        head = f"    {'run_at':<12}" + "".join(f"{r:>16}" for r in result["regimes"])
        lines.append(head)
        for v in m["vintages"]:
            lines.append(f"    {str(v['run_at'])[:10]:<12}"
                         + "".join(f"{_fmt(v[r]):>16}" for r in result["regimes"]))
        for r in result["regimes"]:
            vals = [v[r] for v in m["vintages"] if isinstance(v[r], (int, float))]
            if vals:
                sign = "NEGATIVE" if max(vals) < 0 else ("POSITIVE" if min(vals) > 0
                                                         else "MIXED")
                lines.append(f"    {r}: {sign} in {len(vals)}/{len(vals)} vintages "
                             f"(min {min(vals):+.4f}, max {max(vals):+.4f})")
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifacts", type=pathlib.Path, default=DEFAULT_ARTIFACTS)
    ap.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG,
                    help="strategy config whose blend components define the "
                         "member list (default: the PINNED prod config)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    result = census(args.artifacts, args.config)
    print(json.dumps(result, indent=2, default=str) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
