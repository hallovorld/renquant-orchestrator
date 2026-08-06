#!/usr/bin/env python3
"""Is each shadow leg independent of the primary it is being compared against?

WHY (GOAL-7, measured 2026-08-05). The daily decision line reports

    SHADOW[momentum_residual_v0_shadow] top3=XLK/ASML/ROST top10∩prim=6/10 rho=+0.75
    SHADOW[topdecile_clf_blend_leg]     top3=CRWD/UNH/DDOG top10∩prim=2/10 rho=+0.28

Read naively, the momentum leg "agrees strongly with prod" and the clf leg does
not. But on 2026-08-04 the momentum z-blend was promoted into prod, so
`momentum_residual` is now prod's **component[1]** — and the shadow leg of the
same name serves the SAME artifact. Today's log shows both invocations serving
`a824c480cd9c…`.

So that rho is measuring the momentum model against a primary that CONTAINS the
momentum model. It is inflated by construction. The 0.75-vs-0.28 gap is not
evidence that one leg is better; part of it is arithmetic.

Nothing flags this. The promotion was a deliberate operator decision; what no
step did was notice that it turned a diagnostic into a self-comparison.

IDENTITY IS (kind, artifact_path), DELIBERATELY. An earlier draft of this probe
also required `expected_config_fingerprint` to match -- but components declare
that field and shadow legs do not, so the comparison tested PRESENCE, not
identity, and returned "independent" for the very leg this file exists to catch.
A guard whose subject is not the object you assume passes forever.

Read-only. Usage:
    python ops/renquant104/shadow_leg_independence_probe.py [--config P] [--json]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

DEFAULT_CONFIG = pathlib.Path(
    "/Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/"
    "renquant-strategy-104/configs/strategy_config.json")

INDEPENDENT = "INDEPENDENT"
SELF_COMPARISON = "SELF_COMPARISON"
UNDECLARED = "UNDECLARED_ARTIFACT"


class ConfigUnreadable(RuntimeError):
    """No config, no comparison. Not a fleet of independent legs."""


def identity(entry: dict) -> tuple:
    """What makes a scorer the same scorer: its kind and the artifact it serves.

    NOT the fingerprint -- see the module docstring. Components declare
    `expected_config_fingerprint`; shadow legs need not, so including it
    compares which fields happen to be filled in rather than which model runs.
    """
    return (entry.get("kind", "panel_ltr"), entry.get("artifact_path"))


def scan(config: pathlib.Path = DEFAULT_CONFIG) -> dict:
    try:
        payload = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ConfigUnreadable(f"{config}: {exc}") from exc
    ps = ((payload.get("ranking") or {}).get("panel_scoring") or {})
    if not isinstance(ps, dict) or not ps:
        raise ConfigUnreadable(
            f"{config}: ranking.panel_scoring absent — reporting every leg as "
            "independent from a missing primary would publish a failed read as "
            "a clean result")

    components = ps.get("components") or []
    # A non-blend config scores from a single artifact_path; treat that as the
    # one component so a self-comparison is still detectable there.
    if not components and ps.get("artifact_path"):
        components = [{"kind": ps.get("kind", "panel_ltr"),
                       "artifact_path": ps["artifact_path"]}]
    comp_ids = {identity(c) for c in components if isinstance(c, dict)}

    legs = []
    for s in (ps.get("shadow_models") or []):
        if not isinstance(s, dict):
            continue
        ident = identity(s)
        if ident[1] is None:
            state = UNDECLARED
        elif ident in comp_ids:
            state = SELF_COMPARISON
        else:
            state = INDEPENDENT
        legs.append({"name": s.get("name"), "kind": ident[0],
                     "artifact_path": ident[1], "state": state})

    bad = [x["name"] for x in legs if x["state"] == SELF_COMPARISON]
    return {
        "config": str(config),
        "n_components": len(comp_ids),
        "component_identities": sorted(str(c) for c in comp_ids),
        "n_shadow_legs": len(legs),
        "legs": legs,
        "n_self_comparisons": len(bad),
        "self_comparisons": bad,
        "does_NOT_establish": (
            "that an INDEPENDENT leg's rho is meaningful, or that a "
            "SELF_COMPARISON leg's model is bad. It says only that one of the "
            "reported correlations is not a comparison between two different "
            "things, so the two numbers must not be ranked against each other."
        ),
    }


def render(r: dict) -> str:
    out = ["shadow-leg independence — is each leg a different model from the primary?", ""]
    out.append(f"  primary components: {r['n_components']}")
    for c in r["component_identities"]:
        out.append(f"     {c}")
    out.append("")
    for x in r["legs"]:
        mark = {SELF_COMPARISON: "SELF-COMPARISON", INDEPENDENT: "independent",
                UNDECLARED: "no artifact declared"}[x["state"]]
        out.append(f"  {str(x['name']):34} {mark}")
        if x["state"] == SELF_COMPARISON:
            out.append(f"     serves {x['artifact_path']} — which IS a primary component")
    out.append("")
    if r["n_self_comparisons"]:
        out.append(f"  {r['n_self_comparisons']} leg(s) are compared against a primary that")
        out.append("  CONTAINS them. Their reported rho is inflated by construction and must")
        out.append("  not be ranked against an independent leg's.")
    else:
        out.append("  every declared leg is a different model from the primary's components.")
    out.append("")
    out.append(f"  Does NOT establish {r['does_NOT_establish']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=pathlib.Path, default=DEFAULT_CONFIG)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        r = scan(a.config)
    except ConfigUnreadable as exc:
        print(f"REFUSING: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(r, indent=2) if a.json else render(r))
    return 1 if r["n_self_comparisons"] else 0


if __name__ == "__main__":
    sys.exit(main())
