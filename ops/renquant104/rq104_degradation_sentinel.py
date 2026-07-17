#!/usr/bin/env python3
"""rq104 degradation sentinel (GOAL-5 AC1: silence is not health).

The 2026-07-16 incident: the daily run fail-closed for THREE consecutive
sessions (zero candidates, calibrator contract Traceback swallowed behind
exit 0) while model_protection kept selling — the book drained to 94% cash
and nobody was alerted. Every one of those conditions was visible in data
the whole time; nothing looked.

This checker looks. It alarms on DEGRADED-BUT-ALIVE states that the
existing liveness checkers (which prove jobs *ran*) cannot see:

  a. zero-candidate streak — the last N session days each have live runs
     recorded but every run that day scored 0 candidates and placed 0 buys
  b. traceback-with-success — today's daily log contains a Traceback or a
     fail-closed contract failure, regardless of process exit code
  c. launchd nonzero exits — any com.renquant.* job whose last exit
     status is nonzero
  d. buy-path blocked streak — the last N session days each ended
     buy-blocked (row flag or a BUY-BLOCKED decision line in the log)

Read-only: the runs DB is opened mode=ro&immutable=1; logs are only read.
Session-day gating uses the real NYSE calendar (holidays never alarm), and
every check is anchored to whole past sessions — nothing here measures
intraday freshness, so there is no after-hours false-positive window (the
lesson from the 105 liveness stale-tick alarms).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from liveness_common import alert, is_session_day  # noqa: E402

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
DB = os.path.join(RQ, "data/runs.alpaca.db")
DAILY_LOG_DIR = os.path.join(RQ, "logs/daily_104")

#: consecutive session days of a degraded state before alarming. 2 keeps
#: detection within one session of the incident pattern (07-14/15 already
#: satisfied it) while a single quiet day never pages.
STREAK_N = 2

#: log lines that mean the run hit a swallowed failure even if it exited 0.
_TRACEBACK_PATTERNS = ("Traceback (most recent call last)", "contract fail")

_BUY_BLOCKED_LOG_PATTERN = "BUY-BLOCKED"


# ---------------------------------------------------------------------------
# session-day helpers
# ---------------------------------------------------------------------------

def last_session_days(as_of: dt.date, n: int, *, lookback_days: int = 14) -> list[dt.date]:
    """The n most recent NYSE session days ending at as_of (inclusive if a
    session day), newest first. Bounded lookback so a calendar failure can
    never loop forever."""
    out: list[dt.date] = []
    day = as_of
    for _ in range(lookback_days):
        if is_session_day(day):
            out.append(day)
            if len(out) == n:
                break
        day -= dt.timedelta(days=1)
    return out


# ---------------------------------------------------------------------------
# check a + d: per-session-day run-row states from the runs DB
# ---------------------------------------------------------------------------

def day_run_state(conn: sqlite3.Connection, day: dt.date) -> dict | None:
    """Aggregate the day's live runs: None if no rows (that is a *liveness*
    problem, owned by rq104_liveness_check, not a degradation signal)."""
    row = conn.execute(
        "SELECT COUNT(*), MAX(n_candidates), MAX(n_buys), "
        # the LAST run of the day carries the day's final buy_blocked verdict
        "(SELECT buy_blocked FROM pipeline_runs WHERE run_type='live' "
        " AND run_date=? ORDER BY created_at DESC LIMIT 1) "
        "FROM pipeline_runs WHERE run_type='live' AND run_date=?",
        (day.isoformat(), day.isoformat()),
    ).fetchone()
    n_rows, max_cand, max_buys, last_blocked = row
    if not n_rows:
        return None
    # pipeline_runs alone under-reports purchases: n_candidates is zeroed
    # after VetoWeakBuys clears the scan set, and n_buys excludes TOP-UP
    # orders (2026-07-17 first-firing false alarm: 07-16 placed 3 top-up
    # buys with n_buys=0). The trades table records every emitted buy
    # (NEW_BUY / buy_pending / top-ups), so count it as the buy-activity
    # ground truth for the day.
    try:
        trade_buys = conn.execute(
            "SELECT COUNT(*) FROM trades t JOIN pipeline_runs pr "
            "ON t.run_id = pr.run_id WHERE pr.run_type='live' "
            "AND pr.run_date=? AND t.action LIKE '%buy%'",
            (day.isoformat(),),
        ).fetchone()[0]
    except sqlite3.OperationalError:
        # trades table absent (minimal fixture DBs / legacy stores): fall
        # back to pipeline_runs-only accounting rather than crashing the
        # sentinel — a monitoring tool must degrade, never abort.
        trade_buys = 0
    return {
        "n_rows": n_rows,
        "max_candidates": max_cand or 0,
        "max_buys": max(max_buys or 0, trade_buys),
        "last_buy_blocked": bool(last_blocked),
    }


def check_zero_candidate_streak(conn: sqlite3.Connection, days: list[dt.date]) -> str | None:
    states = [(d, day_run_state(conn, d)) for d in days]
    observed = [(d, s) for d, s in states if s is not None]
    if len(observed) < len(days):
        return None  # a day with no rows at all is the liveness checker's alarm
    if all(s["max_candidates"] == 0 and s["max_buys"] == 0 for _, s in observed):
        detail = ", ".join(f"{d.isoformat()} (runs={s['n_rows']})" for d, s in observed)
        return (
            f"zero-candidate streak: {len(observed)} consecutive session day(s) "
            f"with live runs but 0 candidates and 0 buys — {detail}. "
            f"The buy pipeline is silently fail-closed (2026-07-16 incident pattern)."
        )
    return None


def check_buy_blocked_streak(conn: sqlite3.Connection, days: list[dt.date]) -> str | None:
    hits: list[str] = []
    for d in days:
        state = day_run_state(conn, d)
        blocked_row = bool(state and state["last_buy_blocked"])
        blocked_log = _daily_log_contains(d, (_BUY_BLOCKED_LOG_PATTERN,))
        if blocked_row or blocked_log:
            hits.append(d.isoformat())
    if len(hits) == len(days) and days:
        return (
            f"buy-path blocked streak: {len(hits)} consecutive session day(s) "
            f"ended buy-blocked ({', '.join(hits)}) while exits keep running — "
            f"one-sided book drain risk."
        )
    return None


# ---------------------------------------------------------------------------
# check b: swallowed failures in the daily log
# ---------------------------------------------------------------------------

def _daily_log_contains(day: dt.date, patterns: tuple[str, ...]) -> bool:
    p = Path(DAILY_LOG_DIR) / f"{day.isoformat()}.log"
    if not p.exists():
        return False
    try:
        text = p.read_text(errors="replace")
    except OSError:
        return False
    return any(pat in text for pat in patterns)


def check_traceback_in_daily_log(day: dt.date) -> str | None:
    if _daily_log_contains(day, _TRACEBACK_PATTERNS):
        return (
            f"daily log {day.isoformat()} contains a Traceback / contract-fail "
            f"line ({DAILY_LOG_DIR}/{day.isoformat()}.log) — the run may have "
            f"'succeeded' around a swallowed failure."
        )
    return None


# ---------------------------------------------------------------------------
# check c: launchd job exit statuses
# ---------------------------------------------------------------------------

def parse_launchctl_failures(launchctl_text: str, prefix: str = "com.renquant.") -> list[str]:
    """launchctl list lines: '<pid>\t<status>\t<label>'. A '-' pid means not
    running (normal for calendar jobs); a nonzero status means the LAST exit
    failed. '-' status means never ran since load."""
    failures: list[str] = []
    for line in launchctl_text.splitlines():
        parts = re.split(r"\s+", line.strip())
        if len(parts) != 3:
            continue
        _pid, status, label = parts
        if not label.startswith(prefix):
            continue
        if status not in ("0", "-"):
            failures.append(f"{label} (last exit {status})")
    return failures


ACK_LEDGER = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "sentinel_acks.json")


def load_acks(path: str | None = None) -> dict:
    """Reviewed acknowledgment ledger for KNOWN nonzero last-exits.

    launchctl retains a job's last exit code until its NEXT run, so a fixed
    failure keeps re-alarming for days-to-weeks on low-frequency jobs
    (monthly/weekly/anomaly-triggered). An entry here moves that job's row
    from ALARM to INFO with its disposition; the ledger is a git-tracked,
    review-gated file (same governance as the launchd manifest), and every
    entry carries clears_when so staleness is auditable. An acked job that
    later fails AGAIN still stays INFO until the ack is removed — acks must
    therefore name the specific expected clear event and be pruned at the
    next review touch; the drift scan's job-level checks and the other
    sentinel probes remain independent alarm paths.
    """
    if path is None:
        path = ACK_LEDGER  # resolved at call time (test-patchable)
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def check_launchd_exits() -> tuple[str | None, list[str]]:
    try:
        out = subprocess.run(
            ["launchctl", "list"], capture_output=True, text=True, timeout=30,
        ).stdout
    except Exception as exc:  # noqa: BLE001
        return (f"launchctl list failed ({exc}) — cannot verify job exit statuses", [])
    failures = parse_launchctl_failures(out)
    if not failures:
        return (None, [])
    acks = load_acks()
    infos: list[str] = []
    loud: list[str] = []
    for job in sorted(failures):
        name = job.split(" ")[0]
        ack = acks.get(name)
        if ack:
            infos.append(
                f"acked nonzero exit: {job} — {ack.get('reason', '?')} "
                f"(clears: {ack.get('clears_when', '?')})"
            )
        else:
            loud.append(job)
    alarm = ("launchd job(s) with nonzero last exit: " + ", ".join(loud)) if loud else None
    return (alarm, infos)


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def _open_db_readonly(path: str) -> sqlite3.Connection | None:
    try:
        return sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
    except sqlite3.Error:
        return None


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--as-of", default=None, help="ISO date (default: today)")
    parser.add_argument("--db", default=DB, help="runs DB path (default: prod, read-only)")
    args = parser.parse_args(argv)

    today = dt.date.fromisoformat(args.as_of) if args.as_of else dt.date.today()

    if not is_session_day(today):
        print(f"rq104 degradation sentinel: {today.isoformat()} is not an NYSE session day — skip")
        return 0

    problems: list[str] = []

    conn = _open_db_readonly(args.db)
    if conn is None:
        problems.append(f"runs DB unreadable ({args.db}) — cannot verify run health")
    else:
        days = last_session_days(today, STREAK_N)
        for check in (check_zero_candidate_streak, check_buy_blocked_streak):
            err = check(conn, days)
            if err:
                problems.append(err)
        conn.close()

    err = check_traceback_in_daily_log(today)
    if err:
        problems.append(err)

    err, ack_infos = check_launchd_exits()
    if err:
        problems.append(err)
    for line in ack_infos:
        print(f"INFO: {line}")

    if problems:
        alert(
            f"rq104 DEGRADED: {len(problems)} issue(s) {today.isoformat()}",
            "\n".join(problems),
            rq_root=RQ,
        )
        print("\n".join(problems))
        return 1

    print(f"rq104 degradation sentinel OK {today.isoformat()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
