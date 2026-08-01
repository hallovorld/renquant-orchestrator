#!/usr/bin/env python3
"""Two freshness axes, one run, one cutoff — and only one of them gets the frontier.

MEASURED 2026-08-01 on the 2026-07-25 `weekly-retrain-patchtst` log. The promote step
printed these two lines **in the same refusal block, on the same date, for the same
cutoff**::

    source[fast] transformer_panel: cutoff=2026-04-28 raw-age=88d is fwd-label-clipped:
        achievable frontier=2026-07-21 (cutoff + 60 trading days, stamped lookahead_days);
        age-beyond-frontier=4d sla=28d OK
    source[fast] rawlabel:          cutoff=2026-04-28 age=88d sla=28d OFF-SLA

Same cutoff. Same raw age. One axis subtracts the forward-label frontier and clears its
SLA with 4 days to spare; the other does not and breaches it by 60. The refusal is the
chronic one — GOAL-5's silent-refusal sentinel reports this job as not having acted on 4
consecutive runs.

WHY THIS IS A DEFECT AND NOT A POLICY CHOICE. A label that looks 60 trading days FORWARD
cannot be observed until 60 trading days have passed, so its cutoff is **structurally**
that far behind. The `transformer_panel` line states the arithmetic itself: the frontier
is ``cutoff + 60 trading days``, from a **stamped** ``lookahead_days``. The rawlabel
sidecar's own recipe string is ``…/raw-fwd60d-excess-vs-SPY/bar-frontier-axis`` — the same
60-day forward label, and it even names a frontier axis. Judging that series by a
**28-day** SLA against its RAW cutoff asks it to be fresher than its own construction
permits.

THE SATISFIABILITY TEST, AND WHY IT IS NOT ASSUMED. This tool never assumes a trading-day
to calendar-day ratio. It reads the frontier the log itself derived and measures
``frontier - cutoff`` in days. If that floor exceeds the axis's own SLA, **no data refresh
can ever clear the gate** — the SLA is unsatisfiable by construction, and the gate is
refusing a condition it defines as unreachable.

WHAT IT REPORTS, AND WHAT IT REFUSES TO CONCLUDE. It reports (a) which axes carry a
frontier correction and which do not, (b) for every axis that has one, whether its own SLA
is satisfiable, and (c) axes that share a cutoff where one is corrected and one is not.
It does **not** assert that an uncorrected axis is *entitled* to the correction — that is
a claim about that axis's label, which this file cannot see. For the shared-cutoff case it
reports the sibling's floor as a **CONDITIONAL**: *if* the uncorrected axis has the same
lookahead, its floor is the same number. Naming the condition is the difference between a
finding and a guess.

Read-only. Parses log text, writes nothing, never invokes git, never mutates a job.

Exit codes: ``0`` no finding, ``1`` at least one finding, ``2`` usage/IO error, ``3``
SKIPPED — no log or no refusal block, so nothing was established. 3 exists because a
scheduled caller must be able to tell "checked and clean" from "could not check"; both
collapsing to 0 is how a detector reports health it never measured.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

#: Every ``source[...]`` line is an axis. Deliberately NOT an enumeration of known axis
#: names: an axis added tomorrow would sit outside the list and be silently unwatched,
#: which is the fail-open default this repo has now hit twice.
_AXIS = re.compile(r"source\[(?P<tier>[^\]]*)\]\s*(?P<name>[A-Za-z0-9_.\-]+)\s*:\s*"
                   r"(?P<body>.*)")
_CUTOFF = re.compile(r"cutoff=(?P<d>\d{4}-\d{2}-\d{2})")
_FRONTIER = re.compile(r"achievable frontier=(?P<d>\d{4}-\d{2}-\d{2})")
_SLA = re.compile(r"sla=(?P<n>\d+)d")
_RAW_AGE = re.compile(r"(?:raw-)?age=(?P<n>\d+)d")
_BEYOND = re.compile(r"age-beyond-frontier=(?P<n>\d+)d")

#: Verdict words the refusal block uses. `UNKNOWN` is a third outcome, not a synonym for
#: OK -- an axis whose verdict this parser does not recognise has NOT been shown to pass.
_OK, _BREACH, _UNKNOWN = "OK", "OFF-SLA", "UNKNOWN"

#: ANY of these means the axis did not pass. The first version searched for a bare `OK`
#: anywhere in the line and reported the 2026-07-03 `fundamentals` axis as **OK** -- a
#: line reading `daily feed as-of 2026-06-26 age=7d (max=20d OK); QUARTERLY UNVERIFIABLE
#: ... fail-closed until it exists`. The `OK` it matched belonged to a SUB-CLAUSE about a
#: different sub-check, and the axis was fail-closed. A detector that reads a fail-closed
#: axis as passing is the defect it was written to find.
_NOT_OK = ("OFF-SLA", "fail-closed", "UNVERIFIABLE", "STALE-COVERAGE", "BREACH")


def _date(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def parse_axis(line: str) -> dict | None:
    m = _AXIS.search(line)
    if not m:
        return None
    body = m.group("body")
    cut = _CUTOFF.search(body)
    fro = _FRONTIER.search(body)
    sla = _SLA.search(body)
    age = _RAW_AGE.search(body)
    beyond = _BEYOND.search(body)
    hits = [m for m in _NOT_OK if m in body]
    if hits:
        verdict, why = _BREACH, f"not-OK marker(s): {hits}"
    elif body.rstrip().endswith("OK"):
        # The line's TERMINAL verdict, not any `OK` inside it. `(max=20d OK)` is a
        # sub-clause about one sub-check and says nothing about the axis.
        verdict, why = _OK, "line terminates in OK"
    else:
        verdict, why = _UNKNOWN, "no terminal verdict this parser recognises"
    row: dict = {
        "tier": m.group("tier"),
        "axis": m.group("name"),
        "verdict": verdict,
        "verdict_evidence": why,
        "cutoff": cut.group("d") if cut else None,
        "frontier": fro.group("d") if fro else None,
        "sla_days": int(sla.group("n")) if sla else None,
        "raw_age_days": int(age.group("n")) if age else None,
        "age_beyond_frontier_days": int(beyond.group("n")) if beyond else None,
        "frontier_corrected": bool(fro),
    }
    # The floor is READ from the frontier the log derived, never from an assumed
    # trading-day-to-calendar ratio. An axis with no frontier stamp has no floor HERE --
    # which is `None`, not zero.
    if row["cutoff"] and row["frontier"]:
        row["floor_days"] = (_date(row["frontier"]) - _date(row["cutoff"])).days
    else:
        row["floor_days"] = None
    if row["floor_days"] is not None and row["sla_days"] is not None:
        row["sla_satisfiable"] = row["floor_days"] <= row["sla_days"]
    else:
        row["sla_satisfiable"] = None       # unknown, and unknown is not True
    return row


def analyse(axes: list[dict]) -> dict:
    findings: list[dict] = []

    for a in axes:
        if a["sla_satisfiable"] is False:
            findings.append({
                "kind": "sla_unsatisfiable_by_construction",
                "axis": a["axis"],
                "detail": (f"{a['axis']} cannot be fresher than {a['floor_days']}d after "
                           f"its cutoff (the log's own frontier {a['cutoff']} -> "
                           f"{a['frontier']}), but its SLA is {a['sla_days']}d. No data "
                           f"refresh can clear this gate."),
            })

    # Axes that share a cutoff and disagree about whether the frontier applies.
    by_cut: dict[str, list[dict]] = {}
    for a in axes:
        if a["cutoff"]:
            by_cut.setdefault(a["cutoff"], []).append(a)
    for cut, group in sorted(by_cut.items()):
        corrected = [a for a in group if a["frontier_corrected"]]
        bare = [a for a in group if not a["frontier_corrected"]]
        if not (corrected and bare):
            continue
        for b in bare:
            for c in corrected:
                findings.append({
                    "kind": "frontier_correction_not_applied_to_sibling_axis",
                    "axis": b["axis"],
                    "sibling": c["axis"],
                    "cutoff": cut,
                    "sibling_floor_days": c["floor_days"],
                    "this_axis_verdict": b["verdict"],
                    "sibling_verdict": c["verdict"],
                    # THE CONDITIONAL, NAMED. This file cannot see either axis's label, so
                    # it does not assert entitlement to the correction.
                    "conditional": (
                        f"IF {b['axis']} has the same lookahead as {c['axis']}, its floor "
                        f"is also {c['floor_days']}d, which would make its "
                        f"{b['sla_days']}d SLA unsatisfiable. This tool does not "
                        f"establish that the lookaheads match — it reports that two axes "
                        f"at the identical cutoff {cut} were judged by different rules, "
                        f"and one of them breached."),
                })

    return {
        "n_axes": len(axes),
        "n_frontier_corrected": sum(1 for a in axes if a["frontier_corrected"]),
        "n_breaching": sum(1 for a in axes if a["verdict"] == _BREACH),
        "n_unknown_verdict": sum(1 for a in axes if a["verdict"] == _UNKNOWN),
        "axes": axes,
        "findings": findings,
    }


def read_axes(text: str) -> list[dict]:
    """The LAST refusal block in the file — a log may hold several runs, and the current
    state of the gate is the most recent one, not the first one encountered."""
    rows = [r for r in (parse_axis(ln) for ln in text.splitlines()) if r]
    if not rows:
        return []
    # Keep only the final contiguous run of axis lines.
    out: list[dict] = []
    seen: set[str] = set()
    for r in reversed(rows):
        if r["axis"] in seen:
            break
        seen.add(r["axis"])
        out.append(r)
    return list(reversed(out))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log", required=True, type=Path,
                    help="a job log containing a promote freshness block")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        if not a.log.exists():
            print(f"SKIPPED: no log at {a.log} — nothing was established.",
                  file=sys.stderr)
            return 3
        text = a.log.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"axis-parity: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    axes = read_axes(text)
    if not axes:
        print(f"SKIPPED: no `source[...]` freshness block in {a.log} — the job may not "
              f"have reached the promote step. Not clean; unmeasured.", file=sys.stderr)
        return 3

    rep = analyse(axes)
    rep["log"] = str(a.log)

    if a.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        print(f"  {'axis':<22}{'cutoff':>12}{'frontier':>12}{'floor':>7}{'sla':>6}"
              f"{'satisfiable':>13}  verdict")
        for x in rep["axes"]:
            sat = {True: "yes", False: "NO", None: "unknown"}[x["sla_satisfiable"]]
            print(f"  {x['axis']:<22}{x['cutoff'] or '-':>12}{x['frontier'] or '-':>12}"
                  f"{('-' if x['floor_days'] is None else x['floor_days']):>7}"
                  f"{('-' if x['sla_days'] is None else x['sla_days']):>6}"
                  f"{sat:>13}  {x['verdict']}")
        for f in rep["findings"]:
            print(f"\n  [{f['kind']}] {f['axis']}")
            print(f"    {f.get('detail') or f.get('conditional')}")
        if not rep["findings"]:
            print("\n  no finding")

    return 1 if rep["findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
