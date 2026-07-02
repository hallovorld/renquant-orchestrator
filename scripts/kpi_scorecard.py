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
  1. deployed_fraction          — 1 - cash/portfolio_value, latest live pipeline_runs row
  2. floor_gap_vs_spy           — realized idle-cash foregone-SPY attribution
                                  (method family: doc/research/2026-07-02-rs1-parking-sleeve.md §1)
  3. gate_verdict_age           — wf_gate_metadata freshness on the serving artifact;
                                  no authoritative verdict => "mute since 2026-05-18"
  4. ledger_coverage            — % of aged live candidate_scores rows joinable to a
                                  non-null forward outcome (ticker_forward_returns.fwd_20d)
  5. pit_accrual_days           — count of dated dirs in RenQuant/data/estimate_snapshots
  6. collector_liveness         — newest-file mtimes under logs/rq105 + logs/renquant105_pilot
  7. calibrator_sign_laundered  — latest daily FULL run's counters_json counter
  8. buy_side_decision_tc       — scripts/poc_transfer_coefficient.py round-3 method
                                  (imported, NOT re-implemented — single-impl rule)

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
COLLECTOR_DIRS = {
    "rq105_quote_logger": os.path.join(RQ, "logs/rq105"),
    "renquant105_pilot_ticks": os.path.join(RQ, "logs/renquant105_pilot"),
}
OUT_DIR = os.path.join(REPO_ROOT, "doc/research/evidence/kpi_scorecards")

# Operator-established fact (#231 §0 PROCESS row): no authoritative WF-gate verdict
# on the live primary since this date. Used only when no authoritative verdict is found.
GATE_MUTE_SINCE = "2026-05-18"
# RS-1 §1 window anchor (first session of the measured idle-cash window).
FLOOR_GAP_ANCHOR = "2026-04-24"
# A daily run is FULL (not an intraday monitor pass) if it scored at least this many names.
MIN_FULL_RUN_CANDIDATES = 80
# fwd_20d needs ~20 trading days ≈ 28-29 calendar days to resolve; +buffer.
LEDGER_AGED_CUTOFF_DAYS = 35
# A collector is "live" if its newest file is at most this old (covers the overnight gap).
COLLECTOR_LIVE_MAX_AGE_HOURS = 30.0

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
    """One pipeline_runs row per run_date for run_type='live': the row with the latest
    created_at that day (the last completed run supersedes earlier same-day passes)."""
    import pandas as pd
    runs = pd.read_sql(
        "select run_id, run_date, created_at, portfolio_value, cash, n_candidates "
        "from pipeline_runs where run_type='live' order by created_at", con)
    if runs.empty:
        raise ValueError("no run_type='live' rows in pipeline_runs")
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
    row = con.execute(
        "select run_id, run_date, created_at, portfolio_value, cash from pipeline_runs "
        "where run_type='live' order by created_at desc limit 1").fetchone()
    if row is None:
        raise ValueError("no live pipeline_runs rows")
    run_id, run_date, created_at, pv, cash = row
    if not pv:
        raise ValueError(f"portfolio_value empty on latest live row {run_id}")
    canon = _canonical_daily_live(con)
    canon = canon[canon["portfolio_value"] > 0].copy()
    canon["deployed"] = 1.0 - canon["cash"] / canon["portfolio_value"]
    trailing5 = canon.tail(5)
    return {
        "value": round(1.0 - cash / pv, 4),
        "unit": "fraction of book (1 - cash/portfolio_value)",
        "detail": {
            "latest_live_run_id": run_id,
            "latest_live_run_created_at": created_at,
            "portfolio_value": round(pv, 2),
            "cash": round(cash, 2),
            "trailing_5_session_mean": round(float(trailing5["deployed"].mean()), 4),
            "trailing_5_sessions": trailing5["run_date"].tolist(),
        },
        "source": "runs.alpaca.db pipeline_runs (run_type='live'), latest row by created_at; "
                  "trailing mean over the canonical daily series (last row per run_date)",
        "method": "deployed = 1 - cash/portfolio_value. Counts long stock positions only; "
                  "no parking sleeve exists yet (RS-1 not implemented), so idle cash is "
                  "genuinely idle. Target (#231 §0): >=95% incl. sleeve.",
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
        },
        "source": "runs.alpaca.db pipeline_runs (canonical daily live rows) + "
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


def metric_ledger_coverage(con, as_of: dt.date) -> dict:
    import pandas as pd
    cutoff = (as_of - dt.timedelta(days=LEDGER_AGED_CUTOFF_DAYS)).isoformat()
    cov = pd.read_sql(
        "select p.run_date, tfr.ticker is not null as joined, "
        "       tfr.fwd_20d is not null as has_fwd20 "
        "from candidate_scores cs "
        "join pipeline_runs p on p.run_id = cs.run_id "
        "left join ticker_forward_returns tfr "
        "       on tfr.as_of_date = p.run_date and tfr.ticker = cs.ticker "
        "where p.run_type='live' and p.run_date <= ?", con, params=(cutoff,))
    if cov.empty:
        raise ValueError(f"no aged live candidate_scores rows (run_date <= {cutoff})")
    return {
        "value": round(float(cov["has_fwd20"].mean()) * 100.0, 1),
        "unit": f"% of aged live candidate_scores rows (run_date <= {cutoff}) with a "
                "non-null fwd_20d forward outcome",
        "detail": {
            "n_aged_rows": int(len(cov)),
            "joined_any_pct": round(float(cov["joined"].mean()) * 100.0, 1),
            "aged_cutoff_days": LEDGER_AGED_CUTOFF_DAYS,
        },
        "source": "runs.alpaca.db candidate_scores JOIN pipeline_runs (run_date) "
                  "LEFT JOIN ticker_forward_returns on (as_of_date, ticker)",
        "method": "aged := run_date at least 35 calendar days old (20 trading days for "
                  "fwd_20d to resolve, plus buffer). Coverage = share of those decision "
                  "rows whose (run_date, ticker) has a non-null fwd_20d. S5 AC: >=95%.",
    }


def metric_pit_accrual_days(as_of: dt.date) -> dict:
    if not os.path.isdir(ESTIMATE_SNAPSHOTS):
        raise FileNotFoundError(ESTIMATE_SNAPSHOTS)
    pat = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    days = sorted(d for d in os.listdir(ESTIMATE_SNAPSHOTS)
                  if pat.match(d) and os.path.isdir(os.path.join(ESTIMATE_SNAPSHOTS, d)))
    latest = days[-1] if days else None
    stale = latest is None or \
        (as_of - dt.date.fromisoformat(latest)).days > 3  # weekend + 1 tolerance
    return {
        "value": len(days),
        "unit": "count of dated snapshot dirs (accrued PIT days; time-irreversible, "
                "cannot be backfilled)",
        "detail": {"first": days[0] if days else None, "latest": latest,
                   "accrual_stale": bool(stale)},
        "source": "$RQ_ROOT/data/estimate_snapshots/<YYYY-MM-DD>/ directory listing",
        "method": "count directories named YYYY-MM-DD. accrual_stale flags a latest dir "
                  "more than 3 calendar days old (missed-day alert is task N2's AC). "
                  "M-SIG needs >=120 accrued days before D3.",
    }


def metric_collector_liveness(measured_at: dt.datetime) -> dict:
    per = {}
    worst_age = 0.0
    for name, d in COLLECTOR_DIRS.items():
        if not os.path.isdir(d):
            per[name] = {"status": "unavailable", "blocker": f"missing dir {d}"}
            worst_age = float("inf")
            continue
        files = [os.path.join(d, f) for f in os.listdir(d)
                 if os.path.isfile(os.path.join(d, f))]
        if not files:
            per[name] = {"status": "unavailable", "blocker": f"no files in {d}"}
            worst_age = float("inf")
            continue
        newest = max(files, key=os.path.getmtime)
        mtime = dt.datetime.fromtimestamp(os.path.getmtime(newest))
        age_h = (measured_at - mtime).total_seconds() / 3600.0
        worst_age = max(worst_age, age_h)
        per[name] = {
            "newest_file": os.path.basename(newest),
            "mtime": mtime.isoformat(timespec="seconds"),
            "age_hours": round(age_h, 2),
            "size_bytes": os.path.getsize(newest),
            "zero_byte_warning": os.path.getsize(newest) == 0,
        }
    live = worst_age <= COLLECTOR_LIVE_MAX_AGE_HOURS
    return {
        "value": "live" if live else "stale",
        "unit": f"all collectors' newest file within {COLLECTOR_LIVE_MAX_AGE_HOURS:.0f}h",
        "detail": per,
        "source": "file mtimes under $RQ_ROOT/logs/rq105 and $RQ_ROOT/logs/renquant105_pilot",
        "method": "newest-file mtime per collector dir; 'live' iff every collector wrote "
                  "within 30h (covers the overnight gap, catches a dead launchd job by the "
                  "next scorecard). Weekend runs will read 'stale' benignly — run the "
                  "scorecard on a trading day. Zero-byte newest files are flagged but do "
                  "not fail liveness (a fresh log can legitimately be empty at open).",
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
        },
        "source": "runs.alpaca.db pipeline_runs.counters_json of the latest canonical "
                  f"daily FULL run (>= {MIN_FULL_RUN_CANDIDATES} candidate_scores rows, "
                  "last created_at per run_date)",
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


def main() -> None:
    as_of = _as_of()
    measured_at = dt.datetime.now()
    try:
        con = _connect_ro(DB)
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
        "collector_liveness": _run(metric_collector_liveness, measured_at),
        "calibrator_sign_laundered": db_metric(metric_calibrator_sign_laundered),
        "buy_side_decision_tc": db_metric(metric_buy_side_decision_tc),
    }
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
        },
        "metrics": metrics,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    out_path = os.path.join(OUT_DIR, f"kpi_{as_of.isoformat()}.json")
    with open(out_path, "w") as f:
        json.dump(scorecard, f, indent=2, sort_keys=True, default=str)
        f.write("\n")

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
                extra = f"% fwd_20d over {m['detail']['n_aged_rows']} aged rows"
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
