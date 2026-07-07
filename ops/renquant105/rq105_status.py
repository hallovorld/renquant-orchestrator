#!/usr/bin/env python3
"""rq105 status dashboard — one command, full picture.

Usage:
    python ops/renquant105/rq105_status.py

Shows: process health, launchd job states, today's log freshness, batch-scores
availability, quote-logger feed freshness, paper account state, and any errors.
Read-only — touches nothing.

Path resolution uses runtime_paths.default_repo_root (via RQ_ROOT env fallback
for standalone use). Batch-scores threshold imports from export_batch_scores to
stay in sync with the canonical gate.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

# Allow standalone invocation without package install.
_OPS_DIR = Path(__file__).resolve().parent
_SRC_DIR = _OPS_DIR.parent.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))
if str(_OPS_DIR) not in sys.path:
    sys.path.insert(0, str(_OPS_DIR))

from renquant_orchestrator.runtime_paths import default_repo_root  # noqa: E402

try:
    from export_batch_scores import MIN_ROWS as BATCH_MIN_ROWS  # noqa: E402
except ImportError:
    BATCH_MIN_ROWS = 25

LAUNCHD_PREFIX = "com.renquant.rq105-"

OK = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
WARN = "\033[33m!\033[0m"


def _repo_root() -> Path:
    return Path(os.environ.get("RQ_ROOT", str(default_repo_root())))


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
            if label.startswith(LAUNCHD_PREFIX):
                short = label[len(LAUNCHD_PREFIX):]
                jobs[short] = {"pid": pid, "exit": exit_code}
    results = []
    for short, info in sorted(jobs.items()):
        if info["pid"] != "-":
            results.append({"name": short, "status": f"RUNNING (pid {info['pid']})", "icon": OK})
        elif info["exit"] == "0":
            results.append({"name": short, "status": "exited 0", "icon": OK})
        else:
            results.append({"name": short, "status": f"exited {info['exit']}", "icon": FAIL})
    if not results:
        results.append({"name": "(none)", "status": "no rq105 jobs loaded", "icon": FAIL})
    return results


def _today_logs(rq_root: Path, today: str) -> list[dict]:
    """Check today's log files for each component."""
    log_dir = rq_root / "logs" / "rq105"
    checks = [
        "quote_logger",
        "session_scheduler",
        "shadow_serving",
        "entry_timing_shadow",
        "intraday_pairing_logger",
    ]
    results = []
    for name in checks:
        path = log_dir / f"{name}_{today}.log"
        if not path.exists():
            results.append({"name": name, "status": "no log", "icon": WARN})
        else:
            size = path.stat().st_size
            mtime = dt.datetime.fromtimestamp(path.stat().st_mtime)
            age = dt.datetime.now() - mtime
            age_str = (
                f"{int(age.total_seconds() // 60)}min ago"
                if age.total_seconds() < 3600
                else f"{age.total_seconds() / 3600:.1f}h ago"
            )
            if size == 0:
                results.append({"name": name, "status": f"empty ({age_str})", "icon": WARN})
            else:
                results.append({"name": name, "status": f"{size}B ({age_str})", "icon": OK})
    return results


def _batch_scores(rq_root: Path, today: str) -> dict:
    """Check batch scores availability for today."""
    data_dir = rq_root / "data" / "rq105"
    scores_path = data_dir / f"batch_scores_{today}.json"
    meta_path = data_dir / f"batch_scores_{today}.meta.json"
    if not scores_path.exists():
        return {"status": f"no scores for {today}", "icon": FAIL, "detail": ""}
    scores = json.loads(scores_path.read_text())
    detail = f"{len(scores)} tickers"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        detail += f", run={meta.get('run_id', '?')}, coverage={meta.get('coverage', '?')}"
    return {"status": "available", "icon": OK, "detail": detail}


def _db_latest_run(rq_root: Path) -> dict:
    """Check latest live run in DB with scored candidates."""
    db_path = rq_root / "data" / "runs.alpaca.db"
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
        "ORDER BY p.run_date DESC, p.created_at DESC "
        "LIMIT 1",
    ).fetchone()
    con.close()
    if not row:
        return {"status": "no qualifying runs", "icon": FAIL, "detail": ""}
    return {
        "status": f"date={row[1]} scored={row[2]}",
        "icon": OK if row[2] >= BATCH_MIN_ROWS else WARN,
        "detail": row[0],
    }


def _paper_account(rq_root: Path) -> dict:
    """Check paper account from latest session scheduler log."""
    log_dir = rq_root / "logs" / "rq105"
    today = dt.date.today().isoformat()
    log_path = log_dir / f"session_scheduler_{today}.log"
    if not log_path.exists():
        for i in range(1, 5):
            prev = (dt.date.today() - dt.timedelta(days=i)).isoformat()
            alt = log_dir / f"session_scheduler_{prev}.log"
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


def _errors(rq_root: Path) -> list[str]:
    """Scan launchd error logs for recent failures."""
    log_dir = rq_root / "logs" / "rq105"
    errors = []
    for err_file in sorted(log_dir.glob("launchd_*.err")):
        if err_file.stat().st_size > 0:
            name = err_file.stem.replace("launchd_", "")
            lines = err_file.read_text().strip().splitlines()
            if lines:
                errors.append(f"{name}: {lines[-1][:120]}")
    return errors


def main() -> int:
    rq_root = _repo_root()
    today = dt.date.today().isoformat()
    print(f"{'═' * 60}")
    print(f"  rq105 status — {today}")
    print(f"  root: {rq_root}")
    print(f"  batch MIN_ROWS={BATCH_MIN_ROWS}")
    print(f"{'═' * 60}")

    print("\n┌─ launchd jobs")
    for j in _launchd_status():
        print(f"│  {j['icon']} {j['name']:<25} {j['status']}")

    print("│")
    print("├─ today's logs")
    for entry in _today_logs(rq_root, today):
        print(f"│  {entry['icon']} {entry['name']:<25} {entry['status']}")

    print("│")
    print("├─ batch scores")
    bs = _batch_scores(rq_root, today)
    print(f"│  {bs['icon']} {bs['status']}")
    if bs.get("detail"):
        print(f"│    {bs['detail']}")

    print("│")
    print("├─ latest DB run")
    db = _db_latest_run(rq_root)
    print(f"│  {db['icon']} {db['status']}")
    if db.get("detail"):
        print(f"│    {db['detail']}")

    print("│")
    print("├─ paper account")
    pa = _paper_account(rq_root)
    print(f"│  {pa['icon']} {pa['status']}")

    errors = _errors(rq_root)
    if errors:
        print("│")
        print("├─ recent errors")
        for e in errors:
            print(f"│  {FAIL} {e}")

    print(f"{'═' * 60}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
