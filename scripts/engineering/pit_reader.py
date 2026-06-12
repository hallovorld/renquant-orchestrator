#!/usr/bin/env python3
"""PIT data layer reader (#108 III.2/§8) — pit_append + pit_read(as_of).

manifest.jsonl rows: {date, rows, sha256, collected_at, publication_lag_days}.
pit_read(source, as_of) returns only data VISIBLE at as_of:
visible ⇔ collected_at ≤ as_of AND date + publication_lag ≤ as_of.
Look-ahead becomes impossible at the API, not a review-checklist item.
Self-test reproduces the FINRA/E5 rule and the fundamentals-stale incident
shape. Bootstraps a real manifest for the live short-interest collector.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

PIT_ROOT = Path("/Users/renhao/git/github/RenQuant/data/pit")


def pit_append(source: str, *, date: str, payload_file: Path,
               collected_at: str, publication_lag_days: int = 0) -> dict:
    d = PIT_ROOT / source
    d.mkdir(parents=True, exist_ok=True)
    row = {"date": date, "rows": None, "sha256": hashlib.sha256(payload_file.read_bytes()).hexdigest()[:16],
           "collected_at": collected_at, "publication_lag_days": publication_lag_days,
           "payload": str(payload_file)}
    with open(d / "manifest.jsonl", "a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")
    return row


def pit_visible(source: str, as_of: str) -> list[dict]:
    mf = PIT_ROOT / source / "manifest.jsonl"
    if not mf.exists():
        return []
    out = []
    asof = dt.date.fromisoformat(as_of)
    for line in mf.read_text().splitlines():
        r = json.loads(line)
        eff = dt.date.fromisoformat(r["date"]) + dt.timedelta(days=r["publication_lag_days"])
        if dt.date.fromisoformat(r["collected_at"][:10]) <= asof and eff <= asof:
            out.append(r)
    return out


if __name__ == "__main__":
    import tempfile
    # P1: publication-lag enforcement (the FINRA/E5 rule)
    src = "selftest_" + dt.datetime.now().strftime("%H%M%S")
    p = Path(tempfile.mktemp())
    p.write_text("x")
    pit_append(src, date="2026-05-30", payload_file=p,
               collected_at="2026-06-01", publication_lag_days=9)
    assert pit_visible(src, "2026-06-05") == []          # settled but NOT published
    assert len(pit_visible(src, "2026-06-08")) == 1      # 05-30 + 9d = visible
    # P2: collected_at gate — yesterday's snapshot is invisible to a replay of last week
    pit_append(src, date="2026-06-01", payload_file=p,
               collected_at="2026-06-11", publication_lag_days=0)
    assert all(r["date"] != "2026-06-01" for r in pit_visible(src, "2026-06-05"))
    # P3: bootstrap a REAL manifest for the live short-interest collector
    si = Path("/Users/renhao/git/github/RenQuant/data/short_interest/history.parquet")
    if si.exists():
        row = pit_append("short_interest", date=dt.date.today().isoformat(),
                         payload_file=si, collected_at=dt.datetime.now().isoformat(),
                         publication_lag_days=0)
        print(f"P3 real manifest row: short_interest sha={row['sha256']}")
    print("P1 publication-lag enforced ✓  P2 collected_at gate (no retro-backfill leak) ✓")
