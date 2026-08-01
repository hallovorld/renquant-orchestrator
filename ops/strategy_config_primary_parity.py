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


def resolve_against(rel: str, bases: list[str]) -> list[str]:
    """Every base under which `rel` exists. Plural on purpose.

    Returning the FIRST hit would hide the finding this function was written for: a
    single config can name paths that resolve under different bases, and "it resolved"
    then conceals which one answered.
    """
    if not isinstance(rel, str) or not rel:
        return []
    if os.path.isabs(rel):
        return [""] if os.path.exists(rel) else []
    return [b for b in bases if os.path.exists(os.path.normpath(os.path.join(b, rel)))]


def audit_paths(surface: dict, bases: list[str]) -> dict:
    """Which base does each declared artifact_path resolve against?

    MEASURED 2026-07-31 on the pinned surface — three declared paths, two bases, and no
    single base resolves all three:

        artifacts/patchtst_shadow/.../seed_44/...model.pt  -> umbrella root ONLY
        artifacts/shadow/panel-clf.top-decile.fwd60.json   -> renquant_104 ONLY
        artifacts/prod/panel-ltr.alpha158_fund.json        -> renquant_104 ONLY

    So "what does `artifact_path` resolve against?" has no single answer in this config.
    Either the loader uses a different base per lane, or one of these lanes does not
    resolve at run time -- and a shadow lane that fails to resolve is skipped, which is
    the silent-death failure class GOAL-1 exists for.

    This function reports; it does not guess the loader's base. Naming an authoritative
    base from a directory layout is the same over-reach this module already refuses for
    the authoritative *surface*.
    """
    if surface.get("status") != "read":
        return {"status": surface.get("status"), "entries": []}
    entries = []
    declared = [("primary", surface["identity"].get("artifact_path"))]
    declared += [(f"shadow:{n}", p)
                 for n, p in surface.get("shadow_artifact_paths", [])]
    for role, rel in declared:
        hits = resolve_against(rel, bases) if rel else []
        entries.append({"role": role, "artifact_path": rel,
                        "resolves_under": hits,
                        "status": ("unresolvable" if rel and not hits
                                   else "not_declared" if not rel else "resolved")})
    resolved = [e for e in entries if e["status"] == "resolved"]
    base_sets = {frozenset(e["resolves_under"]) for e in resolved}
    common = set.intersection(*(set(e["resolves_under"]) for e in resolved)) \
        if resolved else set()
    return {
        "status": "read",
        "entries": entries,
        "n_unresolvable": sum(1 for e in entries if e["status"] == "unresolvable"),
        "bases_disagree": len(base_sets) > 1,
        "single_base_that_resolves_everything": sorted(common),
    }


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
    # FAIL CLOSED on a malformed MEMBER, not just a malformed list `[codex on #694]`.
    # The earlier comprehension filtered non-dict members and non-string names out, so
    # `[{"name": 7}]` normalised to `[]` and AGREED WITH A GENUINELY EMPTY SHADOW LIST.
    # Silently turning corruption into a value that can match is the fail-open shape this
    # whole module exists to catch, committed by the module.
    bad = [f"entry {i} is {type(m).__name__}, not an object" if not isinstance(m, dict)
           else f"entry {i} has name={m.get('name')!r} ({type(m.get('name')).__name__}),"
                f" not a string"
           for i, m in enumerate(shadows or [])
           if not isinstance(m, dict) or not isinstance(m.get("name"), str)]
    if bad:
        return {**row, "status": "malformed_shadow_models",
                "why": "; ".join(bad)}
    # Identity fields are REQUIRED. Missing ones compare as equal `None`, so two
    # surfaces that each declare no primary at all would "agree" about who decides.
    missing = [f for f in IDENTITY_FIELDS if ps.get(f) is None]
    if missing:
        return {**row, "status": "incomplete_identity",
                "why": f"missing identity field(s): {', '.join(missing)} — a surface "
                       f"that does not say who decides cannot agree with one that does"}
    names = sorted(m["name"] for m in (shadows or []))
    return {**row, "status": "read",
            "identity": {f: ps.get(f) for f in IDENTITY_FIELDS},
            "shadow_models": names,
            "shadow_artifact_paths": [
                (s.get("name"), s.get("artifact_path"))
                for s in (shadows or [])
                if isinstance(s, dict) and isinstance(s.get("name"), str)]}


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
    ap.add_argument("--base", action="append", dest="bases", default=None,
                    help="a directory artifact_path may be relative to; pass more "
                         "than once. Omit to skip path resolution entirely.")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    surfaces = [read_surface(p) for p in a.configs]
    if a.bases:
        for s in surfaces:
            s["path_audit"] = audit_paths(s, list(a.bases))
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
        for s in surfaces:
            pa = s.get("path_audit")
            if not pa or pa.get("status") != "read":
                continue
            if pa["n_unresolvable"] or pa["bases_disagree"]:
                print(f"\nPATHS  {os.path.basename(s['path'])}")
                for e in pa["entries"]:
                    print(f"   {e['status']:14s} {e['role']}: {e['artifact_path']}")
                    if e["resolves_under"]:
                        print(f"                  under {e['resolves_under']}")
                if pa["bases_disagree"]:
                    print("   BASES DISAGREE — declared paths in ONE config resolve "
                          "against DIFFERENT bases")
                if not pa["single_base_that_resolves_everything"]:
                    print("   NO SINGLE BASE resolves every declared path")
        if rep["primary_and_shadow_are_mirrored"]:
            print("\nMIRRORED: each surface's PRIMARY appears in the other's SHADOWS. "
                  "One says A decides and B watches; the other says the reverse.")
        for d in rep["disagreements"]:
            print(f"DISAGREE  {d}")
        if not rep["disagreements"] and not rep["n_broken"]:
            print("\nall readable surfaces agree on the primary scorer identity")
        print("\n" + rep["scope_note"])

    path_problem = any(
        (s.get("path_audit") or {}).get("n_unresolvable")
        or (s.get("path_audit") or {}).get("bases_disagree")
        for s in surfaces)
    return 1 if (rep["disagreements"] or rep["n_broken"] or path_problem) else 0


if __name__ == "__main__":
    raise SystemExit(main())
