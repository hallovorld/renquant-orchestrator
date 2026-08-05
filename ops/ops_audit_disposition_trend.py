#!/usr/bin/env python3
"""Is the ops-audit getting quieter, and is anything ever DISPOSITIONED?

WHY (GOAL-1, measured 2026-08-05): `com.renquant.ops-audit` runs on a schedule
and exits 1 every time. Across the three dated logs on disk it reported
`findings=10`, `findings=10`, `findings=9` out of 11 detectors — 82–91 % firing
— and its acknowledgement ledger, `ops_audit_acks.json`, **does not exist at
all**: 0 acks, ever.

An audit where nine of eleven detectors fire daily and nothing is ever
dispositioned is one the reader learns to skip. That is the same failure this
project keeps meeting from different directions — a three-claim P0 sitting
two-thirds fixed for four days (orch#726), a sentinel that alarms nine hours
before the session (orch#811). The alarm is not wrong; it is undifferentiated.

The audit is honest about it — it prints `ledger … (0 ack(s))` on every run —
but a line nobody diffs is not a trend. This turns the dated logs into one.

Read-only. Usage:  python ops/ops_audit_disposition_trend.py [--days 14]
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys

REPO = pathlib.Path(os.environ.get("RENQUANT_REPO_ROOT",
                                   "/Users/renhao/git/github/RenQuant"))
LOGS = REPO / "logs" / "ops_audit"
LOG_RE = re.compile(r"ops_audit_(\d{4}-\d{2}-\d{2})\.log$")
SUMMARY_RE = re.compile(
    r"(\d+) detector\(s\) — ok=(\d+) findings=(\d+) info=(\d+)")
LEDGER_RE = re.compile(r"ledger (\S+) \((\d+) ack\(s\)\)")


def read_runs(logs_dir: pathlib.Path = LOGS, days: int = 14) -> list[dict]:
    """One row per dated log, newest last. A log with no summary line is
    RECORDED as unparsed rather than skipped — a day the audit failed to
    summarise is a fact about the audit, not an absence."""
    rows: list[dict] = []
    if not logs_dir.is_dir():
        return rows
    for path in sorted(logs_dir.glob("ops_audit_*.log"))[-days:]:
        m = LOG_RE.search(path.name)
        if not m:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        s = None
        for s in SUMMARY_RE.finditer(text):
            pass                       # last summary in the file wins
        led = None
        for led in LEDGER_RE.finditer(text):
            pass
        if s is None:
            rows.append({"date": m.group(1), "parsed": False,
                         "note": "no summary line — the audit did not report"})
            continue
        rows.append({
            "date": m.group(1), "parsed": True,
            "n_detectors": int(s.group(1)), "ok": int(s.group(2)),
            "findings": int(s.group(3)), "info": int(s.group(4)),
            "ack_ledger": led.group(1) if led else None,
            "n_acks": int(led.group(2)) if led else None,
        })
    return rows


def summarize(rows: list[dict]) -> dict:
    good = [r for r in rows if r.get("parsed")]
    fired = [r["findings"] for r in good]
    acks = [r["n_acks"] for r in good if r["n_acks"] is not None]
    return {
        "n_days": len(rows),
        "n_parsed": len(good),
        "findings_first": fired[0] if fired else None,
        "findings_last": fired[-1] if fired else None,
        "findings_min": min(fired) if fired else None,
        "findings_max": max(fired) if fired else None,
        # The load-bearing number: an audit with acks available but never used
        # is indistinguishable, to a reader, from one whose findings are all real.
        "max_acks_seen": max(acks) if acks else None,
        "never_dispositioned": bool(acks) and max(acks) == 0,
    }


def render(rows: list[dict], s: dict) -> str:
    out = ["ops-audit disposition trend", ""]
    out.append(f"  {'date':<12}{'detectors':>10}{'ok':>5}{'findings':>10}{'acks':>7}")
    for r in rows:
        if not r.get("parsed"):
            out.append(f"  {r['date']:<12}  {r['note']}")
            continue
        out.append(f"  {r['date']:<12}{r['n_detectors']:>10}{r['ok']:>5}"
                   f"{r['findings']:>10}"
                   f"{('—' if r['n_acks'] is None else r['n_acks']):>7}")
    out.append("")
    if s["n_parsed"] < 2:
        out.append("  fewer than two parsed runs — no trend can be read yet")
    else:
        d = s["findings_last"] - s["findings_first"]
        direction = "quieter" if d < 0 else ("louder" if d > 0 else "unchanged")
        out.append(f"  findings {s['findings_first']} → {s['findings_last']} "
                   f"over {s['n_parsed']} runs: {direction}")
    if s["never_dispositioned"]:
        out.append("  NOTHING has ever been dispositioned (max acks seen: 0) — "
                   "every finding\n  reads the same as every other, which is how "
                   "a reader learns to skip them.")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rows = read_runs(days=args.days)
    s = summarize(rows)
    print(json.dumps({"runs": rows, "summary": s}, indent=2) if args.json
          else render(rows, s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
