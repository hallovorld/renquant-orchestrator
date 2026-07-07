#!/usr/bin/env python3
"""rq105 status dashboard — one command, full picture.

Usage:
    python ops/renquant105/rq105_status.py

Shows: process health, launchd job states, today's log freshness, batch-scores
availability, quote-logger feed freshness, paper account state, and any errors.
Read-only — touches nothing.

Path resolution uses runtime_paths.default_data_root — the resolver this repo's
multi-repo migration uses for operator state, decoupled from the umbrella
checkout (honors RENQUANT_DATA_ROOT; falls back to the umbrella root only as
a migration compatibility path, never a first-class default). Batch-scores
threshold imports from export_batch_scores to stay in sync with the canonical
gate. Launchd job identity is derived from scheduled_jobs.py's registry
(filtered to the intraday_session cadence, the native rq105 job set) rather
than a launchctl label-prefix scan, since the wrapper-era `com.renquant.rq105-`
prefix predates the native multirepo launchd labels this repo has migrated
to (e.g. com.renquant.intraday-quote-logger) and would silently miss every
job under the new naming. The "latest DB run" check reuses
export_batch_scores._select_source_run against the same expected prior
session the real exporter checks, instead of a separately-approximated query
that could disagree with the real qualifying-run contract (pipeline_runs
completion, run_type='live', non-empty strategy, MIN_ROWS panel_score rows,
created_at ordering — see that module's docstring for the full history of
why each of those checks exists).
"""
from __future__ import annotations

import datetime as dt
import json
import os
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

from renquant_orchestrator.runtime_paths import default_data_root  # noqa: E402
from renquant_orchestrator.scheduled_jobs import scheduled_jobs  # noqa: E402

try:
    from export_batch_scores import MIN_ROWS as BATCH_MIN_ROWS  # noqa: E402
    from export_batch_scores import _select_source_run  # noqa: E402
    from batch_scores_bundle import expected_previous_session  # noqa: E402
except ImportError:
    BATCH_MIN_ROWS = 25
    _select_source_run = None
    expected_previous_session = None

# The native multirepo launchd labels for rq105's intraday-session jobs,
# derived from the scheduled_jobs registry rather than hardcoded here — this
# stays correct as the registry evolves instead of drifting from it.
_RQ105_CADENCE = "intraday_session"

OK = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
WARN = "\033[33m!\033[0m"


def _repo_root() -> Path:
    return Path(os.environ.get("RENQUANT_DATA_ROOT", str(default_data_root())))


def _rq105_job_labels() -> dict[str, str]:
    """job_id -> launchd_label for the native rq105 intraday-session jobs,
    sourced from the scheduled_jobs registry (the canonical orchestrator
    inventory), not a launchctl label-prefix scan."""
    return {
        job.job_id: job.launchd_label
        for job in scheduled_jobs()
        if job.cadence == _RQ105_CADENCE and job.launchd_label
    }


def _launchd_status() -> list[dict]:
    """Check launchctl state for the registry's rq105 intraday-session jobs."""
    expected = _rq105_job_labels()
    try:
        raw = subprocess.check_output(
            ["launchctl", "list"], text=True, stderr=subprocess.DEVNULL,
        )
    except Exception:
        raw = ""
    loaded = {}
    for line in raw.strip().splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) >= 3:
            pid, exit_code, label = parts[0], parts[1], parts[2]
            loaded[label] = {"pid": pid, "exit": exit_code}
    results = []
    for job_id, label in sorted(expected.items()):
        info = loaded.get(label)
        if info is None:
            results.append({"name": job_id, "status": "not loaded", "icon": FAIL})
        elif info["pid"] != "-":
            results.append({"name": job_id, "status": f"RUNNING (pid {info['pid']})", "icon": OK})
        elif info["exit"] == "0":
            results.append({"name": job_id, "status": "exited 0", "icon": OK})
        else:
            results.append({"name": job_id, "status": f"exited {info['exit']}", "icon": FAIL})
    if not results:
        results.append({"name": "(none)", "status": "no rq105 jobs in registry", "icon": FAIL})
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
    """Check the canonical qualifying run for the exporter's expected prior
    session, reusing export_batch_scores._select_source_run — the real
    exporter contract (pipeline_runs completion, run_type='live', non-empty
    strategy, MIN_ROWS panel_score rows, created_at ordering) — rather than a
    dashboard-local approximation that could disagree with it."""
    db_path = rq_root / "data" / "runs.alpaca.db"
    if not db_path.exists():
        return {"status": "no DB", "icon": FAIL, "detail": ""}
    if _select_source_run is None or expected_previous_session is None:
        return {"status": "export_batch_scores unavailable", "icon": FAIL, "detail": ""}
    import sqlite3 as _sqlite3  # noqa: PLC0415 — keep top-level import list free of DB-only need

    con = _sqlite3.connect(str(db_path))
    try:
        expected_date = expected_previous_session(dt.date.today().isoformat())
        result = _select_source_run(con, expected_date)
    finally:
        con.close()
    if not result:
        return {
            "status": f"no qualifying run for {expected_date}",
            "icon": FAIL,
            "detail": "",
        }
    run_id, run_date, _run_bundle = result
    return {
        "status": f"date={run_date}",
        "icon": OK,
        "detail": run_id,
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
