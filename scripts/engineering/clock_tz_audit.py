#!/usr/bin/env python3
"""Clock/timezone hazard audit (#108 III.4; self-discovered gap #3).

The box runs America/Los_Angeles; the market runs America/New_York. Counts
naive time sources in decision-relevant code and computes proximity to the
next DST transition (the classic detonation week). Output is a ranked
remediation queue for the single-Clock migration.
"""
from __future__ import annotations

import datetime as dt
import subprocess
import zoneinfo
from pathlib import Path

G = Path("/Users/renhao/git/github")
SCOPES = {
    "pipeline-kernel": G / "renquant-pipeline/src/renquant_pipeline/kernel",
    "umbrella-adapters": G / "RenQuant/backtesting/renquant_104/adapters",
    "umbrella-scripts": G / "RenQuant/scripts",
}
PATTERNS = {
    "datetime.now()": r"datetime\.now\(\)",          # naive local clock
    "date.today()": r"date\.today\(\)",              # naive local date
    "utcnow()": r"utcnow\(\)",                       # naive UTC (deprecated)
    "time.time()": r"\btime\.time\(\)",
}


def count(scope: Path, pat: str) -> int:
    r = subprocess.run(f"grep -rE '{pat}' '{scope}' --include='*.py' | wc -l",
                       shell=True, capture_output=True, text=True)
    return int(r.stdout.strip() or 0)


if __name__ == "__main__":
    print(f"{'scope':18s} " + " ".join(f"{k:>16s}" for k in PATTERNS))
    total = 0
    for name, scope in SCOPES.items():
        row = [count(scope, p) for p in PATTERNS.values()]
        total += sum(row)
        print(f"{name:18s} " + " ".join(f"{c:16d}" for c in row))
    print(f"\nnaive time sources in decision-relevant code: {total} "
          f"(every one is a DST/cross-tz hazard; target after Clock migration: 0 outside the Clock module)")
    # DST proximity — both zones
    ny = zoneinfo.ZoneInfo("America/New_York")
    today = dt.datetime.now(ny)
    probe = today
    for _ in range(370):
        probe2 = probe + dt.timedelta(days=1)
        if probe2.astimezone(ny).utcoffset() != probe.astimezone(ny).utcoffset():
            print(f"next NY DST transition: ~{probe2.date()} "
                  f"({(probe2.date()-today.date()).days} days away) — schedule the Clock "
                  f"migration to land BEFORE it, and add a DST-week replay case to the corpus")
            break
        probe = probe2
    offset = (dt.datetime.now().astimezone().utcoffset()
              - today.utcoffset())
    print(f"box-vs-market offset right now: {offset} (PT vs ET)")
