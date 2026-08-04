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

Exit codes `[codex on orch#699, round 3]`:

  ``0``  every precondition was CHECKED and PASSED
  ``1``  at least one precondition FAILED
  ``3``  nothing failed, but at least one precondition was SKIPPED -- not established
  ``2``  usage/IO error

A SKIPPED check used to leave the process green while the report printed "SKIPPED, not
passed". A caller reads the exit code, so the two surfaces disagreed and the exit code
won. `3` is distinct from `1` on purpose: "we could not establish this" sends a reader
somewhere different from "this is broken".
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


def check_artifact(entry: dict | None, bases: list[str],
                   loader_base: str | None = None) -> dict:
    """2 — does the artifact resolve, and under WHICH base?

    AMBIGUITY IS NON-PASSING `[codex on orch#699]`. The first version returned `ok=True`
    when a path resolved under several bases and let `preflight` silently take
    `resolves_under[0]` — contradicting this module's own statement that the loader's
    base is not established here. A check cannot both refuse to name the authoritative
    base and quietly pick one.

    Supply `--loader-base` to resolve it: with a declared base, that base decides and the
    check can pass. Without one, multiple resolving bases yield `ok=None` — SKIPPED, not
    passed.
    """
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
    if not bases:
        # #723: zero DECLARED bases is the same epistemic state as multiple bases with
        # no --loader-base — whether the path resolves is UNESTABLISHED, because this
        # checker was never told where to look. ok=False here asserted a fact it had
        # no evidence for, and a base-less call site would have alarmed on every lane
        # forever.
        return {"check": "artifact_resolves", "ok": None, "artifact_path": rel,
                "resolves_under": [],
                "why": "no --base was declared, so whether this path resolves is "
                       "UNESTABLISHED — SKIPPED, not failed"}
    hits = [b for b in bases
            if os.path.exists(os.path.normpath(os.path.join(b, rel)))]
    if not hits:
        return {"check": "artifact_resolves", "ok": False, "artifact_path": rel,
                "resolves_under": [], "why": f"resolves under none of {bases}"}
    if len(hits) > 1 and not loader_base:
        return {"check": "artifact_resolves", "ok": None, "artifact_path": rel,
                "resolves_under": hits,
                "why": f"{len(hits)} bases resolve this path and no --loader-base was "
                       f"declared, so WHICH ONE the loader uses is unknown. SKIPPED, not "
                       f"passed: choosing the first would be this checker asserting the "
                       f"authority it says it cannot establish."}
    if loader_base:
        chosen = os.path.normpath(os.path.join(loader_base, rel))
        if not os.path.exists(chosen):
            return {"check": "artifact_resolves", "ok": False, "artifact_path": rel,
                    "resolves_under": hits,
                    "why": f"declared loader base {loader_base} does NOT resolve it "
                           f"(other bases do: {hits}) — a lane that resolves only "
                           f"somewhere the loader does not look is not served"}
        return {"check": "artifact_resolves", "ok": True, "artifact_path": rel,
                "resolves_under": [loader_base], "also_resolves_under": hits,
                "note": (f"{len(hits)} bases resolve it; the declared loader base was "
                         f"used" if len(hits) > 1 else "")}
    return {"check": "artifact_resolves", "ok": True, "artifact_path": rel,
            "resolves_under": hits}


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


def check_loadable(resolved: str | None, upstream_ok: bool | None = False) -> dict:
    """4 — does the artifact actually load?

    A MISSING INPUT IS A SKIP, NOT A FAILURE. When check 2 could not establish which base
    the loader uses, or found the artifact nowhere, loadability is **unestablished** — it
    was not falsified. Reporting it as a second FAILURE both double-counts the upstream
    problem and, worse, let an ambiguity regression pass for the wrong reason: the test
    written to prove ambiguity is non-passing was green because its fixture happened to
    fail HERE instead.
    """
    if not resolved:
        return {"check": "artifact_loads", "ok": None,
                "why": ("no artifact was resolved upstream, so loadability is "
                        "UNESTABLISHED — SKIPPED, not failed; the upstream check "
                        f"reports the reason (artifact_resolves ok={upstream_ok})")}
    if resolved.endswith(".jsonl"):
        # The momentum lane declares its LEDGER as the artifact_path (machine-produced
        # `momentum_artifact_ledger.jsonl`); the serving loader follows the verified
        # tail row to the dated artifact beside it. Before 2026-08-03 this branch
        # SKIPPED ("only loads JSON boosters"), which made the detector exit 3 and
        # the whole ops-audit line UNUSABLE on a HEALTHY lane — a permanent skip on
        # a living lane is a blind spot, not caution.
        return _check_momentum_ledger_loadable(resolved)
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
    # ACTUALLY LOAD IT `[codex on orch#699]`. Testing that the FIELD is non-empty
    # establishes structural presence, not loadability: a truncated or
    # wrong-version booster passes that test and fails at serving time. The
    # canonical loader is the only thing that can answer the question this check
    # claims to answer.
    try:
        import xgboost as xgb
    except ImportError as exc:
        return {"check": "artifact_loads", "ok": None,
                "why": f"xgboost unavailable ({exc}) — the canonical loader could not "
                       f"be invoked, so this is SKIPPED, not passed. Structural "
                       f"presence of `booster_raw_json` was confirmed; loadability was "
                       f"NOT."}
    raw = payload["booster_raw_json"]
    try:
        booster = xgb.Booster()
        booster.load_model(bytearray(raw if isinstance(raw, str)
                                     else json.dumps(raw), "utf-8"))
    except Exception as exc:  # noqa: BLE001
        return {"check": "artifact_loads", "ok": False,
                "why": f"the canonical loader REFUSED it: "
                       f"{type(exc).__name__}: {str(exc)[:160]}"}
    return {"check": "artifact_loads", "ok": True,
            "note": "loaded by xgboost.Booster.load_model, not merely present"}


#: Dated-artifact basename beside the momentum ledger. MUST equal the serving
#: convention (pipeline momentum_residual_scorer / model tools ARTIFACT_BASENAME);
#: a test pins the literal so a renamed convention breaks there, not silently here.
MOMENTUM_ARTIFACT_BASENAME = "momentum_residual_v0.json"


def _check_momentum_ledger_loadable(ledger_path: str) -> dict:
    """Mechanical loadability for the momentum lane's ledger-declared artifact.

    What this DOES establish: the ledger's tail row parses, the dated artifact
    it points at (`<ledger dir>/<cutoff_date>/momentum_residual_v0.json`)
    exists and parses as JSON, its `kind` matches the row's, and the row's
    `artifact_content_sha256` pin EQUALS the artifact's self-carried
    `content_sha256`.

    What this deliberately does NOT do: recompute any digest. The canonical
    byte-level chain verification (per-row chain, body recompute, pin-over-
    bytes) belongs to the serving loader in renquant-pipeline; a hand-copied
    recompute here would be a fourth fingerprint implementation — the exact
    triple-impl class behind the recurring calibrator mismatch incidents.
    String-comparing the two DECLARED identities catches the swapped-file and
    stale-ledger shapes without re-implementing the recipe.
    """
    try:
        with open(ledger_path, "rb") as fh:
            lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    except OSError as exc:
        return {"check": "artifact_loads", "ok": False,
                "why": f"ledger unreadable: {type(exc).__name__}: {exc}"}
    if not lines:
        return {"check": "artifact_loads", "ok": False,
                "why": "ledger has no rows — nothing has ever been produced, so "
                       "there is no artifact to serve"}
    try:
        row = json.loads(lines[-1])
    except ValueError as exc:
        return {"check": "artifact_loads", "ok": False,
                "why": f"ledger tail row is not JSON: {exc}"}
    cutoff = row.get("cutoff_date")
    pinned = row.get("artifact_content_sha256")
    row_kind = row.get("kind")
    # NON-EMPTY STRINGS required, not merely present [codex on orch#770]: a
    # row with kind=None comparing equal to an artifact with kind=None, or a
    # str() coercion equating pin "123" with field 123, would restore a green
    # ops-audit signal over exactly the malformed data the serving loader
    # rejects. The pipeline requires these fields and compares native values;
    # so does this preflight.
    if not (isinstance(cutoff, str) and cutoff
            and isinstance(pinned, str) and pinned
            and isinstance(row_kind, str) and row_kind):
        return {"check": "artifact_loads", "ok": False,
                "why": "ledger tail row lacks non-empty string "
                       "cutoff_date/artifact_content_sha256/kind — the serving "
                       "loader requires all three; nothing resolvable to serve"}
    dated = os.path.join(os.path.dirname(ledger_path), str(cutoff),
                         MOMENTUM_ARTIFACT_BASENAME)
    try:
        with open(dated, "rb") as fh:
            artifact = json.loads(fh.read())
    except OSError as exc:
        return {"check": "artifact_loads", "ok": False,
                "why": f"dated artifact the tail row points at is unreadable "
                       f"({dated}): {type(exc).__name__}: {exc}"}
    except ValueError as exc:
        return {"check": "artifact_loads", "ok": False,
                "why": f"dated artifact is not JSON ({dated}): {exc}"}
    art_kind = artifact.get("kind") if isinstance(artifact, dict) else None
    if not (isinstance(art_kind, str) and art_kind):
        return {"check": "artifact_loads", "ok": False,
                "why": f"dated artifact lacks a non-empty string kind "
                       f"(got {art_kind!r}) — the serving loader requires it"}
    if row_kind != art_kind:
        return {"check": "artifact_loads", "ok": False,
                "why": f"kind mismatch: ledger row says {row_kind!r}, artifact "
                       f"says {art_kind!r}"}
    carried = artifact.get("content_sha256") if isinstance(artifact, dict) else None
    if not (isinstance(carried, str) and carried):
        return {"check": "artifact_loads", "ok": False,
                "why": f"dated artifact lacks a non-empty string content_sha256 "
                       f"(got {type(carried).__name__}) — the serving loader "
                       f"requires it"}
    # NATIVE equality — both proven non-empty str above; no coercion.
    if carried != pinned:
        return {"check": "artifact_loads", "ok": False,
                "why": f"identity mismatch: ledger pins {pinned[:16]}…, artifact "
                       f"self-carries {carried[:16]}… — a swapped or stale "
                       f"dated file"}
    return {"check": "artifact_loads", "ok": True,
            "note": f"ledger tail ({cutoff}) resolves to {MOMENTUM_ARTIFACT_BASENAME}; "
                    f"kind + declared identity agree (byte-level chain verification "
                    f"is the serving loader's job, deliberately not duplicated here)"}


def preflight(lane: str, runner_config: str, bases: list[str],
              watched: list[str], shadow_name: str,
              loader_base: str | None = None) -> dict:
    declared = check_declared(runner_config, lane)
    entry = declared.get("entry")
    artifact = check_artifact(entry, bases, loader_base)
    resolved = None
    if artifact.get("ok") and artifact.get("resolves_under"):
        # Exactly one entry here by construction: `check_artifact` returns ok=True only
        # for a single resolving base or a declared loader base.
        b = artifact["resolves_under"][0]
        resolved = (artifact["artifact_path"] if b == "<absolute>"
                    else os.path.normpath(os.path.join(b, artifact["artifact_path"])))
    checks = [declared, artifact,
              check_sentinel_visible(lane, watched, shadow_name),
              check_loadable(resolved, artifact.get("ok"))]
    failed = [c["check"] for c in checks if c["ok"] is False]
    skipped = [c["check"] for c in checks if c["ok"] is None]
    return {"lane": lane, "runner_config": runner_config, "checks": checks,
            "n_failed": len(failed), "failed": failed,
            "n_skipped": len(skipped), "skipped": skipped,
            "scope_note": (
                "These are MECHANICAL preconditions for a lane to be served and seen. "
                "Passing them says nothing about whether the model is any good, whether "
                "it should be deployed, or whether the lane will produce a usable "
                "signal. A skipped check (ok=null) is not a pass.")}


#: Resolved defaults (#723: the tool had no caller partly because every invocation
#: had to reconstruct these). The pinned config is the runner's real input (R5), the
#: umbrella base is where its artifact_paths are relative to, and the default lanes are
#: WHATEVER shadow_models the pinned config declares — resolved at run time, never a
#: hardcoded lane list that rots.
DEFAULT_RUNNER_CONFIG = os.environ.get(
    "RQ104_RUNNER_CONFIG",
    "/Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/renquant-strategy-104/"
    "configs/strategy_config.json")
#: TWO default bases, because the deployment splits exactly this way (live-deploy
#: mechanism: config from the pinned subrepo, artifacts from the umbrella tree): the
#: clf lane's artifact_path resolves under backtesting/renquant_104, the PatchTST
#: lane's under the umbrella root. Each lane resolves under exactly one, so the
#: multi-base ambiguity rule stays dormant unless something genuinely duplicates.
DEFAULT_BASES = [
    os.environ.get("RQ104_ARTIFACT_BASE",
                   "/Users/renhao/git/github/RenQuant/backtesting/renquant_104"),
    os.environ.get("RQ104_UMBRELLA_ROOT", "/Users/renhao/git/github/RenQuant"),
]


def declared_lanes(runner_config: str) -> list[str]:
    """The shadow_models names the pinned config declares. Read, not assumed."""
    with open(runner_config) as fh:
        cfg = json.load(fh)
    models = (((cfg.get("ranking") or {}).get("panel_scoring") or {})
              .get("shadow_models") or [])
    return [m.get("name") for m in models if isinstance(m, dict) and m.get("name")]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lane", default=None,
                    help="default: run EVERY lane the runner config declares")
    ap.add_argument("--runner-config", default=DEFAULT_RUNNER_CONFIG,
                    help="the config the RUNNER reads — the pinned one (R5)")
    ap.add_argument("--base", action="append", dest="bases", default=[],
                    help="a directory artifact_path may be relative to")
    ap.add_argument("--watched-lane", action="append", dest="watched", default=[],
                    help="a lane name the sentinel watches; pass more than once")
    ap.add_argument("--loader-base", default=None,
                    help="the base the LOADER uses; required to pass check 2 when more "
                         "than one base resolves the artifact")
    ap.add_argument("--shadow-name", default="hf_patchtst",
                    help="the sentinel's SHADOW_NAME, for the '_<suffix>' rule")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    lanes = [a.lane] if a.lane else None
    if lanes is None:
        try:
            lanes = declared_lanes(a.runner_config)
        except (OSError, ValueError) as exc:
            print(f"shadow-lane preflight: cannot resolve lanes from "
                  f"{a.runner_config}: {exc}", file=sys.stderr)
            return 2
        if not lanes:
            print("shadow-lane preflight: the runner config declares no shadow_models "
                  "— nothing to check is a FINDING here, not a pass", file=sys.stderr)
            return 1
    if not a.watched:
        # Default: the CONFIG-declared lanes are the watched set — the sentinel's
        # registry mirrors the config (orch#727 verified both lanes patrolled). NOT
        # defaulted from --lane: an explicit lane against a config declaring nothing
        # must still hit the empty-watched refusal below (the pre-existing contract).
        try:
            a.watched = declared_lanes(a.runner_config)
        except (OSError, ValueError):
            pass
    if not a.watched:
        print("shadow-lane preflight: --watched-lane is required — with none, check 3 "
              "would pass or fail on an empty set and mean nothing", file=sys.stderr)
        return 2

    bases = list(a.bases) or list(DEFAULT_BASES)
    reports = [preflight(l, a.runner_config, bases, list(a.watched),
                         a.shadow_name, a.loader_base) for l in lanes]
    rep = reports[0] if len(reports) == 1 else {
        "lanes": [r["lane"] for r in reports],
        "checks": [c for r in reports for c in
                   [{**c, "lane": r["lane"]} for c in r["checks"]]],
        "n_failed": sum(r["n_failed"] for r in reports),
        "failed": [f"{r['lane']}:{f}" for r in reports for f in r["failed"]],
        "n_skipped": sum(r["n_skipped"] for r in reports),
        "skipped": [f"{r['lane']}:{f}" for r in reports for f in r["skipped"]],
        "scope_note": reports[0]["scope_note"], "lane": ", ".join(l for l in lanes)}
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
        print(f"{rep['n_skipped']} check(s) SKIPPED (not passed): "
              f"{rep['skipped'] or 'none'}")
        print("\n" + rep["scope_note"])
    if rep["n_failed"]:
        return 1
    # A skipped precondition is NOT a pass. Distinct code so the two outcomes stay
    # distinguishable to a caller, per the module docstring.
    return 3 if rep["n_skipped"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
