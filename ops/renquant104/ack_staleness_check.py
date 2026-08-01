#!/usr/bin/env python3
"""Has a suppression outlived its own stated clearing condition? (GOAL-1)

`ops/renquant104/sentinel_acks.json` suppresses a sentinel's last-exit alarm for a named
job. Every row carries `acked_at` and `clears_when` — a **condition**, per the containment
protocol, because "temporary" is not an expiry and "until X is deployed" is.

**Nothing checked the conditions.** An ack whose stated clearing date has passed keeps
suppressing its alarm, indefinitely and silently. That is the same shape this programme
keeps finding — a guard that passes forever — applied to the *suppression ledger* itself,
which is the one place where passing forever means an alarm never fires.

MEASURED 2026-07-31, 10 acks:

  3 name a clearing DATE that has already passed, all 2026-07-20, 11 days ago:
      com.renquant.daily104              "next NYSE session's 13:55 wrapper run (2026-07-20)"
      com.renquant.shadow-ab-daily       "next NYSE session 14:35 two-arm run (2026-07-20)"
      com.renquant.weekly-retrain-patchtst "next weekly cycle (review if still failing 2026-07-20+)"

  7 name an EVENT with no date — "next VIX-anomaly trigger", "a staged model passes the
  WF gate", "task #75". One says so outright: "open-ended; gate is correct".

WHAT THIS TOOL CLAIMS. Only that a **date** written into a clearing condition has passed.
That is a syntactic fact about the ledger, checkable without touching any job.

WHAT IT DOES NOT CLAIM, and the distinction is the whole point: it does **not** claim the
condition was met, nor that the underlying fault is fixed, nor that the ack should be
removed. A date-bearing condition like *"review if still failing 2026-07-20+"* asks for a
REVIEW on that date — the passing of the date is the trigger, not the verdict. And for the
7 event-based rows it claims nothing at all: an open-ended condition is a deliberate
choice here, not a defect, and counting it as stale would manufacture an alarm out of a
design decision.

It never edits the ledger. Auto-clearing a suppression is a mutation of a reviewed surface
and would need the containment protocol; this only makes the state visible.

Read-only. Exit codes: ``0`` no ack has a past clearing date, ``1`` at least one has (or
the ledger is unreadable/malformed), ``2`` usage/IO error — so a broken invocation cannot
read as a clean ledger.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys

#: An ISO date anywhere in the clearing condition. Deliberately permissive about
#: surrounding prose: the conditions are written for humans and the date is the only part
#: a machine can check.
_DATE = re.compile(r"(20\d{2}-\d{2}-\d{2})")


def audit(path: str, today: dt.date) -> dict:
    if not os.path.exists(path):
        return {"status": "ledger_missing", "path": path}
    try:
        with open(path, "rb") as fh:
            data = json.loads(fh.read())
    except (OSError, ValueError) as exc:
        return {"status": "ledger_unreadable", "path": path,
                "why": f"{type(exc).__name__}: {exc}"}
    if not isinstance(data, dict):
        return {"status": "ledger_unreadable", "path": path,
                "why": f"top-level JSON is {type(data).__name__}, not an object"}

    rows, malformed = [], []
    for job, row in sorted(data.items()):
        if not isinstance(row, dict):
            malformed.append({"job": job,
                              "why": f"entry is {type(row).__name__}, not an object"})
            continue
        cw = row.get("clears_when")
        if not isinstance(cw, str) or not cw.strip():
            # A suppression with NO stated clearing condition is the worst row possible:
            # it can never be shown to have outlived anything. It is a defect, not a
            # date-less event condition.
            malformed.append({"job": job,
                              "why": "no `clears_when` — a suppression with no stated "
                                     "clearing condition can never be shown to have "
                                     "outlived it"})
            continue
        acked_at = row.get("acked_at")
        try:
            age = (today - dt.date.fromisoformat(str(acked_at)[:10])).days
        except (TypeError, ValueError):
            age = None
        dates = []
        for token in _DATE.findall(cw):
            try:
                dates.append(dt.date.fromisoformat(token))
            except ValueError:
                pass
        past = sorted(d for d in dates if d < today)
        rows.append({
            "job": job,
            "acked_at": acked_at,
            "age_days": age,
            "clears_when": cw,
            "dates_in_condition": [d.isoformat() for d in sorted(dates)],
            "past_dates": [d.isoformat() for d in past],
            "days_since_earliest_past_date": (today - past[0]).days if past else None,
            "kind": ("date_bearing" if dates else "event_only"),
            "overdue": bool(past),
        })

    overdue = [r for r in rows if r["overdue"]]
    return {
        "status": "read",
        "path": os.path.basename(path),
        "as_of": today.isoformat(),
        "n_acks": len(rows),
        "n_date_bearing": sum(1 for r in rows if r["kind"] == "date_bearing"),
        "n_event_only": sum(1 for r in rows if r["kind"] == "event_only"),
        "n_overdue": len(overdue),
        "overdue_jobs": [r["job"] for r in overdue],
        "malformed": malformed,
        "acks": rows,
        "scope_note": (
            "OVERDUE means a DATE written into the clearing condition has passed. It "
            "does NOT mean the condition was met, that the fault is fixed, or that the "
            "ack should be removed — a condition like 'review if still failing "
            "2026-07-20+' makes the date a TRIGGER, not a verdict. Event-only rows are "
            "claimed nothing about: an open-ended condition is a deliberate choice here, "
            "and counting it as stale would manufacture an alarm out of a design "
            "decision. This tool never edits the ledger."),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--ledger", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "sentinel_acks.json"))
    ap.add_argument("--as-of", help="YYYY-MM-DD; defaults to today")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        today = (dt.date.fromisoformat(a.as_of) if a.as_of
                 else dt.date.today())
    except ValueError:
        print(f"ack staleness: --as-of {a.as_of!r} is not an ISO date", file=sys.stderr)
        return 2

    rep = audit(a.ledger, today)
    if rep["status"] != "read":
        print(f"ack staleness: {rep['status']} — {rep.get('why', rep.get('path'))}",
              file=sys.stderr)
        return 2 if rep["status"] == "ledger_missing" else 1

    if a.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        print(f"{rep['path']} as of {rep['as_of']}: {rep['n_acks']} ack(s) — "
              f"{rep['n_date_bearing']} date-bearing, {rep['n_event_only']} event-only")
        for r in rep["acks"]:
            if r["overdue"]:
                print(f"  OVERDUE  {r['job']}: clearing date {r['past_dates'][0]} "
                      f"passed {r['days_since_earliest_past_date']} d ago "
                      f"(acked {r['acked_at']})")
                print(f"           clears_when: {r['clears_when']}")
        for m in rep["malformed"]:
            print(f"  MALFORMED {m['job']}: {m['why']}")
        if not rep["n_overdue"] and not rep["malformed"]:
            print("  no ack has a clearing date in the past")
        print("\n" + rep["scope_note"])

    return 1 if (rep["n_overdue"] or rep["malformed"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
