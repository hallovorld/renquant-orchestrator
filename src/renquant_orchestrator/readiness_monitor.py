"""Automated readiness monitor for data-accumulation gates.

Each accumulation item in the unified master plan (#231) has an acceptance
criterion that depends on elapsed time or accumulated observations. This module
defines each as a programmatic check, runs them against the live DB/filesystem,
and reports a dashboard. State transitions (NOT_READY -> READY) are logged to a
JSON-lines file so downstream automation can trigger the next step.

Read-only: never writes to the DB or production data paths.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from renquant_orchestrator.runtime_paths import default_data_root


class Status(str, Enum):
    READY = "READY"
    NOT_READY = "NOT_READY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: Status
    current: Any
    threshold: Any
    detail: str
    pct: float = 0.0


@dataclass
class ReadinessCheck:
    name: str
    description: str
    check: Callable[..., CheckResult]


def _safe_connect(db_path: Path) -> sqlite3.Connection | None:
    if not db_path.exists():
        return None
    return sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)


# ---------------------------------------------------------------------------
# Individual checks
# ---------------------------------------------------------------------------

def check_pit_snapshots(data_root: Path) -> CheckResult:
    """N2: PIT revision snapshots — need ≥90 consecutive days."""
    name = "N2_pit_snapshots"
    threshold = 90
    snapshot_dir = data_root / "data" / "estimate_snapshots"
    if not snapshot_dir.exists():
        return CheckResult(name, Status.UNKNOWN, 0, threshold,
                           f"snapshot dir not found: {snapshot_dir}")
    days = sorted(
        d.name for d in snapshot_dir.iterdir()
        if d.is_dir() and len(d.name) == 10 and d.name[4] == "-"
    )
    n = len(days)
    status = Status.READY if n >= threshold else Status.NOT_READY
    rng = f"{days[0]}..{days[-1]}" if days else "none"
    return CheckResult(name, status, n, threshold,
                       f"{n} snapshot days ({rng})",
                       pct=min(n / threshold, 1.0) * 100)


def check_pit_features(data_root: Path) -> CheckResult:
    """N2 downstream: C1 revision-drift feature file built from ≥90d snapshots."""
    name = "N2_pit_features"
    threshold = 90
    manifest = data_root / "data" / "pit_features" / "c1_revision_drift.manifest.json"
    if not manifest.exists():
        return CheckResult(name, Status.UNKNOWN, 0, threshold,
                           "manifest not found")
    try:
        m = json.loads(manifest.read_text())
        days = m.get("processed_days", [])
    except (json.JSONDecodeError, KeyError):
        return CheckResult(name, Status.UNKNOWN, 0, threshold,
                           "manifest unreadable")
    n = len(days)
    status = Status.READY if n >= threshold else Status.NOT_READY
    return CheckResult(name, status, n, threshold,
                       f"{n} processed days in manifest",
                       pct=min(n / threshold, 1.0) * 100)


def check_intraday_corpus(data_root: Path) -> CheckResult:
    """N1/S10: intraday quote collector corpus — need tickers × trading days."""
    name = "S10_intraday_corpus"
    threshold_tickers = 100
    intraday_dir = data_root / "data" / "intraday"
    if not intraday_dir.exists():
        return CheckResult(name, Status.UNKNOWN, 0, threshold_tickers,
                           "intraday dir not found")
    tickers = [d.name for d in intraday_dir.iterdir() if d.is_dir()]
    n_tickers = len(tickers)
    status = Status.READY if n_tickers >= threshold_tickers else Status.NOT_READY
    return CheckResult(name, status, n_tickers, threshold_tickers,
                       f"{n_tickers} tickers with intraday data",
                       pct=min(n_tickers / threshold_tickers, 1.0) * 100)


def check_readonly_sessions(data_root: Path) -> CheckResult:
    """M1: 105 Stage-1 readonly sessions — need 5 clean sessions."""
    name = "M1_readonly_sessions"
    threshold = 5
    sessions_dir = data_root / "data" / "105_sessions"
    if not sessions_dir.exists():
        sessions_dir = data_root / "data" / "intraday_sessions"
    if not sessions_dir.exists():
        return CheckResult(name, Status.NOT_READY, 0, threshold,
                           "no session log directory found (Stage-1 not yet started)",
                           pct=0.0)
    session_files = list(sessions_dir.glob("*.json")) + list(sessions_dir.glob("*.jsonl"))
    n = len(session_files)
    status = Status.READY if n >= threshold else Status.NOT_READY
    return CheckResult(name, status, n, threshold,
                       f"{n} session files found",
                       pct=min(n / threshold, 1.0) * 100)


def check_decision_ledger(db_path: Path) -> CheckResult:
    """S5: decision-ledger wiring — need entries written + ≥95% join coverage."""
    name = "S5_decision_ledger"
    threshold_pct = 95.0
    conn = _safe_connect(db_path)
    if conn is None:
        return CheckResult(name, Status.UNKNOWN, 0, threshold_pct,
                           "DB not found")
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        if "decision_ledger" not in tables and "decision_entries" not in tables:
            return CheckResult(name, Status.NOT_READY, 0, threshold_pct,
                               "ledger table not yet created (wiring pending)",
                               pct=0.0)
        table = "decision_entries" if "decision_entries" in tables else "decision_ledger"
        n_entries = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
        if n_entries == 0:
            return CheckResult(name, Status.NOT_READY, 0, threshold_pct,
                               "table exists but empty", pct=0.0)
        n_with_outcome = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE fwd_return IS NOT NULL"  # noqa: S608
        ).fetchone()[0]
        coverage = (n_with_outcome / n_entries * 100) if n_entries > 0 else 0
        status = Status.READY if coverage >= threshold_pct else Status.NOT_READY
        return CheckResult(name, status, round(coverage, 1), threshold_pct,
                           f"{n_entries} entries, {n_with_outcome} with outcomes ({coverage:.1f}%)",
                           pct=min(coverage / threshold_pct, 1.0) * 100)
    finally:
        conn.close()


def check_gate_verdict_freshness(db_path: Path) -> CheckResult:
    """S4/D1: WF-gate verdicts flowing — need a verdict within last 14 days."""
    name = "D1_gate_verdict"
    threshold_days = 14
    conn = _safe_connect(db_path)
    if conn is None:
        return CheckResult(name, Status.UNKNOWN, None, threshold_days,
                           "DB not found")
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        if "gate_verdicts" not in tables:
            return CheckResult(name, Status.UNKNOWN, None, threshold_days,
                               "gate_verdicts table not found")
        row = conn.execute(
            "SELECT MAX(run_date) FROM gate_verdicts"
        ).fetchone()
        if not row or not row[0]:
            return CheckResult(name, Status.NOT_READY, None, threshold_days,
                               "no gate verdicts recorded", pct=0.0)
        last_date = date.fromisoformat(row[0])
        age = (date.today() - last_date).days
        status = Status.READY if age <= threshold_days else Status.NOT_READY
        return CheckResult(name, status, age, threshold_days,
                           f"last verdict {row[0]} ({age}d ago)",
                           pct=max(0, min((threshold_days - age) / threshold_days, 1.0)) * 100)
    finally:
        conn.close()


def check_lambda_sweep(db_path: Path) -> CheckResult:
    """S6: λ sweep experiments — need 3 configs × 15 sessions each = 45 sessions."""
    name = "S6_lambda_sweep"
    threshold_sessions = 45
    conn = _safe_connect(db_path)
    if conn is None:
        return CheckResult(name, Status.UNKNOWN, 0, threshold_sessions,
                           "DB not found")
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()]
        if "config_experiments" not in tables:
            return CheckResult(name, Status.NOT_READY, 0, threshold_sessions,
                               "config_experiments table not created (sweep not started)",
                               pct=0.0)
        n = conn.execute("SELECT COUNT(*) FROM config_experiments").fetchone()[0]
        status = Status.READY if n >= threshold_sessions else Status.NOT_READY
        return CheckResult(name, status, n, threshold_sessions,
                           f"{n}/{threshold_sessions} experiment sessions",
                           pct=min(n / threshold_sessions, 1.0) * 100)
    finally:
        conn.close()


def check_trading_days(db_path: Path) -> CheckResult:
    """Baseline: total live trading days in the DB."""
    name = "baseline_trading_days"
    threshold = 60
    conn = _safe_connect(db_path)
    if conn is None:
        return CheckResult(name, Status.UNKNOWN, 0, threshold, "DB not found")
    try:
        n = conn.execute(
            "SELECT COUNT(DISTINCT run_date) FROM pipeline_runs WHERE run_type='live'"
        ).fetchone()[0]
        status = Status.READY if n >= threshold else Status.NOT_READY
        return CheckResult(name, status, n, threshold,
                           f"{n} live trading days",
                           pct=min(n / threshold, 1.0) * 100)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

ALL_CHECKS: list[ReadinessCheck] = [
    ReadinessCheck("N2_pit_snapshots",
                   "PIT revision snapshots (≥90d for revision-drift features)",
                   check_pit_snapshots),
    ReadinessCheck("N2_pit_features",
                   "C1 revision-drift features built from PIT snapshots",
                   check_pit_features),
    ReadinessCheck("S10_intraday_corpus",
                   "Intraday quote collector corpus (≥100 tickers)",
                   check_intraday_corpus),
    ReadinessCheck("M1_readonly_sessions",
                   "105 Stage-1 readonly sessions (5 clean)",
                   check_readonly_sessions),
    ReadinessCheck("S5_decision_ledger",
                   "Decision-ledger entries with forward-return coverage (≥95%)",
                   check_decision_ledger),
    ReadinessCheck("D1_gate_verdict",
                   "WF-gate verdict freshness (≤14d since last)",
                   check_gate_verdict_freshness),
    ReadinessCheck("S6_lambda_sweep",
                   "λ sweep config experiments (3×15 sessions)",
                   check_lambda_sweep),
    ReadinessCheck("baseline_trading_days",
                   "Total live trading days (≥60 baseline)",
                   check_trading_days),
]


def run_all_checks(
    data_root: Path | None = None,
    db_path: Path | None = None,
) -> list[CheckResult]:
    if data_root is None:
        data_root = default_data_root()
    if db_path is None:
        db_path = data_root / "data" / "runs.alpaca.db"
    results = []
    for rc in ALL_CHECKS:
        try:
            sig = rc.check.__code__.co_varnames[:rc.check.__code__.co_argcount]
            if "db_path" in sig:
                results.append(rc.check(db_path))
            else:
                results.append(rc.check(data_root))
        except Exception as e:
            results.append(CheckResult(rc.name, Status.UNKNOWN, None, None,
                                       f"check failed: {e}"))
    return results


def record_transitions(
    results: list[CheckResult],
    state_file: Path,
) -> list[tuple[str, Status, Status]]:
    """Compare current results against last-known state; log transitions."""
    prev: dict[str, str] = {}
    if state_file.exists():
        try:
            prev = json.loads(state_file.read_text())
        except (json.JSONDecodeError, ValueError):
            pass

    transitions = []
    current: dict[str, str] = {}
    for r in results:
        current[r.name] = r.status.value
        old = prev.get(r.name)
        if old and old != r.status.value:
            transitions.append((r.name, Status(old), r.status))

    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(current, indent=2) + "\n")

    if transitions:
        log_path = state_file.with_suffix(".transitions.jsonl")
        with open(log_path, "a") as f:
            for name, old_s, new_s in transitions:
                entry = {
                    "ts": datetime.utcnow().isoformat() + "Z",
                    "check": name,
                    "from": old_s.value,
                    "to": new_s.value,
                }
                f.write(json.dumps(entry) + "\n")
    return transitions


def _render_table(results: list[CheckResult]) -> str:
    lines = []
    ready = sum(1 for r in results if r.status == Status.READY)
    total = len(results)
    lines.append(f"Readiness: {ready}/{total} checks passing\n")

    name_w = max((len(r.name) for r in results), default=10)
    lines.append(f"{'Check':<{name_w}}  {'Status':>10}  {'Progress':>8}  Detail")
    lines.append("-" * (name_w + 35))

    for r in results:
        icon = {"READY": "+", "NOT_READY": "-", "UNKNOWN": "?"}[r.status.value]
        lines.append(
            f"{r.name:<{name_w}}  [{icon}] {r.status.value:>8}  "
            f"{r.pct:>6.1f}%  {r.detail}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Data-accumulation readiness monitor")
    parser.add_argument("--data-root", type=Path, default=None,
                        help="Override data root (default: auto-detect)")
    parser.add_argument("--db", type=Path, default=None,
                        help="Override DB path")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--state-file", type=Path, default=None,
                        help="Path to persist state for transition detection")
    args = parser.parse_args(argv)

    results = run_all_checks(data_root=args.data_root, db_path=args.db)

    if args.state_file:
        transitions = record_transitions(results, args.state_file)
        if transitions and not args.json:
            for name, old_s, new_s in transitions:
                print(f"  TRANSITION: {name} {old_s.value} -> {new_s.value}")
            print()

    if args.json:
        out = [{"name": r.name, "status": r.status.value, "current": r.current,
                "threshold": r.threshold, "pct": r.pct, "detail": r.detail}
               for r in results]
        json.dump(out, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        print(_render_table(results))

    return 0 if all(r.status == Status.READY for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
