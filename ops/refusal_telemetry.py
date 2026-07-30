#!/usr/bin/env python3
"""GOAL-5 AC5: make funnel-integrity refusals QUERYABLE, not just logged.

The detection layer already exists and already fires. Measured 2026-07-30 across
169 daily-run logs `[VERIFIED]`:

    wash_sale_mass_block         12 files
    single_gate_funnel_kill       6
    fail_close_event              6
    universe_admission_collapse   1
    threshold_scale_mismatch      1
    zero_priced_candidates        0

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

A caveat this tool states rather than hides: it parses LOGS, which is a
reconstruction, not a source of record. The durable fix is for the pipeline to
persist these findings as rows. Until then this makes the existing evidence
aggregatable — and its own numbers should be treated as a floor, since a firing
whose log was rotated away is invisible to it.
"""
from __future__ import annotations

import argparse
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
# A count near the check name, e.g. "... blocked 41 candidates" / "n=41".
COUNT_NEAR = re.compile(r"(?:n=|blocked\s+|killed\s+|=\s*)(\d+)")


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
            for check in KNOWN_CHECKS:
                if check in line:
                    m = COUNT_NEAR.search(line)
                    per_check[check].append({
                        "date": d.isoformat() if d else None,
                        "file": path.name,
                        "count": int(m.group(1)) if m else None,
                        "line": line.strip()[:200],
                    })
            # a funnel-integrity finding whose name we do not track
            if "funnel_integrity" in line or "FunnelIntegrity" in line:
                for tok in re.findall(r"[a-z][a-z0-9_]{8,}", line):
                    if tok not in KNOWN_CHECKS and tok.endswith(
                            ("_kill", "_collapse", "_mismatch", "_event", "_block")):
                        untracked[tok] += 1
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
        counts = [h["count"] for h in hits if h["count"] is not None]
        line = (f"  {check:<28} firings={len(hits):<4} files={len(files):<3} "
                f"dates={len(dates)}")
        if counts:
            line += f"  count max={max(counts)} median={sorted(counts)[len(counts)//2]}"
        print(line)
        for h in hits:
            if h["date"] and dt.date.fromisoformat(h["date"]) >= window_start:
                recent.append({"check": check, **h})
    if r["untracked_candidates"]:
        print(f"  UNTRACKED check-like tokens near funnel_integrity: "
              f"{r['untracked_candidates']} — a refusal reason this tool does not "
              f"know about is the one it must not miss; add it to KNOWN_CHECKS")

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
