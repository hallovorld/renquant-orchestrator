#!/usr/bin/env python3
"""Did the daily run actually load its models, or decide on a skeleton fleet?

WHY (GOAL-5 P0, measured 2026-08-06). Three sessions produced
`Phase 2b (buy scan): 0 candidates from 0 tickers` and were recorded as ordinary
no-trade days. They were not. The model fleet had collapsed:

    2026-06-29   74/145 loaded      no alert
    2026-06-30    7/145 loaded      no alert
    2026-07-08    4/145 loaded      no alert
    2026-07-09    4/145 loaded      no alert
    2026-07-10  125/145 loaded      recovered on its own

On the collapsed days the only tickers with a loadable model were **the names
already held** — so every candidate scored on nothing and the universe emptied.
The book could not have bought anything, and nothing said so.

**No ops detector reads this number.** `grep -rl "Loaded models for" ops/` returns
nothing. The run logs it, the funnel silently empties, and the session reports a
clean no-trade.

TWO FLOORS, because one is not enough:

  * ABSOLUTE  — below `--min-frac` of the universe is a collapse on its own terms.
  * RELATIVE  — a drop of more than `--max-drop` against the median of the
    sessions BEFORE it. Catches a fleet decaying from a high base, which an
    absolute floor tuned low would sleep through.

    The baseline is strictly PRIOR sessions, never the whole window. An earlier
    revision took one median over the entire window and judged every row against
    it, so a sustained partial decline dragged the baseline down and evaded both
    checks: 140,140,80,80,80 of 145 has a window median of 80, giving the 80-rows
    a drop of zero while 55 % clears a 50 % absolute floor. The decline was
    invisible in exactly the shape the relative floor exists for (codex on
    orch#878). A row with fewer than `--min-history` prior readable sessions is
    reported INSUFFICIENT_HISTORY for the relative test — the absolute floor
    still applies to it.

A day that fails EITHER is a finding. This is deliberately not an
`and`: the two floors exist to catch different shapes, and requiring both would
mean each can veto the other.

REFUSALS. A missing log, or a log with no `Loaded models` line, is
`UNREADABLE`, never "coverage fine". Exit 2 when that is the ONLY problem in the
window -- a checker that cannot see is not a checker that saw nothing wrong. But
a collapse outranks an unreadable neighbor: exit 1 fires whenever `n_collapsed`
is nonzero, even alongside unreadable sessions. The live logs have three
unreadable historical sessions sitting in the same 30-day window as the six
collapsed ones this detector exists to catch (codex on orch#878) -- an earlier
revision let UNREADABLE's exit 2 win that race, which `ops_audit` reads as
`unusable` (2 is not a declared finding exit), silently discarding the collapse
finding on the one path this detector is actually wired into.

Read-only. Usage:
    python ops/renquant104/model_load_coverage_scan.py [--days 30] [--json]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import statistics
import sys

LOG_DIR = pathlib.Path("/Users/renhao/git/github/RenQuant/logs/daily_104")
LOADED_RE = re.compile(r"Loaded models for (\d+)/(\d+) symbols")
DATED_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.log$")

#: Below this fraction of the universe the fleet is a skeleton whatever the
#: trailing history says. 0.50 is deliberately loose: the measured collapses were
#: 0.03-0.05 and the healthy days 0.51-0.86, so this separates them with room.
DEFAULT_MIN_FRAC = 0.50
#: A fall of more than this fraction BELOW the trailing median is a collapse even
#: if the absolute floor is met.
DEFAULT_MAX_DROP = 0.40
#: Minimum PRIOR readable sessions before a relative verdict is meaningful. Below
#: this the row is INSUFFICIENT_HISTORY, never OK — a median over one or two
#: points is not a baseline.
DEFAULT_MIN_HISTORY = 3

OK = "OK"
BELOW_ABSOLUTE = "BELOW_ABSOLUTE_FLOOR"
BELOW_TRAILING = "COLLAPSED_VS_TRAILING"
UNREADABLE = "UNREADABLE"
INSUFFICIENT = "INSUFFICIENT_HISTORY"


class NoSessions(RuntimeError):
    """No dated session log could be read. Not a clean coverage report."""


def dated_logs(log_dir: pathlib.Path = LOG_DIR) -> list[tuple[str, pathlib.Path]]:
    """Every DATED daily log, oldest first.

    Sorted by the filename date, never by mtime: a re-copied log gets a fresh
    mtime without being newer, and this repo has already published one wrong
    'newest file' from an mtime sort."""
    if not log_dir.is_dir():
        return []
    out = []
    for p in sorted(log_dir.glob("*.log")):
        m = DATED_RE.match(p.name)
        if m:
            out.append((m.group(1), p))
    return sorted(out)


def read_coverage(path: pathlib.Path) -> tuple[int | None, int | None, str]:
    """(loaded, universe, detail) for one session. The FIRST match wins — later
    lines belong to shadow lanes replaying the same bar, not to the prod scan."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return None, None, f"unreadable: {exc}"
    m = LOADED_RE.search(text)
    if not m:
        return None, None, "no `Loaded models for N/M symbols` line in this log"
    return int(m.group(1)), int(m.group(2)), ""


def scan(log_dir: pathlib.Path = LOG_DIR, days: int = 30,
         min_frac: float = DEFAULT_MIN_FRAC,
         max_drop: float = DEFAULT_MAX_DROP,
         min_history: int = DEFAULT_MIN_HISTORY) -> dict:
    sessions = dated_logs(log_dir)[-days:]
    if not sessions:
        raise NoSessions(
            f"no dated session log under {log_dir} — reporting full model "
            "coverage from zero sessions would publish a failed scan as a clean "
            "result")

    rows = []
    for date, path in sessions:
        loaded, universe, detail = read_coverage(path)
        if loaded is None or not universe:
            rows.append({"date": date, "state": UNREADABLE, "detail": detail,
                         "loaded": None, "universe": None, "frac": None})
            continue
        rows.append({"date": date, "loaded": loaded, "universe": universe,
                     "frac": loaded / universe, "state": None, "detail": ""})

    # Each row is judged against the sessions BEFORE it. Never the whole window:
    # that would include the row itself and every later collapse, so a sustained
    # decline lowers its own baseline and hides.
    prior: list[float] = []
    for r in rows:
        if r["state"] == UNREADABLE:
            continue
        base = statistics.median(prior) if len(prior) >= min_history else None
        drop = None if base in (None, 0) else (base - r["frac"]) / base
        r["baseline_frac"] = base
        r["n_prior_sessions"] = len(prior)
        r["drop_vs_prior"] = drop
        if r["frac"] < min_frac:
            r["state"] = BELOW_ABSOLUTE
        elif drop is not None and drop > max_drop:
            r["state"] = BELOW_TRAILING
        elif base is None:
            r["state"] = INSUFFICIENT
        else:
            r["state"] = OK
        prior.append(r["frac"])

    fracs = [r["frac"] for r in rows if r["frac"] is not None]
    trailing = statistics.median(fracs) if fracs else None

    bad = [r for r in rows if r["state"] in (BELOW_ABSOLUTE, BELOW_TRAILING)]
    unreadable = [r for r in rows if r["state"] == UNREADABLE]
    return {
        "log_dir": str(log_dir), "n_sessions": len(rows),
        "trailing_median_frac": trailing,
        "min_frac": min_frac, "max_drop": max_drop,
        "min_history": min_history,
        "n_insufficient_history": sum(1 for r in rows if r["state"] == INSUFFICIENT),
        # The daily alert surface: the LATEST session against its own prior
        # baseline, never one that includes itself.
        "latest": (rows[-1] if rows else None),
        "n_collapsed": len(bad), "n_unreadable": len(unreadable),
        "collapsed": [{k: r[k] for k in ("date", "loaded", "universe", "state")}
                      for r in bad],
        "rows": rows,
        "does_NOT_establish": (
            "why the models failed to load, or that a healthy count means the "
            "models are correct. This counts artifacts the runner could open — "
            "not whether any of them is fresh, well-fit, or the right one."
        ),
    }


def render(r: dict) -> str:
    if r["n_collapsed"]:
        dates = ", ".join(x["date"] for x in r["collapsed"])
        out = [f"{r['n_collapsed']} session(s) decided on a skeleton model "
               f"fleet: {dates}", ""]
    else:
        out = [f"model-load coverage — {r['n_sessions']} session(s)", ""]
    out.append(f"  trailing median coverage : "
               f"{'—' if r['trailing_median_frac'] is None else f'{100*r[chr(116)+chr(114)+chr(97)+chr(105)+chr(108)+chr(105)+chr(110)+chr(103)+chr(95)+chr(109)+chr(101)+chr(100)+chr(105)+chr(97)+chr(110)+chr(95)+chr(102)+chr(114)+chr(97)+chr(99)]:.1f}%'}")
    out.append(f"  absolute floor           : {100*r['min_frac']:.0f}%")
    out.append(f"  max drop vs trailing     : {100*r['max_drop']:.0f}%")
    out.append("")
    for x in r["rows"]:
        if x["state"] == UNREADABLE:
            out.append(f"  {x['date']}  UNREADABLE — {x['detail'][:52]}")
        elif x["state"] != OK:
            out.append(f"  {x['date']}  {x['loaded']:>4}/{x['universe']:<4} "
                       f"({100*x['frac']:>5.1f}%)  {x['state']}")
    out.append("")
    if r["n_collapsed"]:
        out.append("  A run that scores every candidate against a missing artifact")
        out.append("  reports a clean no-trade. That is the defect, not the no-trade.")
    else:
        out.append("  every readable session met both floors.")
    if r["n_unreadable"]:
        out.append(f"  {r['n_unreadable']} session(s) UNREADABLE — not a pass.")
    out.append("")
    out.append(f"  Does NOT establish {r['does_NOT_establish']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log-dir", type=pathlib.Path, default=LOG_DIR)
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--min-frac", type=float, default=DEFAULT_MIN_FRAC)
    ap.add_argument("--max-drop", type=float, default=DEFAULT_MAX_DROP)
    ap.add_argument("--min-history", type=int, default=DEFAULT_MIN_HISTORY)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        r = scan(a.log_dir, a.days, a.min_frac, a.max_drop, a.min_history)
    except NoSessions as exc:
        print(f"REFUSING: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(r, indent=2) if a.json else render(r))
    # A collapse outranks an unreadable neighbor: never let UNREADABLE's exit 2
    # mask a COLLAPSED_VS_TRAILING / BELOW_ABSOLUTE_FLOOR finding (orch#878).
    if r["n_collapsed"]:
        return 1
    if r["n_unreadable"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
