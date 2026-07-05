"""M5 Tournament Retirement — shadow admission logger.

Logs BOTH per-ticker tournament and panel admission verdicts in parallel so
the two paths can be compared over >= 20 sessions before permanently removing
the tournament gate.

Background: ``bypass_ticker_gate = true`` already lets the panel path rank
directly, but the tournament's ``ScoreBuyTask`` + ``ScoreThresholdTask`` still
compute and record scores even in bypass mode.  This module captures the
admission verdict from BOTH paths per run, enabling a quantitative delta
report before the tournament code is retired.

Output: one JSON-lines record per daily run appended to
``data/shadow/tournament_vs_panel_admission.jsonl`` (NOT a production path --
``data/shadow/`` is explicitly non-canonical and safe for observability writes).

SAFETY:
  - Default OFF (``enabled`` must be explicitly true in config or env).
  - Fail-open: any error is logged and swallowed; the pipeline continues.
  - No orders, no production writes, no model changes.
  - No git operations on any live tree.
"""
from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

log = logging.getLogger("renquant_orchestrator.tournament_shadow_admission")

# Schema version for the JSONL records -- bump on breaking layout changes.
SCHEMA_VERSION = 1

# Default output path (relative to the strategy/umbrella root).
DEFAULT_SHADOW_DIR = "data/shadow"
DEFAULT_LOG_FILENAME = "tournament_vs_panel_admission.jsonl"

# Minimum sample size for a retirement decision. This applies to the
# ADMISSION-RELEVANT subset (sessions where at least one path admitted a
# ticker), not the total calendar session count -- the effective sample
# size for this experiment is the former, since sessions where both paths
# trivially reject everything carry no information about whether the two
# paths agree on the names that matter.
MIN_ADMISSION_RELEVANT_SESSIONS = 20


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TickerAdmission:
    """Single-ticker admission verdict under one path."""

    ticker: str
    admitted: bool
    blocked_by: str | None = None
    raw_score: float | None = None
    rank_score: float | None = None
    signal: str | None = None


@dataclass(frozen=True)
class SessionRecord:
    """One daily session's paired tournament-vs-panel admission log."""

    schema_version: int
    run_date: str                          # ISO date of the pipeline run
    logged_at: str                         # wall-clock timestamp
    bypass_ticker_gate: bool               # current config state
    n_watchlist: int                       # total tickers considered
    tournament_admitted: list[str]         # tickers the tournament would admit
    tournament_rejected: list[str]         # tickers the tournament would reject
    panel_admitted: list[str]              # tickers the panel path admits
    panel_rejected: list[str]             # tickers the panel path rejects
    agreed_admit: list[str]               # both paths admit
    agreed_reject: list[str]              # both paths reject
    tournament_only: list[str]            # tournament admits, panel rejects
    panel_only: list[str]                 # panel admits, tournament rejects
    agreement_rate: float                 # whole-watchlist agreement — CONTEXT
                                           # ONLY. Dominated by trivial
                                           # both-reject names; not the
                                           # retirement-decision signal. See
                                           # ``conditional_agreement_rate``.
    conditional_agreement_rate: float | None
    # Jaccard overlap of the two paths' ADMITTED sets: |agreed_admit| /
    # |tournament_admitted ∪ panel_admitted|. Restricted to the
    # admission-relevant subset (names at least one path would admit), so
    # it cannot be inflated by names both paths trivially reject. This is
    # the decision-grade redundancy signal. None when neither path admitted
    # anything this session (no admission-relevant subset to measure).
    admission_precision: float | None
    # Of tournament-admitted names, fraction panel also admits. None when
    # tournament admitted nothing this session.
    admission_recall: float | None
    # Of panel-admitted names, fraction tournament also admits. None when
    # panel admitted nothing this session.
    tournament_details: list[dict]        # per-ticker TickerAdmission dicts
    panel_details: list[dict]             # per-ticker TickerAdmission dicts
    regime: str | None = None
    min_model_score: float | None = None  # the regime threshold used


# ---------------------------------------------------------------------------
# Tournament-path gate logic (replay)
# ---------------------------------------------------------------------------

def _tournament_would_admit(
    ticker: str,
    signal: str | None,
    raw_score: float | None,
    rank_score: float | None,
    min_model_score: float,
) -> TickerAdmission:
    """Evaluate whether the per-ticker tournament gates would admit a ticker.

    Replays the logic of ``ScoreBuyTask`` + ``ScoreThresholdTask`` from
    ``kernel/pipeline/task_candidates.py`` with ``bypass_ticker_gate = false``.
    """
    # ScoreBuyTask gate: signal must be "buy"
    if signal is None:
        return TickerAdmission(
            ticker=ticker, admitted=False, blocked_by="no_model_signal",
            raw_score=raw_score, rank_score=rank_score, signal=signal,
        )
    if signal != "buy":
        return TickerAdmission(
            ticker=ticker, admitted=False, blocked_by=f"model_signal:{signal}",
            raw_score=raw_score, rank_score=rank_score, signal=signal,
        )

    # ScoreThresholdTask gate: rank_score >= min_model_score
    if rank_score is None or not math.isfinite(rank_score):
        return TickerAdmission(
            ticker=ticker, admitted=False, blocked_by="rank_below_min",
            raw_score=raw_score, rank_score=rank_score, signal=signal,
        )
    if rank_score < min_model_score:
        return TickerAdmission(
            ticker=ticker, admitted=False, blocked_by="rank_below_min",
            raw_score=raw_score, rank_score=rank_score, signal=signal,
        )

    return TickerAdmission(
        ticker=ticker, admitted=True,
        raw_score=raw_score, rank_score=rank_score, signal=signal,
    )


# ---------------------------------------------------------------------------
# Panel-path gate logic (observed)
# ---------------------------------------------------------------------------

def _panel_admission(
    ticker: str,
    is_candidate: bool,
    blocked_by: str | None,
    rank_score: float | None,
) -> TickerAdmission:
    """Record the panel path's observed admission for one ticker.

    In the panel path, a ticker is admitted if it survived through the
    pipeline into ``ctx.candidates`` (i.e., was not blocked by
    ``VetoWeakBuysTask``, ``RegimeModelAdmissionTask``, or other panel gates).
    """
    return TickerAdmission(
        ticker=ticker,
        admitted=is_candidate,
        blocked_by=blocked_by if not is_candidate else None,
        rank_score=rank_score,
    )


# ---------------------------------------------------------------------------
# Session evaluation
# ---------------------------------------------------------------------------

def evaluate_session(
    *,
    run_date: date,
    watchlist: Sequence[str],
    ticker_scores: Mapping[str, Mapping[str, Any]],
    panel_candidates: Sequence[str],
    panel_blocked: Mapping[str, str],
    min_model_score: float,
    bypass_ticker_gate: bool,
    regime: str | None = None,
) -> SessionRecord:
    """Evaluate both admission paths for one daily session.

    Parameters
    ----------
    run_date : date
        The pipeline bar date.
    watchlist : sequence of str
        All tickers in the configured watchlist for this run.
    ticker_scores : mapping
        Per-ticker scoring data.  Each value should be a dict with keys:
        ``signal`` (str | None), ``raw_score`` (float | None),
        ``rank_score`` (float | None).  Tickers absent from this mapping
        are treated as having no model (blocked upstream).
    panel_candidates : sequence of str
        Tickers that survived through the panel admission path.
    panel_blocked : mapping
        Tickers blocked by the panel path, keyed by ticker with value =
        the blocking reason.
    min_model_score : float
        The ``regime_params.min_model_score`` threshold used by the
        tournament's ``ScoreThresholdTask``.
    bypass_ticker_gate : bool
        Current state of ``ranking.panel_scoring.bypass_ticker_gate``.
    regime : str or None
        Current regime label.

    Returns
    -------
    SessionRecord
    """
    panel_candidate_set = set(panel_candidates)
    tournament_details: list[TickerAdmission] = []
    panel_details: list[TickerAdmission] = []

    for ticker in sorted(watchlist):
        scores = ticker_scores.get(ticker, {})
        signal = scores.get("signal")
        raw_score = scores.get("raw_score")
        rank_score = scores.get("rank_score")

        # Tournament path replay
        if ticker not in ticker_scores:
            tournament_details.append(TickerAdmission(
                ticker=ticker, admitted=False,
                blocked_by="no_model_data",
            ))
        else:
            tournament_details.append(_tournament_would_admit(
                ticker, signal, raw_score, rank_score, min_model_score,
            ))

        # Panel path observation
        panel_details.append(_panel_admission(
            ticker=ticker,
            is_candidate=ticker in panel_candidate_set,
            blocked_by=panel_blocked.get(ticker),
            rank_score=rank_score,
        ))

    # Compute sets
    tourn_admitted = {a.ticker for a in tournament_details if a.admitted}
    tourn_rejected = {a.ticker for a in tournament_details if not a.admitted}
    panel_admit_set = {a.ticker for a in panel_details if a.admitted}
    panel_reject_set = {a.ticker for a in panel_details if not a.admitted}

    agreed_admit = sorted(tourn_admitted & panel_admit_set)
    agreed_reject = sorted(tourn_rejected & panel_reject_set)
    tournament_only = sorted(tourn_admitted - panel_admit_set)
    panel_only = sorted(panel_admit_set - tourn_admitted)

    n = len(watchlist) if watchlist else 1
    agreement_rate = (len(agreed_admit) + len(agreed_reject)) / n

    admission_relevant = tourn_admitted | panel_admit_set
    conditional_agreement_rate = (
        round(len(agreed_admit) / len(admission_relevant), 4)
        if admission_relevant else None
    )
    admission_precision = (
        round(len(agreed_admit) / len(tourn_admitted), 4)
        if tourn_admitted else None
    )
    admission_recall = (
        round(len(agreed_admit) / len(panel_admit_set), 4)
        if panel_admit_set else None
    )

    return SessionRecord(
        schema_version=SCHEMA_VERSION,
        run_date=run_date.isoformat(),
        logged_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        bypass_ticker_gate=bypass_ticker_gate,
        n_watchlist=len(watchlist),
        tournament_admitted=sorted(tourn_admitted),
        tournament_rejected=sorted(tourn_rejected),
        panel_admitted=sorted(panel_admit_set),
        panel_rejected=sorted(panel_reject_set),
        agreed_admit=agreed_admit,
        agreed_reject=agreed_reject,
        tournament_only=tournament_only,
        panel_only=panel_only,
        agreement_rate=round(agreement_rate, 4),
        conditional_agreement_rate=conditional_agreement_rate,
        admission_precision=admission_precision,
        admission_recall=admission_recall,
        tournament_details=[asdict(d) for d in tournament_details],
        panel_details=[asdict(d) for d in panel_details],
        regime=regime,
        min_model_score=min_model_score,
    )


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def append_record(record: SessionRecord, log_path: Path) -> Path:
    """Append a SessionRecord as one JSON line.  Creates parent dirs."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(record), default=str) + "\n")
    return log_path


def read_records(log_path: Path) -> list[dict]:
    """Read all JSON-lines records from the shadow log."""
    if not log_path.exists():
        return []
    records: list[dict] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                log.warning("Skipping malformed line in %s", log_path)
    return records


# ---------------------------------------------------------------------------
# Top-level entry point (fail-open)
# ---------------------------------------------------------------------------

def log_shadow_admission(
    *,
    run_date: date,
    watchlist: Sequence[str],
    ticker_scores: Mapping[str, Mapping[str, Any]],
    panel_candidates: Sequence[str],
    panel_blocked: Mapping[str, str],
    min_model_score: float,
    bypass_ticker_gate: bool,
    regime: str | None = None,
    shadow_dir: str | Path | None = None,
    log_filename: str = DEFAULT_LOG_FILENAME,
    enabled: bool | None = None,
) -> SessionRecord | None:
    """Evaluate and persist one session's shadow admission log.

    Fail-open: any error is caught and logged; returns None on failure.
    Returns the SessionRecord on success.

    Parameters
    ----------
    enabled : bool or None
        When None, checks env var ``RQ_TOURNAMENT_SHADOW_ENABLED``.
        Must be explicitly true to log.
    shadow_dir : str or Path or None
        Directory to write the JSONL log into.  When None, uses
        ``DEFAULT_SHADOW_DIR`` (relative CWD).
    """
    if enabled is None:
        enabled = os.environ.get("RQ_TOURNAMENT_SHADOW_ENABLED", "").lower() in (
            "1", "true", "yes",
        )
    if not enabled:
        return None

    try:
        record = evaluate_session(
            run_date=run_date,
            watchlist=watchlist,
            ticker_scores=ticker_scores,
            panel_candidates=panel_candidates,
            panel_blocked=panel_blocked,
            min_model_score=min_model_score,
            bypass_ticker_gate=bypass_ticker_gate,
            regime=regime,
        )
        out_dir = Path(shadow_dir) if shadow_dir else Path(DEFAULT_SHADOW_DIR)
        log_path = out_dir / log_filename
        append_record(record, log_path)
        log.info(
            "tournament_shadow_admission: logged session %s "
            "(agreement=%.1f%%, tourn_only=%d, panel_only=%d)",
            run_date.isoformat(),
            record.agreement_rate * 100,
            len(record.tournament_only),
            len(record.panel_only),
        )
        return record
    except Exception:
        log.exception("tournament_shadow_admission: FAILED (fail-open, pipeline continues)")
        return None


# ---------------------------------------------------------------------------
# Delta report
# ---------------------------------------------------------------------------

@dataclass
class DeltaReport:
    """Aggregated delta report across multiple sessions."""

    n_sessions: int
    date_range: tuple[str, str]
    mean_agreement_rate: float             # whole-watchlist — CONTEXT ONLY
    median_agreement_rate: float
    min_agreement_rate: float
    max_agreement_rate: float
    # Admission-relevant (Jaccard) agreement — the retirement DECISION
    # signal. None fields below when no session had any admission-relevant
    # activity to measure (n_sessions_admission_relevant == 0).
    mean_conditional_agreement_rate: float | None
    median_conditional_agreement_rate: float | None
    min_conditional_agreement_rate: float | None
    max_conditional_agreement_rate: float | None
    n_sessions_admission_relevant: int
    mean_admission_precision: float | None
    mean_admission_recall: float | None
    total_tickers_evaluated: int
    mean_tournament_admitted: float
    mean_panel_admitted: float
    # Names that appear in tournament_only or panel_only across sessions
    chronic_tournament_only: dict[str, int]   # ticker -> count
    chronic_panel_only: dict[str, int]        # ticker -> count
    # Per-session summaries
    per_session: list[dict]
    recommendation: str


def generate_delta_report(records: list[dict]) -> DeltaReport:
    """Analyze shadow log records and generate a migration readiness report.

    Parameters
    ----------
    records : list of dict
        Parsed JSONL records from ``read_records``.

    Returns
    -------
    DeltaReport
    """
    if not records:
        return DeltaReport(
            n_sessions=0,
            date_range=("", ""),
            mean_agreement_rate=0.0,
            median_agreement_rate=0.0,
            min_agreement_rate=0.0,
            max_agreement_rate=0.0,
            mean_conditional_agreement_rate=None,
            median_conditional_agreement_rate=None,
            min_conditional_agreement_rate=None,
            max_conditional_agreement_rate=None,
            n_sessions_admission_relevant=0,
            mean_admission_precision=None,
            mean_admission_recall=None,
            total_tickers_evaluated=0,
            mean_tournament_admitted=0.0,
            mean_panel_admitted=0.0,
            chronic_tournament_only={},
            chronic_panel_only={},
            per_session=[],
            recommendation=(
                f"Insufficient data (0 sessions). "
                f"Need >= {MIN_ADMISSION_RELEVANT_SESSIONS} sessions."
            ),
        )

    dates = sorted(r.get("run_date", "") for r in records)
    agreement_rates = [float(r.get("agreement_rate", 0)) for r in records]
    tourn_admitted_counts = [len(r.get("tournament_admitted", [])) for r in records]
    panel_admitted_counts = [len(r.get("panel_admitted", [])) for r in records]

    conditional_rates = [
        r["conditional_agreement_rate"] for r in records
        if r.get("conditional_agreement_rate") is not None
    ]
    precisions = [
        r["admission_precision"] for r in records
        if r.get("admission_precision") is not None
    ]
    recalls = [
        r["admission_recall"] for r in records
        if r.get("admission_recall") is not None
    ]
    n_relevant = len(conditional_rates)

    # Chronic disagreements
    chronic_tourn: dict[str, int] = {}
    chronic_panel: dict[str, int] = {}
    per_session: list[dict] = []

    for r in records:
        for t in r.get("tournament_only", []):
            chronic_tourn[t] = chronic_tourn.get(t, 0) + 1
        for t in r.get("panel_only", []):
            chronic_panel[t] = chronic_panel.get(t, 0) + 1
        per_session.append({
            "date": r.get("run_date"),
            "regime": r.get("regime"),
            "agreement_rate": r.get("agreement_rate"),
            "n_watchlist": r.get("n_watchlist"),
            "tournament_admitted": len(r.get("tournament_admitted", [])),
            "panel_admitted": len(r.get("panel_admitted", [])),
            "tournament_only": r.get("tournament_only", []),
            "panel_only": r.get("panel_only", []),
        })

    n = len(records)
    sorted_rates = sorted(agreement_rates)
    median_rate = sorted_rates[n // 2] if n % 2 else (
        sorted_rates[n // 2 - 1] + sorted_rates[n // 2]
    ) / 2

    mean_agreement = sum(agreement_rates) / n
    mean_tourn = sum(tourn_admitted_counts) / n
    mean_panel = sum(panel_admitted_counts) / n

    def _mean(xs: list[float]) -> float | None:
        return round(sum(xs) / len(xs), 4) if xs else None

    def _median(xs: list[float]) -> float | None:
        if not xs:
            return None
        s = sorted(xs)
        m = len(s)
        return s[m // 2] if m % 2 else (s[m // 2 - 1] + s[m // 2]) / 2

    mean_conditional = _mean(conditional_rates)
    median_conditional = _median(conditional_rates)
    min_conditional = round(min(conditional_rates), 4) if conditional_rates else None
    max_conditional = round(max(conditional_rates), 4) if conditional_rates else None
    mean_precision = _mean(precisions)
    mean_recall = _mean(recalls)

    # Generate recommendation — driven by conditional_agreement_rate (the
    # admission-relevant subset), NOT the whole-watchlist agreement_rate,
    # which is dominated by trivial both-reject names and can look
    # comfortingly high even when the paths materially disagree on the
    # names that actually matter for the retirement decision.
    if n < MIN_ADMISSION_RELEVANT_SESSIONS:
        recommendation = (
            f"Insufficient data ({n} sessions). "
            f"Need >= {MIN_ADMISSION_RELEVANT_SESSIONS} sessions before making a retirement decision."
        )
    elif n_relevant == 0:
        recommendation = (
            f"CANNOT ASSESS. Across {n} sessions, neither path ever admitted "
            f"a ticker, so there is no admission-relevant subset to compare "
            f"— redundancy cannot be evaluated from this data."
        )
    elif n_relevant < MIN_ADMISSION_RELEVANT_SESSIONS:
        recommendation = (
            f"INSUFFICIENT ADMISSION-RELEVANT SAMPLE. Only {n_relevant} of "
            f"{n} sessions had any admission activity under either path — "
            f"the effective sample size for this retirement decision is the "
            f"admission-relevant subset, not the total calendar count. Need "
            f">= {MIN_ADMISSION_RELEVANT_SESSIONS} admission-relevant "
            f"sessions before making a retirement decision, regardless of "
            f"how many total sessions have been observed."
        )
    elif mean_conditional >= 0.95:
        recommendation = (
            f"READY for permanent bypass. Admission-relevant agreement "
            f"{mean_conditional:.1%} across {n_relevant} session(s) with "
            f"admission activity (of {n} total) is >= 95%. The tournament "
            f"gate adds no differentiation beyond what the panel path "
            f"already provides on the names that matter."
        )
    elif mean_conditional >= 0.85:
        chronic_count = len(chronic_tourn) + len(chronic_panel)
        recommendation = (
            f"LIKELY READY with caveats. Admission-relevant agreement "
            f"{mean_conditional:.1%} across {n_relevant} session(s) with "
            f"admission activity (of {n} total). {chronic_count} chronic "
            f"disagreement ticker(s). Review chronic_tournament_only and "
            f"chronic_panel_only for names where the paths structurally "
            f"disagree."
        )
    else:
        recommendation = (
            f"NOT READY. Admission-relevant agreement {mean_conditional:.1%} "
            f"across {n_relevant} session(s) with admission activity (of "
            f"{n} total) is < 85%. The two paths still produce materially "
            f"different admission sets on the names that matter. "
            f"Investigate structural disagreements before retiring the "
            f"tournament. (Whole-watchlist agreement {mean_agreement:.1%} "
            f"is context only — do not use it for this decision.)"
        )

    return DeltaReport(
        n_sessions=n,
        date_range=(dates[0], dates[-1]),
        mean_agreement_rate=round(mean_agreement, 4),
        median_agreement_rate=round(median_rate, 4),
        min_agreement_rate=round(min(agreement_rates), 4),
        max_agreement_rate=round(max(agreement_rates), 4),
        mean_conditional_agreement_rate=mean_conditional,
        median_conditional_agreement_rate=median_conditional,
        min_conditional_agreement_rate=min_conditional,
        max_conditional_agreement_rate=max_conditional,
        n_sessions_admission_relevant=n_relevant,
        mean_admission_precision=mean_precision,
        mean_admission_recall=mean_recall,
        total_tickers_evaluated=sum(r.get("n_watchlist", 0) for r in records),
        mean_tournament_admitted=round(mean_tourn, 2),
        mean_panel_admitted=round(mean_panel, 2),
        chronic_tournament_only=dict(sorted(
            chronic_tourn.items(), key=lambda x: -x[1],
        )),
        chronic_panel_only=dict(sorted(
            chronic_panel.items(), key=lambda x: -x[1],
        )),
        per_session=per_session,
        recommendation=recommendation,
    )


def format_delta_report(report: DeltaReport) -> str:
    """Format a DeltaReport as human-readable text."""
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("  Tournament vs Panel Admission — Delta Report")
    lines.append("=" * 72)
    lines.append("")
    lines.append(f"Sessions analyzed:   {report.n_sessions}")
    lines.append(f"Date range:          {report.date_range[0]} to {report.date_range[1]}")
    lines.append("")
    lines.append("--- Admission-relevant agreement (DECISION SIGNAL) ---")
    if report.n_sessions_admission_relevant > 0:
        lines.append(
            f"Sessions w/ admission activity: {report.n_sessions_admission_relevant} "
            f"of {report.n_sessions}"
        )
        lines.append(f"Mean conditional agreement:  {report.mean_conditional_agreement_rate:.1%}")
        lines.append(f"Median conditional agreement:{report.median_conditional_agreement_rate:.1%}")
        lines.append(
            f"Range:                       "
            f"[{report.min_conditional_agreement_rate:.1%}, "
            f"{report.max_conditional_agreement_rate:.1%}]"
        )
        if report.mean_admission_precision is not None:
            lines.append(f"Mean admission precision:    {report.mean_admission_precision:.1%}")
        if report.mean_admission_recall is not None:
            lines.append(f"Mean admission recall:       {report.mean_admission_recall:.1%}")
    else:
        lines.append("No session had admission activity under either path.")
    lines.append("")
    lines.append("--- Whole-watchlist agreement (CONTEXT ONLY — not the decision signal) ---")
    lines.append(f"Mean agreement:      {report.mean_agreement_rate:.1%}")
    lines.append(f"Median agreement:    {report.median_agreement_rate:.1%}")
    lines.append(f"Range:               [{report.min_agreement_rate:.1%}, "
                 f"{report.max_agreement_rate:.1%}]")
    lines.append(f"Mean tourn admitted: {report.mean_tournament_admitted:.1f}")
    lines.append(f"Mean panel admitted: {report.mean_panel_admitted:.1f}")
    lines.append("")
    lines.append(f"RECOMMENDATION: {report.recommendation}")
    lines.append("")

    if report.chronic_tournament_only:
        lines.append("--- Chronic Tournament-Only (tournament admits, panel rejects) ---")
        for ticker, count in list(report.chronic_tournament_only.items())[:20]:
            lines.append(f"  {ticker:<8s}  {count:3d} sessions")
        lines.append("")

    if report.chronic_panel_only:
        lines.append("--- Chronic Panel-Only (panel admits, tournament rejects) ---")
        for ticker, count in list(report.chronic_panel_only.items())[:20]:
            lines.append(f"  {ticker:<8s}  {count:3d} sessions")
        lines.append("")

    lines.append("--- Per-Session Detail ---")
    for s in report.per_session:
        tourn_only_str = ",".join(s["tournament_only"][:5]) or "-"
        panel_only_str = ",".join(s["panel_only"][:5]) or "-"
        lines.append(
            f"  {s['date']}  regime={s['regime'] or '?':<12s}  "
            f"agree={s['agreement_rate']:.1%}  "
            f"tourn={s['tournament_admitted']:3d}  "
            f"panel={s['panel_admitted']:3d}  "
            f"t-only=[{tourn_only_str}]  p-only=[{panel_only_str}]"
        )

    lines.append("")
    lines.append("=" * 72)
    return "\n".join(lines)


__all__ = [
    "SCHEMA_VERSION",
    "DeltaReport",
    "SessionRecord",
    "TickerAdmission",
    "append_record",
    "evaluate_session",
    "format_delta_report",
    "generate_delta_report",
    "log_shadow_admission",
    "read_records",
]
