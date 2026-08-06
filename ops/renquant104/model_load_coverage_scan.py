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
  * RELATIVE  — a drop of more than `--max-drop` against the trailing median
    catches a fleet that is decaying from a high base, which an absolute floor
    tuned low would sleep through.

A day that fails EITHER is a finding. This is deliberately not an
`and`: the two floors exist to catch different shapes, and requiring both would
mean each can veto the other.

REFUSALS. A missing log, or a log with no `Loaded models` line, is
`UNREADABLE` -> exit 2, never "coverage fine". A checker that cannot see is not a
checker that saw nothing wrong -- and this whole defect class is invisibility.

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

OK = "OK"
BELOW_ABSOLUTE = "BELOW_ABSOLUTE_FLOOR"
BELOW_TRAILING = "COLLAPSED_VS_TRAILING"
UNREADABLE = "UNREADABLE"


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
         max_drop: float = DEFAULT_MAX_DROP) -> dict:
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

    fracs = [r["frac"] for r in rows if r["frac"] is not None]
    trailing = statistics.median(fracs) if fracs else None

    for r in rows:
        if r["state"] == UNREADABLE:
            continue
        drop = None if trailing in (None, 0) else (trailing - r["frac"]) / trailing
        r["drop_vs_trailing"] = drop
        if r["frac"] < min_frac:
            r["state"] = BELOW_ABSOLUTE
        elif drop is not None and drop > max_drop:
            r["state"] = BELOW_TRAILING
        else:
            r["state"] = OK

    bad = [r for r in rows if r["state"] in (BELOW_ABSOLUTE, BELOW_TRAILING)]
    unreadable = [r for r in rows if r["state"] == UNREADABLE]
    return {
        "log_dir": str(log_dir), "n_sessions": len(rows),
        "trailing_median_frac": trailing,
        "min_frac": min_frac, "max_drop": max_drop,
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
        out.append(f"  {r['n_collapsed']} session(s) decided on a skeleton model fleet.")
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
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    try:
        r = scan(a.log_dir, a.days, a.min_frac, a.max_drop)
    except NoSessions as exc:
        print(f"REFUSING: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(r, indent=2) if a.json else render(r))
    if r["n_unreadable"]:
        return 2
    return 1 if r["n_collapsed"] else 0


if __name__ == "__main__":
    sys.exit(main())
