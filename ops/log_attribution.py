#!/usr/bin/env python3
"""Which lines of a log belong to WHICH run? Refuse rather than guess.

**The failure this exists to make impossible.** On 2026-07-30 I misread an
append-only log as today's evidence three separate times, in one afternoon:

  1. `logs/rq104/launchd_dawn_preflight.out` — reported `No module named 'live'`
     as today's dawn-preflight failure. Historical line; today's run reached a
     decision and exited 0.
  2. `logs/preopen_gate/stderr.log` — nearly told the operator that six pending
     orders (AVGO, PANW, MU, AMZN, CRWD, CSCO) were cancelled this morning. That
     cancellation happened **2026-06-23**, five weeks earlier. Today's gate passed
     with `cancelled=[]`.
  3. `logs/rq104_shadow_scorer_sentinel.log` — read an mtime of `14:45` as "already
     ran today" at 14:26. The file was from **2026-07-29**.

None of the three was caught by a tool. Two were caught by re-reading, one by the
arithmetic that 14:45 has not happened at 14:26. That is not a control.

**The rule.** An append-only stream is a concatenation of runs. A line in it means
nothing until it is attributed, and there are exactly two ways to attribute one:

  * the FILENAME carries the date (`<name>_2026-07-30.log`), so the whole file
    belongs to that date; or
  * the LINE carries a timestamp this module can parse.

If neither holds the answer is **UNATTRIBUTABLE**, and this module returns that
status with **no lines** — never the whole file, which is the shape that produced
all three misreads.

    python ops/log_attribution.py --path <log> --date 2026-07-30 --grep ERROR
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from pathlib import Path

#: A date in the FILE NAME. Matches `x_2026-07-30.log` and `2026-07-30.log`.
FILENAME_DATE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")

#: A date at the START of a line. Deliberately anchored: a date appearing anywhere
#: in a line is usually DATA (a cutoff, a trained_date, a ticker's as-of), not the
#: line's own timestamp. Attributing on a loose match would invent evidence.
LINE_DATE = re.compile(r"^\[?(\d{4}-\d{2}-\d{2})[ T]")

ATTRIBUTED_BY_FILENAME = "filename"
ATTRIBUTED_BY_TIMESTAMP = "timestamp"
UNATTRIBUTABLE = "UNATTRIBUTABLE"

EXIT_OK, EXIT_UNATTRIBUTABLE, EXIT_ERROR = 0, 3, 2


def filename_date(path: Path) -> dt.date | None:
    m = FILENAME_DATE.search(path.name)
    if not m:
        return None
    try:
        return dt.date.fromisoformat(m.group(1))
    except ValueError:
        return None


def line_date(line: str) -> dt.date | None:
    m = LINE_DATE.match(line)
    if not m:
        return None
    try:
        return dt.date.fromisoformat(m.group(1))
    except ValueError:
        return None


def lines_for_date(path: Path, day: dt.date) -> tuple[str, list[str], str]:
    """(status, lines, why). `lines` is EMPTY unless status is an attribution.

    Never returns the whole file on failure. That is the entire point: the three
    misreads above all came from a reader that fell back to "all lines" when it
    could not attribute.
    """
    if not path.exists():
        return UNATTRIBUTABLE, [], f"{path} does not exist"
    text = path.read_text(errors="ignore")
    raw = text.splitlines()

    fd = filename_date(path)
    if fd is not None:
        if fd != day:
            return (UNATTRIBUTABLE, [],
                    f"{path.name} is the log for {fd}, not {day} — a dated file "
                    f"cannot supply evidence about another date")
        return ATTRIBUTED_BY_FILENAME, raw, f"filename names {day}"

    stamped = [l for l in raw if line_date(l) is not None]
    if not stamped:
        return (UNATTRIBUTABLE, [],
                f"{path.name} carries no date in its name and no parseable "
                f"line timestamps — it is an append-only stream of many runs and "
                f"NO line in it can be attributed to {day}")

    coverage = len(stamped) / len(raw) if raw else 0.0
    hits = [l for l in stamped if line_date(l) == day]
    why = (f"{len(stamped)}/{len(raw)} lines timestamped "
           f"({coverage:.0%}); {len(hits)} on {day}")
    if coverage < 0.5:
        # Most lines are continuations (tracebacks, tables, wrapped output) whose
        # own date is unknown. Returning only the stamped ones would silently drop
        # the body of every multi-line record.
        return (UNATTRIBUTABLE, [],
                why + " — under half the lines carry a timestamp, so a filtered "
                      "view would drop the body of multi-line records")
    return ATTRIBUTED_BY_TIMESTAMP, hits, why


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--path", required=True)
    ap.add_argument("--date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--grep", default=None, help="optional regex over attributed lines")
    a = ap.parse_args(argv)
    try:
        day = dt.date.fromisoformat(a.date)
    except ValueError as exc:
        print(f"bad --date: {exc}", file=sys.stderr)
        return EXIT_ERROR

    status, lines, why = lines_for_date(Path(a.path), day)
    if status == UNATTRIBUTABLE:
        print(f"UNATTRIBUTABLE: {why}", file=sys.stderr)
        print("Refusing to print lines. Attributing them to a date would be a "
              "guess, and this tool exists because that guess was wrong three "
              "times on 2026-07-30.", file=sys.stderr)
        return EXIT_UNATTRIBUTABLE

    if a.grep:
        rx = re.compile(a.grep)
        lines = [l for l in lines if rx.search(l)]
    print(f"# attributed by {status}: {why}", file=sys.stderr)
    for l in lines:
        print(l)
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
