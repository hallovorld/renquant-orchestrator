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
import datetime as dt
import json
import subprocess
import sys
import time
from pathlib import Path

OPS = Path(__file__).resolve().parent
PY = sys.executable

sys.path.insert(0, str(OPS))
from audit_finding_disposition import ACKED, classify  # noqa: E402

#: Committed ack ledger. Absent by default, and that is the intended starting state:
#: with no ledger every finding is NEW and this aggregator behaves exactly as it did
#: before dispositioning existed. Acking is a human decision and a reviewed diff — this
#: file only ever READS the ledger.
ACK_LEDGER = OPS / "ops_audit_acks.json"

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
#: The contract is a DEFAULT INVERSION, not an allow-list of bad codes. We do not
#: enumerate the unusable codes and hope we got them all — an enumerated deny-list
#: always leaves a fail-open `else`, which is exactly how this bug arrived. Only the
#: codes that mean "verdict reached" are listed; **every other nonzero is HARNESS by
#: default**, including codes no member uses today and codes added by a future edit.
#:
#: Codes READ from each member's source at b44f735c on 2026-07-30 — cited, not
#: asserted, because "measured" with no citation is how the last one got in.
#: `test_declared_contract_matches_each_member_source` re-derives this table from the
#: member ASTs, so the citations below are checked rather than trusted.
#:
#:   silent-refusal   rq104_silent_refusal_sentinel.py:236 `return 1 if findings else 0`
#:                    — only 0/1; no unusable code of its own.
#:   blind-notifiers  blind_notifier_scan.py:95
#:                    `EXIT_OK, EXIT_FINDINGS, EXIT_UNUSABLE = 0, 1, 2`
#:                    findings returned :219; EXIT_UNUSABLE returned :205 (the exit
#:                    codex named — source directory absent).
#:   undelivered-alerts undelivered_alert_scan.py:159 `return 1`; clean 0 at :154.
#:   import-resolution  import_resolution_check.py:203 `return 1`; 2 = FATAL at
#:                    :191 (pin file missing) and :197 (pin file unreadable).
#:   umbrella-script-shadow umbrella_script_shadow_check.py:258 `return 1`; 2 =
#:                    UNVERIFIABLE at :237, :242, :247, :256 — the state #634 added
#:                    so "could not check" could not read as "checked, found nothing".
#:   launchd-liveness launchd_liveness_scan.py:354 `return 1 if bad else 0`; 2 at
#:                    :339 (manifest unreadable) and :342 (manifest lists no jobs).
#:
#: Result: all six signal findings with 1; four also use 2 for unusable. argparse
#: also exits 2 with no traceback, so a typo in any `tail` lands on HARNESS too.
#: Read-only detectors only — see module docstring.
MEMBERS: tuple[tuple[str, str, list[str], tuple[int, ...]], ...] = (
    ("silent-refusal", "renquant104/rq104_silent_refusal_sentinel.py", [], (1,)),
    # GOAL-1 layer 1 (#723: merged with no caller — the exact merged-but-inert class
    # this aggregator exists to end). Argless: lanes and watched set resolve from the
    # pinned config, bases from the deployment's own split. Exit 3 (skipped
    # preconditions) lands UNUSABLE = harness, which is correct: a precondition that
    # could not be checked is not a checked-and-passed one.
    ("shadow-lane-preflight", "renquant104/shadow_lane_preflight.py", [], (1,)),
    ("blind-notifiers", "blind_notifier_scan.py", [], (1,)),
    ("undelivered-alerts", "undelivered_alert_scan.py", [], (1,)),
    ("import-resolution", "import_resolution_check.py", [], (1,)),
    ("umbrella-script-shadow", "umbrella_script_shadow_check.py", [], (1,)),
    ("launchd-liveness", "launchd_liveness_scan.py", [], (1,)),
    # ack-ledger, added 2026-08-01. MEASURED BEFORE ADDING, and it is the same finding
    # the five entries below were added for: `ack_ledger_audit.py` was merged, works, and
    # reports 11 findings against the live ledger today -- while being invoked by NOTHING
    # except its own test file. The 07-31 dark-detector sweep missed it.
    #
    # Why it matters that it runs unconditionally: `ack_expiry` IS consulted elsewhere,
    # but only from `rq104_degradation_sentinel.expired_or_unacked()`, which reaches it
    # only for jobs whose LAST EXIT IS NONZERO, inside a sentinel that SKIPS non-session
    # days. So an expired ack on a currently-passing job is never examined, and on a
    # weekend the ledger is not read at all. Measured 2026-08-01: 9 of 10 acks expired,
    # the oldest by 12 days. An expiry nobody reads is not a reminder.
    #
    # Exit contract read from source: `EXIT_OK, EXIT_FINDINGS, EXIT_HARNESS = 0, 1, 3`
    # at ack_ledger_audit.py:68; findings returned :283; 3 returned :260 on an
    # unexpected exception. 3 is not declared a finding exit, so it lands on HARNESS by
    # the default rule -- which is the intent.
    #
    # WRITE-CALL SWEEP, and what it forced. The membership rule is read-only detectors
    # only, enforced mechanically by `test_no_member_writes` -- which REJECTED this
    # member on the first attempt. It had one write, `open(a.json_out, "w")`, reachable
    # only via a `--json-out` flag that had NO CALLER anywhere in the repo. Documenting
    # it as an exception would have weakened a guard that was doing its job, so the flag
    # was deleted instead: `--json` prints the same payload to stdout. That is what made
    # this tool schedulable. Its `subprocess` calls are `git rev-parse` / `git log` /
    # `git show` -- read-only, against this repository.
    ("ack-ledger", "renquant104/ack_ledger_audit.py", [], (1,)),
    # Added 2026-08-01. Measured before adding: five detectors merged on 2026-07-31 were
    # invoked by NOTHING -- `git grep` over ops/*.sh, ops/*.json, scripts/, Makefile and
    # the installed plists returned zero callers for each. Merged and dark is the
    # "inert scaffolding" failure this repo already has a rule against, committed five
    # times in one night by the same author.
    #
    # Write-call sweep before inclusion, per the membership rule above: 0 matches for
    # `open(...,'w'/'a')`, `write_text`, `json.dump(`, `mkdir`, `shutil.`, `os.remove`,
    # `os.rename` in each `[VERIFIED — sweep over origin/main, 2026-08-01]`.
    #
    # Finding contracts, cited to the line as the six above are:
    #   gate-stamp-parity    gate_stamp_parity.py:287 `return 1 if problems else 0`.
    #                        No 2: an empty scan is turned into a PROBLEM at :129 rather
    #                        than a usage error, so "no subjects" still exits 1.
    #   booster-identity     booster_identity_census.py:333 `return 0 if
    #                        (census_complete and no collapse) else 1`; 2 at :294 (root
    #                        unreadable) and :299 (no artifact matched) — an empty
    #                        census must not read as one-identity-per-model.
    #   bundle-producer-keys bundle_producer_key_audit.py:261 `return 1 if (unread or
    #                        unreadable or unvalidated) else 0`; 2 at :252 (audit could
    #                        not run at all).
    #
    # So two of the three also use 2 for unusable, matching the pattern above: argparse
    # exits 2 as well, which means a typo in any `tail` lands on HARNESS, not on
    # "found nothing".
    ("gate-stamp-parity", "renquant104/gate_stamp_parity.py",
     ["--query", "panel-ltr.alpha158_fund*.json"], (1,)),
    ("booster-identity", "renquant104/booster_identity_census.py",
     ["--query", "panel-ltr.alpha158_fund*.json"], (1,)),
    ("bundle-producer-keys", "bundle_producer_key_audit.py", [], (1,)),
)

#: Detectors that CANNOT join yet, and why — recorded rather than silently omitted, so
#: "the audit covers the detectors" is not read off a list that quietly excludes two.
#:
#:   wf_corpus_coverage.py            requires `--artifacts <path...>`: a per-artifact
#:                                    census with no defensible repo-wide default. It is
#:                                    invoked against a named artifact, not swept.
#:   strategy_config_primary_parity.py requires `--config <path> --config <path>`: the
#:                                    two surfaces are machine paths (one pinned subrepo,
#:                                    one umbrella tree). Baking either into this
#:                                    reviewed tuple is the "tests that measure the
#:                                    operator's disk" failure.
#:
#: Both need a resolved default in the tool itself first — the same fix applied to
#: gate_stamp_parity and booster_identity_census in this change.
UNSCHEDULABLE_YET = (
    "renquant104/wf_corpus_coverage.py",
    "strategy_config_primary_parity.py",
)

#: A member may not run forever inside a scheduled job.
PER_MEMBER_TIMEOUT_S = 300

STATUS_OK, STATUS_FINDINGS, STATUS_CRASH, STATUS_TIMEOUT, STATUS_MISSING = (
    "ok", "findings", "crash", "timeout", "missing")
#: A nonzero exit that is NOT in the member's finding contract. The detector ran but
#: reached no verdict — an absent input, a bad argument, an unreadable pin. Distinct
#: from `crash` because nothing died, and emphatically distinct from `findings`.
STATUS_UNUSABLE = "unusable"

#: A finding whose fingerprint is acked, unexpired, and whose numbers have not moved.
#: Still printed, with its reason — nothing is suppressed silently. It is the ONLY
#: status dispositioning can produce, and it can only ever come from STATUS_FINDINGS.
#:
#: DISPOSITION NEVER TOUCHES THE HARNESS STATUSES. A crash, timeout, missing member or
#: unusable exit is not a finding and cannot be acked: those say the detector did not
#: reach a verdict, and an ack that could quiet them would let a BROKEN detector read as
#: an acknowledged one — the exact crash-vs-alarm confusion this aggregator exists to
#: prevent, re-introduced through the quieting layer. `_disposition` is applied inside
#: the `status == STATUS_FINDINGS` branch only, and a test pins that.
STATUS_INFO = "info"

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
    #
    # NOTE THE DIRECTION OF THE `else`. It is STATUS_UNUSABLE, not STATUS_FINDINGS.
    # The fix is not "enumerate the known-bad codes"; that is the same fail-open with
    # a longer list, and it re-breaks the day a member invents a code nobody added.
    # An unrecognised code is HARNESS by default and must stay that way: the failure
    # mode we are buying off is a BROKEN detector reading as a HEALTHY one, and that
    # trade only holds if the unknown case falls on the harness side.
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


def load_ledger(path: Path = ACK_LEDGER) -> dict:
    """The ack ledger, or `{}`.

    A malformed ledger returns `{}` rather than raising: the failure mode to avoid is a
    bad ack file taking the whole audit down. It cannot hide anything, because an empty
    ledger acks nothing — every finding stays loud.
    """
    try:
        led = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return led if isinstance(led, dict) else {}


def audit(ops: Path = OPS, members=MEMBERS, ledger_path: Path = ACK_LEDGER,
          today: dt.date | None = None) -> dict:
    results = [run_member(n, r, t, f, ops) for n, r, t, f in members]

    # ---- disposition, at the per-finding counting boundary ----
    # Only STATUS_FINDINGS rows are eligible; see STATUS_INFO on why the harness
    # statuses are untouchable. An acked-and-unchanged finding becomes INFO and stops
    # counting as an alarm; NEW / ACKED_BUT_CHANGED / ACK_EXPIRED all stay findings.
    ledger = load_ledger(ledger_path)
    day = today or dt.date.today()
    for r in results:
        if r["status"] != STATUS_FINDINGS:
            continue
        d = classify(r["member"], r.get("detail", ""), ledger, day)
        r["disposition"] = d["state"]
        r["fingerprint"] = d["fingerprint"]
        if d.get("reason"):
            r["ack_reason"] = d["reason"]
        if d["state"] == ACKED:
            r["status"] = STATUS_INFO

    counts = {s: sum(1 for r in results if r["status"] == s)
              for s in (STATUS_OK, STATUS_FINDINGS, STATUS_INFO, STATUS_CRASH,
                        STATUS_TIMEOUT, STATUS_MISSING, STATUS_UNUSABLE)}
    # WORST severity wins: a harness problem outranks a finding, because a detector
    # that could not run is not a detector that found nothing. `unusable` sits on the
    # harness side for exactly that reason.
    if (counts[STATUS_CRASH] or counts[STATUS_TIMEOUT] or counts[STATUS_MISSING]
            or counts[STATUS_UNUSABLE]):
        aggregate = EXIT_HARNESS
    elif counts[STATUS_FINDINGS]:
        # INFO is deliberately absent here: an acked, unexpired, unchanged finding is
        # what "quiet" MEANS, and a job that still exits nonzero on it has not become
        # signalling. EXPIRED and CHANGED never reach INFO, so they still exit 1.
        aggregate = EXIT_FINDINGS
    else:
        aggregate = EXIT_OK
    return {"members": len(results), "counts": counts,
            "aggregate_exit": aggregate, "results": results,
            "ledger": str(ledger_path), "n_acks_in_ledger": len(ledger),
            "as_of": day.isoformat()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--ledger", type=Path, default=ACK_LEDGER)
    ap.add_argument("--as-of", default=None,
                    help="classify acks as of this date (default: today)")
    a = ap.parse_args(argv)
    try:
        day = dt.date.fromisoformat(a.as_of) if a.as_of else None
    except ValueError:
        print(f"ops-audit: --as-of is not a date: {a.as_of!r}", file=sys.stderr)
        return EXIT_HARNESS
    res = audit(ledger_path=a.ledger, today=day)
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        c = res["counts"]
        print(f"ops-audit: {res['members']} detector(s) — ok={c['ok']} "
              f"findings={c['findings']} info={c['info']} unusable={c['unusable']} "
              f"crash={c['crash']} timeout={c['timeout']} missing={c['missing']}")
        for r in res["results"]:
            disp = f" {r['disposition']}" if r.get("disposition") else ""
            print(f"  [{r['status']:8}] {r['member']:24} exit={r['exit_code']}{disp} "
                  f"{r['detail'][:96]}")
            if r.get("ack_reason"):
                print(f"      acked because: {str(r['ack_reason'])[:96]}")
        print(f"  ledger {res['ledger']} ({res['n_acks_in_ledger']} ack(s)), "
              f"as of {res['as_of']}. An INFO finding is still printed — nothing is "
              f"suppressed silently, and the ledger is never written here.")
    return res["aggregate_exit"]


if __name__ == "__main__":
    raise SystemExit(main())
