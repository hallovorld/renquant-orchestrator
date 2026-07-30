#!/usr/bin/env python3
"""GOAL-5 AC5: make funnel-integrity refusals QUERYABLE, not just logged.

The detection layer already exists and already fires. Re-measured 2026-07-30
against the real emitted-event grammar (see below), across 169 daily-run logs
`[VERIFIED — this session, post exact-grammar fix]`:

    wash_sale_mass_block         13 firings / 12 files /  8 dates
    single_gate_funnel_kill       6 /  6 /  6
    fail_close_event              6 /  6 /  6
    universe_admission_collapse   1 /  1 /  1
    threshold_scale_mismatch      1 /  1 /  1
    zero_priced_candidates        0 /  0 /  0

So AC5 is NOT a missing alarm. The gap is that every one of those firings exists
only as free text in a per-day log file, with ZERO rows in `runs.alpaca.db`. You
cannot ask "which refusals fired this month", "is one accelerating", or "did the
day the book went to cash have a mass refusal" without grepping by hand — which
is how a real firing stays invisible in practice.

This reads the logs and emits the aggregate. READ-ONLY: it opens log files and
writes nothing anywhere.

    python3 ops/refusal_telemetry.py --log-dir <umbrella>/logs/daily_104
    python3 ops/refusal_telemetry.py --log-dir ... --since 2026-07-01 --json

Exit codes: 0 clean, 1 a refusal fired inside --alert-window-days (default 7).
So it is usable as a daily scan, not only as a report.

EMITTED-EVENT GRAMMAR (what counts as a firing): renquant-pipeline's
``task_funnel_integrity.py::FunnelIntegrityTask.run`` logs a WARNING of the
exact form ``FunnelIntegrityAlert: STRUCTURAL_BLOCK ... fired=[<python list
of invariant names>]`` only when the session's verdict is STRUCTURAL_BLOCK. A
check NAME appearing anywhere else in a log line (docstrings, "checks
registered: ...", config dumps, an INFO line's bare ``fired=<count>``) is NOT
a firing and must not be counted — a mention is not an event. This tool
therefore parses ONLY that ``fired=[...]`` list; every name inside it that is
not in ``KNOWN_CHECKS`` is reported as UNTRACKED, no suffix heuristics.

A caveat this tool states rather than hides, twice:
  1. it parses LOGS, which is a reconstruction, not a source of record. The
     durable fix is for the pipeline to persist these findings as rows.
     Until then this makes the existing evidence aggregatable — and its own
     numbers should be treated as a floor, since a firing whose log was
     rotated away is invisible to it.
  2. the pipeline only emits the named ``fired=[...]`` line for STRUCTURAL_BLOCK
     verdicts (zero buys). A DEGRADED verdict — an invariant fired but buy
     capability partially survived, or only a warn-severity finding fired —
     logs just an unnamed ``fired=<count>`` in its INFO line, so this tool
     cannot recover which invariant it was. Structural (zero-buy) firings are
     the ones this tool sees; DEGRADED firings are a second floor beneath the
     one already stated above.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

#: The checks registered in renquant-pipeline's task_funnel_integrity.py.
#: Keep in sync deliberately: an unknown check firing is reported as UNTRACKED
#: rather than silently dropped, because a new refusal reason is exactly the
#: thing this tool must not miss.
KNOWN_CHECKS = (
    "single_gate_funnel_kill",
    "universe_admission_collapse",
    "threshold_scale_mismatch",
    "fail_close_event",
    "wash_sale_mass_block",
    "zero_priced_candidates",
)

DATE_IN_NAME = re.compile(r"(\d{4}-\d{2}-\d{2})")
# The exact line task_funnel_integrity.py emits for a STRUCTURAL_BLOCK verdict
# (see FunnelIntegrityTask.run): "FunnelIntegrityAlert: STRUCTURAL_BLOCK ...
# fired=['name1', 'name2']". Only this shape is a firing; a bare mention of a
# check name elsewhere in a line is not.
FIRED_LINE = re.compile(
    r"FunnelIntegrityAlert:\s*STRUCTURAL_BLOCK\b.*?\bfired=(?P<fired>\[.*\])\s*$"
)


def parse_fired_list(raw: str) -> list[str] | None:
    """Safely decode the ``fired=[...]`` Python-list-repr suffix, or None."""
    try:
        names = ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return None
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        return None
    return names


def log_date(path: Path) -> dt.date | None:
    m = DATE_IN_NAME.search(path.name)
    if m:
        try:
            return dt.date.fromisoformat(m.group(1))
        except ValueError:
            return None
    return None


def scan(log_dir: Path, since: dt.date | None) -> dict:
    per_check: dict[str, list[dict]] = defaultdict(list)
    files_scanned = 0
    files_skipped_date = 0
    untracked: Counter[str] = Counter()
    for path in sorted(log_dir.glob("*.log")):
        d = log_date(path)
        if since and d and d < since:
            files_skipped_date += 1
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        files_scanned += 1
        for line in text.splitlines():
            m = FIRED_LINE.search(line)
            if not m:
                continue
            names = parse_fired_list(m.group("fired"))
            if names is None:
                continue
            for name in names:
                if name in KNOWN_CHECKS:
                    per_check[name].append({
                        "date": d.isoformat() if d else None,
                        "file": path.name,
                        "line": line.strip()[:200],
                    })
                else:
                    # a firing whose name this tool does not track — surfaced,
                    # never dropped, because a new refusal reason is exactly
                    # the thing this tool must not miss.
                    untracked[name] += 1
    return {"files_scanned": files_scanned,
            "files_skipped_by_since": files_skipped_date,
            "per_check": {k: v for k, v in per_check.items()},
            "untracked_candidates": dict(untracked)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--log-dir", required=True, type=Path)
    ap.add_argument("--since", type=dt.date.fromisoformat, default=None)
    ap.add_argument("--alert-window-days", type=int, default=7)
    ap.add_argument("--today", type=dt.date.fromisoformat, default=None,
                    help="override for deterministic tests")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    if not a.log_dir.is_dir():
        print(f"ABORT: --log-dir {a.log_dir} is not a directory. This tool is "
              f"only meaningful against the DAILY RUN log directory; pointing it "
              f"at training logs yields zeros and reads as 'nothing fired'.")
        return 2

    r = scan(a.log_dir, a.since)
    today = a.today or dt.date.today()
    window_start = today - dt.timedelta(days=a.alert_window_days)

    recent: list[dict] = []
    print(f"funnel-integrity refusals, {r['files_scanned']} log file(s) scanned"
          + (f", {r['files_skipped_by_since']} skipped by --since" if a.since else ""))
    for check in KNOWN_CHECKS:
        hits = r["per_check"].get(check, [])
        files = sorted({h["file"] for h in hits})
        dates = sorted({h["date"] for h in hits if h["date"]})
        line = (f"  {check:<28} firings={len(hits):<4} files={len(files):<3} "
                f"dates={len(dates)}")
        print(line)
        for h in hits:
            if h["date"] and dt.date.fromisoformat(h["date"]) >= window_start:
                recent.append({"check": check, **h})
    if r["untracked_candidates"]:
        print(f"  UNTRACKED fired-event names: {r['untracked_candidates']} — a "
              f"refusal reason this tool does not know about is the one it must "
              f"not miss; add it to KNOWN_CHECKS")

    print("\nCAVEAT: this parses LOGS, which is a reconstruction, not a source of "
          "record. Treat the counts as a FLOOR — a firing whose log rotated away "
          "is invisible here. The durable fix is to persist these findings as rows.")

    if a.json:
        print(json.dumps({"summary": {k: len(v) for k, v in r["per_check"].items()},
                          "recent": recent, "window_start": window_start.isoformat()},
                         indent=2))
    if recent:
        print(f"\nALERT: {len(recent)} refusal firing(s) since {window_start} — "
              + ", ".join(sorted({x['check'] for x in recent})))
        return 1
    print(f"\nOK: no refusal firing since {window_start}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
