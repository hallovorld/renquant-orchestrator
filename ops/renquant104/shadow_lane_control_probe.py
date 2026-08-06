#!/usr/bin/env python3
"""Is each shadow lane still a CONTROL, or has it become a copy of prod?

WHY (GOAL-4, measured 2026-08-05). The `alpaca_shadow_blend_mom` lane scores
rho=0.9998 against prod with 10/10 top-k overlap and an affine residual ratio of
0.0149. That is not a coincidence and not a bug: every score-affecting key in
`strategy_config.shadow_blend_momentum.json` is IDENTICAL to prod's, down to the
component content digests.

The cause is a promotion. The operator moved the z-blend into prod on 2026-08-04
("z-blend进prod / 整本切换"). `_mom` existed to shadow that blend. The moment the
blend became prod, the shadow became a duplicate — and a lane that agrees with
prod by construction cannot inform an ensemble, cannot falsify prod, and costs a
scheduled slot every day while looking healthy.

Nothing alarms on this. The lane runs, scores, and reports. Only a rank
correlation against prod reveals it, and only if someone thinks to look.

WHAT THIS COMPARES, precisely: the SCORE-AFFECTING subset of
`ranking.panel_scoring`. Keys beginning with `_` are commentary and are excluded.
`shadow_experiment` and `shadow_models` are excluded too -- they name the shadow
LEGS a lane reports alongside its decision and do not enter its own score, so a
lane that differs only there is still a copy.

Read-only. Usage:
    python ops/renquant104/shadow_lane_control_probe.py [--configs DIR] [--json]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

DEFAULT_CONFIGS = pathlib.Path(
    "/Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/"
    "renquant-strategy-104/configs")
PROD = "strategy_config.json"

#: Reported alongside a decision, not used to compute it. A lane differing ONLY
#: here is still a copy of prod for every purpose an ensemble cares about.
NON_SCORING_KEYS = frozenset({"shadow_experiment", "shadow_models"})

IS_A_CONTROL = "IS_A_CONTROL"
COPY_OF_PROD = "COPY_OF_PROD"
UNREADABLE = "UNREADABLE"


class ProdConfigUnreadable(RuntimeError):
    """Without prod there is no baseline. Not a fleet of controls."""


def scoring_block(payload: dict) -> dict:
    r = payload.get("ranking")
    ps = (r or {}).get("panel_scoring") if isinstance(r, dict) else None
    return ps if isinstance(ps, dict) else {}


def _strip(obj):
    """Drop `_`-prefixed commentary at every level, recursively.

    Recursion matters: an earlier draft stripped only the top level, so two
    blocks differing solely in a nested `_reason` string were reported as
    genuinely different — a lane would have been called a control on the
    strength of a comment."""
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


def scoring_identity(ps: dict) -> dict:
    return _strip({k: v for k, v in ps.items() if k not in NON_SCORING_KEYS})


def compare(prod_ps: dict, lane_ps: dict) -> dict:
    p, l = scoring_identity(prod_ps), scoring_identity(lane_ps)
    keys = sorted(set(p) | set(l))
    differing = [k for k in keys
                 if json.dumps(p.get(k), sort_keys=True)
                 != json.dumps(l.get(k), sort_keys=True)]
    return {
        "n_score_affecting_keys": len(keys),
        "differing_keys": differing,
        "state": IS_A_CONTROL if differing else COPY_OF_PROD,
    }


def scan(configs: pathlib.Path = DEFAULT_CONFIGS) -> dict:
    try:
        prod_ps = scoring_block(json.loads((configs / PROD).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProdConfigUnreadable(
            f"{configs / PROD}: {exc} — without prod there is no baseline, and "
            "reporting every lane as a control would publish a missing "
            "comparison as a clean fleet") from exc
    if not prod_ps:
        raise ProdConfigUnreadable(
            f"{configs / PROD}: ranking.panel_scoring is absent or empty")

    lanes = []
    for f in sorted(configs.glob("strategy_config.shadow*.json")):
        try:
            ps = scoring_block(json.loads(f.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            lanes.append({"lane": f.name, "state": UNREADABLE, "detail": str(exc)})
            continue
        if not ps:
            lanes.append({"lane": f.name, "state": UNREADABLE,
                          "detail": "ranking.panel_scoring absent or empty"})
            continue
        lanes.append({"lane": f.name, **compare(prod_ps, ps)})

    copies = [x["lane"] for x in lanes if x["state"] == COPY_OF_PROD]
    return {
        "configs": str(configs),
        "n_lanes": len(lanes),
        "lanes": lanes,
        "n_copies_of_prod": len(copies),
        "copies_of_prod": copies,
        "n_unreadable": sum(1 for x in lanes if x["state"] == UNREADABLE),
        "does_NOT_establish": (
            "that a differing lane is a GOOD control. Differing config is "
            "necessary for a lane to carry information, not sufficient — a lane "
            "can differ and still be worthless. This checks only that the lane "
            "is not prod."
        ),
    }


def render(r: dict) -> str:
    out = ["shadow-lane control check — is each lane still distinguishable from prod?", ""]
    for x in r["lanes"]:
        if x["state"] == UNREADABLE:
            out.append(f"  {x['lane']:48} UNREADABLE — {x['detail'][:50]}")
        elif x["state"] == COPY_OF_PROD:
            out.append(f"  {x['lane']:48} COPY OF PROD (0 of "
                       f"{x['n_score_affecting_keys']} score-affecting keys differ)")
        else:
            out.append(f"  {x['lane']:48} control ({len(x['differing_keys'])}/"
                       f"{x['n_score_affecting_keys']} differ: "
                       f"{','.join(x['differing_keys'][:3])})")
    out.append("")
    if r["n_copies_of_prod"]:
        out.append(f"  {r['n_copies_of_prod']} lane(s) are NOT controls — they agree with prod")
        out.append("  by construction, so they cannot inform an ensemble or falsify prod,")
        out.append("  while consuming a scheduled slot daily and looking healthy.")
    else:
        out.append("  every readable lane differs from prod in at least one scoring key.")
    out.append("")
    out.append(f"  Does NOT establish {r['does_NOT_establish']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", type=pathlib.Path, default=DEFAULT_CONFIGS)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        r = scan(a.configs)
    except ProdConfigUnreadable as exc:
        print(f"REFUSING: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(r, indent=2) if a.json else render(r))
    return 1 if r["n_copies_of_prod"] or r["n_unreadable"] else 0


if __name__ == "__main__":
    sys.exit(main())
