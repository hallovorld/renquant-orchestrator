#!/usr/bin/env python3
"""rq105 status dashboard — one command, full picture.

Usage:
    python ops/renquant105/rq105_status.py
    python -m renquant_orchestrator.rq105_status          # if wired as module

Shows: process health, launchd job states, today's log freshness, batch-scores
availability, quote-logger feed freshness, paper account state, and any errors.
Read-only — touches nothing.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

RQ_ROOT = Path(os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant"))
RQ105_DATA = RQ_ROOT / "data" / "rq105"
RQ105_LOGS = RQ_ROOT / "logs" / "rq105"

LAUNCHD_JOBS = [
    "com.renquant.rq105-quote-logger",
    "com.renquant.rq105-session-scheduler",
    "com.renquant.rq105-batch-scores-export",
    "com.renquant.rq105-shadow-serving",
    "com.renquant.rq105-postclose",
    "com.renquant.rq105-liveness",
]

OK = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
WARN = "\033[33m!\033[0m"


def _launchd_status() -> list[dict]:
    """Parse launchctl list for rq105 jobs."""
    try:
        raw = subprocess.check_output(
            ["launchctl", "list"], text=True, stderr=subprocess.DEVNULL,
        )
    except Exception:
        return []
    jobs = {}
    for line in raw.strip().splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) >= 3:
            pid, exit_code, label = parts[0], parts[1], parts[2]
            jobs[label] = {"pid": pid, "exit": exit_code}
    results = []
    for label in LAUNCHD_JOBS:
        short = label.replace("com.renquant.rq105-", "")
        info = jobs.get(label)
        if not info:
            results.append({"name": short, "status": "NOT LOADED", "icon": FAIL})
        elif info["pid"] != "-":
            results.append({"name": short, "status": f"RUNNING (pid {info['pid']})", "icon": OK})
        elif info["exit"] == "0":
            results.append({"name": short, "status": "exited 0", "icon": OK})
        else:
            results.append({"name": short, "status": f"exited {info['exit']}", "icon": FAIL})
    return results


def _today_logs(today: str) -> list[dict]:
    """Check today's log files for each component."""
    checks = [
        ("quote_logger", RQ105_LOGS / f"quote_logger_{today}.log"),
        ("session_scheduler", RQ105_LOGS / f"session_scheduler_{today}.log"),
        ("shadow_serving", RQ105_LOGS / f"shadow_serving_{today}.log"),
        ("entry_timing", RQ105_LOGS / f"entry_timing_shadow_{today}.log"),
        ("pairing_logger", RQ105_LOGS / f"intraday_pairing_logger_{today}.log"),
    ]
    results = []
    for name, path in checks:
        if not path.exists():
            results.append({"name": name, "status": "no log", "icon": WARN})
        else:
            size = path.stat().st_size
            mtime = dt.datetime.fromtimestamp(path.stat().st_mtime)
            age = dt.datetime.now() - mtime
            age_str = f"{int(age.total_seconds() // 60)}min ago" if age.total_seconds() < 3600 else f"{age.total_seconds() / 3600:.1f}h ago"
            if size == 0:
                results.append({"name": name, "status": f"empty ({age_str})", "icon": WARN})
            else:
                results.append({"name": name, "status": f"{size}B ({age_str})", "icon": OK})
    return results


def _batch_scores(today: str) -> dict:
    """Check batch scores availability for today."""
    scores_path = RQ105_DATA / f"batch_scores_{today}.json"
    meta_path = RQ105_DATA / f"batch_scores_{today}.meta.json"
    if not scores_path.exists():
        return {"status": f"no scores for {today}", "icon": FAIL, "detail": ""}
    scores = json.loads(scores_path.read_text())
    detail = f"{len(scores)} tickers"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        detail += f", run={meta.get('run_id', '?')}, coverage={meta.get('coverage', '?')}"
    return {"status": "available", "icon": OK, "detail": detail}


def _db_latest_run() -> dict:
    """Check latest live run in DB with scored candidates."""
    db_path = RQ_ROOT / "data" / "runs.alpaca.db"
    if not db_path.exists():
        return {"status": "no DB", "icon": FAIL, "detail": ""}
    con = sqlite3.connect(str(db_path))
    row = con.execute(
        "SELECT p.run_id, p.run_date, COUNT(cs.ticker) as n "
        "FROM pipeline_runs p "
        "JOIN candidate_scores cs ON cs.run_id = p.run_id "
        "  AND cs.role = 'candidate' AND cs.panel_score IS NOT NULL "
        "WHERE p.run_type = 'live' "
        "GROUP BY p.run_id "
        "ORDER BY p.run_date DESC, n DESC "
        "LIMIT 1",
    ).fetchone()
    con.close()
    if not row:
        return {"status": "no qualifying runs", "icon": FAIL, "detail": ""}
    return {
        "status": f"date={row[1]} scored={row[2]}",
        "icon": OK if row[2] >= 30 else WARN,
        "detail": row[0],
    }


def _paper_account() -> dict:
    """Check paper account from latest session scheduler log."""
    today = dt.date.today().isoformat()
    log_path = RQ105_LOGS / f"session_scheduler_{today}.log"
    if not log_path.exists():
        for i in range(1, 5):
            prev = (dt.date.today() - dt.timedelta(days=i)).isoformat()
            alt = RQ105_LOGS / f"session_scheduler_{prev}.log"
            if alt.exists():
                log_path = alt
                break
    if not log_path.exists():
        return {"status": "no scheduler log", "icon": WARN}
    text = log_path.read_text()
    for line in reversed(text.splitlines()):
        if "cash=$" in line:
            start = line.index("cash=$")
            end = line.index(")", start) if ")" in line[start:] else len(line)
            return {"status": line[start:end], "icon": OK}
    return {"status": "no cash info", "icon": WARN}


def _errors() -> list[str]:
    """Scan launchd error logs for recent failures."""
    errors = []
    for name in ["batch-scores-export", "shadow-serving", "liveness", "session-scheduler"]:
        err_path = RQ105_LOGS / f"launchd_{name}.err"
        if err_path.exists() and err_path.stat().st_size > 0:
            lines = err_path.read_text().strip().splitlines()
            if lines:
                errors.append(f"{name}: {lines[-1][:120]}")
    return errors


def main() -> int:
    today = dt.date.today().isoformat()
    print(f"{'═' * 60}")
    print(f"  rq105 status — {today}")
    print(f"{'═' * 60}")

    print("\n┌─ launchd jobs")
    for j in _launchd_status():
        print(f"│  {j['icon']} {j['name']:<25} {j['status']}")

    print("│")
    print("├─ today's logs")
    for l in _today_logs(today):
        print(f"│  {l['icon']} {l['name']:<25} {l['status']}")

    print("│")
    print("├─ batch scores")
    bs = _batch_scores(today)
    print(f"│  {bs['icon']} {bs['status']}")
    if bs.get("detail"):
        print(f"│    {bs['detail']}")

    print("│")
    print("├─ latest DB run")
    db = _db_latest_run()
    print(f"│  {db['icon']} {db['status']}")
    if db.get("detail"):
        print(f"│    {db['detail']}")

    print("│")
    print("├─ paper account")
    pa = _paper_account()
    print(f"│  {pa['icon']} {pa['status']}")

    errors = _errors()
    if errors:
        print("│")
        print("├─ recent errors")
        for e in errors:
            print(f"│  {FAIL} {e}")

    print(f"{'═' * 60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
