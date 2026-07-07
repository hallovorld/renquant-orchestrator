#!/usr/bin/env python3
"""rq105 status dashboard — one command, full picture.

Usage:
    python ops/renquant105/rq105_status.py
    python -m renquant_orchestrator.rq105_status          # if wired as module

Shows: process health, launchd job states, today's log freshness, batch-scores
availability, quote-logger feed freshness, paper account state, and any errors.
Read-only — touches nothing.

Every check below reuses this repo's existing canonical primitive for that
concern rather than a second, independently-maintained copy — the split-brain
risk this module was blocked on in review: job identity comes from
``scheduled_jobs.scheduled_jobs()``, data-root resolution from
``runtime_paths.default_data_root()``, canonical-run selection from
``tc_measurement._canonical_daily_runs()``, the batch-scores health threshold
from ``export_batch_scores.MIN_ROWS``, and collector-data-output freshness
from ``rq105_liveness_check.check_collector_data_outputs()``.
"""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

_ORCH_SRC = Path(__file__).resolve().parents[2] / "src"
if str(_ORCH_SRC) not in sys.path:
    sys.path.insert(0, str(_ORCH_SRC))

from renquant_orchestrator.runtime_paths import default_data_root  # noqa: E402
from renquant_orchestrator.scheduled_jobs import scheduled_jobs  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_batch_scores import MIN_ROWS  # noqa: E402
from rq105_liveness_check import check_collector_data_outputs  # noqa: E402

RQ_ROOT = default_data_root()
RQ105_DATA = RQ_ROOT / "data" / "rq105"
RQ105_LOGS = RQ_ROOT / "logs" / "rq105"

# job_ids in scheduled_jobs.scheduled_jobs() that make up the rq105 intraday
# pipeline — this is the ONLY place that list is named; everything else
# (launchd label, command, migration state) is read from the registry entry
# itself so it can never drift from what's actually scheduled.
_RQ105_JOB_IDS = (
    "intraday_quote_logger",
    "intraday_session_scheduler",
    "shadow_realtime_serving",
    "intraday_pairing_logger",
    "entry_timing_shadow",
)

OK = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
WARN = "\033[33m!\033[0m"


def _rq105_jobs() -> list:
    """rq105-relevant entries from the canonical scheduled-job registry, in
    ``_RQ105_JOB_IDS`` order. A job_id with no launchd_label (or not present
    in the registry at all) is skipped — this dashboard reports on what the
    registry actually tracks, it does not invent a job that isn't there."""
    by_id = {j.job_id: j for j in scheduled_jobs()}
    return [
        by_id[jid] for jid in _RQ105_JOB_IDS
        if jid in by_id and by_id[jid].launchd_label
    ]


def _launchd_status() -> list[dict]:
    """Parse launchctl list for rq105 jobs, using labels from the canonical
    scheduled_jobs registry (not a second hardcoded label list)."""
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
    for job in _rq105_jobs():
        label = job.launchd_label
        short = job.job_id
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
    """Today's collector data-output freshness, via the SAME per-collector
    freshness-basis logic (row-event-time vs file-mtime) rq105_liveness_check
    itself uses in production — not a second, naive size/mtime check that
    would silently disagree with what actually pages the operator."""
    results = []
    outputs = check_collector_data_outputs(RQ_ROOT, dt.date.today())
    for name, info in outputs.items():
        if info["status"] == "ok":
            results.append({"name": name, "status": "ok (fresh)", "icon": OK})
        else:
            results.append({"name": name, "status": info["reason"] or "stale/missing", "icon": FAIL})

    # session_scheduler / shadow_serving have no data-output freshness check
    # in rq105_liveness_check (that module only covers the three collectors
    # above) — presence/size of today's wrapper log is the only signal
    # available for these two, so it is kept as a simple existence+mtime
    # check rather than invented against a contract that doesn't exist yet.
    for name in ("session_scheduler", "shadow_serving"):
        path = RQ105_LOGS / f"{name}_{today}.log"
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
    """Latest canonical live run and its scored-candidate count, via the
    SAME canonical-run selection tc_measurement uses (one run per run_date,
    max created_at, real completed pipeline_runs row) — not a second,
    subtly-different selection query."""
    import sqlite3

    from renquant_orchestrator.tc_measurement import _canonical_daily_runs

    db_path = RQ_ROOT / "data" / "runs.alpaca.db"
    if not db_path.exists():
        return {"status": "no DB", "icon": FAIL, "detail": ""}
    con = sqlite3.connect(str(db_path))
    try:
        canonical = _canonical_daily_runs(con)
        if not canonical:
            return {"status": "no qualifying runs", "icon": FAIL, "detail": ""}
        latest = canonical[-1]
        row = con.execute(
            "SELECT COUNT(*) FROM candidate_scores "
            "WHERE run_id=? AND role='candidate' AND panel_score IS NOT NULL",
            (latest["run_id"],),
        ).fetchone()
        n = row[0] if row else 0
    finally:
        con.close()
    return {
        "status": f"date={latest['run_date']} scored={n}",
        "icon": OK if n >= MIN_ROWS else WARN,
        "detail": latest["run_id"],
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
    """Scan launchd error logs for recent failures, for whatever rq105 jobs
    the canonical registry currently tracks."""
    errors = []
    for job in _rq105_jobs():
        err_path = job.launchd_stderr_path
        if err_path and Path(err_path).exists() and Path(err_path).stat().st_size > 0:
            lines = Path(err_path).read_text().strip().splitlines()
            if lines:
                errors.append(f"{job.job_id}: {lines[-1][:120]}")
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
