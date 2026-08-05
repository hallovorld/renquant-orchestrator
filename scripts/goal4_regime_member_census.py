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

# The live blend's members (s104 prod profile, 2026-08-05). Named explicitly so
# a member that has NO evidence shows up as a row rather than as an absence.
MEMBERS = (
    ("panel primary (XGB recipe)", "panel-ltr.alpha158_fund"),
    ("clf top-decile fwd60", "panel-clf.top-decile.fwd60"),
    ("momentum residual v0", "momentum_residual_v0"),
)


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


def census(artifacts: pathlib.Path = DEFAULT_ARTIFACTS) -> dict:
    members = []
    for label, stem in MEMBERS:
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
    return {"shift": SHIFT, "regimes": list(REGIMES), "members": members}


def _fmt(value) -> str:
    return f"{value:+.4f}" if isinstance(value, (int, float)) else "  n/a "


def render(result: dict) -> str:
    lines = [f"GOAL-4 per-regime member census (genuine_ic at {result['shift']} shift)", ""]
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
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    result = census(args.artifacts)
    print(json.dumps(result, indent=2, default=str) if args.json else render(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
