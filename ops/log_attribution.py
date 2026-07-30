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


def filename_date(path: Path) -> tuple[dt.date | None, str]:
    """(date, why). MORE THAN ONE distinct date in the name is a REFUSAL.

    Codex on #648: a filename carrying two dates — `x_2026-07-29_to_2026-07-30.log`,
    a rotated range, a backfill window — is not evidence that the whole file belongs
    to the first one `search()` happens to hit. Taking the first match is picking a
    winner from an ambiguity, which is the guessing this module exists to refuse.
    """
    found = []
    for raw in FILENAME_DATE.findall(path.name):
        try:
            d = dt.date.fromisoformat(raw)
        except ValueError:
            continue
        if d not in found:
            found.append(d)
    if not found:
        return None, "no date in filename"
    if len(found) > 1:
        return None, (f"{path.name} carries {len(found)} distinct dates "
                      f"({', '.join(d.isoformat() for d in found)}) — a naming "
                      f"contract that does not establish ONE run date cannot "
                      f"attribute the file")
    return found[0], f"filename names {found[0]}"


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

    fd, fwhy = filename_date(path)
    if fd is None and "distinct dates" in fwhy:
        return UNATTRIBUTABLE, [], fwhy
    if fd is not None:
        if fd != day:
            return (UNATTRIBUTABLE, [],
                    f"{path.name} is the log for {fd}, not {day} — a dated file "
                    f"cannot supply evidence about another date")
        return ATTRIBUTED_BY_FILENAME, raw, fwhy

    # RECORD FRAMING, replacing a 50%-coverage ratio that codex correctly rejected.
    # A timestamp establishes the date of ITS OWN line and of nothing else. The ratio
    # rule accepted a 51%-stamped stream and silently dropped every continuation —
    # tracebacks, tables, wrapped output — which is an attribution gap inside the
    # module built to refuse them.
    #
    # A RECORD is a timestamped line plus every following un-timestamped line, up to
    # the next timestamp. The record inherits its header's date and is returned whole
    # or not at all. Nothing is dropped and nothing is guessed.
    records: list[tuple[dt.date, list[str]]] = []
    orphan: list[str] = []
    for line in raw:
        d = line_date(line)
        if d is not None:
            records.append((d, [line]))
        elif records:
            records[-1][1].append(line)
        elif line.strip():
            orphan.append(line)          # non-blank text before ANY timestamp

    if not records:
        return (UNATTRIBUTABLE, [],
                f"{path.name} carries no date in its name and no parseable "
                f"line timestamps — it is an append-only stream of many runs and "
                f"NO line in it can be attributed to {day}")

    # Text before the first timestamp belongs to no record IN THIS FILE — a banner
    # printed at creation, or the tail of a run that started in a rotated-away file.
    # It is EXCLUDED (the guarantee is that no un-attributable line is ever
    # returned) and the exclusion is REPORTED (a silent drop is the defect one level
    # down). Refusing the whole file over it would be over-refusal: measured on
    # logs/preopen_gate/stderr.log the orphan is a one-line path banner, while every
    # actual record below it is well framed and attributable.
    hits = [l for d, body in records if d == day for l in body]
    why = (f"{len(records)} framed record(s); "
           f"{sum(1 for d, _ in records if d == day)} on {day}")
    if orphan:
        why += (f"; EXCLUDED {len(orphan)} non-blank line(s) before the first "
                f"timestamp — they belong to no record in this file")
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
