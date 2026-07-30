#!/usr/bin/env python3
"""Run the read-only ops detectors together, once, and report (GOAL-5, issue #649).

**The problem this closes.** Measured 2026-07-30: `ops/` carries **24**
independently runnable tools and **7** are referenced by a launchd job. The 17
unscheduled ones include every detector merged that day — and
`rq104_silent_refusal_sentinel.py`, GOAL-5's **AC5**, which had **never run**: absent
from the manifest, absent from `launchctl list`, and with no log file matching
`*refusal*` anywhere under `logs/`. The goal ledger read "AC5 = #619 merged", which
was true about the merge and silent about the deployment.

**Why one job and not nine.** Nine launchd entries are nine machine landings and
nine plists to keep in step with the manifest, on a fleet where a single plist
already drifted undetected (#639). One aggregator means one entry, one plist, one
authorisation — and a detector added later joins by being listed HERE, which is a
reviewed code change rather than a machine landing.

**Membership rule.** A member must be **read-only** and **self-terminating**. Each
was checked for write calls before inclusion (`open(...,'w'/'a')`, `write_text`,
`json.dump`, `mkdir`, `shutil`, `os.remove`): all zero
`[VERIFIED — sweep over origin/main, 2026-07-30]`. A tool that mutates state does
not belong here however useful its output.

**Exit codes are aggregated, never collapsed.** Each member's own code is preserved
in the report. The aggregate is the WORST severity seen, so one silent member cannot
mask a loud one — and a member that CRASHES is reported distinctly from one that
found something, because those send a reader to different places (the #622 lesson).

    python ops/ops_audit.py           # human
    python ops/ops_audit.py --json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

OPS = Path(__file__).resolve().parent
PY = sys.executable

#: (name, relative path, argv tail, ALLOWED FINDING EXIT CODES).
#:
#: The fourth field is the member's **finding-exit contract** and it is the whole
#: point. Without it the aggregator read "any nonzero without a traceback" as a
#: finding, which is false for every detector here: each one already distinguishes
#: "I checked and found something" from "I could not check", and the second is a
#: HARNESS problem. Codex on #650 named `blind_notifier_scan`'s exit 2 (source
#: directory absent); the same is true of `umbrella_script_shadow_check`, whose
#: exit 2 means UNVERIFIABLE — it would have been reported as a healthy detector
#: finding something while it had nothing to look at. argparse also exits 2 without
#: a traceback, so a typo in `tail` would have read as a finding too.
#:
#: Codes MEASURED from each member's `main()` on 2026-07-30, not assumed:
#: all six use 1 = findings, and four of them use 2 = unusable/unverifiable.
#: Read-only detectors only — see module docstring.
MEMBERS: tuple[tuple[str, str, list[str], tuple[int, ...]], ...] = (
    ("silent-refusal", "renquant104/rq104_silent_refusal_sentinel.py", [], (1,)),
    ("blind-notifiers", "blind_notifier_scan.py", [], (1,)),
    ("undelivered-alerts", "undelivered_alert_scan.py", [], (1,)),
    ("import-resolution", "import_resolution_check.py", [], (1,)),
    ("umbrella-script-shadow", "umbrella_script_shadow_check.py", [], (1,)),
    ("launchd-liveness", "launchd_liveness_scan.py", [], (1,)),
)

#: A member may not run forever inside a scheduled job.
PER_MEMBER_TIMEOUT_S = 300

STATUS_OK, STATUS_FINDINGS, STATUS_CRASH, STATUS_TIMEOUT, STATUS_MISSING = (
    "ok", "findings", "crash", "timeout", "missing")
#: A nonzero exit that is NOT in the member's finding contract. The detector ran but
#: reached no verdict — an absent input, a bad argument, an unreadable pin. Distinct
#: from `crash` because nothing died, and emphatically distinct from `findings`.
STATUS_UNUSABLE = "unusable"

#: Aggregate exit codes. `findings` is 1 so the job's nonzero exit means "a detector
#: found something"; a harness problem gets its own code so it is never read as a
#: finding — the crash-vs-alarm confusion #622 was opened for.
EXIT_OK, EXIT_FINDINGS, EXIT_HARNESS = 0, 1, 3


def run_member(name: str, rel: str, tail: list[str],
               finding_exits: tuple[int, ...], ops: Path) -> dict:
    path = ops / rel
    if not path.exists():
        return {"member": name, "status": STATUS_MISSING, "exit_code": None,
                "detail": f"{rel} not present in this checkout"}
    t0 = time.monotonic()
    try:
        p = subprocess.run([PY, str(path), *tail], capture_output=True, text=True,
                           timeout=PER_MEMBER_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"member": name, "status": STATUS_TIMEOUT, "exit_code": None,
                "elapsed_s": round(time.monotonic() - t0, 1),
                "detail": f"exceeded {PER_MEMBER_TIMEOUT_S}s"}
    except Exception as exc:  # noqa: BLE001
        return {"member": name, "status": STATUS_CRASH, "exit_code": None,
                "detail": f"{type(exc).__name__}: {exc}"}
    out = (p.stdout or "").strip().splitlines()
    err = (p.stderr or "").strip().splitlines()
    # A traceback on stderr means the tool DIED. Absent one, a nonzero code means a
    # verdict ONLY if it is in this member's declared finding contract; every other
    # nonzero is a detector that ran without reaching a verdict.
    #
    # The previous version had `else STATUS_FINDINGS`, so exit 2 = "could not check"
    # was reported as "checked and found something" — the crash-vs-alarm confusion
    # #622 exists for, reproduced one layer up in the aggregator built to prevent it.
    crashed = any("Traceback (most recent call last)" in l for l in err)
    if crashed:
        status = STATUS_CRASH
    elif p.returncode == 0:
        status = STATUS_OK
    elif p.returncode in finding_exits:
        status = STATUS_FINDINGS
    else:
        status = STATUS_UNUSABLE
    return {"member": name, "status": status, "exit_code": p.returncode,
            "elapsed_s": round(time.monotonic() - t0, 1),
            "detail": (err[-1] if crashed and err else
                       (out[0] if out else (err[0] if err else "")))[:200]}


def audit(ops: Path = OPS, members=MEMBERS) -> dict:
    results = [run_member(n, r, t, f, ops) for n, r, t, f in members]
    counts = {s: sum(1 for r in results if r["status"] == s)
              for s in (STATUS_OK, STATUS_FINDINGS, STATUS_CRASH,
                        STATUS_TIMEOUT, STATUS_MISSING, STATUS_UNUSABLE)}
    # WORST severity wins: a harness problem outranks a finding, because a detector
    # that could not run is not a detector that found nothing. `unusable` sits on the
    # harness side for exactly that reason.
    if (counts[STATUS_CRASH] or counts[STATUS_TIMEOUT] or counts[STATUS_MISSING]
            or counts[STATUS_UNUSABLE]):
        aggregate = EXIT_HARNESS
    elif counts[STATUS_FINDINGS]:
        aggregate = EXIT_FINDINGS
    else:
        aggregate = EXIT_OK
    return {"members": len(results), "counts": counts,
            "aggregate_exit": aggregate, "results": results}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    res = audit()
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        c = res["counts"]
        print(f"ops-audit: {res['members']} detector(s) — ok={c['ok']} "
              f"findings={c['findings']} unusable={c['unusable']} "
              f"crash={c['crash']} timeout={c['timeout']} missing={c['missing']}")
        for r in res["results"]:
            print(f"  [{r['status']:8}] {r['member']:24} exit={r['exit_code']} "
                  f"{r['detail'][:96]}")
    return res["aggregate_exit"]


if __name__ == "__main__":
    raise SystemExit(main())
