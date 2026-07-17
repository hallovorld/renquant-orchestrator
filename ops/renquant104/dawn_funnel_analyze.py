#!/usr/bin/env python3
"""Analyze a dawn readonly-funnel log for known daily-run killers (AC5, D2).

The dawn preflight (deploy/com.renquant.rq104-dawn-preflight.plist, 06:05
PT template) runs the SAME full inference funnel the 13:55 PT daily will
run — read-only broker, pinned strategy config — and this analyzer alerts
on the failure classes that have actually killed dailies:

  * calibrator/scorer or panel contract failures (07-14/15 incident)
  * ModuleNotFoundError / ImportError (07-16, orchestrator #524 class)
  * subrepo pin drift refusals
  * any Traceback (swallowed or not)
  * the funnel never reaching a decision line at all (crash/hang/truncated)

Alerting early gives ~8 hours of lead to fix before the daily trades.
Exit 0 = clean funnel; exit 1 = alert fired; exit 2 = usage error.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from liveness_common import alert  # noqa: E402

KILLER_PATTERNS: tuple[tuple[str, str], ...] = (
    ("contract fail", "artifact/calibrator contract failure"),
    ("panel_scorer_config_mismatch", "panel scorer config-consistency failure"),
    ("ModuleNotFoundError", "cross-repo import gap (#524 class)"),
    ("ImportError", "cross-repo import gap (#524 class)"),
    ("subrepo pin drift", "runtime pins drifted from subrepos.lock.json"),
    ("Traceback (most recent call last)", "unhandled exception in the funnel"),
)

# A healthy readonly funnel always ends with the runner's decision ntfy
# line (SHADOW-DECISION for readonly broker) or an explicit no-trade line.
COMPLETION_MARKERS = ("ntfy sent:", "DECISION")


def analyze(log_text: str) -> list[str]:
    problems: list[str] = []
    for needle, label in KILLER_PATTERNS:
        if needle in log_text:
            line = next((ln.strip() for ln in log_text.splitlines()
                         if needle in ln), needle)
            problems.append(f"{label}: {line[:300]}")
    if not any(m in log_text for m in COMPLETION_MARKERS):
        problems.append(
            "funnel never reached a decision line — crashed, hung, or "
            "truncated before completing"
        )
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", type=Path, required=True)
    ap.add_argument("--no-alert", action="store_true",
                    help="report only (tests)")
    args = ap.parse_args(argv)
    if not args.log.is_file():
        print(f"dawn preflight log missing: {args.log}", file=sys.stderr)
        if not args.no_alert:
            alert("RQ104 dawn preflight",
                  f"preflight log missing ({args.log}) — the dawn funnel "
                  "run itself failed to start")
        return 1
    problems = analyze(args.log.read_text(encoding="utf-8", errors="replace"))
    if not problems:
        print("dawn funnel preflight OK")
        return 0
    body = "; ".join(problems[:5])
    print(f"dawn funnel preflight: {len(problems)} problem(s): {body}")
    if not args.no_alert:
        alert("RQ104 dawn preflight",
              f"{len(problems)} problem(s) 8h before the daily: {body}",
              rq_root=os.environ.get("RQ_ROOT"))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
