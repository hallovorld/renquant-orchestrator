#!/usr/bin/env python3
"""rq104 liveness check (XC-6: monitoring gap).

Verifies that TODAY's launchd-scheduled rq104 jobs actually ran and produced
output. Checks wrapper log presence (proves the job fired) and module output
freshness (proves it produced a result).

Read-only; touches nothing but stdout/stderr.

Jobs checked:
  risk_budget    wrapper log: logs/rq104/risk_budget_<date>.log
  scorer_identity wrapper log: logs/rq104/scorer_identity_<date>.log

Session-day gating uses the real NYSE exchange calendar (same as rq105/pit
liveness checkers) so market holidays don't fire false alarms.
"""
from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from liveness_common import alert, is_session_day  # noqa: E402

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
LOG_DIR = os.path.join(RQ, "logs/rq104")

_WRAPPER_LOGS = ("risk_budget", "scorer_identity")


def _check_wrapper_log(job: str, today_iso: str) -> str | None:
    """Return an error string if the wrapper log for today is missing."""
    p = os.path.join(LOG_DIR, f"{job}_{today_iso}.log")
    if not os.path.exists(p):
        return f"{job}: wrapper log missing ({p})"
    if os.path.getsize(p) == 0:
        return f"{job}: wrapper log is zero-byte ({p})"
    return None


def _check_scorer_identity_verdict(today_iso: str) -> str | None:
    """Check that the scorer identity monitor produced a verdict line today."""
    log = os.path.join(LOG_DIR, f"scorer_identity_{today_iso}.log")
    if not os.path.exists(log):
        return None  # already caught by wrapper-log check
    try:
        text = Path(log).read_text(errors="replace")
    except OSError:
        return None
    if "scorer_identity_check:" not in text and "identity ok" not in text.lower():
        return f"scorer_identity: log exists but no verdict line found (module may have crashed)"
    return None


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=None, help="ISO date (default: today)")
    args = parser.parse_args(argv)

    today = dt.date.fromisoformat(args.as_of) if args.as_of else dt.date.today()
    today_iso = today.isoformat()

    if not is_session_day(today):
        print(f"rq104 liveness: {today_iso} is not an NYSE session day — skip")
        return 0

    problems: list[str] = []

    for job in _WRAPPER_LOGS:
        err = _check_wrapper_log(job, today_iso)
        if err:
            problems.append(err)

    verdict_err = _check_scorer_identity_verdict(today_iso)
    if verdict_err:
        problems.append(verdict_err)

    if problems:
        alert(
            f"rq104 LIVENESS: {len(problems)} issue(s) {today_iso}",
            "\n".join(problems),
            rq_root=RQ,
        )
        print("\n".join(problems))
        return 1

    print(f"rq104 liveness OK {today_iso}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
