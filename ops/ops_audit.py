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

#: (name, relative path, argv tail). Read-only detectors only — see module docstring.
MEMBERS: tuple[tuple[str, str, list[str]], ...] = (
    ("silent-refusal", "renquant104/rq104_silent_refusal_sentinel.py", []),
    ("blind-notifiers", "blind_notifier_scan.py", []),
    ("undelivered-alerts", "undelivered_alert_scan.py", []),
    ("import-resolution", "import_resolution_check.py", []),
    ("umbrella-script-shadow", "umbrella_script_shadow_check.py", []),
    ("launchd-liveness", "launchd_liveness_scan.py", []),
)

#: A member may not run forever inside a scheduled job.
PER_MEMBER_TIMEOUT_S = 300

STATUS_OK, STATUS_FINDINGS, STATUS_CRASH, STATUS_TIMEOUT, STATUS_MISSING = (
    "ok", "findings", "crash", "timeout", "missing")

#: Aggregate exit codes. `findings` is 1 so the job's nonzero exit means "a detector
#: found something"; a harness problem gets its own code so it is never read as a
#: finding — the crash-vs-alarm confusion #622 was opened for.
EXIT_OK, EXIT_FINDINGS, EXIT_HARNESS = 0, 1, 3


def run_member(name: str, rel: str, tail: list[str], ops: Path) -> dict:
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
    # A traceback on stderr means the tool DIED; a nonzero code without one means it
    # reached a verdict. Collapsing the two is the defect #622 exists for.
    crashed = any("Traceback (most recent call last)" in l for l in err)
    status = (STATUS_CRASH if crashed else
              STATUS_OK if p.returncode == 0 else STATUS_FINDINGS)
    return {"member": name, "status": status, "exit_code": p.returncode,
            "elapsed_s": round(time.monotonic() - t0, 1),
            "detail": (err[-1] if crashed and err else
                       (out[0] if out else (err[0] if err else "")))[:200]}


def audit(ops: Path = OPS, members=MEMBERS) -> dict:
    results = [run_member(n, r, t, ops) for n, r, t in members]
    counts = {s: sum(1 for r in results if r["status"] == s)
              for s in (STATUS_OK, STATUS_FINDINGS, STATUS_CRASH,
                        STATUS_TIMEOUT, STATUS_MISSING)}
    # WORST severity wins: a harness problem outranks a finding, because a detector
    # that could not run is not a detector that found nothing.
    if counts[STATUS_CRASH] or counts[STATUS_TIMEOUT] or counts[STATUS_MISSING]:
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
              f"findings={c['findings']} crash={c['crash']} "
              f"timeout={c['timeout']} missing={c['missing']}")
        for r in res["results"]:
            print(f"  [{r['status']:8}] {r['member']:24} exit={r['exit_code']} "
                  f"{r['detail'][:96]}")
    return res["aggregate_exit"]


if __name__ == "__main__":
    raise SystemExit(main())
