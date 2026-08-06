#!/usr/bin/env python3
"""Which scheduled jobs execute the PINNED kernel, and which the umbrella one?

WHY (P0, 2026-08-05). `compute_position_size` exists twice: once in the pinned
`renquant-pipeline` runtime and once in the umbrella tree. The pinned copy clamps
the 25 % oversize fallback; the umbrella copy does not, and sizes 21-25 % single
positions. That is 1 defect in 1 file — but the two kernels have diverged in
**120 of the 169 files they share**, so "which copy ran" decides far more than
one sizer.

Nothing in review shows you the answer. The multirepo bridge aliases
`kernel.<stem>` -> `renquant_pipeline.kernel.<stem>` (`live_bridge.py`), so a job
that dispatches through `daily-bridge`/`live-bridge` executes the PINNED kernel,
and a job that invokes `-m live.runner` directly executes the UMBRELLA one. The
difference is a single line inside a shell wrapper, and it is invisible in the
launchd manifest that review actually reads.

This turns that into a census: every job in `ops/launchd_manifest.json`,
classified by the kernel it will import.

TWO REFUSALS, both because a silent answer here is worse than none:

  * A wrapper that cannot be read is `WRAPPER_UNREADABLE`, never "no runner".
    An unreadable wrapper is not a safe one, and the whole point of this probe
    is that the dangerous state is the one nobody looked at.
  * A wrapper that dispatches on `RQ_DAILY_RUNNER` is reported as
    `BRIDGE_WITH_UMBRELLA_FALLBACK` together with whether that variable is
    actually set anywhere -- the fallback is dormant, not absent, and a census
    that called it "pinned" would be describing today's env as if it were the
    contract.

Read-only. Touches no umbrella file. Usage:
    python ops/renquant104/kernel_surface_census.py [--json]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys

ORCH_REPO = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ORCH_REPO / "ops" / "launchd_manifest.json"
DEFAULT_LAUNCHAGENTS = pathlib.Path.home() / "Library" / "LaunchAgents"

# `-m live.runner` with any amount of quoting/whitespace between, which covers
# both the shell form (`-m live.runner`) and the embedded-python list form
# (`"-m", "live.runner"`) that daily_104.sh uses for its shadow lanes.
DIRECT_RUNNER_RE = re.compile(r"-m[\"'\s,]+live\.runner")
BRIDGE_RE = re.compile(r"\b(daily-bridge|live-bridge)\b")
RUNNER_ENV_VAR = "RQ_DAILY_RUNNER"

PINNED = "BRIDGE_PINNED_KERNEL"
UMBRELLA = "DIRECT_UMBRELLA_KERNEL"
FALLBACK = "BRIDGE_WITH_UMBRELLA_FALLBACK"
NO_RUNNER = "NO_LIVE_RUNNER"
UNREADABLE = "WRAPPER_UNREADABLE"
NO_WRAPPER = "NO_WRAPPER_IN_PROGRAM_ARGS"

# The states in which a job can execute the stale umbrella kernel. Named as a
# set rather than tested inline so that adding a state cannot silently inherit
# the benign default -- an enumerated allow-list that leaves a fail-open `else`
# is exactly how this class of guard goes quiet.
REACHES_UMBRELLA = frozenset({UMBRELLA})
UNDETERMINED = frozenset({UNREADABLE, NO_WRAPPER})


class ManifestUnreadable(RuntimeError):
    """The manifest itself could not be parsed. Not an empty census."""


def wrapper_of(program_args: list) -> str | None:
    """The first .sh/.py argument. launchd jobs here are `<interp> <wrapper>`."""
    for a in program_args or []:
        if isinstance(a, str) and a.endswith((".sh", ".py")):
            return a
    return None


def classify_text(text: str) -> str:
    bridge = bool(BRIDGE_RE.search(text))
    direct = bool(DIRECT_RUNNER_RE.search(text))
    if bridge and direct:
        return FALLBACK
    if bridge:
        return PINNED
    if direct:
        return UMBRELLA
    return NO_RUNNER


def runner_env_is_set(launchagents: pathlib.Path = DEFAULT_LAUNCHAGENTS,
                      manifest: dict | None = None) -> dict:
    """Is RQ_DAILY_RUNNER armed anywhere? Reported, never assumed.

    Checked in BOTH places it could live -- the loaded plists and the manifest's
    own environment blocks -- because a census that only read one of them would
    be true about the file it read and wrong about the machine."""
    plists = []
    if launchagents.is_dir():
        for p in sorted(launchagents.glob("*.plist")):
            try:
                if RUNNER_ENV_VAR in p.read_text(encoding="utf-8", errors="replace"):
                    plists.append(p.name)
            except OSError:
                continue
    in_manifest = []
    for label, spec in ((manifest or {}).get("jobs") or {}).items():
        env = (spec or {}).get("environment") or (spec or {}).get("env") or {}
        if RUNNER_ENV_VAR in env:
            in_manifest.append(label)
    return {
        "var": RUNNER_ENV_VAR,
        "launchagent_plists_setting_it": plists,
        "manifest_jobs_setting_it": in_manifest,
        "armed_anywhere": bool(plists or in_manifest),
    }


def census(manifest_path: pathlib.Path = DEFAULT_MANIFEST,
           launchagents: pathlib.Path = DEFAULT_LAUNCHAGENTS) -> dict:
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestUnreadable(f"{manifest_path}: {exc}") from exc
    if not isinstance(manifest, dict) or not isinstance(manifest.get("jobs"), dict):
        raise ManifestUnreadable(
            f"{manifest_path}: expected a JSON object with a 'jobs' object")

    rows = []
    for label, spec in sorted(manifest["jobs"].items()):
        wrapper = wrapper_of((spec or {}).get("program_args") or [])
        if wrapper is None:
            rows.append({"label": label, "wrapper": None, "surface": NO_WRAPPER,
                         "note": "no .sh/.py in program_args"})
            continue
        try:
            text = pathlib.Path(wrapper).read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            # NOT NO_RUNNER. See module docstring.
            rows.append({"label": label, "wrapper": wrapper, "surface": UNREADABLE,
                         "note": str(exc)})
            continue
        rows.append({"label": label, "wrapper": wrapper,
                     "surface": classify_text(text), "note": None})

    env = runner_env_is_set(launchagents, manifest)
    by = {}
    for r in rows:
        by[r["surface"]] = by.get(r["surface"], 0) + 1

    # A fallback job's surface depends on the ENVIRONMENT, not on its wrapper
    # alone. Once RQ_DAILY_RUNNER=umbrella is armed anywhere, every
    # BRIDGE_WITH_UMBRELLA_FALLBACK job DOES execute the umbrella kernel and is
    # no longer dormant.
    #
    # An earlier revision counted FALLBACK rows as dormant unconditionally, so on
    # an armed machine it reported n_reaching_umbrella_kernel=0 alongside
    # fallback_is_armed=true -- under-reporting exposure in exactly the scenario
    # this probe exists to surface (codex MED on orch#854).
    armed = env["armed_anywhere"]
    n_fallback = sum(1 for r in rows if r["surface"] == FALLBACK)
    n_direct = sum(1 for r in rows if r["surface"] in REACHES_UMBRELLA)
    return {
        "manifest": str(manifest_path),
        "jobs": rows,
        "counts": by,
        "runner_env": env,
        # Direct importers ALWAYS reach it; fallback jobs reach it only when armed.
        "n_reaching_umbrella_kernel": n_direct + (n_fallback if armed else 0),
        "n_direct_umbrella_kernel": n_direct,
        "n_undetermined": sum(1 for r in rows if r["surface"] in UNDETERMINED),
        # Dormant ONLY while the env is unarmed. Reported separately from the
        # total so a reader never has to infer one from the other.
        "n_with_dormant_umbrella_fallback": 0 if armed else n_fallback,
        "n_with_armed_umbrella_fallback": n_fallback if armed else 0,
        "fallback_is_armed": armed,
    }


def render(c: dict) -> str:
    out = ["kernel surface census — which kernel does each scheduled job import?", ""]
    order = {UMBRELLA: 0, FALLBACK: 1, UNREADABLE: 2, NO_WRAPPER: 3, PINNED: 4,
             NO_RUNNER: 5}
    for r in sorted(c["jobs"], key=lambda r: (order.get(r["surface"], 9), r["label"])):
        if r["surface"] == NO_RUNNER:
            continue
        w = pathlib.Path(r["wrapper"]).name if r["wrapper"] else "—"
        out.append(f"  {r['label']:<42}{w:<34}{r['surface']}")
        if r["note"]:
            out.append(f"      note: {r['note']}")
    out.append("")
    out.append(f"  jobs importing the UMBRELLA (stale) kernel : "
               f"{c['n_reaching_umbrella_kernel']}")
    out.append(f"  jobs with a DORMANT umbrella fallback      : "
               f"{c['n_with_dormant_umbrella_fallback']}")
    out.append(f"  jobs whose surface is UNDETERMINED         : {c['n_undetermined']}")
    e = c["runner_env"]
    out.append(f"  {e['var']} armed anywhere                  : {e['armed_anywhere']}"
               + (f"  ({e['launchagent_plists_setting_it'] + e['manifest_jobs_setting_it']})"
                  if e["armed_anywhere"] else ""))
    if c["n_undetermined"]:
        out.append("")
        out.append("  UNDETERMINED is not a pass: a wrapper that could not be read is\n"
                   "  not a wrapper that was found safe.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", type=pathlib.Path, default=DEFAULT_MANIFEST)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    try:
        c = census(args.manifest)
    except ManifestUnreadable as exc:
        print(f"REFUSING: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(c, indent=2) if args.json else render(c))
    # Exit 1 when anything is undetermined: an unmeasured surface is the state
    # this probe exists to make loud.
    return 1 if c["n_undetermined"] else 0


if __name__ == "__main__":
    sys.exit(main())
