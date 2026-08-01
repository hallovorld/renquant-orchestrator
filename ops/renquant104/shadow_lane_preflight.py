#!/usr/bin/env python3
"""Would a NEW shadow lane actually be served, and seen? (GOAL-7)

GOAL-7 wants a standalone momentum model deployed **to shadow**. "Deployed to shadow" is
not one step — it is four mechanical preconditions, each of which this programme has
already watched fail somewhere else. This checks them before the lane exists, so the
answer is not discovered from a silence.

    1. DECLARED WHERE THE RUNNER READS.  Two files present as the 104 strategy config and
       they disagree; twin-registry R5 records that the runner takes the PINNED one. A
       lane declared only in the other file is not served.

    2. THE ARTIFACT RESOLVES -- AND UNDER WHICH BASE.  Measured 2026-07-31 (orch#694):
       within the pinned config, three declared paths resolve under two different bases
       and NO single base resolves all three. So "it resolves" is not an answer; "it
       resolves under X" is.

    3. THE SENTINEL CAN SEE IT.  `rq104_shadow_scorer_sentinel` retains a health record
       only when `shadow_name` matches a watched lane -- exactly, or as
       `<SHADOW_NAME>_<suffix>`. A lane whose name matches nothing is invisible, and its
       silence is indistinguishable from health (orch#689).

    4. THE ARTIFACT LOADS.  A booster that cannot be loaded is a skip, not an error, on
       the serving path.

MEASURED on the two lanes that exist today, 2026-07-31 -- and this is a NEGATIVE result
worth stating: I expected a name mismatch and there is none.

    hf_patchtst_pt07_strict_seed44_previous_primary  -> matches `hf_patchtst` via the
                                                        `_<suffix>` rule
    topdecile_clf_blend_leg                          -> matches the clf lane, whose name
                                                        is `os.environ.get(
                                                        "RQ104_CLF_LANE_NAME",
                                                        "topdecile_clf_blend_leg")`

The environment variable is set in **no** installed plist, so the default answers -- and
the default is exactly what the config declares. Unset is harmless here. That is only true
by coincidence of the default, which is why check 3 exists: a lane renamed in config and
not in the sentinel's default would go invisible with nothing to say so.

Read-only. Opens configs and artifacts, writes nothing, never invokes git, never installs
anything.

Exit codes: ``0`` every checked precondition passes, ``1`` at least one fails, ``2``
usage/IO error -- so a preflight that could not run cannot read as a green light.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


def _panel_scoring(path: str) -> tuple[dict | None, str]:
    if not os.path.exists(path):
        return None, "config does not exist"
    try:
        with open(path, "rb") as fh:
            cfg = json.loads(fh.read())
    except (OSError, ValueError) as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if not isinstance(cfg, dict):
        return None, f"top-level JSON is {type(cfg).__name__}"
    ranking = cfg.get("ranking")
    if not isinstance(ranking, dict):
        return None, f"`ranking` is {type(ranking).__name__}, not an object"
    ps = ranking.get("panel_scoring")
    if not isinstance(ps, dict):
        return None, f"`ranking.panel_scoring` is {type(ps).__name__}, not an object"
    return ps, ""


def check_declared(runner_config: str, lane: str) -> dict:
    """1 — is the lane in the config the RUNNER reads?"""
    ps, why = _panel_scoring(runner_config)
    if ps is None:
        return {"check": "declared_in_runner_config", "ok": False, "why": why}
    shadows = ps.get("shadow_models")
    if not isinstance(shadows, list):
        return {"check": "declared_in_runner_config", "ok": False,
                "why": f"`shadow_models` is {type(shadows).__name__}, not a list"}
    names = [s.get("name") for s in shadows if isinstance(s, dict)]
    entry = next((s for s in shadows
                  if isinstance(s, dict) and s.get("name") == lane), None)
    return {"check": "declared_in_runner_config", "ok": entry is not None,
            "declared_lanes": names, "entry": entry,
            "why": "" if entry else f"{lane!r} is not among {names}"}


def check_artifact(entry: dict | None, bases: list[str]) -> dict:
    """2 — does the artifact resolve, and under WHICH base?"""
    if not entry:
        return {"check": "artifact_resolves", "ok": False,
                "why": "no config entry, so no artifact_path to resolve"}
    rel = entry.get("artifact_path")
    if not isinstance(rel, str) or not rel:
        return {"check": "artifact_resolves", "ok": False,
                "why": f"artifact_path is {type(rel).__name__}, not a non-empty string"}
    if os.path.isabs(rel):
        return {"check": "artifact_resolves", "ok": os.path.exists(rel),
                "artifact_path": rel, "resolves_under": ["<absolute>"],
                "why": "" if os.path.exists(rel) else "absolute path does not exist"}
    hits = [b for b in bases
            if os.path.exists(os.path.normpath(os.path.join(b, rel)))]
    return {"check": "artifact_resolves", "ok": bool(hits), "artifact_path": rel,
            "resolves_under": hits,
            "why": "" if hits else f"resolves under none of {bases}",
            "note": ("more than one base resolves it — which one the loader uses is not "
                     "established here" if len(hits) > 1 else "")}


def check_sentinel_visible(lane: str, watched: list[str], shadow_name: str) -> dict:
    """3 — would the sentinel retain a record carrying this lane name?"""
    exact = lane in watched
    decorated = lane.startswith(shadow_name + "_")
    return {"check": "sentinel_can_see_it", "ok": exact or decorated,
            "watched_lanes": watched, "matched_exactly": exact,
            "matched_as_decorated": decorated,
            "why": "" if (exact or decorated) else
                   f"{lane!r} matches no watched lane and is not "
                   f"'{shadow_name}_<suffix>' — its silence would be "
                   f"indistinguishable from health"}


def check_loadable(resolved: str | None) -> dict:
    """4 — does the artifact actually load?"""
    if not resolved:
        return {"check": "artifact_loads", "ok": False,
                "why": "nothing resolved to load"}
    if not resolved.endswith(".json"):
        # A .pt or other non-JSON artifact is out of this checker's scope; saying so is
        # better than reporting a pass it did not establish.
        return {"check": "artifact_loads", "ok": None,
                "why": f"not a JSON artifact ({os.path.basename(resolved)}) — this "
                       f"check only loads JSON boosters, so it is SKIPPED, not passed"}
    try:
        with open(resolved, "rb") as fh:
            payload = json.loads(fh.read())
    except (OSError, ValueError) as exc:
        return {"check": "artifact_loads", "ok": False,
                "why": f"{type(exc).__name__}: {exc}"}
    if not isinstance(payload, dict) or not payload.get("booster_raw_json"):
        return {"check": "artifact_loads", "ok": False,
                "why": "no `booster_raw_json` in the artifact"}
    return {"check": "artifact_loads", "ok": True}


def preflight(lane: str, runner_config: str, bases: list[str],
              watched: list[str], shadow_name: str) -> dict:
    declared = check_declared(runner_config, lane)
    entry = declared.get("entry")
    artifact = check_artifact(entry, bases)
    resolved = None
    if artifact.get("ok") and artifact.get("resolves_under"):
        b = artifact["resolves_under"][0]
        resolved = (artifact["artifact_path"] if b == "<absolute>"
                    else os.path.normpath(os.path.join(b, artifact["artifact_path"])))
    checks = [declared, artifact,
              check_sentinel_visible(lane, watched, shadow_name),
              check_loadable(resolved)]
    failed = [c["check"] for c in checks if c["ok"] is False]
    return {"lane": lane, "runner_config": runner_config, "checks": checks,
            "n_failed": len(failed), "failed": failed,
            "scope_note": (
                "These are MECHANICAL preconditions for a lane to be served and seen. "
                "Passing them says nothing about whether the model is any good, whether "
                "it should be deployed, or whether the lane will produce a usable "
                "signal. A skipped check (ok=null) is not a pass.")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lane", required=True)
    ap.add_argument("--runner-config", required=True,
                    help="the config the RUNNER reads — the pinned one (R5)")
    ap.add_argument("--base", action="append", dest="bases", default=[],
                    help="a directory artifact_path may be relative to")
    ap.add_argument("--watched-lane", action="append", dest="watched", default=[],
                    help="a lane name the sentinel watches; pass more than once")
    ap.add_argument("--shadow-name", default="hf_patchtst",
                    help="the sentinel's SHADOW_NAME, for the '_<suffix>' rule")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if not a.watched:
        print("shadow-lane preflight: --watched-lane is required — with none, check 3 "
              "would pass or fail on an empty set and mean nothing", file=sys.stderr)
        return 2

    rep = preflight(a.lane, a.runner_config, list(a.bases), list(a.watched),
                    a.shadow_name)
    if a.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        print(f"lane: {rep['lane']}")
        for c in rep["checks"]:
            mark = {True: "PASS", False: "FAIL", None: "SKIP"}[c["ok"]]
            print(f"  {mark}  {c['check']}")
            for k in ("why", "note", "resolves_under", "watched_lanes"):
                if c.get(k):
                    print(f"        {k}: {c[k]}")
        print(f"\n{rep['n_failed']} check(s) failed: {rep['failed'] or 'none'}")
        print("\n" + rep["scope_note"])
    return 1 if rep["n_failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
