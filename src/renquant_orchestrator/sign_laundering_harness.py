"""Sign-laundering measurement harness (M4-b).

The calibrator neutral raw score sits at approximately -0.29 (not 0).
Raw scores in (neutral, 0) map to mu of the OPPOSITE sign through the
calibration curve. This module measures how many names fall in that zone
and tracks the rate over time.

Read-only: never modifies scorer, calibrator, or DB artifacts.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from renquant_orchestrator.runtime_paths import default_data_root

DEFAULT_DB = default_data_root() / "data" / "runs.alpaca.db"


def _connect_ro(db_path=None):
    if db_path is None:
        db_path = DEFAULT_DB
    uri = f"file:{Path(db_path)}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _find_neutral_raw_from_calibrator(calibrator_path):
    cal = json.loads(Path(calibrator_path).read_text())
    breakpoints = cal.get("breakpoints") or cal.get("calibration_breakpoints")
    if breakpoints and isinstance(breakpoints, list):
        for i in range(len(breakpoints) - 1):
            bp_a = breakpoints[i]
            bp_b = breakpoints[i + 1]
            raw_a = bp_a.get("raw", bp_a.get("x", 0.0))
            mu_a = bp_a.get("mu", bp_a.get("y", 0.0))
            raw_b = bp_b.get("raw", bp_b.get("x", 0.0))
            mu_b = bp_b.get("mu", bp_b.get("y", 0.0))
            if mu_a * mu_b <= 0 and mu_a != mu_b:
                t = mu_a / (mu_a - mu_b)
                return float(raw_a + t * (raw_b - raw_a))
    intercept = cal.get("intercept")
    slope = cal.get("slope")
    if intercept is not None and slope is not None and slope != 0:
        return float(-intercept / slope)
    return None


def _estimate_neutral_raw_from_scores(by_ticker):
    pairs = []
    for info in by_ticker.values():
        raw = info.get("raw")
        mu = info.get("mu")
        if raw is not None and mu is not None:
            pairs.append((raw, mu))
    if len(pairs) < 2:
        return None
    pairs.sort(key=lambda p: p[0])
    for i in range(len(pairs) - 1):
        raw_a, mu_a = pairs[i]
        raw_b, mu_b = pairs[i + 1]
        if mu_a * mu_b <= 0 and mu_a != mu_b:
            t = mu_a / (mu_a - mu_b)
            return float(raw_a + t * (raw_b - raw_a))
    return None


def measure_sign_laundering(scorer_path, calibrator_path=None, neutral_raw_override=None):
    scorer = json.loads(Path(scorer_path).read_text())
    by_ticker = {}
    candidates = (
        scorer.get("candidates")
        or scorer.get("scores")
        or scorer.get("per_ticker")
        or {}
    )
    if isinstance(candidates, dict):
        for ticker, info in candidates.items():
            if isinstance(info, dict):
                by_ticker[ticker] = {
                    "raw": info.get("raw_score", info.get("rank_score")),
                    "mu": info.get("mu"),
                    "sigma": info.get("sigma"),
                }
    elif isinstance(candidates, list):
        for entry in candidates:
            if isinstance(entry, dict) and "ticker" in entry:
                by_ticker[entry["ticker"]] = {
                    "raw": entry.get("raw_score", entry.get("rank_score")),
                    "mu": entry.get("mu"),
                    "sigma": entry.get("sigma"),
                }
    neutral_raw = neutral_raw_override
    if neutral_raw is None and calibrator_path is not None:
        neutral_raw = _find_neutral_raw_from_calibrator(Path(calibrator_path))
    if neutral_raw is None:
        neutral_raw = _estimate_neutral_raw_from_scores(by_ticker)
    laundered_names = []
    raw_values = []
    for ticker, info in by_ticker.items():
        raw = info.get("raw")
        mu = info.get("mu")
        if raw is None:
            continue
        raw_values.append(raw)
        info["laundered"] = False
        if neutral_raw is not None and mu is not None:
            if neutral_raw < 0:
                if neutral_raw < raw < 0 and mu > 0:
                    info["laundered"] = True
                    laundered_names.append(ticker)
            elif neutral_raw > 0:
                if 0 < raw < neutral_raw and mu < 0:
                    info["laundered"] = True
                    laundered_names.append(ticker)
    total = len(by_ticker)
    laundered_count = len(laundered_names)
    return {
        "total_names": total,
        "laundered_names": sorted(laundered_names),
        "laundered_count": laundered_count,
        "laundering_rate": laundered_count / total if total > 0 else 0.0,
        "neutral_raw": neutral_raw,
        "raw_score_range": (
            (float(min(raw_values)), float(max(raw_values)))
            if raw_values
            else (None, None)
        ),
        "by_ticker": by_ticker,
    }


def audit_laundering_history(db_path=None, n_runs=30, run_type="live"):
    conn = _connect_ro(db_path)
    try:
        q = """
            SELECT cs.run_id, pr.run_date, cs.ticker,
                   cs.rank_score, cs.mu
            FROM candidate_scores cs
            JOIN pipeline_runs pr ON pr.run_id = cs.run_id
            WHERE pr.run_type = ?
              AND cs.rank_score IS NOT NULL
              AND cs.mu IS NOT NULL
            ORDER BY pr.run_date DESC
        """
        df = pd.read_sql(q, conn, params=(run_type,))
    finally:
        conn.close()
    if df.empty:
        return []
    run_ids = df["run_id"].unique()
    if len(run_ids) > n_runs:
        date_order = (
            df.drop_duplicates("run_id")
            .sort_values("run_date", ascending=False)
        )
        keep_ids = set(date_order["run_id"].iloc[:n_runs])
        df = df[df["run_id"].isin(keep_ids)]
    records = []
    for run_id, g in df.groupby("run_id"):
        by_ticker = {}
        for _, row in g.iterrows():
            by_ticker[row["ticker"]] = {
                "raw": float(row["rank_score"]),
                "mu": float(row["mu"]),
            }
        neutral_raw = _estimate_neutral_raw_from_scores(by_ticker)
        if neutral_raw is None:
            continue
        laundered = 0
        total = len(by_ticker)
        for info in by_ticker.values():
            raw = info["raw"]
            mu = info["mu"]
            if neutral_raw < 0:
                if neutral_raw < raw < 0 and mu > 0:
                    laundered += 1
            elif neutral_raw > 0:
                if 0 < raw < neutral_raw and mu < 0:
                    laundered += 1
        records.append({
            "run_id": run_id,
            "run_date": g["run_date"].iloc[0],
            "total_names": total,
            "laundered_count": laundered,
            "laundering_rate": laundered / total if total > 0 else 0.0,
            "neutral_raw": neutral_raw,
        })
    records.sort(key=lambda r: r["run_date"])
    return records


def _render_report(result):
    lines = [
        "# Sign-Laundering Report",
        "",
        f"Total names:     {result['total_names']}",
        f"Laundered:       {result['laundered_count']}",
        f"Rate:            {result['laundering_rate']:.1%}",
    ]
    if result["neutral_raw"] is not None:
        lines.append(f"Neutral raw:     {result['neutral_raw']:.4f}")
    lo, hi = result["raw_score_range"]
    if lo is not None:
        lines.append(f"Raw range:       [{lo:.4f}, {hi:.4f}]")
    if result["laundered_names"]:
        lines += ["", "## Laundered names"]
        for t in result["laundered_names"]:
            info = result["by_ticker"][t]
            lines.append(
                f"  {t:8s}  raw={info['raw']:+.4f}  mu={info['mu']:+.4f}"
            )
    return "\n".join(lines)


def _render_history(history):
    if not history:
        return "No runs with sign-change data found."
    lines = [
        "# Sign-Laundering History",
        "",
        f"{'Date':12s} {'Total':>6s} {'Laund':>6s} {'Rate':>7s} {'Neutral':>9s}",
        "-" * 44,
    ]
    for r in history:
        lines.append(
            f"{r['run_date']:12s} {r['total_names']:6d} "
            f"{r['laundered_count']:6d} {r['laundering_rate']:6.1%} "
            f"{r['neutral_raw']:+9.4f}"
        )
    rates = [r["laundering_rate"] for r in history]
    lines += [
        "",
        f"Mean rate: {np.mean(rates):.1%}  "
        f"Trend: {rates[-1] - rates[0]:+.1%} (first->last)",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Measure sign laundering in scorer/calibrator artifacts"
    )
    sub = parser.add_subparsers(dest="action", required=True)
    measure = sub.add_parser("measure", help="measure a single scorer artifact")
    measure.add_argument("scorer", type=Path, help="path to scorer JSON")
    measure.add_argument("--calibrator", type=Path, default=None)
    measure.add_argument("--neutral-raw", type=float, default=None)
    measure.add_argument("--json", action="store_true", dest="as_json")
    history = sub.add_parser("history", help="audit laundering across recent runs")
    history.add_argument("--db", type=Path, default=None)
    history.add_argument("--n-runs", type=int, default=30)
    history.add_argument("--run-type", default="live")
    history.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)
    if args.action == "measure":
        result = measure_sign_laundering(
            args.scorer,
            calibrator_path=args.calibrator,
            neutral_raw_override=args.neutral_raw,
        )
        if args.as_json:
            json.dump(result, sys.stdout, indent=2, default=str)
            sys.stdout.write("\n")
        else:
            print(_render_report(result))
        return 1 if result["laundering_rate"] > 0.10 else 0
    if args.action == "history":
        records = audit_laundering_history(
            db_path=args.db, n_runs=args.n_runs, run_type=args.run_type,
        )
        if args.as_json:
            json.dump(records, sys.stdout, indent=2, default=str)
            sys.stdout.write("\n")
        else:
            print(_render_history(records))
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
