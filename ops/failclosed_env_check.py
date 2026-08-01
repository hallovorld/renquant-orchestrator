#!/usr/bin/env python3
"""Is the fail-closed guard actually ARMED in the deployed job? (GOAL-5, P0)

MEASURED 2026-07-31 — it is not, on `com.renquant.daily104`.

`daily_104.sh` resolves the production strategy config from the PINNED subrepo, and on
failure it either aborts or falls back:

    if ! PROD_STRATEGY_CONFIG="$(renquant_strategy_config "$SUBREPO_ROOT" ...)"; then
        if { [ "${RENQUANT_STRICT_SUBREPO_PATHS:-0}" = "1" ] \\
             || [ "${RENQUANT_OPS_FAIL_CLOSED:-0}" = "1" ]; } \\
            && [ "${RQ_DAILY_RUNNER:-multirepo}" != "umbrella" ]; then
            echo "ERROR: pinned ... unavailable"; exit 1
        fi
        PROD_STRATEGY_CONFIG="$REPO_DIR/backtesting/renquant_104/strategy_config.json"
    fi

Both flags default to ``0``. Checked in every place either could be set — the installed
plist's ``EnvironmentVariables``, `daily_104.sh`, and `scripts/subrepo_env.sh` — **neither
is set anywhere**; the two scripts only ever *read* them.

WHY THAT MATTERS. Twin-registry **R5** records that the two configs are inverted: the
pinned one makes XGB primary, the umbrella one makes a PatchTST checkpoint primary. So the
fallback does not merely pick a different file — it **swaps which model decides the book**,
to a checkpoint measured at 625 days stale against a 28-day limit, whose scores are
intrinsically all-negative and therefore admit no name at all.

AND THE FALLBACK IS SILENT. There is an ``echo`` on the abort path and **none** on the
fallback path. The substitution leaves no log line, so "did this happen?" is not answerable
after the fact from the run log.

WHAT THIS TOOL CLAIMS AND DOES NOT. It reports whether the guard is **armed**. It does
**not** claim the resolver is currently failing, and therefore does not claim the book is
being decided by the stale checkpoint today — that is a separate measurement against a
separate artifact. The claim here is narrower and sufficient: **the guard that would stop
a known, documented failure mode is disabled in the deployed job.**

Read-only. Parses plists and shell scripts, writes nothing, never invokes git, never
mutates a job.

Exit codes: ``0`` every declared job arms the guard, ``1`` at least one does not (or a
declared job/script is missing), ``2`` usage/IO error — so a broken invocation cannot be
mistaken for an armed guard.
"""

from __future__ import annotations

import argparse
import json
import os
import plistlib
import re
import subprocess
import sys

#: Either flag arms the guard — the shell condition is an OR.
FAILCLOSED_FLAGS = ("RENQUANT_STRICT_SUBREPO_PATHS", "RENQUANT_OPS_FAIL_CLOSED")

#: An assignment, not a read. `${VAR:-0}` and `[ "$VAR" = "1" ]` are reads and must not
#: count as arming it — that mistake would report every script that merely *mentions* the
#: flag as having set it, which is the fail-open version of this whole check.
#:
#: AND THE VALUE MUST BE 1 `[codex on orch#695]`. The first version counted ANY
#: assignment, so `export RENQUANT_OPS_FAIL_CLOSED=0` reported ARMED while the job still
#: took the fallback path — a fail-open false positive that also DISAGREED with the plist
#: branch, which checks the value. The two halves of one check must not answer
#: differently.
_ASSIGN = (r"(?:^|\n)(?P<indent>[ \t]*)(?:export[ \t]+)?"
           r"{name}[ \t]*=(?P<val>[^\n#]*)")


def _plist_load(path: str) -> dict | None:
    """Parse a plist, falling back to `plutil` for ones expat refuses.

    Two of the heavily-annotated plists contain `--` inside an XML comment, which
    `plistlib`'s expat rejects while launchd loads them fine. Treating that as "job
    absent" would under-count the surface and read as evidence about it.
    """
    try:
        with open(path, "rb") as fh:
            return plistlib.load(fh)
    except Exception:  # noqa: BLE001
        try:
            res = subprocess.run(["plutil", "-convert", "xml1", "-o", "-", "--", path],
                                 capture_output=True, timeout=30)
            return plistlib.loads(res.stdout) if res.returncode == 0 else None
        except Exception:  # noqa: BLE001
            return None


def script_assigns(path: str, name: str) -> tuple[bool, list[str]]:
    """(unambiguously_arms, findings) for ONE file.

    ARMS only when this file contains **exactly one** assignment of `name`, that
    assignment is at **top level** (column 0, optionally `export `), and its value is a
    literal `1`.

    WHY NOT SHELL SEMANTICS `[codex on orch#695]`. An earlier version claimed
    "last assignment wins". That is false in two ways this checker cannot see:

      * **across files** — `audit_job` inspects a ProgramArguments script AND sourced
        helpers, and their real execution order is not knowable from the plist;
      * **inside conditionals** — `if false; then FLAG=1; fi` is a syntactic assignment
        and an unreachable one, and a regex cannot tell them apart.

    Modelling reachability and source order is a static-analysis project, not an ops
    check. So the rule is the conservative half of the review's own offer: **anything
    other than one unambiguous effective assignment is INDETERMINATE and does not arm.**
    """
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return False, [f"unreadable: {path}"]
    hits = list(re.finditer(_ASSIGN.format(name=re.escape(name)), text))
    if not hits:
        return False, []
    if len(hits) > 1:
        return False, [f"{name} assigned {len(hits)} times in this file — INDETERMINATE, "
                       f"does not arm (execution order is not modelled)"]
    m = hits[0]
    # The indentation is captured by the pattern, not re-derived from offsets: an
    # earlier attempt computed the line with `rfind("\n", 0, m.start())`, but the
    # pattern itself begins at the preceding newline, so that walked back one line too
    # far and the indent test never fired.
    if m.group("indent"):
        return False, [f"{name} is assigned in an INDENTED line — possibly inside a "
                       f"conditional or function; INDETERMINATE, does not arm"]
    raw = (m.group("val") or "").strip()
    val = raw.strip('"').strip("'").strip()
    if any(c in raw for c in "$`("):
        return False, [f"{name}={raw!r} is DYNAMIC — cannot be evaluated here, does not "
                       f"arm"]
    if val != "1":
        return False, [f"{name}={raw!r} does NOT arm the guard (only `1` does)"]
    return True, []


def audit_job(plist_path: str, extra_scripts: list[str]) -> dict:
    row: dict = {"plist": os.path.basename(plist_path),
                 "plist_path": plist_path,
                 "plist_exists": os.path.exists(plist_path)}
    if not row["plist_exists"]:
        # A declared job that is not installed is a FAILURE, not a pass: otherwise
        # uninstalling the job is the cheapest way to make this check green.
        return {**row, "status": "job_not_installed", "armed": False}
    data = _plist_load(plist_path)
    if data is None:
        return {**row, "status": "plist_unparseable", "armed": False}

    env = data.get("EnvironmentVariables")
    if env is not None and not isinstance(env, dict):
        return {**row, "status": "malformed_environment", "armed": False,
                "why": f"EnvironmentVariables is {type(env).__name__}, not a dict"}
    env = env or {}
    from_env = sorted(f for f in FAILCLOSED_FLAGS if str(env.get(f, "0")) == "1")

    program = data.get("ProgramArguments")
    scripts = [p for p in (program if isinstance(program, list) else [])
               if isinstance(p, str) and os.path.exists(p)]
    scripts += [p for p in extra_scripts if os.path.exists(p)]
    # ACROSS FILES, TOO `[codex on orch#695]`. A flag armed in one script and disarmed
    # in another is INDETERMINATE: the plist does not tell us which runs, or in what
    # order relative to a sourced helper. Only a flag with exactly ONE unambiguously
    # arming file and NO other assignment anywhere counts.
    from_script, script_findings = set(), []
    for f in FAILCLOSED_FLAGS:
        arming, touching = [], []
        for sc in scripts:
            arms, why = script_assigns(sc, f)
            if arms:
                arming.append(sc)
            if why:
                touching.append(sc)
                script_findings.extend(f"{os.path.basename(sc)}: {w}" for w in why)
        if len(arming) == 1 and not touching:
            from_script.add(f)
        elif arming:
            script_findings.append(
                f"{f}: armed in {[os.path.basename(x) for x in arming]} but also "
                f"assigned/ambiguous in {[os.path.basename(x) for x in touching]} — "
                f"INDETERMINATE across files, does not arm")
    from_script = sorted(from_script)

    return {**row, "status": "checked",
            "armed": bool(from_env or from_script),
            "armed_by_plist_env": from_env,
            "armed_by_script_assignment": from_script,
            "script_findings": script_findings,
            "scripts_inspected": scripts,
            "n_scripts_inspected": len(scripts)}


def audit(jobs: list[str], extra_scripts: list[str]) -> dict:
    rows = [audit_job(p, extra_scripts) for p in jobs]
    return {
        "n_jobs_declared": len(jobs),
        "n_armed": sum(1 for r in rows if r["armed"]),
        "unarmed": [r["plist"] for r in rows if not r["armed"]],
        "jobs": rows,
        "flags": list(FAILCLOSED_FLAGS),
        "scope_note": (
            "This reports whether the guard is ARMED. It does not claim the resolver is "
            "currently failing, and so does not claim the stale checkpoint is deciding "
            "the book today — that is a separate measurement. The claim is narrower and "
            "sufficient: the guard that would stop a known, documented failure mode "
            "(twin-registry R5) is disabled in the deployed job."),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--job", action="append", dest="jobs", required=True,
                    help="path to an installed launchd plist; pass more than once")
    ap.add_argument("--also-script", action="append", dest="scripts", default=[],
                    help="an additional script that could assign the flags "
                         "(e.g. a sourced env helper)")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        rep = audit(list(a.jobs), list(a.scripts))
    except OSError as exc:
        print(f"fail-closed check: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if a.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        for r in rep["jobs"]:
            mark = "ARMED    " if r["armed"] else "NOT ARMED"
            print(f"  {mark} {r['plist']}  [{r['status']}]")
            if r["status"] == "checked":
                print(f"            plist env: {r['armed_by_plist_env'] or 'neither flag'}")
                print(f"            script assignment: "
                      f"{r['armed_by_script_assignment'] or 'none'} "
                      f"({r['n_scripts_inspected']} script(s) inspected)")
                for w in r.get("script_findings", []):
                    print(f"              {w}")
            elif r.get("why"):
                print(f"            {r['why']}")
        print(f"\n{rep['n_armed']} of {rep['n_jobs_declared']} declared job(s) arm "
              f"the fail-closed guard ({' or '.join(rep['flags'])})")
        print("\n" + rep["scope_note"])

    return 0 if rep["n_armed"] == rep["n_jobs_declared"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
