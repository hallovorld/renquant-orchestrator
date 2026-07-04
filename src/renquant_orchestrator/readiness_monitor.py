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
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from renquant_orchestrator.intraday_quote_logger import default_tick_feed_path
from renquant_orchestrator.runtime_paths import default_data_root

_OPS_PIT_DIR = Path(__file__).resolve().parents[2] / "ops" / "pit"


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
    authoritative: bool = True
    """False for progress-only diagnostics that must NOT feed the aggregate
    READY count / exit code — used when no real completion-artifact contract
    exists yet to bind the check to (see S10/M1 below), so the check would
    otherwise look stricter/more authoritative than it actually is."""


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
    """N2: PIT revision snapshots — count of days that PASS the N2
    collector's own 4-endpoint publication contract, reused unchanged from
    ``ops/pit/pit_liveness_check.check_snapshot()`` (the same validator
    ``scripts/kpi_scorecard.py::metric_pit_accrual_days`` uses for the
    D1/D3 accrual metric) — never a bare directory-name count. A directory
    that merely exists (partial write, crashed mid-publish, stale manifest)
    does not count; this is a time-irreversible, never-backfillable source,
    so a false-positive day here can never be corrected later.

    This check's threshold (90) is N2's own local AC, distinct from D3's
    (>=120d, per the KPI scorecard). "Consecutive" was this check's own
    prior (incorrect) framing: the established single-implementation source
    of truth (``metric_pit_accrual_days``) counts total ACCRUED valid days
    plus a separate staleness signal (latest valid day not >3 calendar days
    old) — not an unbroken day-to-day run — so this mirrors that real
    contract rather than inventing a stricter one.
    """
    name = "N2_pit_snapshots"
    threshold = 90
    snapshot_dir = data_root / "data" / "estimate_snapshots"
    if not snapshot_dir.exists():
        return CheckResult(name, Status.UNKNOWN, 0, threshold,
                           f"snapshot dir not found: {snapshot_dir}")

    if str(_OPS_PIT_DIR) not in sys.path:
        sys.path.insert(0, str(_OPS_PIT_DIR))
    import pit_liveness_check as liveness  # noqa: PLC0415

    prev_root = liveness.ROOT
    liveness.ROOT = str(snapshot_dir)
    try:
        pat = re.compile(r"^\d{4}-\d{2}-\d{2}$")
        candidate_dirs = sorted(
            d.name for d in snapshot_dir.iterdir()
            if d.is_dir() and pat.match(d.name)
        )
        valid_days: list[str] = []
        rejected: dict[str, list[str]] = {}
        for d in candidate_dirs:
            problems = liveness.check_snapshot(date.fromisoformat(d))
            if problems:
                rejected[d] = problems
            else:
                valid_days.append(d)
    finally:
        liveness.ROOT = prev_root

    n = len(valid_days)
    latest = valid_days[-1] if valid_days else None
    stale = latest is None or (date.today() - date.fromisoformat(latest)).days > 3
    status = Status.READY if (n >= threshold and not stale) else Status.NOT_READY
    rng = f"{valid_days[0]}..{valid_days[-1]}" if valid_days else "none"
    detail = f"{n} valid snapshot days ({rng})"
    if rejected:
        detail += f", {len(rejected)} rejected as partial/invalid (not counted)"
    if stale and valid_days:
        detail += f", STALE (latest valid day {latest} is >3d old)"
    return CheckResult(name, status, n, threshold, detail,
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
    """N1/S10: intraday quote collector corpus — PROGRESS-ONLY, not
    authoritative.

    Round-3 finding (round 2 only fixed S5/N2): this used to count ticker
    DIRECTORIES under a ``data/intraday/`` tree that the real N1 collector
    (``intraday_quote_logger.py``) never writes to at all — it appends
    ``{date, ticker, ...}`` records to a single rolling JSONL
    (``default_tick_feed_path()``, ``logs/renquant105_pilot/intraday_ticks.jsonl``).
    The old check was silently dead code (always UNKNOWN on a real data
    root), not merely measuring the wrong axis.

    Fixed to read the real feed and report DISTINCT TRADING DAYS accrued —
    the S10 docs (``doc/progress/2026-07-02-s10-open-auction-is.md``) name
    day-accrual, not symbol breadth, as "the binding step" for the S10
    open-auction-IS prize. But there is no fixed ``N_days`` target anywhere
    in the codebase to gate READY/NOT_READY on: the actual power calculation
    (``scripts/s10_open_auction_is_study.py::_cluster_robust_prospective_n_days``)
    is a data-dependent sensitivity table, not a frozen constant, and
    computing it here would require this lightweight filesystem monitor to
    invoke real statistical power analysis over the fill-vs-VWAP corpus —
    out of scope. Per Codex's own explicit fallback ("rename ... and keep
    them out of the authoritative READY count"), this is progress-only:
    reports days + distinct symbols accrued so far, participates in NEITHER
    the READY/total ratio NOR the overall exit code.
    """
    name = "S10_intraday_symbols_present"
    tick_feed = default_tick_feed_path(data_root)
    if not tick_feed.exists():
        return CheckResult(name, Status.UNKNOWN, 0, None,
                           f"tick feed not found: {tick_feed}",
                           authoritative=False)
    days: set[str] = set()
    tickers: set[str] = set()
    with tick_feed.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            d = rec.get("date")
            t = rec.get("ticker")
            if d:
                days.add(str(d))
            if t:
                tickers.add(str(t))
    n_days = len(days)
    n_tickers = len(tickers)
    detail = (
        f"{n_days} distinct trading day(s), {n_tickers} distinct ticker(s) "
        f"in the tick feed — day-accrual (not symbol count) is S10's real "
        f"binding step per doc/progress/2026-07-02-s10-open-auction-is.md; "
        f"no frozen N_days target exists to gate on yet"
    )
    return CheckResult(name, Status.UNKNOWN, n_days, None, detail,
                       authoritative=False)


def check_readonly_sessions(data_root: Path) -> CheckResult:
    """M1: 105 Stage-1 readonly sessions — PROGRESS-ONLY, not authoritative.

    Round-3 finding: this counted raw ``*.json``/``*.jsonl`` session-log
    FILES as if that alone meant "5 clean sessions." The real M1 AC is
    stronger and multi-part — decisions logged, nothing placed, four-class
    replay green on every tick, census complete — and the sharpest
    real evidence contract for it, ``Stage2Authorization``'s
    ``evidence.shadow_sessions_clean``/``evidence.replay_audits_green``
    (``intraday_live_executor.py``), is a SCHEMA VALIDATOR over a
    manually-authored authorization file, not an automated per-session
    verifier — it can only confirm a human's *claim* passes shape/value
    checks, not independently re-derive it from raw session logs.

    The actual per-tick verifier that COULD derive "clean" (four-class
    replay) is ``intraday_replay_audit.replay_session()`` — but it requires
    binding a live tick-runner to the real strategy/data/artifact pipeline
    ("fail closed" per its own docstring) and has no default persisted
    report location (``--report-out`` is optional, operator-chosen); there
    is nothing on disk this lightweight, read-only filesystem monitor can
    safely glob for without invoking that heavy pipeline machinery itself
    (out of scope for this module's own "never invoke the pipeline" scope).

    Per Codex's own explicit fallback ("rename ... and keep them out of the
    authoritative READY count"), this stays a raw file count — genuinely all
    that's cheaply knowable here — but is now clearly labeled as such and
    excluded from the authoritative aggregate.
    """
    name = "M1_session_logs_observed"
    sessions_dir = data_root / "data" / "105_sessions"
    if not sessions_dir.exists():
        sessions_dir = data_root / "data" / "intraday_sessions"
    if not sessions_dir.exists():
        return CheckResult(name, Status.UNKNOWN, 0, None,
                           "no session log directory found (Stage-1 not yet started) "
                           "— NOTE: file presence alone does not mean clean/replay-green",
                           authoritative=False)
    session_files = list(sessions_dir.glob("*.json")) + list(sessions_dir.glob("*.jsonl"))
    n = len(session_files)
    detail = (
        f"{n} session log file(s) found — file presence only; does NOT verify "
        f"decisions-logged/nothing-placed/four-class-replay-green/census-complete "
        f"(the real M1 AC requires intraday_replay_audit against the live pipeline)"
    )
    return CheckResult(name, Status.UNKNOWN, n, None, detail,
                       authoritative=False)


def check_decision_ledger(db_path: Path | None = None) -> CheckResult:
    """S5: decision-ledger wiring — need entries written + >=95% aged
    fwd-outcome join coverage, measured against the real schema
    (``decision_ledger`` + ``decision_outcomes``, ``fwd_5d_ret``/
    ``fwd_20d_ret``/``fwd_60d_ret``) via the single-implementation
    ``ledger_attribution.outcome_coverage()`` query — never a locally
    invented ``decision_entries.fwd_return`` contract.

    Default DB path matches ``decision_ledger.DEFAULT_DB``
    (``~/renquant-data/decision_ledger.db``) — a DIFFERENT file from the
    shared ``runs.alpaca.db`` the other DB-backed checks in this module use;
    pass an explicit ``db_path`` to override (tests do).

    "Aged" = ``as_of`` at least 60 calendar days old (``fwd_60d_ret`` is the
    longest tracked outcome horizon), measured over a rolling 90-day accrual
    window ending at that cutoff. Read-only: unlike
    ``ledger_attribution.connect_attribution()``, this never creates the
    ``decision_outcomes`` table if it's missing — a missing table is
    NOT_READY, matching this module's own never-writes contract.
    """
    from .decision_ledger import DEFAULT_DB as LEDGER_DEFAULT_DB
    from .ledger_attribution import outcome_coverage

    name = "S5_decision_ledger"
    threshold_pct = 95.0
    resolved_db = Path(db_path) if db_path else LEDGER_DEFAULT_DB
    conn = _safe_connect(resolved_db)
    if conn is None:
        return CheckResult(name, Status.UNKNOWN, 0, threshold_pct,
                           "DB not found")
    try:
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
        if "decision_ledger" not in tables:
            return CheckResult(name, Status.NOT_READY, 0, threshold_pct,
                               "decision_ledger table not yet created (wiring pending)",
                               pct=0.0)
        if "decision_outcomes" not in tables:
            return CheckResult(name, Status.NOT_READY, 0, threshold_pct,
                               "decision_ledger exists but decision_outcomes not yet created",
                               pct=0.0)

        aging_days = 60
        window_days = 90
        today = date.today()
        end_date = (today - timedelta(days=aging_days)).isoformat()
        start_date = (today - timedelta(days=aging_days + window_days)).isoformat()

        rows = outcome_coverage(conn, start_date, end_date)
        n_verdicts = sum(r["n_verdicts"] for r in rows)
        n_covered = sum(r["n_covered"] or 0 for r in rows)
        if n_verdicts == 0:
            return CheckResult(name, Status.NOT_READY, 0, threshold_pct,
                               f"no aged (>={aging_days}d) decisions in {start_date}..{end_date}",
                               pct=0.0)
        coverage = n_covered / n_verdicts * 100
        status = Status.READY if coverage >= threshold_pct else Status.NOT_READY
        return CheckResult(name, status, round(coverage, 1), threshold_pct,
                           f"{n_verdicts} aged (as_of,scope,gate) decisions, "
                           f"{n_covered} covered ({coverage:.1f}%) over {start_date}..{end_date}",
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
    ReadinessCheck("S10_intraday_symbols_present",
                   "Intraday tick-feed progress (days/symbols accrued; "
                   "informational, no frozen N_days target yet)",
                   check_intraday_corpus),
    ReadinessCheck("M1_session_logs_observed",
                   "105 Stage-1 session log files present (informational; "
                   "does not verify clean/replay-green)",
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
    ledger_db_path: Path | None = None,
) -> list[CheckResult]:
    if data_root is None:
        data_root = default_data_root()
    if db_path is None:
        db_path = data_root / "data" / "runs.alpaca.db"
    results = []
    for rc in ALL_CHECKS:
        try:
            if rc.check is check_decision_ledger:
                # Separate default DB from the shared runs.alpaca.db — see
                # check_decision_ledger's own docstring.
                results.append(rc.check(ledger_db_path))
                continue
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
    authoritative = [r for r in results if r.authoritative]
    ready = sum(1 for r in authoritative if r.status == Status.READY)
    total = len(authoritative)
    lines.append(f"Readiness: {ready}/{total} authoritative checks passing\n")

    name_w = max((len(r.name) for r in results), default=10)
    lines.append(f"{'Check':<{name_w}}  {'Status':>10}  {'Progress':>8}  Detail")
    lines.append("-" * (name_w + 35))

    for r in results:
        icon = {"READY": "+", "NOT_READY": "-", "UNKNOWN": "?"}[r.status.value]
        tag = "" if r.authoritative else "  [informational — excluded from READY count]"
        lines.append(
            f"{r.name:<{name_w}}  [{icon}] {r.status.value:>8}  "
            f"{r.pct:>6.1f}%  {r.detail}{tag}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Data-accumulation readiness monitor")
    parser.add_argument("--data-root", type=Path, default=None,
                        help="Override data root (default: auto-detect)")
    parser.add_argument("--db", type=Path, default=None,
                        help="Override DB path (runs.alpaca.db-backed checks)")
    parser.add_argument("--ledger-db", type=Path, default=None,
                        help="Override decision-ledger DB path "
                             "(default: decision_ledger.DEFAULT_DB)")
    parser.add_argument("--json", action="store_true", help="JSON output")
    parser.add_argument("--state-file", type=Path, default=None,
                        help="Path to persist state for transition detection")
    args = parser.parse_args(argv)

    results = run_all_checks(data_root=args.data_root, db_path=args.db,
                              ledger_db_path=args.ledger_db)

    if args.state_file:
        transitions = record_transitions(results, args.state_file)
        if transitions and not args.json:
            for name, old_s, new_s in transitions:
                print(f"  TRANSITION: {name} {old_s.value} -> {new_s.value}")
            print()

    if args.json:
        out = [{"name": r.name, "status": r.status.value, "current": r.current,
                "threshold": r.threshold, "pct": r.pct, "detail": r.detail,
                "authoritative": r.authoritative}
               for r in results]
        json.dump(out, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        print(_render_table(results))

    authoritative = [r for r in results if r.authoritative]
    return 0 if all(r.status == Status.READY for r in authoritative) else 1


if __name__ == "__main__":
    sys.exit(main())
