#!/usr/bin/env python3
"""RS-6: weekly KPI scorecard — one runnable command for every #231 §0 state-vector metric.

Emits a dated JSON scorecard (every metric with value + source + method + measured_at)
to doc/research/evidence/kpi_scorecards/kpi_<YYYY-MM-DD>.json and prints a compact table.

Design rules (per the RS-6 task of the unified 107 master plan, §0 state vector / §4
standing measurement plan):
  - READ-ONLY against all inputs. The only write is the scorecard JSON inside THIS repo.
  - Every metric degrades gracefully to {"status": "unavailable", "blocker": ...} —
    a broken input never crashes the scorecard; it becomes a reported fact instead.
  - Deterministic where possible: fixed window anchors, canonical-row selection rules
    stated per metric, floats rounded, keys sorted. The two intrinsically time-varying
    inputs are the as-of date (override with KPI_AS_OF=YYYY-MM-DD) and file mtimes.

Metrics (source of truth for definitions: doc/research/2026-07-02-rs6-kpi-scorecard.md):
  1. deployed_fraction          — 1 - cash/portfolio_value, latest CANONICAL FULL live
                                  pipeline_runs row (full-run status via candidate_scores
                                  JOIN+count, never pipeline_runs.n_candidates, which is
                                  unpopulated in production)
  2. floor_gap_vs_spy           — realized idle-cash foregone-SPY attribution over the
                                  same canonical FULL-run daily series
                                  (method family: doc/research/2026-07-02-rs1-parking-sleeve.md §1)
  3. gate_verdict_age           — wf_gate_metadata freshness on the serving artifact;
                                  no authoritative verdict => "mute since 2026-05-18"
  4. ledger_coverage            — % of aged live candidate_scores rows joinable to a
                                  non-null forward outcome (ticker_forward_returns.fwd_20d)
  5. pit_accrual_days           — dated dirs under RenQuant/data/estimate_snapshots that
                                  PASS ops/pit/pit_liveness_check.check_snapshot()'s full
                                  4-endpoint publication contract (imported, NOT
                                  re-implemented — single-impl rule); a directory that
                                  merely exists but fails the contract is excluded, not
                                  counted
  6. collector_liveness         — ops/renquant105/rq105_liveness_check.py's own STABLE
                                  PUBLIC interface, check_collector_data_outputs()
                                  (imported unchanged, single-impl rule — this file never
                                  re-derives per-collector freshness rules); each collector's
                                  own freshness basis (continuous row-event-time for the
                                  quote feed, post-close file-mtime completion proxy for the
                                  pairing/entry-timing one-shots) is #248's responsibility,
                                  never this file's own directory-mtime scanning; every
                                  collector reported independently
  7. calibrator_sign_laundered  — latest daily FULL run's counters_json counter
  8. buy_side_decision_tc       — scripts/poc_transfer_coefficient.py round-3 method
                                  (imported, NOT re-implemented — single-impl rule)

Provenance: every DB-derived metric records the exact canonical run_id(s)/date(s) it read
plus a content hash of the deterministic query extract that produced its value (NOT just
the mutable runs.alpaca.db file's mtime+size, which cannot prove which rows were actually
read nor distinguish two DB states that happen to share a size/mtime); pit_accrual_days
records a hash of the validated manifests; collector_liveness records a hash of the
specific row that determined freshness. output_content_sha256 (hash over the metrics
payload) proves run-to-run output reproducibility but does NOT substitute for this
per-metric source provenance. All DB-derived metrics are computed inside ONE explicit
read transaction (BEGIN before the first query, ROLLBACK after the last) so they
represent one coherent point-in-time state vector, not several independent snapshots
that could straddle a concurrent writer's commit.

Reproduce:
  /Users/renhao/git/github/RenQuant/.venv/bin/python scripts/kpi_scorecard.py
Inputs (all read-only):
  $RQ_ROOT/data/runs.alpaca.db (opened mode=ro; falls back to immutable=1 for
  sandboxed readers that cannot create the WAL -shm file)
  $RQ_ROOT/data/ohlcv/SPY/1d.parquet
  $RQ_ROOT/backtesting/renquant_104/artifacts/panel-ltr.alpha158_fund.json
  $RQ_ROOT/data/estimate_snapshots/ , $RQ_ROOT/logs/rq105/ , $RQ_ROOT/logs/renquant105_pilot/
Output:
  doc/research/evidence/kpi_scorecards/kpi_<as_of>.json (this repo)
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import sqlite3
import sys
import traceback

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
DB = os.path.join(RQ, "data/runs.alpaca.db")
SPY_PARQUET = os.path.join(RQ, "data/ohlcv/SPY/1d.parquet")
SERVING_ARTIFACT = os.path.join(
    RQ, "backtesting/renquant_104/artifacts/panel-ltr.alpha158_fund.json")
ESTIMATE_SNAPSHOTS = os.path.join(RQ, "data/estimate_snapshots")
OUT_DIR = os.path.join(REPO_ROOT, "doc/research/evidence/kpi_scorecards")

# Single-implementation rule (same as buy_side_decision_tc): these two ops/
# scripts already carry reviewed, exact per-collector path resolvers and
# publication-contract validators. Re-scanning directories by mtime here
# would silently drift from those contracts and can false-green on an empty
# or irrelevant file (measured incident: an empty quote-logger wrapper log
# and a censored intermediate ticks file were both reported "live" under the
# old directory-mtime scan). Import and reuse, never reimplement.
sys.path.insert(0, os.path.join(REPO_ROOT, "ops", "renquant105"))
sys.path.insert(0, os.path.join(REPO_ROOT, "ops", "pit"))

# Operator-established fact (#231 §0 PROCESS row): no authoritative WF-gate verdict
# on the live primary since this date. Used only when no authoritative verdict is found.
GATE_MUTE_SINCE = "2026-05-18"
# RS-1 §1 window anchor (first session of the measured idle-cash window).
FLOOR_GAP_ANCHOR = "2026-04-24"
# A daily run is FULL (not an intraday monitor pass) if it scored at least this many names.
MIN_FULL_RUN_CANDIDATES = 80
# fwd_20d needs ~20 trading days ≈ 28-29 calendar days to resolve; +buffer.
LEDGER_AGED_CUTOFF_DAYS = 35

_DB_OPEN_MODE = None  # recorded into the scorecard for provenance


def _connect_ro(path: str) -> sqlite3.Connection:
    """Read-only sqlite open. Prefer mode=ro; fall back to immutable=1 (needed when the
    reader cannot create the WAL -shm file, e.g. sandboxed sessions). immutable=1 assumes
    no concurrent writer mid-read; acceptable for a once-weekly snapshot, and the mode
    used is recorded in the scorecard."""
    global _DB_OPEN_MODE
    if not os.path.exists(path):
        raise FileNotFoundError(path)
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        con.execute("select 1 from sqlite_master limit 1")
        _DB_OPEN_MODE = "mode=ro"
        return con
    except sqlite3.OperationalError:
        con = sqlite3.connect(f"file:{path}?mode=ro&immutable=1", uri=True)
        con.execute("select 1 from sqlite_master limit 1")
        _DB_OPEN_MODE = "mode=ro&immutable=1"
        return con


def _as_of() -> dt.date:
    env = os.environ.get("KPI_AS_OF")
    return dt.date.fromisoformat(env) if env else dt.date.today()


def _canonical_daily_live(con):
    """One pipeline_runs row per run_date for run_type='live', restricted to
    FULL runs: the row with the latest created_at that day AMONG rows whose
    candidate_scores row count is >= MIN_FULL_RUN_CANDIDATES (the last
    completed FULL run supersedes an earlier same-day FULL attempt; an
    intraday monitor pass never wins this selection, even if its created_at
    is later than the day's full run).

    Full-run status is determined by JOINING candidate_scores and counting,
    the same way poc_transfer_coefficient._canonical_daily_runs() does —
    NOT via pipeline_runs.n_candidates, which is 0 on every real production
    row (verified against runs.alpaca.db: 1441/1441 live rows have
    n_candidates==0; it is not a populated proxy for run size in this
    schema, despite the column name)."""
    import pandas as pd
    counts = pd.read_sql(
        "select run_id, count(*) n from candidate_scores "
        "group by run_id having n >= ?", con, params=(MIN_FULL_RUN_CANDIDATES,))
    if counts.empty:
        raise ValueError(
            f"no candidate_scores-backed runs with >= {MIN_FULL_RUN_CANDIDATES} rows "
            "(full runs)")
    runs = pd.read_sql(
        "select run_id, run_date, created_at, portfolio_value, cash "
        "from pipeline_runs where run_type='live' and run_id in ({})".format(
            ",".join("?" * len(counts))),
        con, params=counts["run_id"].tolist())
    if runs.empty:
        raise ValueError(
            "candidate_scores has full runs but none match a run_type='live' "
            "pipeline_runs row")
    runs["created_at"] = pd.to_datetime(runs["created_at"])
    idx = runs.groupby("run_date")["created_at"].idxmax()
    return runs.loc[idx].sort_values("run_date").reset_index(drop=True)


def _spy_close():
    import pandas as pd
    spy = pd.read_parquet(SPY_PARQUET)["close"]
    spy.index = spy.index.strftime("%Y-%m-%d")
    return spy


# ---------------------------------------------------------------- metrics


def metric_deployed_fraction(con) -> dict:
    canon = _canonical_daily_live(con)  # FULL runs only — see docstring
    canon = canon[canon["portfolio_value"] > 0].copy()
    if canon.empty:
        raise ValueError("no full-run canonical rows with positive portfolio_value")
    canon["deployed"] = 1.0 - canon["cash"] / canon["portfolio_value"]
    latest = canon.iloc[-1]
    trailing5 = canon.tail(5)
    return {
        "value": round(float(latest["deployed"]), 4),
        "unit": "fraction of book (1 - cash/portfolio_value), latest CANONICAL FULL run",
        "detail": {
            "latest_full_run_id": latest["run_id"],
            "latest_full_run_date": latest["run_date"],
            "latest_full_run_created_at": str(latest["created_at"]),
            "portfolio_value": round(float(latest["portfolio_value"]), 2),
            "cash": round(float(latest["cash"]), 2),
            "trailing_5_session_mean": round(float(trailing5["deployed"].mean()), 4),
            "trailing_5_sessions": trailing5["run_date"].tolist(),
            "canonical_full_run_ids": canon["run_id"].tolist(),
            "canonical_extract_sha256": _extract_hash(canon),
        },
        "source": "runs.alpaca.db pipeline_runs (run_type='live') JOIN candidate_scores "
                  f"count >= {MIN_FULL_RUN_CANDIDATES}, latest row by created_at among "
                  "FULL runs only; trailing mean over the same canonical daily series",
        "method": "deployed = 1 - cash/portfolio_value, computed on the latest CANONICAL "
                  "FULL run (not the raw latest pipeline_runs row by created_at — an "
                  "intraday monitor pass can be more recent than the day's full run and "
                  "must never silently supersede it for this metric). Counts long stock "
                  "positions only; no parking sleeve exists yet (RS-1 not implemented), so "
                  "idle cash is genuinely idle. Target (#231 §0): >=95% incl. sleeve.",
    }


def metric_floor_gap_vs_spy(con, as_of: dt.date) -> dict:
    import pandas as pd  # noqa: F401  (used via helpers)
    spy = _spy_close()
    canon = _canonical_daily_live(con)
    win = canon[(canon["run_date"] >= FLOOR_GAP_ANCHOR)
                & (canon["run_date"] <= as_of.isoformat())].copy()
    win = win[win["run_date"].isin(spy.index)].copy()  # trading sessions only
    if len(win) < 2:
        raise ValueError(f"fewer than 2 sessions since {FLOOR_GAP_ANCHOR}")
    win = win[win["portfolio_value"] > 0]
    win["cash_weight"] = win["cash"] / win["portfolio_value"]
    win["spy_close"] = win["run_date"].map(spy)
    win["spy_ret_next"] = win["spy_close"].shift(-1) / win["spy_close"] - 1.0
    foregone_pp = float((win["cash_weight"] * win["spy_ret_next"]).sum() * 100.0)
    first, last = win["run_date"].iloc[0], win["run_date"].iloc[-1]
    spy_span = float(spy[last] / spy[first] - 1.0) * 100.0
    return {
        "value": round(foregone_pp, 2),
        "unit": "pp of book, cumulative realized foregone SPY return on idle cash "
                f"({first} -> {last}); DESCRIPTIVE, NOT annualized (RS-1 §1)",
        "detail": {
            "window": [first, last],
            "n_sessions": int(len(win)),
            "avg_cash_weight_pct": round(float(win["cash_weight"].mean()) * 100.0, 1),
            "spy_span_return_pct": round(spy_span, 1),
            "canonical_full_run_ids": win["run_id"].tolist(),
            "canonical_extract_sha256": _extract_hash(win[["run_id", "run_date", "cash", "portfolio_value"]]),
        },
        "source": "runs.alpaca.db pipeline_runs (canonical daily live FULL rows) + "
                  "data/ohlcv/SPY/1d.parquet close",
        "method": "for each canonical session t (last live row per run_date, trading days "
                  "only): foregone += cash_weight(t) * SPY close-to-close return t->t+1; "
                  "cumulative simple sum in pp of book. Same method family as RS-1 §1 "
                  "(which reported 46 sessions / 75.5% avg cash / 2.88pp on this window); "
                  "this implementation's canonical-row selection yields the same session "
                  "count but slightly different weights — treat RS-1's exact figures as "
                  "its own snapshot and THIS series as the standing weekly definition.",
    }


def metric_gate_verdict_age(con, as_of: dt.date) -> dict:
    n_db_verdicts = 0
    try:
        n_db_verdicts = con.execute("select count(*) from gate_verdicts").fetchone()[0]
    except sqlite3.Error:
        n_db_verdicts = None
    stamp = None
    if os.path.exists(SERVING_ARTIFACT):
        with open(SERVING_ARTIFACT) as f:
            art = json.load(f)
        stamp = (art.get("metadata") or {}).get("wf_gate_metadata")
    mute_days = (as_of - dt.date.fromisoformat(GATE_MUTE_SINCE)).days
    detail = {
        "gate_verdicts_table_rows": n_db_verdicts,
        "serving_artifact": SERVING_ARTIFACT.replace(RQ + "/", "$RQ_ROOT/"),
    }
    if stamp is not None:
        detail["latest_wf_gate_metadata_stamp"] = {
            "run_at": stamp.get("run_at"),
            "passed": stamp.get("passed"),
            "diagnostic_only": stamp.get("diagnostic_only"),
            "gate_version": stamp.get("gate_version"),
            "wf_reason": stamp.get("wf_reason"),
            "sanity_reason": stamp.get("sanity_reason"),
        }
    authoritative = bool(stamp) and stamp.get("diagnostic_only") is not True \
        and stamp.get("passed") is not None
    if authoritative:
        run_at = dt.datetime.fromisoformat(stamp["run_at"]).date()
        value = (as_of - run_at).days
        unit = "days since last authoritative wf_gate_metadata verdict"
    else:
        value = f"mute since {GATE_MUTE_SINCE} ({mute_days} days)"
        unit = ("no authoritative verdict exists — the freshest stamp on the serving "
                "artifact is diagnostic_only")
    return {
        "value": value,
        "unit": unit,
        "detail": detail,
        "source": "metadata.wf_gate_metadata stamped by RenQuant/scripts/run_wf_gate.py "
                  "into the serving artifact; cross-checked against the (empty) "
                  "runs.alpaca.db gate_verdicts table",
        "method": "authoritative verdict := wf_gate_metadata with diagnostic_only != true "
                  "and a non-null passed field; report its age in days. Otherwise report "
                  f"'mute since {GATE_MUTE_SINCE}' (operator-established date, #231 §0) "
                  "with the latest diagnostic stamp attached for context. Unmuting is "
                  "S1-S4 of the master plan.",
    }


def _ledger_session_keys(run_dates) -> "tuple[pd.Series, str]":
    """Map run_dates to the canonical decision-session key: the last NYSE
    session at or before the date — the same pure-date rule as
    renquant-backtesting `analysis/session_resolution.py` (backtesting#60
    review: weekend/holiday-dated live runs share their preceding session's
    market realization, so raw row coverage and unique-session admissible
    coverage must be reported separately).

    Returns (keys, calendar_kind). calendar_kind is 'nyse' when the shared
    NYSE calendar (pandas_market_calendars) resolved the keys, else
    'weekday_fallback' (Sat/Sun roll to Friday; weekday holidays are NOT
    detected — degraded, flagged in the metric detail).
    """
    import pandas as pd
    d = pd.to_datetime(run_dates).dt.normalize()
    try:
        import pandas_market_calendars as mcal
        cal = mcal.get_calendar("NYSE")
        sessions = pd.DatetimeIndex(cal.valid_days(
            start_date=(d.min() - pd.Timedelta(days=14)).date(),
            end_date=(d.max() + pd.Timedelta(days=7)).date(),
        ))
        if sessions.tz is not None:
            sessions = sessions.tz_localize(None)
        sessions = sessions.normalize()
        idx = (sessions.searchsorted(d.values, side="right") - 1).clip(min=0)
        return pd.Series(sessions.values[idx], index=d.index), "nyse"
    except ImportError:
        shift = (d.dt.weekday - 4).clip(lower=0)  # Sat -> -1d, Sun -> -2d
        return d - pd.to_timedelta(shift, unit="D"), "weekday_fallback"


def metric_ledger_coverage(con, as_of: dt.date) -> dict:
    import pandas as pd
    cutoff = (as_of - dt.timedelta(days=LEDGER_AGED_CUTOFF_DAYS)).isoformat()
    cov = pd.read_sql(
        "select p.run_date, cs.ticker as ticker, "
        "       tfr.ticker is not null as joined, "
        "       tfr.fwd_20d is not null as has_fwd20 "
        "from candidate_scores cs "
        "join pipeline_runs p on p.run_id = cs.run_id "
        "left join ticker_forward_returns tfr "
        "       on tfr.as_of_date = p.run_date and tfr.ticker = cs.ticker "
        "where p.run_type='live' and p.run_date <= ?", con, params=(cutoff,))
    if cov.empty:
        raise ValueError(f"no aged live candidate_scores rows (run_date <= {cutoff})")
    # Admissible view (backtesting#60): weekend/holiday-dated rows resolve
    # their forward outcome as-of the preceding NYSE session, so they share
    # ONE market realization with that session's rows. Raw row coverage
    # measures ledger storage; unique (ticker, session) coverage measures
    # independent realizations — a cluster counts as covered when any of
    # its rows joined a non-null fwd_20d.
    skeys, calendar_kind = _ledger_session_keys(cov["run_date"])
    cov["session"] = skeys
    clusters = cov.groupby(["ticker", "session"])["has_fwd20"].max()
    n_non_session = int(
        (pd.to_datetime(cov["run_date"]).dt.normalize() != cov["session"]).sum()
    )
    return {
        "value": round(float(cov["has_fwd20"].mean()) * 100.0, 1),
        "unit": f"% of aged live candidate_scores rows (run_date <= {cutoff}) with a "
                "non-null fwd_20d forward outcome",
        "detail": {
            "n_aged_rows": int(len(cov)),
            "joined_any_pct": round(float(cov["joined"].mean()) * 100.0, 1),
            "admissible_coverage_pct": round(float(clusters.mean()) * 100.0, 1),
            "n_unique_ticker_sessions": int(len(clusters)),
            "n_non_session_rows": n_non_session,
            "session_calendar": calendar_kind,
            "aged_cutoff_days": LEDGER_AGED_CUTOFF_DAYS,
            "run_date_range": [cov["run_date"].min(), cov["run_date"].max()],
            "extract_sha256": _extract_hash(cov),
        },
        "source": "runs.alpaca.db candidate_scores JOIN pipeline_runs (run_date) "
                  "LEFT JOIN ticker_forward_returns on (as_of_date, ticker)",
        "method": "aged := run_date at least 35 calendar days old (20 trading days for "
                  "fwd_20d to resolve, plus buffer). Raw coverage = share of those "
                  "decision rows whose (run_date, ticker) has a non-null fwd_20d. "
                  "Admissible coverage = share of unique (ticker, NYSE-session) "
                  "clusters covered, where session = last NYSE session at or before "
                  "run_date (weekend/holiday rows share their base session's "
                  "realization — backtesting#60). S5 AC: >=95% on BOTH.",
    }


def metric_pit_accrual_days(as_of: dt.date) -> dict:
    """Count only days whose snapshot genuinely passes the N2 collector's own
    publication contract (all 4 endpoint manifests present, status=='ok',
    as_of matching, referenced parquet present and non-empty) — reused
    unchanged from ops/pit/pit_liveness_check.check_snapshot(), the same
    validator the liveness alert uses for TODAY. A directory that merely
    EXISTS (partial write, crashed mid-publish, leftover from a failed run)
    must not inflate this count: pit_accrual_days feeds an irreversible,
    never-backfillable gate (M-SIG D3's >=120-day bar), so a false-positive
    day here cannot be corrected later — it has to be right the first time."""
    if not os.path.isdir(ESTIMATE_SNAPSHOTS):
        raise FileNotFoundError(ESTIMATE_SNAPSHOTS)
    from pit_liveness_check import ENDPOINTS, check_snapshot  # single-impl rule

    pat = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    candidate_dirs = sorted(
        d for d in os.listdir(ESTIMATE_SNAPSHOTS)
        if pat.match(d) and os.path.isdir(os.path.join(ESTIMATE_SNAPSHOTS, d)))
    valid_days = []
    rejected = {}
    day_manifest_hashes = {}
    for d in candidate_dirs:
        problems = check_snapshot(dt.date.fromisoformat(d))
        if problems:
            rejected[d] = problems
        else:
            valid_days.append(d)
            # Hash the 4 validated manifests' own content — proves WHAT was
            # actually read as "valid" for this day, not just that
            # check_snapshot() returned no problems.
            manifest_blobs = []
            for endpoint in ENDPOINTS:
                mpath = os.path.join(ESTIMATE_SNAPSHOTS, d, f"{endpoint}.manifest.json")
                with open(mpath, "rb") as f:
                    manifest_blobs.append(f.read())
            day_manifest_hashes[d] = hashlib.sha256(b"".join(manifest_blobs)).hexdigest()
    latest = valid_days[-1] if valid_days else None
    stale = latest is None or \
        (as_of - dt.date.fromisoformat(latest)).days > 3  # weekend + 1 tolerance
    return {
        "value": len(valid_days),
        "unit": "count of dated snapshot dirs that PASS the N2 collector's own 4-endpoint "
                "publication contract (accrued PIT days; time-irreversible, cannot be "
                "backfilled)",
        "detail": {
            "first": valid_days[0] if valid_days else None,
            "latest": latest,
            "accrual_stale": bool(stale),
            "n_dirs_scanned": len(candidate_dirs),
            "n_rejected_partial_or_invalid": len(rejected),
            "rejected_days": rejected,
            "valid_day_manifest_sha256": day_manifest_hashes,
            "accrual_extract_sha256": hashlib.sha256(
                json.dumps(day_manifest_hashes, sort_keys=True).encode("utf-8")).hexdigest(),
        },
        "source": "$RQ_ROOT/data/estimate_snapshots/<YYYY-MM-DD>/ directory listing, "
                  "each day validated via ops/pit/pit_liveness_check.check_snapshot() "
                  "(the same contract the daily liveness alert enforces for today)",
        "method": "count directories named YYYY-MM-DD whose check_snapshot() returns zero "
                  "problems (all 4 endpoint manifests present, status=='ok', as_of matching "
                  "the directory date, referenced parquet present and non-empty). A partial "
                  "or crashed publish is excluded, not counted. accrual_stale flags a latest "
                  "VALID dir more than 3 calendar days old (missed-day alert is task N2's "
                  "AC). M-SIG needs >=120 accrued (valid) days before D3.",
    }


def metric_collector_liveness(as_of: dt.date) -> dict:
    """Per-collector liveness via rq105_liveness_check's STABLE PUBLIC
    interface, check_collector_data_outputs() (single-impl rule) — never a
    generic directory-mtime scan, and never this file re-deriving per-
    collector freshness rules on its own. Measured false-green under the old
    directory scan: an EMPTY quote-logger wrapper log and a censored
    intermediate ticks file were both reported 'live' from directory
    activity alone. Reports every expected collector INDEPENDENTLY; the
    aggregate value is 'live' only if every one of them individually passes.

    Calling the STABLE public function (not internal helpers like the old
    _data_outputs/_data_output_fresh this metric previously called directly)
    means this metric does not need to know or track which of the three
    collectors uses row-event-time vs. file-mtime freshness, or how many
    positional fields that file's internals carry — that dispatch logic is
    #248's own responsibility and can change without breaking this
    consumer, exactly the kind of cross-PR breakage a prior round hit when
    #248's internal signatures changed underneath this file's direct calls
    to them."""
    from pathlib import Path

    from rq105_liveness_check import _is_session_day, check_collector_data_outputs

    if not _is_session_day(as_of):
        return {
            "value": "not_a_session_day",
            "unit": "NYSE session-day gate (same calendar rq105_liveness_check uses)",
            "detail": {"as_of": as_of.isoformat()},
            "source": "renquant_orchestrator.intraday_quote_logger.default_session_calendar",
            "method": "collector liveness is only evaluated on NYSE session days; a "
                      "weekend/holiday as_of is reported as its own state, not "
                      "conflated with 'live' or 'stale'.",
        }

    per = check_collector_data_outputs(Path(RQ), as_of)
    for detail in per.values():
        if detail.get("path"):
            detail["path"] = detail["path"].replace(RQ + "/", "$RQ_ROOT/")
    all_live = all(v["status"] == "ok" for v in per.values())
    return {
        "value": "live" if all_live else "stale",
        "unit": "every rq105 pilot/shadow collector's OWN freshness contract "
                "(row-event-time for the continuous quote feed, file-mtime completion "
                "proxy for the post-close one-shot pairing/entry-timing collectors — "
                "the exact rule per collector is #248's own responsibility, not "
                "re-derived here), not directory mtime",
        "detail": per,
        "source": "ops/renquant105/rq105_liveness_check.py's check_collector_data_outputs() "
                  "— the STABLE PUBLIC interface (imported unchanged, single-impl rule)",
        "method": "'live' iff EVERY collector's own check_collector_data_outputs() entry "
                  "reports status=='ok'. Each entry also carries row_content_sha256 (a hash "
                  "of the EXACT row the validator selected as the one that determined the "
                  "verdict, not an arbitrary tail-read blob) and freshness_basis "
                  "('row_event_time' | 'file_mtime') for provenance. Any single collector "
                  "missing/stale/unavailable fails the aggregate — no generic directory "
                  "activity can substitute for a real per-collector check.",
    }


def metric_calibrator_sign_laundered(con) -> dict:
    import pandas as pd
    counts = pd.read_sql(
        "select run_id, count(*) n from candidate_scores where run_id like '%-live-%' "
        f"group by run_id having n >= {MIN_FULL_RUN_CANDIDATES}", con)
    if counts.empty:
        raise ValueError("no FULL live runs (candidate_scores >= "
                         f"{MIN_FULL_RUN_CANDIDATES}) found")
    runs = pd.read_sql(
        "select run_id, run_date, created_at, counters_json from pipeline_runs "
        "where run_id in ({})".format(",".join("?" * len(counts))),
        con, params=counts["run_id"].tolist())
    runs = runs.merge(counts, on="run_id")
    runs["created_at"] = pd.to_datetime(runs["created_at"])
    idx = runs.groupby("run_date")["created_at"].idxmax()
    latest = runs.loc[idx].sort_values("run_date").iloc[-1]
    if not latest["counters_json"]:
        raise ValueError(f"latest full run {latest['run_id']} has empty counters_json")
    counters = json.loads(latest["counters_json"])
    if "calibrator_sign_laundered" not in counters:
        raise ValueError(
            f"counters_json of {latest['run_id']} has no 'calibrator_sign_laundered' key "
            f"(keys: {sorted(counters)})")
    return {
        "value": int(counters["calibrator_sign_laundered"]),
        "unit": "names whose calibrated mu sign was laundered, latest daily FULL run",
        "detail": {
            "run_id": latest["run_id"],
            "run_date": latest["run_date"],
            "n_scored": int(latest["n"]),
            "all_counters": counters,
            "counters_json_sha256": hashlib.sha256(
                latest["counters_json"].encode("utf-8")).hexdigest(),
        },
        "source": "runs.alpaca.db pipeline_runs.counters_json of the latest canonical "
                  f"daily FULL run (>= {MIN_FULL_RUN_CANDIDATES} candidate_scores rows via "
                  "candidate_scores JOIN+count, last created_at per run_date)",
        "method": "parse counters_json['calibrator_sign_laundered']. M4 AC: single digits "
                  "(BL-1 recentering); 44/90 was the measured 2026-07-01 state.",
    }


def metric_buy_side_decision_tc(con) -> dict:
    # Single-implementation rule: import the reviewed round-3 method from the POC script
    # (three hand-copied fingerprint impls once diverged for months — never again).
    sys.path.insert(0, os.path.join(REPO_ROOT, "scripts"))
    import numpy as np
    from poc_transfer_coefficient import _canonical_daily_runs, buy_side_decision_tc
    canonical = _canonical_daily_runs(con)
    if not canonical:
        raise ValueError("no canonical daily FULL runs for TC")
    results = [r for r in (buy_side_decision_tc(con, rid) for rid in canonical) if r]
    measured = [r for r in results if r["category"] == "measured"]
    tcs = [r["buy_side_decision_tc"] for r in measured]
    mean_tc = round(float(np.mean(tcs)), 3) if tcs else None
    se_tc = (round(float(np.std(tcs, ddof=1) / np.sqrt(len(tcs))), 3)
             if len(tcs) >= 2 else None)
    categories = {}
    for r in results:
        categories[r["category"]] = categories.get(r["category"], 0) + 1
    return {
        "value": mean_tc,
        "unit": "mean Pearson corr(kelly_target_pct, emitted buy target_pct) over "
                "admission-surviving candidates, 'measured'-category canonical runs only "
                "— EXPLORATORY DIAGNOSTIC, not measured-tier TC (POC-S-TC round 3)",
        "detail": {
            "n_canonical_runs": len(canonical),
            "n_measured": len(tcs),
            "se_measured": se_tc,
            "category_counts": categories,
            "per_run": [
                {"run_id": r["run_id"], "category": r["category"],
                 "tc": r["buy_side_decision_tc"],
                 "exposure_transfer_ratio": r.get("exposure_transfer_ratio"),
                 "n_survived_admission": r["n_survived_admission"]}
                for r in results
            ],
            "canonical_run_ids": canonical,
            "per_run_extract_sha256": _extract_hash([
                {"run_id": r["run_id"], "category": r["category"],
                 "tc": r["buy_side_decision_tc"],
                 "n_survived_admission": r["n_survived_admission"]}
                for r in results
            ]),
        },
        "source": "runs.alpaca.db candidate_scores + trades via "
                  "scripts/poc_transfer_coefficient.py (round-3 blocked_by taxonomy)",
        "method": "imported unchanged from poc_transfer_coefficient.buy_side_decision_tc: "
                  "eligible = candidates with mu >= 0.03; admission survivors classified "
                  "by the round-3 blocked_by stage taxonomy; Pearson TC only over runs "
                  "with real dispersion ('measured'); undefined cases categorized, never "
                  "averaged in as 0. Caveats in "
                  "doc/progress/2026-07-02-s-tc-measurement.md apply verbatim.",
    }


# ---------------------------------------------------------------- runner


def _run(fn, *args) -> dict:
    try:
        out = fn(*args)
        out["status"] = "ok"
        return out
    except Exception as exc:  # noqa: BLE001 — graceful degradation is the contract
        return {
            "status": "unavailable",
            "blocker": f"{type(exc).__name__}: {exc}",
            "traceback_tail": traceback.format_exc().strip().splitlines()[-1],
        }


def _generator_sha256() -> str:
    """Content hash of THIS script — a self-referential generator_commit (a
    commit hash that predates the very commit adding this stamping logic) is
    a chicken-and-egg bug already hit once this session (#430); a content
    hash computed live has no such ordering dependency."""
    with open(os.path.abspath(__file__), "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _canonical_content_hash(metrics: dict) -> str:
    """Hash of the metrics payload ALONE (excludes measured_at/as_of/inputs,
    which vary run-to-run even when the underlying data is identical) —
    sorted-key JSON with a fixed float representation, same canonicalization
    family as #430's regen_oos_pick_table.output_content_sha256. Two runs
    against the same underlying DB/filesystem state must produce the same
    hash; this is what makes 'reproducible' a checkable claim, not an
    assertion in prose."""
    def _canon(obj):
        if isinstance(obj, float):
            return round(obj, 8)
        if isinstance(obj, dict):
            return {k: _canon(v) for k, v in sorted(obj.items())
                    if k != "measured_at"}  # wall-clock, not content
        if isinstance(obj, list):
            return [_canon(v) for v in obj]
        return obj

    canonical = _canon(metrics)
    blob = json.dumps(canonical, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _extract_hash(rows) -> str:
    """Content hash of a deterministic query-extract (a pandas DataFrame or
    a list of row tuples/dicts) — proves WHAT DATA a metric actually read,
    not just which run_id it picked. runs.alpaca.db is a mutable,
    continuously-written file; stamping only its size+mtime cannot
    distinguish two DB states that happen to share both, and cannot bind
    the exact rows a metric consumed. Sorted, canonicalized JSON of the
    extract's own content, same family as _canonical_content_hash."""
    if hasattr(rows, "to_dict"):
        rows = rows.to_dict(orient="records")

    def _canon(obj):
        if isinstance(obj, float):
            return round(obj, 8)
        if isinstance(obj, dict):
            return {k: _canon(v) for k, v in sorted(obj.items())}
        if isinstance(obj, (list, tuple)):
            return [_canon(v) for v in obj]
        return obj

    canonical = [_canon(r) for r in rows]
    blob = json.dumps(canonical, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def _atomic_write_json(path: str, payload: dict) -> None:
    """Temp file + fsync + rename in the SAME directory as the final path —
    atomic on POSIX filesystems (a reader sees the old complete file or the
    new complete file, never a partial write); same pattern as #236's
    batch_scores_bundle atomic-write fix."""
    tmp_path = f"{path}.tmp-{os.getpid()}"
    with open(tmp_path, "w") as f:
        json.dump(payload, f, indent=2, sort_keys=True, default=str)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp_path, path)


def main() -> None:
    as_of = _as_of()
    measured_at = dt.datetime.now()
    db_snapshot_stat = None
    db_txn_open = False
    try:
        con = _connect_ro(DB)
        db_snapshot_stat = os.stat(DB)
        # Pin ONE consistent read snapshot for every DB-derived metric in
        # this run. python's sqlite3 module does NOT implicitly wrap
        # SELECT-only work in a transaction (isolation_level="" only
        # auto-BEGINs before DML) — without this, each metric's own
        # independent SELECT could observe a DIFFERENT committed WAL state
        # if a concurrent writer commits mid-run, so the scorecard's several
        # metrics would not actually represent one coherent point-in-time
        # state vector even though they're all read from "the same
        # connection". An explicit BEGIN (DEFERRED, the sqlite3 default) on
        # a mode=ro connection still establishes SQLite's standard WAL
        # snapshot-isolation boundary at the first read within it — every
        # subsequent SELECT in this transaction sees exactly that snapshot,
        # regardless of what writers commit afterward. Proven by
        # test_all_db_metrics_share_one_snapshot_despite_concurrent_writer.
        con.execute("BEGIN")
        db_txn_open = True
    except Exception as exc:  # every DB metric degrades together, others still run
        con = None
        db_blocker = f"{type(exc).__name__}: {exc}"

    def db_metric(fn, *args):
        if con is None:
            return {"status": "unavailable", "blocker": f"db unavailable: {db_blocker}"}
        return _run(fn, con, *args)

    metrics = {
        "deployed_fraction": db_metric(metric_deployed_fraction),
        "floor_gap_vs_spy": db_metric(metric_floor_gap_vs_spy, as_of),
        "gate_verdict_age": db_metric(metric_gate_verdict_age, as_of),
        "ledger_coverage": db_metric(metric_ledger_coverage, as_of),
        "pit_accrual_days": _run(metric_pit_accrual_days, as_of),
        "collector_liveness": _run(metric_collector_liveness, as_of),
        "calibrator_sign_laundered": db_metric(metric_calibrator_sign_laundered),
        "buy_side_decision_tc": db_metric(metric_buy_side_decision_tc),
    }
    if db_txn_open:
        # Read-only transaction; nothing was written. ROLLBACK (not COMMIT)
        # is the correct way to release it — there is no DML to persist.
        con.execute("ROLLBACK")
    for m in metrics.values():
        m["measured_at"] = measured_at.isoformat(timespec="seconds")

    scorecard = {
        "schema_version": 1,
        "scorecard": "RS-6 weekly KPI scorecard (#231 §0 state vector)",
        "as_of": as_of.isoformat(),
        "measured_at": measured_at.isoformat(timespec="seconds"),
        "inputs": {
            "rq_root": RQ,
            "db": DB,
            "db_open_mode": _DB_OPEN_MODE,
            "db_snapshot": {
                "size_bytes": db_snapshot_stat.st_size,
                "mtime": dt.datetime.fromtimestamp(
                    db_snapshot_stat.st_mtime).isoformat(timespec="seconds"),
                "note": "size+mtime alone do NOT prove which rows were read from this "
                        "mutable, continuously-written file, nor distinguish two DB "
                        "states that happen to share both — see each DB-derived metric's "
                        "own detail.*_extract_sha256/canonical_extract_sha256 field for "
                        "the actual per-metric source-content provenance",
            } if db_snapshot_stat else None,
            "spy_parquet_sha256": (
                hashlib.sha256(open(SPY_PARQUET, "rb").read()).hexdigest()
                if os.path.exists(SPY_PARQUET) else None),
            "serving_artifact_sha256": (
                hashlib.sha256(open(SERVING_ARTIFACT, "rb").read()).hexdigest()
                if os.path.exists(SERVING_ARTIFACT) else None),
        },
        "generator_sha256": _generator_sha256(),
        "metrics": metrics,
    }
    scorecard["output_content_sha256"] = _canonical_content_hash(metrics)

    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"kpi_{as_of.isoformat()}.json")
    _atomic_write_json(out_path, scorecard)

    print(f"KPI scorecard  as_of={as_of}  ->  {os.path.relpath(out_path, REPO_ROOT)}")
    print(f"{'metric':<28} {'status':<12} value")
    print("-" * 78)
    for name, m in metrics.items():
        if m["status"] == "ok":
            val = m["value"]
            extra = ""
            if name == "floor_gap_vs_spy":
                extra = (f"pp foregone / {m['detail']['n_sessions']} sessions / "
                         f"avg cash {m['detail']['avg_cash_weight_pct']}%")
            elif name == "ledger_coverage":
                extra = (f"% fwd_20d raw over {m['detail']['n_aged_rows']} aged rows; "
                         f"admissible {m['detail']['admissible_coverage_pct']}% over "
                         f"{m['detail']['n_unique_ticker_sessions']} (ticker, session) "
                         f"clusters [{m['detail']['session_calendar']}]")
            elif name == "buy_side_decision_tc":
                extra = (f"(n_measured={m['detail']['n_measured']}, "
                         f"categories={m['detail']['category_counts']})")
            elif name == "calibrator_sign_laundered":
                extra = f"on {m['detail']['run_date']}"
            elif name == "deployed_fraction":
                extra = f"(trailing-5 mean {m['detail']['trailing_5_session_mean']})"
            elif name == "pit_accrual_days":
                extra = f"(latest {m['detail']['latest']})"
            print(f"{name:<28} {'ok':<12} {val} {extra}")
        else:
            print(f"{name:<28} {'UNAVAILABLE':<12} {m['blocker']}")


if __name__ == "__main__":
    main()
