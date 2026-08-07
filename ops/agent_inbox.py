#!/usr/bin/env python3
"""Agent inbox — one read-only answer to "what is broken right now".

Why this exists
---------------
Operator directive 2026-08-06: *"出现的问题应该直接推送给你这个 agent 这样你可以
直接开始修"* — problems should reach the agent directly so it can start fixing.

Today the path is: job → ntfy → the operator's phone → the operator relays it in
chat. Every fault therefore costs a human round-trip, and anything the operator
does not happen to read is simply never worked. Measured while writing this:
``alert_incidents`` held **three unacked CRITICAL score-drift rows from
2026-08-06** (``psi~5.9``, ``psi~5.1``, ``psi~5.3``) that had reached neither
party.

The alert SOURCES already exist and are good. What was missing is a single
agent-facing view. This aggregates them; it invents no new signal.

Three sources
-------------
1. ``alert_incidents`` (runs DB) — the incident ledger, already deduplicated by
   ``cause_hash`` with ``first_seen`` / ``last_seen`` / ``acked``.
2. ``ops/ops_audit.py --json`` — the detector aggregator's findings.
3. ``launchctl list`` last-exit codes — with the designed/unknown split below.

The launchd split is the point
------------------------------
A daily alert lists ~14 jobs "with nonzero last exit" and reads as fourteen
failures. Measured 2026-08-06, most are jobs REPORTING, not failing:

    rq105-shadow-serving          4  EXIT_NOT_WIRED   — designed "not wired yet"
    rq104-shadow-scorer-sentinel  8  EXIT_ALARM       — designed "I am alarming"
    run-surface-drift             1  drift found      — designed "I found something"
    rq104-model-freshness         3  genuine BREACH   — designed "it is stale"
    rq104-risk-budget          1, 2  CRITICAL / WARN  — designed "over budget"
    weekly-wf-promote             1  no train         — designed "nothing to promote"
    ops-audit                     1  findings present — designed "I found something"

Conflating "I have something to report" with "I crashed" is the same defect
class as a rotation counter reading ``considered=0`` on a run that considered
one: the number a monitor reads says nothing happened, on exactly the occasions
something did. So this module reports DESIGNED codes as informational and
surfaces UNKNOWN codes as the work.

``DESIGNED_EXIT_CODES`` is a claim about other files. It is kept honest by
``tests/test_agent_inbox.py``, which re-greps each cited source and fails when a
wrapper's contract moves — the map is asserted here and MEASURED there.

``weekly-wf-promote`` stays OUT of ``DESIGNED_EXIT_CODES`` even though the table
above lists it: its wrapper (``scripts/weekly_wf_promote.sh``) lives in the
sibling umbrella repo, which this repo's CI does not check out (`.github/workflows/ci.yml`
checks out only the ``renquant-*`` subrepos) — a claim this module cannot MEASURE
here would be exactly the un-probed, silently-rotting assertion the map exists to
prevent. It therefore still surfaces as UNKNOWN until cross-repo source
verification exists; that is accurate, not a gap in this pass.

Read-only: never acks, never writes, never mutates a job.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parent.parent
RQ = Path(os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant"))
RUNS_DB = RQ / "data" / "runs.alpaca.db"

#: job suffix → {exit code: (label, source file, the token proving it, whether
#: the exit is itself a genuine problem someone must act on).
#: Every entry is a claim about a file in another repo; the test re-greps the
#: source for `probe` and fails if it is gone. An unlisted code is UNKNOWN by
#: construction — the default is "this needs a human", never "probably fine".
#: `actionable=False` means the exit is purely a status report (e.g. "not
#: wired yet"); `actionable=True` means the documented meaning IS the
#: problem (a breach, an alarm, a budget over limit) — "designed" tells you
#: the code's meaning is known, not that nothing is wrong.
DESIGNED_EXIT_CODES: dict[str, dict[int, tuple[str, str, str, bool]]] = {
    "rq105-shadow-serving": {
        4: ("not wired yet (no feature-snapshot producer)",
            "ops/renquant105/run_shadow_serving.sh", "EXIT_NOT_WIRED=4", False),
    },
    "rq104-shadow-scorer-sentinel": {
        8: ("alarming — a watched shadow lane is degraded",
            "ops/renquant104/rq104_shadow_scorer_sentinel.py", "EXIT_ALARM = 8",
            True),
    },
    "ops-audit": {
        # Informational here: the live findings from this same job already
        # surface through `read_audit_findings()`; this launchd code is a
        # stale echo of that (see the module docstring's own warning that a
        # launchd exit code "may be hours old").
        1: ("findings present", "ops/ops_audit.py", "findings", False),
    },
    "run-surface-drift": {
        1: ("run-surface drift found", "ops/run_surface_drift_check.py",
            "exit 1", True),
    },
    "rq104-model-freshness": {
        3: ("genuine BREACH (or UNKNOWN artifact) — model artifact is stale",
            "ops/renquant104/run_model_freshness_monitor.sh",
            "3 breach (>28d) or UNKNOWN", True),
    },
    "rq104-risk-budget": {
        1: ("CRITICAL — a budget is at or over 100%",
            "ops/renquant104/run_risk_budget_statement.sh",
            "1 CRITICAL (>=100%)", True),
        2: ("WARN — a budget is over 80%",
            "ops/renquant104/run_risk_budget_statement.sh",
            "2 WARN (>80% of any budget)", True),
    },
    # The three below were in the UNKNOWN bucket until 2026-08-07. They were
    # never undocumented — my earlier greps looked for `EXIT_X = N` literals and
    # bare `exit N`, and missed both a NAMED constant defined in another module
    # and a `return 1 if findings else 0` expression. "I could not find the
    # contract" is not "there is no contract", and the difference is one more
    # read.
    "rq104-silent-refusal": {
        1: ("findings — a scheduled job has stopped acting",
            "ops/renquant104/rq104_silent_refusal_sentinel.py",
            "return 1 if findings else 0", True),
    },
    "rq104-degradation-sentinel": {
        # EXIT_ALARMS is defined in sentinel_receipt.py, imported here — which is
        # why grepping the sentinel itself for `= 1` found only EXIT_INTERNAL=3
        # and made the live exit 1 look like a contract mismatch. It is not.
        1: ("EXIT_ALARMS — the sentinel raised alarms",
            "ops/renquant104/sentinel_receipt.py", "EXIT_ALARMS = 1", True),
        3: ("EXIT_INTERNAL — the sentinel itself crashed",
            "ops/renquant104/rq104_degradation_sentinel.py",
            "EXIT_INTERNAL = 3", True),
    },
    "rq105-liveness": {
        1: ("collector issue(s) — the 'rq105 DOWN' alert fired",
            "ops/renquant105/rq105_liveness_check.py", "rq105 DOWN", True),
    },
}

#: Incident states worth acting on. `acked` rows are excluded regardless — the
#: ack ledger is the operator's and this module never second-guesses it.
ACTIONABLE_STATES = ("CRITICAL", "WARN", "BREACH", "FAULT", "ALARM")


def _job_suffix(label: str) -> str:
    return label.split("com.renquant.", 1)[-1]


def read_launchd_exits() -> list[dict[str, Any]]:
    """`launchctl list` → the renquant jobs whose LAST exit was nonzero.

    `launchctl` reports the last exit until the next run, so a code here may be
    hours old; that is a property of the source, recorded rather than smoothed.
    """
    try:
        out = subprocess.run(["launchctl", "list"], capture_output=True,
                             text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        return [{"job": "(launchctl unavailable)", "code": None,
                 "kind": "unknown", "detail": str(exc)}]
    rows: list[dict[str, Any]] = []
    for line in out.splitlines():
        parts = line.split()
        if len(parts) < 3 or not parts[2].startswith("com.renquant."):
            continue
        try:
            code = int(parts[1])
        except ValueError:
            continue
        if code == 0:
            continue
        suffix = _job_suffix(parts[2])
        known = DESIGNED_EXIT_CODES.get(suffix, {}).get(code)
        row = {
            "job": suffix,
            "code": code,
            "kind": "designed" if known else "unknown",
            "detail": known[0] if known else "no documented meaning for this code",
        }
        if known:
            row["actionable"] = known[3]
        rows.append(row)
    return rows


def read_incidents(db: Path = RUNS_DB) -> list[dict[str, Any]]:
    """Unacked, actionable rows from the incident ledger, newest last_seen first.

    ``state`` is persisted independently of ``acked`` — a row can be
    ``RESOLVED`` and still carry ``acked = 0`` forever if nobody ever acked
    it (RenQuant `backtesting/renquant_104/kernel/persistence.py`, the
    ``alert_incidents`` table comment: ``state TEXT -- WARN | CRITICAL |
    RESOLVED``). Filtering on ``acked`` alone would render a resolved
    incident as active work indefinitely, so this also requires ``state`` to
    be one of ``ACTIONABLE_STATES``.
    """
    if not db.exists():
        return []
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        placeholders = ",".join("?" * len(ACTIONABLE_STATES))
        cur = con.execute(
            "SELECT audit, scope, cause_hash, first_seen, last_seen, state, "
            f"acked FROM alert_incidents WHERE acked = 0 AND state IN "
            f"({placeholders}) ORDER BY last_seen DESC",
            ACTIONABLE_STATES,
        )
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
        con.close()
    except sqlite3.Error as exc:
        return [{"audit": "(incident ledger unreadable)", "scope": "",
                 "cause_hash": str(exc), "state": "UNKNOWN"}]
    return rows


def read_audit_findings() -> list[dict[str, Any]]:
    """`ops_audit.py --json` findings. Never raises: the inbox must still
    render its other two sources when one is broken."""
    script = REPO / "ops" / "ops_audit.py"
    if not script.exists():
        return []
    try:
        res = subprocess.run([sys.executable, str(script), "--json"],
                             capture_output=True, text=True, timeout=600)
        payload = json.loads(res.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        return [{"name": "(ops-audit unreadable)", "status": "unknown",
                 "summary": str(exc)[:200]}]
    # Schema MEASURED, not guessed (2026-08-06): the payload is
    # {members:int, counts:dict, aggregate_exit:int, results:[...], ...} and
    # each result carries member/status/exit_code/detail/disposition. A first
    # cut read `members` as the list and crashed on an int — the same
    # invented-key error this whole module exists to surface.
    results = payload.get("results")
    if not isinstance(results, list):
        return [{"name": "(ops-audit schema changed)", "status": "unknown",
                 "summary": f"no 'results' list; top-level keys = {sorted(payload)}"}]
    out = []
    for m in results:
        if not isinstance(m, dict):
            continue
        status = str(m.get("status") or "").lower()
        # `ok` is clean. `info` is a finding the ack ledger has DISPOSITIONED —
        # already someone's decision, not new work. Everything else is work.
        if status in ("ok", "info"):
            continue
        out.append({
            "name": m.get("member") or "?",
            "status": status or "finding",
            "exit_code": m.get("exit_code"),
            "summary": str(m.get("detail") or "")[:220],
        })
    return out


def collect() -> dict[str, Any]:
    launchd = read_launchd_exits()
    designed = [r for r in launchd if r["kind"] == "designed"]
    return {
        "incidents": read_incidents(),
        "audit_findings": read_audit_findings(),
        "launchd_unknown": [r for r in launchd if r["kind"] == "unknown"],
        # "designed" only means the exit code's meaning is documented — it
        # does not mean nothing is wrong. Split on the per-entry `actionable`
        # flag: a genuine BREACH/CRITICAL/ALARM still needs a human even
        # though the exit code itself is not a mystery.
        "launchd_designed": [r for r in designed if not r["actionable"]],
        "launchd_designed_actionable": [r for r in designed if r["actionable"]],
    }


def render(box: dict[str, Any]) -> str:
    L: list[str] = []
    inc, aud = box["incidents"], box["audit_findings"]
    unk, des = box["launchd_unknown"], box["launchd_designed"]
    act = box.get("launchd_designed_actionable", [])

    L.append(f"AGENT INBOX — {len(inc)} unacked incident(s), "
             f"{len(aud)} audit finding(s), {len(unk)} unexplained job exit(s), "
             f"{len(act)} designed-but-actionable job exit(s)")
    L.append("")

    L.append(f"== UNACKED INCIDENTS ({len(inc)}) ==")
    if not inc:
        L.append("  none")
    for r in inc:
        L.append(f"  [{r.get('state','?'):<8}] {r.get('audit','?')}/{r.get('scope','')} "
                 f"— {r.get('cause_hash','')}  first={r.get('first_seen','?')} "
                 f"last={r.get('last_seen','?')}")
    L.append("")

    L.append(f"== OPS-AUDIT FINDINGS ({len(aud)}) ==")
    if not aud:
        L.append("  none")
    for r in aud:
        L.append(f"  [{r['status']:<8}] {r['name']}: {r['summary']}")
    L.append("")

    L.append(f"== JOB EXITS NEEDING EXPLANATION ({len(unk)}) ==")
    if not unk:
        L.append("  none")
    for r in unk:
        L.append(f"  {r['job']} (exit {r['code']}) — {r['detail']}")
    L.append("")

    L.append(f"== JOB EXITS THAT ARE DESIGNED BUT ACTIONABLE ({len(act)}) ==")
    if not act:
        L.append("  none")
    for r in act:
        L.append(f"  {r['job']} (exit {r['code']}) — {r['detail']}")
    L.append("")

    L.append(f"== JOB EXITS THAT ARE BY DESIGN ({len(des)}) — not work ==")
    for r in des:
        L.append(f"  {r['job']} (exit {r['code']}) — {r['detail']}")
    if not des:
        L.append("  none")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="machine-readable")
    args = ap.parse_args(argv)
    box = collect()
    print(json.dumps(box, indent=2, default=str) if args.json else render(box))
    # Exit 1 when there IS work, so a wrapper can page on it. Purely
    # informational designed exits (e.g. "not wired yet") deliberately do not
    # count — that conflation is what this module exists to end. But a
    # designed exit whose documented meaning IS a problem (BREACH, CRITICAL,
    # ALARM, drift found) must still page: "designed" means the code's
    # meaning is known, not that nothing is wrong.
    has_work = bool(box["incidents"] or box["audit_findings"]
                    or box["launchd_unknown"]
                    or box.get("launchd_designed_actionable"))
    return 1 if has_work else 0


if __name__ == "__main__":
    raise SystemExit(main())
