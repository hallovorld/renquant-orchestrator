#!/usr/bin/env python3
"""The mechanical check for twin-registry R5. (GOAL-3 / GOAL-5)

THIS IS NOT A NEW FINDING, AND SAYING SO IS THE POINT. The inversion below is already
registered as **R5** in `doc/arch/twin-implementation-registry.md`, in this repo, with
more detail than I had when I re-measured it: R5 names the runner's config resolution
(`daily_104.sh`, via `renquant_strategy_config "$SUBREPO_ROOT"`), the watchlist gap
(145 vs 142, exactly `CRWV`/`RKLB`/`SPCX`), and the consequence — a resolver failure
promoting a 623-day-stale shadow checkpoint to primary, whose all-negative scores admit
no name at all, i.e. a silent sell-only book.

I re-derived it from the files without checking the registry first. The registry exists
precisely so that does not happen.

WHAT THIS MODULE ACTUALLY ADDS is R5's own retirement condition #3 — *"a single source
for role assignment in R5/R6 — today three files assert it"* — in its mechanical half:
a check that **fails** when the surfaces disagree, so the divergence stops depending on
someone re-reading two files. A registry row records a defect; this makes it detectable.

MEASURED 2026-07-31, unchanged from R5 and re-derivable by running this:

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

WHAT THIS TOOL DOES NOT DECIDE, AND WHY THAT IS STILL RIGHT. It does not read the run
scripts, so it does not itself establish which surface executes — asserting that from a
directory layout is how "which copy executes" defects get published as facts. The answer
IS known and is not this tool's to assert: R5 records that the runner takes the **pinned**
config, and `daily_104.sh` resolves it through `renquant_strategy_config "$SUBREPO_ROOT"`
with a fallback that is fail-closed only when `RENQUANT_STRICT_SUBREPO_PATHS=1` or
`RENQUANT_OPS_FAIL_CLOSED=1`. A caller that wants that answer should read R5, not infer it
from this output.

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
        # THE FAILURE is an EMPTY intersection, not merely different hit sets
        # `[codex on orch#694]`. If the primary resolves under {A, B} and a shadow only
        # under {A}, the intersection is {A} and the loader can consistently use A --
        # calling that a disagreement flags a configuration that is perfectly coherent.
        "no_common_base": bool(resolved) and not common,
        # Diagnostic only, never fails: a path present under more than one base is worth
        # SEEING (it is how a copy gets edited in the wrong place) but it is not itself
        # a defect.
        "hit_sets_differ": len(base_sets) > 1,
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
    # orch#1020: the WATCHLIST is part of what a surface declares it trades.
    # Two surfaces drifted to 145 vs 142 names (CRWV/RKLB/SPCX) and nothing
    # reported it, because identity parity never looked at the universe.
    # Malformed members fail closed (the #694 lesson, same as shadows above);
    # an ABSENT watchlist is recorded as None and compared explicitly — a
    # surface that does not say what it trades cannot agree with one that does.
    wl = cfg.get("watchlist")
    if wl is not None:
        if not isinstance(wl, list):
            return {**row, "status": "malformed_watchlist",
                    "why": f"`watchlist` is {type(wl).__name__}, not a list"}
        bad_wl = [f"entry {i} is {type(t).__name__}, not a string"
                  for i, t in enumerate(wl) if not isinstance(t, str)]
        if bad_wl:
            return {**row, "status": "malformed_watchlist",
                    "why": "; ".join(bad_wl)}
    names = sorted(m["name"] for m in (shadows or []))
    return {**row, "status": "read",
            "identity": {f: ps.get(f) for f in IDENTITY_FIELDS},
            "watchlist": sorted(wl) if wl is not None else None,
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

    # orch#1020: universe drift. Symmetric difference of the declared
    # watchlists, named ticker by ticker (bounded), so "adding a ticker to
    # the served config can never produce an artifact" stops being invisible.
    # None-vs-list is a disagreement too: a surface that does not declare a
    # universe cannot agree with one that does.
    wls = {s["path"]: s.get("watchlist") for s in read}
    if len({json.dumps(w) for w in wls.values()}) > 1:
        parts = []
        as_sets = {p: set(w) for p, w in wls.items() if w is not None}
        if len(as_sets) == len(wls) and len(as_sets) >= 2:
            union_all = set.union(*as_sets.values())
            common = set.intersection(*as_sets.values())
            for p, names in as_sets.items():
                extra = sorted(names - common)
                label = (f"{os.path.basename(os.path.dirname(p))}/"
                         f"{os.path.basename(p)}")
                parts.append(f"{label} n={len(names)}"
                             + (f" only={extra[:10]}"
                                + ("…" if len(extra) > 10 else "")
                                if extra else ""))
            del union_all
        else:
            for p, w in wls.items():
                label = (f"{os.path.basename(os.path.dirname(p))}/"
                         f"{os.path.basename(p)}")
                parts.append(f"{label} watchlist="
                             + ("ABSENT" if w is None else f"n={len(w)}"))
        disagreements.append("watchlist: " + "; ".join(parts))

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
    ap.add_argument("--config", action="append", dest="configs", default=None,
                    help="a strategy_config.json surface; pass more than once. "
                         "Omit to compare the two surfaces the daily run "
                         "actually stitches, derived from $RQ_ROOT (orch#1020) "
                         "— the pinned subrepo config and the umbrella "
                         "tournament config.")
    ap.add_argument("--base", action="append", dest="bases", default=None,
                    help="a directory artifact_path may be relative to; pass more "
                         "than once. Omit to skip path resolution entirely.")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if not a.configs:
        # orch#1020: the audit registry refused to bake machine paths into a
        # reviewed tuple ("tests that measure the operator's disk"). The fleet
        # answer to that is already established: every scheduled probe derives
        # its subjects from $RQ_ROOT. Same convention here, so the detector can
        # finally be RUN by the audit instead of existing next to it.
        rq = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
        a.configs = [
            os.path.join(rq, ".subrepo_runtime", "repos",
                         "renquant-strategy-104", "configs",
                         "strategy_config.json"),
            os.path.join(rq, "backtesting", "renquant_104",
                         "strategy_config.json"),
        ]

    surfaces = [read_surface(p) for p in a.configs]
    if a.bases:
        for s in surfaces:
            s["path_audit"] = audit_paths(s, list(a.bases))
    rep = compare(surfaces)
    if rep["n_read"] == 0:
        print("strategy-config parity: no surface could be read — the check has no "
              "subjects, which is not the same as agreement", file=sys.stderr)
        return 2

    # The FIRST stdout line is what ops_audit fingerprints (run_member takes
    # out[0]). It must therefore encode the disagreement STRUCTURE — field
    # names and drifted tickers — so an ack binds to THIS drift and any new
    # drift re-fingerprints as a NEW finding. Fingerprinting the surface
    # listing (the old first line) would let one ack silently cover every
    # future divergence: the wrong object, at the disposition layer.
    def _summary() -> str:
        if not (rep["disagreements"] or rep["n_broken"]):
            return "PARITY: all readable surfaces agree"
        tags = []
        for d in rep["disagreements"]:
            field = d.split(":", 1)[0]
            if field == "watchlist":
                import re as _re
                drift = sorted(set(_re.findall(r"[A-Z][A-Z0-9.]{0,9}",
                                               d.split("only=", 1)[1])))                     if "only=" in d else []
                tags.append("watchlist(" + ",".join(drift) + ")")
            else:
                tags.append(field)
        if rep["n_broken"]:
            tags.append(f"broken_surfaces={rep['n_broken']}")
        return (f"PARITY: {len(rep['disagreements'])} disagreement(s) "
                f"[{'; '.join(tags)}]")

    if a.json:
        rep["summary"] = _summary()
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        print(_summary())
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
            if pa["n_unresolvable"] or pa["no_common_base"] or pa["hit_sets_differ"]:
                print(f"\nPATHS  {os.path.basename(s['path'])}")
                for e in pa["entries"]:
                    print(f"   {e['status']:14s} {e['role']}: {e['artifact_path']}")
                    if e["resolves_under"]:
                        print(f"                  under {e['resolves_under']}")
                if pa["no_common_base"]:
                    print("   NO SINGLE BASE resolves every declared path — the loader "
                          "cannot use one base consistently")
                elif pa["hit_sets_differ"]:
                    print(f"   note: paths resolve under different SETS of bases, but "
                          f"{pa['single_base_that_resolves_everything']} resolves all "
                          f"of them — coherent, reported for visibility only")
        if rep["primary_and_shadow_are_mirrored"]:
            print("\nMIRRORED: each surface's PRIMARY appears in the other's SHADOWS. "
                  "One says A decides and B watches; the other says the reverse.")
        for d in rep["disagreements"]:
            print(f"DISAGREE  {d}")
        if not rep["disagreements"] and not rep["n_broken"]:
            print("\nall readable surfaces agree on the primary scorer identity")
        print("\n" + rep["scope_note"])

    # Only an EMPTY intersection (or an unresolvable path) fails. Differing hit sets are
    # diagnostic: a common base means the loader can be consistent.
    path_problem = any(
        (s.get("path_audit") or {}).get("n_unresolvable")
        or (s.get("path_audit") or {}).get("no_common_base")
        for s in surfaces)
    return 1 if (rep["disagreements"] or rep["n_broken"] or path_problem) else 0


if __name__ == "__main__":
    raise SystemExit(main())
