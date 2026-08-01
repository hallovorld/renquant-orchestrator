#!/usr/bin/env python3
"""Two DEGRADED shadow lanes, two completely different remedies — the sentinel says neither.

MEASURED 2026-08-01, as of the 2026-07-31 session. `rq104_shadow_scorer_sentinel.py` fires
on both watched lanes with alarms that read identically::

    [hf_patchtst]              degraded: stale_625d_limit_28d
    [topdecile_clf_blend_leg]  degraded: stale_94d_limit_28d

They are not the same failure. The rawlabel corpus every downstream label depends on ends
at **2026-04-28** — 94 days before that session `[本次实测]`. So:

===========================  =======  ==============  =========================
lane                          stale    implied cutoff  beyond the frontier
===========================  =======  ==============  =========================
`topdecile_clf_blend_leg`      94d      2026-04-28      **0d** -- AT the frontier
`hf_patchtst`                 625d      2024-11-13      **531d**
===========================  =======  ==============  =========================

**clf is exactly as fresh as its input permits.** Retraining it changes nothing; the only
thing that moves it is the corpus frontier. **PatchTST is 531 days behind a frontier that
was available to it** — that is an independent failure with its own owner.

An operator looking at two identical-looking DEGRADED alarms cannot tell those apart, and
the cheaper-looking one (94d) is the one that CANNOT be fixed in the lane while the
expensive-looking one (625d) is the one that can. That inversion is the defect.

WHY A LABEL HORIZON MAKES THIS STRUCTURAL, NOT A BACKLOG. A 60-trading-day forward label
cannot be observed until 60 trading days have passed, so the corpus frontier is
permanently that far behind the calendar. A lane trained to the frontier is therefore
*always* "stale" against a 28-day limit. This is the same shape GOAL-5 measured on the
promote path, where one freshness axis subtracts the frontier and its sibling does not.

WHAT THIS TOOL WILL NOT DO. It will not treat a frontier it cannot certify as a fact. The
rawlabel provenance sidecar currently carries an **invalidation receipt newer than the
provenance stamp**, so the frontier is reported with its trust state attached and every
verdict derived from an uncertified frontier is marked ``provisional``. `UNKNOWN` is a
real outcome: no provenance at all means the attribution was not established, which is not
the same as "the lane is fine".

Read-only. Reads sidecar JSON and a reason string, writes nothing, never invokes git,
never mutates a job.

Exit codes: ``0`` no independently-stale lane, ``1`` at least one, ``2`` usage/IO error,
``3`` SKIPPED — the frontier could not be established at all, so nothing was attributed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from pathlib import Path

#: `stale_<N>d_limit_<M>d`, the sentinel's own reason vocabulary.
_STALE = re.compile(r"stale_(?P<age>\d+)d_limit_(?P<limit>\d+)d")

FRONTIER_BOUND = "FRONTIER_BOUND"
INDEPENDENTLY_STALE = "INDEPENDENTLY_STALE"
UNKNOWN = "UNKNOWN"

#: Trust states for the frontier itself. `INVALIDATED` is not `ABSENT`: an invalidated
#: sidecar still carries a date, and suppressing it would hide the attribution entirely
#: rather than qualify it.
CERTIFIED, INVALIDATED, ABSENT = "certified", "invalidated", "absent"


def read_frontier(provenance: Path, invalid_receipt: Path | None) -> dict:
    """The corpus frontier, WITH its trust state — never a bare date.

    A date lifted out of an invalidated sidecar and presented as a fact is how a document
    ends up resting on a number nobody certified.
    """
    out: dict = {"frontier": None, "trust": ABSENT, "provenance_path": str(provenance),
                 "why": None}
    if not provenance.exists():
        out["why"] = "no provenance sidecar"
        return out
    try:
        prov = json.loads(provenance.read_text())
    except (OSError, ValueError) as exc:
        out["why"] = f"provenance unreadable/unparseable: {exc}"
        return out
    if not isinstance(prov, dict):
        out["why"] = f"provenance is {type(prov).__name__}, not an object"
        return out
    f = prov.get("source_panel_frontier")
    if not isinstance(f, str):
        out["why"] = "provenance carries no `source_panel_frontier` string"
        return out
    try:
        dt.date.fromisoformat(f[:10])
    except ValueError:
        out["why"] = f"`source_panel_frontier` is not a date: {f!r}"
        return out

    out["frontier"] = f[:10]
    out["trust"] = CERTIFIED
    out["built_at"] = prov.get("built_at")

    if invalid_receipt is not None and invalid_receipt.exists():
        try:
            rec = json.loads(invalid_receipt.read_text())
        except (OSError, ValueError) as exc:
            # An unreadable receipt is NOT an absent one. Treating it as absent would let
            # a corrupt file certify the corpus.
            out["trust"] = INVALIDATED
            out["why"] = f"invalidation receipt present but unreadable: {exc}"
            return out
        at = rec.get("invalidated_at") if isinstance(rec, dict) else None
        built = out.get("built_at")
        newer = not (isinstance(at, str) and isinstance(built, str)) or at > built
        if newer:
            out["trust"] = INVALIDATED
            out["invalidated_at"] = at
            out["why"] = (rec.get("reason") if isinstance(rec, dict) else None) or \
                         "invalidation receipt present"
    return out


def attribute(lane: str, reason: str, as_of: dt.date, frontier: dict) -> dict:
    """Split one lane's staleness into the part its input forces and the part it owns."""
    m = _STALE.search(reason or "")
    row: dict = {"lane": lane, "reason": reason, "as_of": as_of.isoformat(),
                 "status": UNKNOWN, "provisional": frontier["trust"] != CERTIFIED}
    if not m:
        row["why"] = "reason carries no `stale_<N>d_limit_<M>d` term"
        return row
    age = int(m.group("age"))
    row["stale_days"] = age
    row["limit_days"] = int(m.group("limit"))
    row["implied_cutoff"] = (as_of - dt.timedelta(days=age)).isoformat()
    if frontier["frontier"] is None:
        row["why"] = f"frontier not established ({frontier['why']})"
        return row
    fr = dt.date.fromisoformat(frontier["frontier"])
    beyond = (fr - (as_of - dt.timedelta(days=age))).days
    row["frontier"] = frontier["frontier"]
    row["beyond_frontier_days"] = beyond
    row["frontier_age_days"] = (as_of - fr).days
    if beyond <= 0:
        row["status"] = FRONTIER_BOUND
        row["remedy"] = ("advance the corpus frontier — retraining this lane cannot "
                         "reduce its staleness, because it is already trained to the "
                         "frontier")
    else:
        row["status"] = INDEPENDENTLY_STALE
        row["remedy"] = (f"this lane is {beyond}d behind a frontier that was available "
                         f"to it; the fault is in the lane, not the corpus")
    return row


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--lane", action="append", default=[], metavar="NAME=REASON",
                    required=True,
                    help="a lane and its sentinel reason, e.g. "
                         "'topdecile_clf_blend_leg=stale_94d_limit_28d'")
    ap.add_argument("--as-of", required=True, help="the session date the reasons are from")
    ap.add_argument("--provenance", required=True, type=Path,
                    help="rawlabel provenance sidecar JSON")
    ap.add_argument("--invalid-receipt", type=Path, default=None,
                    help="rawlabel .INVALID.json receipt, if any")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        as_of = dt.date.fromisoformat(a.as_of)
    except ValueError:
        print(f"attribution: --as-of is not a date: {a.as_of!r}", file=sys.stderr)
        return 2

    try:
        frontier = read_frontier(a.provenance, a.invalid_receipt)
    except OSError as exc:
        print(f"attribution: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    rows = []
    for spec in a.lane:
        name, _, reason = spec.partition("=")
        rows.append(attribute(name, reason, as_of, frontier))

    rep = {"as_of": as_of.isoformat(), "frontier": frontier, "lanes": rows,
           "n_independently_stale": sum(1 for r in rows
                                        if r["status"] == INDEPENDENTLY_STALE),
           "n_frontier_bound": sum(1 for r in rows if r["status"] == FRONTIER_BOUND),
           "n_unknown": sum(1 for r in rows if r["status"] == UNKNOWN)}

    if a.json:
        print(json.dumps(rep, indent=2, sort_keys=True))
    else:
        print(f"  corpus frontier: {frontier['frontier'] or 'NOT ESTABLISHED'} "
              f"[{frontier['trust']}]")
        if frontier["trust"] != CERTIFIED and frontier["why"]:
            print(f"    {str(frontier['why'])[:150]}")
        print(f"\n  {'lane':<28}{'stale':>7}{'cutoff':>13}{'beyond':>8}  status")
        for r in rows:
            print(f"  {r['lane']:<28}"
                  f"{r.get('stale_days', '-'):>7}"
                  f"{r.get('implied_cutoff', '-'):>13}"
                  f"{r.get('beyond_frontier_days', '-'):>8}  {r['status']}"
                  f"{'  (provisional)' if r['provisional'] else ''}")
        for r in rows:
            if r.get("remedy"):
                print(f"\n  [{r['lane']}] {r['remedy']}")
            elif r.get("why"):
                print(f"\n  [{r['lane']}] not attributed: {r['why']}")

    if frontier["frontier"] is None:
        return 3
    return 1 if rep["n_independently_stale"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
