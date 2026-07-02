#!/usr/bin/env python3
"""PIT N2 liveness check (#212 rule: liveness alert, separate from freshness).

Verifies TODAY's estimate snapshot exists and is non-trivial:
  data/estimate_snapshots/<today>/  contains >=1 parquet + a manifest.
Alerts via ntfy on a weekday miss. A missed day is UNRECOVERABLE (PIT
invariant: no backfill), so this alert is the package's most important file.
Read-only.
"""
import datetime as dt
import glob
import os
import subprocess
import sys

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
ROOT = os.path.join(RQ, "data", "estimate_snapshots")


def _alert(title: str, body: str) -> None:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic and os.path.exists(os.path.join(RQ, ".env")):
        for line in open(os.path.join(RQ, ".env")):
            if line.startswith("NTFY_TOPIC="):
                topic = line.split("=", 1)[1].strip().strip('"')
    if topic:
        subprocess.run(["curl", "-s", "-H", f"Title: {title}", "-d", body,
                        f"ntfy.sh/{topic}"], capture_output=True)


def main() -> int:
    if dt.date.today().weekday() >= 5:
        return 0
    today = dt.date.today().isoformat()
    day_dir = os.path.join(ROOT, today)
    parquets = glob.glob(os.path.join(day_dir, "*.parquet"))
    manifests = glob.glob(os.path.join(day_dir, "*manifest*"))
    problems = []
    if not os.path.isdir(day_dir):
        problems.append(f"{day_dir} missing — snapshot never ran")
    elif not parquets:
        problems.append(f"{day_dir} has no parquet outputs")
    elif not manifests:
        problems.append(f"{day_dir} has no manifest")
    if problems:
        _alert(f"PIT LIVENESS: snapshot missing {today}",
               "\n".join(problems) + "\nEvery missed day is UNRECOVERABLE.")
        print("\n".join(problems))
        return 1
    print(f"PIT liveness OK {today}: {len(parquets)} parquet(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
