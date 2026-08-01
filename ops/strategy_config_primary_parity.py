#!/usr/bin/env python3
"""Do the strategy-config surfaces agree about WHICH MODEL IS PRIMARY? (GOAL-5)

MEASURED 2026-07-31 — they do not, and they disagree in the most consequential way
available: the two files are **mirror images**.

    renquant-strategy-104/configs/strategy_config.json   (the reviewed, pinned surface)
        ranking.panel_scoring.kind = "xgb"
        shadow_models = ["hf_patchtst_..._previous_primary", "topdecile_clf_blend_leg"]

    RenQuant/backtesting/renquant_104/strategy_config.json   (a run-tree surface)
        ranking.panel_scoring.kind = "hf_patchtst"
        shadow_models = ["xgb_alpha158_fund_previous_primary"]

Primary and shadow are **exactly swapped**. One surface says XGB decides and PatchTST
watches; the other says PatchTST decides and XGB watches.

WHY NOTHING CAUGHT IT. `engineering_census._default_strategy_configs` already names both
paths — and then passes if **any** of them exists:

    if not any(item["exists"] for item in payload["strategy_configs"]): ...

An existence check over interchangeable candidates cannot notice that the candidates
contradict each other. This tool asks the question that one does not.

WHAT THIS TOOL DOES NOT DECIDE. It does **not** claim which surface the daily run reads,
and it must not: that resolution lives in the run scripts, and asserting it from a
directory layout is how "which copy executes" defects get published as facts. It reports
that two declared surfaces disagree and names the disagreement. Establishing which one is
authoritative — and repairing the other — is the follow-up, and it needs the run-side
evidence this tool deliberately does not invent.

Read-only. Opens config files, writes nothing, never invokes git.

Exit codes: ``0`` every readable surface agrees, ``1`` they disagree or a surface is
unreadable/malformed, ``2`` usage error or no surface found at all — so an empty run
cannot be mistaken for agreement.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

#: The identity fields that decide WHO DECIDES. A disagreement on any of them means the
#: two surfaces describe different systems, whatever else matches.
IDENTITY_FIELDS = ("kind", "enabled", "artifact_path")


def _panel_scoring(cfg: object) -> tuple[dict | None, str]:
    """`ranking.panel_scoring`, or a reason it could not be read.

    Every container is type-checked rather than `or {}`-ed. `(x or {}).get(...)` is not
    a guard — a non-empty string is truthy, so the fallback never fires and `.get` raises.
    Three tools in this repo have now needed that sentence.
    """
    if not isinstance(cfg, dict):
        return None, f"top-level JSON is {type(cfg).__name__}, not an object"
    ranking = cfg.get("ranking")
    if ranking is None:
        return None, "no `ranking` section"
    if not isinstance(ranking, dict):
        return None, f"`ranking` is {type(ranking).__name__}, not an object"
    ps = ranking.get("panel_scoring")
    if ps is None:
        return None, "no `ranking.panel_scoring` section"
    if not isinstance(ps, dict):
        return None, f"`ranking.panel_scoring` is {type(ps).__name__}, not an object"
    return ps, ""


def read_surface(path: str) -> dict:
    row: dict = {"path": path, "exists": os.path.exists(path)}
    if not row["exists"]:
        # Absent is NOT a disagreement — a surface that is not deployed here says
        # nothing about the ones that are. It is recorded and excluded from comparison.
        return {**row, "status": "absent"}
    try:
        with open(path, "rb") as fh:
            cfg = json.loads(fh.read())
    except (OSError, ValueError) as exc:
        return {**row, "status": "unreadable",
                "why": f"{type(exc).__name__}: {exc}"}
    ps, why = _panel_scoring(cfg)
    if ps is None:
        return {**row, "status": "no_panel_scoring", "why": why}
    shadows = ps.get("shadow_models")
    if shadows is not None and not isinstance(shadows, list):
        return {**row, "status": "malformed_shadow_models",
                "why": f"`shadow_models` is {type(shadows).__name__}, not a list"}
    names = sorted(s.get("name") for s in (shadows or [])
                   if isinstance(s, dict) and isinstance(s.get("name"), str))
    return {**row, "status": "read",
            "identity": {f: ps.get(f) for f in IDENTITY_FIELDS},
            "shadow_models": names}


def compare(surfaces: list[dict]) -> dict:
    read = [s for s in surfaces if s["status"] == "read"]
    broken = [s for s in surfaces if s["status"] not in ("read", "absent")]
    disagreements: list[str] = []

    for field in IDENTITY_FIELDS:
        values = {s["path"]: s["identity"].get(field) for s in read}
        if len({json.dumps(v, sort_keys=True) for v in values.values()}) > 1:
            disagreements.append(
                f"ranking.panel_scoring.{field}: " +
                "; ".join(f"{os.path.basename(os.path.dirname(p))}/"
                          f"{os.path.basename(p)}={v!r}" for p, v in values.items()))

    shadow_sets = {s["path"]: s["shadow_models"] for s in read}
    if len({json.dumps(v) for v in shadow_sets.values()}) > 1:
        disagreements.append(
            "shadow_models: " + "; ".join(
                f"{os.path.basename(os.path.dirname(p))}/{os.path.basename(p)}={v}"
                for p, v in shadow_sets.items()))

    # The mirror case, called out by name because it is the worst shape and the one
    # measured on this machine: each surface's PRIMARY appears in the other's SHADOWS.
    mirrored = False
    if len(read) == 2:
        a, b = read
        a_kind = str(a["identity"].get("kind") or "")
        b_kind = str(b["identity"].get("kind") or "")
        mirrored = bool(a_kind and b_kind and a_kind != b_kind
                        and any(a_kind in n for n in b["shadow_models"])
                        and any(b_kind in n for n in a["shadow_models"]))

    return {
        "n_surfaces_declared": len(surfaces),
        "n_read": len(read),
        "n_absent": sum(1 for s in surfaces if s["status"] == "absent"),
        "n_broken": len(broken),
        "disagreements": disagreements,
        "primary_and_shadow_are_mirrored": mirrored,
        "surfaces": surfaces,
        "scope_note": (
            "This reports that declared surfaces disagree. It does NOT identify which "
            "one the daily run reads — that resolution lives in the run scripts, and "
            "asserting it from a directory layout is how 'which copy executes' defects "
            "get published as facts."),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", action="append", required=True, dest="configs",
                    help="a strategy_config.json surface; pass more than once")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    surfaces = [read_surface(p) for p in a.configs]
    rep = compare(surfaces)
    if rep["n_read"] == 0:
        print("strategy-config parity: no surface could be read — the check has no "
              "subjects, which is not the same as agreement", file=sys.stderr)
        return 2

    if a.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        for s in surfaces:
            print(f"  {s['status']:22s} {s['path']}")
            if s["status"] == "read":
                print(f"                         primary={s['identity']}")
                print(f"                         shadows={s['shadow_models']}")
            elif s.get("why"):
                print(f"                         {s['why']}")
        if rep["primary_and_shadow_are_mirrored"]:
            print("\nMIRRORED: each surface's PRIMARY appears in the other's SHADOWS. "
                  "One says A decides and B watches; the other says the reverse.")
        for d in rep["disagreements"]:
            print(f"DISAGREE  {d}")
        if not rep["disagreements"] and not rep["n_broken"]:
            print("\nall readable surfaces agree on the primary scorer identity")
        print("\n" + rep["scope_note"])

    return 1 if (rep["disagreements"] or rep["n_broken"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
