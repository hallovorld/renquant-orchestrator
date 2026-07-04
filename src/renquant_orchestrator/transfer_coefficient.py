"""Transfer coefficient (TC) measurement — sprint S-TC.

TC = corr(w_unconstrained, w_constrained) within each run's candidate set.
The Grinold–Kahn value equation (IR = TC × IC × √BR) makes TC a key lever:
a TC of 0.4 means the portfolio construction stack (shrinkage, correlation
limits, sector caps, whole-share rounding, position count cap) discards 60%
of the model's information.

Data source: ``candidate_scores`` table in the run DB (read-only).
- ``kelly_target_pct`` = unconstrained Kelly weight (the model's intent)
- ``qp_target_w``      = QP-constrained final weight (after all shrinkage)

TC is computed per run_id (cross-sectional correlation across candidates),
then summarized as a time series.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from renquant_orchestrator.runtime_paths import default_data_root

DEFAULT_DB = default_data_root() / "data" / "runs.alpaca.db"


def connect(db_path: str | Path | None = None) -> sqlite3.Connection:
    if db_path is None:
        db_path = DEFAULT_DB
    uri = f"file:{Path(db_path)}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def _load_candidate_weights(
    conn: sqlite3.Connection,
    run_type: str = "live",
    min_candidates: int = 5,
) -> pd.DataFrame:
    """Load per-run candidate weight pairs (kelly_target_pct, qp_target_w).

    Filters to runs with at least ``min_candidates`` rows where both weights
    are non-null — TC is meaningless with fewer points.
    """
    q = """
        SELECT cs.run_id, pr.run_date, cs.ticker, cs.role,
               cs.kelly_target_pct, cs.qp_target_w, cs.mu, cs.sigma,
               cs.rank_score, cs.blocked_by, cs.selected,
               cs.qp_status,
               pr.regime, pr.portfolio_value
        FROM candidate_scores cs
        JOIN pipeline_runs pr ON pr.run_id = cs.run_id
        WHERE pr.run_type = ?
          AND cs.kelly_target_pct IS NOT NULL
          AND cs.qp_target_w IS NOT NULL
    """
    df = pd.read_sql(q, conn, params=(run_type,))
    if df.empty:
        return df
    counts = df.groupby("run_id").size()
    valid_runs = counts[counts >= min_candidates].index
    return df[df["run_id"].isin(valid_runs)].copy()


def compute_tc_per_run(
    conn: sqlite3.Connection,
    run_type: str = "live",
    min_candidates: int = 5,
) -> pd.DataFrame:
    """Compute TC = corr(kelly_target_pct, qp_target_w) for each run.

    Returns a DataFrame with columns:
        run_id, run_date, regime, n_candidates, tc, tc_rank,
        mean_kelly, std_kelly, mean_qp, std_qp,
        max_shrinkage (max absolute weight reduction)
    """
    df = _load_candidate_weights(conn, run_type, min_candidates)
    if df.empty:
        return pd.DataFrame(columns=[
            "run_id", "run_date", "regime", "n_candidates",
            "tc", "tc_rank", "mean_kelly", "std_kelly",
            "mean_qp", "std_qp", "max_shrinkage",
        ])

    records: list[dict[str, Any]] = []
    for run_id, g in df.groupby("run_id"):
        kelly = g["kelly_target_pct"].values
        qp = g["qp_target_w"].values

        tc = float(np.corrcoef(kelly, qp)[0, 1]) if len(g) >= 2 else float("nan")
        tc_rank = float(pd.Series(kelly).corr(pd.Series(qp), method="spearman")) if len(g) >= 2 else float("nan")

        shrinkage = np.abs(kelly - qp)

        qp_status = g["qp_status"].iloc[0] if "qp_status" in g.columns else None
        # Honest taxonomy: qp_status is whatever the solver actually stamped.
        # Group by the REAL value rather than collapsing every non-infeasible
        # case into "optimal" -- a blank/missing status is not evidence the
        # solver succeeded, it is evidence the field was never recorded.
        if qp_status is None or (isinstance(qp_status, float) and pd.isna(qp_status)) or str(qp_status).strip() == "":
            qp_status_category = "missing"
        elif "infeasible" in str(qp_status):
            qp_status_category = "infeasible"
        elif str(qp_status) == "optimal":
            qp_status_category = "optimal"
        else:
            qp_status_category = f"other:{qp_status}"
        is_infeasible = qp_status_category == "infeasible"

        records.append({
            "run_id": run_id,
            "run_date": g["run_date"].iloc[0],
            "regime": g["regime"].iloc[0],
            "qp_status": qp_status,
            "qp_status_category": qp_status_category,
            "qp_infeasible": is_infeasible,
            "n_candidates": len(g),
            "tc": tc,
            "tc_rank": tc_rank,
            "mean_kelly": float(np.mean(kelly)),
            "std_kelly": float(np.std(kelly, ddof=1)) if len(g) > 1 else 0.0,
            "mean_qp": float(np.mean(qp)),
            "std_qp": float(np.std(qp, ddof=1)) if len(g) > 1 else 0.0,
            "max_shrinkage": float(np.max(shrinkage)),
        })

    result = pd.DataFrame(records)
    result["run_date"] = pd.to_datetime(result["run_date"]).dt.strftime("%Y-%m-%d")
    return result.sort_values("run_date").reset_index(drop=True)


def tc_summary(tc_series: pd.DataFrame) -> dict[str, Any]:
    """Summary statistics for the TC time series."""
    if tc_series.empty:
        return {"n_runs": 0}

    tc = tc_series["tc"].dropna()

    # Honest taxonomy: group by the actual qp_status_category rather than
    # collapsing every non-infeasible run into "optimal". A run whose status
    # was never recorded ("missing") is not evidence the solver succeeded.
    by_qp_status: dict[str, Any] = {}
    if "qp_status_category" in tc_series.columns:
        for label, g in tc_series.groupby("qp_status_category"):
            tc_g = g["tc"].dropna()
            if len(tc_g) >= 1:
                by_qp_status[label] = {
                    "n": len(tc_g),
                    "tc_mean": float(tc_g.mean()),
                    "tc_median": float(tc_g.median()),
                    "frac_of_runs": len(tc_g) / max(len(tc), 1),
                }

    return {
        "n_runs": len(tc_series),
        "n_valid": len(tc),
        "tc_mean": float(tc.mean()),
        "tc_median": float(tc.median()),
        "tc_std": float(tc.std(ddof=1)) if len(tc) > 1 else 0.0,
        "tc_min": float(tc.min()),
        "tc_max": float(tc.max()),
        "tc_q25": float(tc.quantile(0.25)),
        "tc_q75": float(tc.quantile(0.75)),
        "tc_rank_mean": float(tc_series["tc_rank"].dropna().mean()),
        "by_qp_status": by_qp_status,
        "by_regime": {
            regime: {
                "n": len(g),
                "tc_mean": float(g["tc"].mean()),
                "tc_median": float(g["tc"].median()),
            }
            for regime, g in tc_series.groupby("regime")
            if len(g) >= 3
        },
    }


def tc_decomposition(
    conn: sqlite3.Connection,
    run_type: str = "live",
    min_candidates: int = 5,
) -> dict[str, Any]:
    """Decompose TC loss by source: which constraints eat the most information?

    For each run, compares kelly_target_pct (unconstrained) to qp_target_w
    (constrained) per candidate and attributes the gap to:
    - blocked candidates (blocked_by is not null, qp_target_w forced to 0)
    - selected but shrunken (selected=1 but qp_target_w < kelly_target_pct)
    - expanded (qp_target_w > kelly_target_pct — QP redistribution)
    """
    df = _load_candidate_weights(conn, run_type, min_candidates)
    if df.empty:
        return {"n_runs": 0, "by_source": {}}

    records = []
    for run_id, g in df.groupby("run_id"):
        kelly = g["kelly_target_pct"].values
        qp = g["qp_target_w"].values
        blocked = g["blocked_by"].notna().values

        blocked_loss = np.sum(np.abs(kelly[blocked] - qp[blocked]))
        passed = ~blocked
        shrunken_mask = passed & (qp < kelly)
        expanded_mask = passed & (qp > kelly)
        shrink_loss = np.sum(np.abs(kelly[shrunken_mask] - qp[shrunken_mask]))
        expand_loss = np.sum(np.abs(kelly[expanded_mask] - qp[expanded_mask]))
        total_loss = np.sum(np.abs(kelly - qp))

        records.append({
            "run_id": run_id,
            "run_date": g["run_date"].iloc[0],
            "total_abs_loss": float(total_loss),
            "blocked_abs_loss": float(blocked_loss),
            "shrink_abs_loss": float(shrink_loss),
            "expand_abs_loss": float(expand_loss),
            "n_blocked": int(blocked.sum()),
            "n_shrunken": int(shrunken_mask.sum()),
            "n_expanded": int(expanded_mask.sum()),
            "n_unchanged": int(np.sum(passed & (qp == kelly))),
        })

    decomp = pd.DataFrame(records)
    return {
        "n_runs": len(decomp),
        "by_source": {
            "blocked": {
                "mean_abs_loss": float(decomp["blocked_abs_loss"].mean()),
                "frac_of_total": float(
                    decomp["blocked_abs_loss"].sum() / max(decomp["total_abs_loss"].sum(), 1e-10)
                ),
                "mean_n_blocked": float(decomp["n_blocked"].mean()),
            },
            "shrinkage": {
                "mean_abs_loss": float(decomp["shrink_abs_loss"].mean()),
                "frac_of_total": float(
                    decomp["shrink_abs_loss"].sum() / max(decomp["total_abs_loss"].sum(), 1e-10)
                ),
                "mean_n_shrunken": float(decomp["n_shrunken"].mean()),
            },
            "expansion": {
                "mean_abs_loss": float(decomp["expand_abs_loss"].mean()),
                "frac_of_total": float(
                    decomp["expand_abs_loss"].sum() / max(decomp["total_abs_loss"].sum(), 1e-10)
                ),
                "mean_n_expanded": float(decomp["n_expanded"].mean()),
            },
        },
    }


def measure_tc(
    db_path: str | Path | None = None,
    run_type: str = "live",
    min_candidates: int = 5,
) -> dict[str, Any]:
    """End-to-end TC measurement: time series + summary + decomposition.

    Returns a dict with:
    - summary: aggregate TC stats
    - decomposition: where TC loss comes from
    - time_series: list of per-run TC records (for plotting / ledger)
    """
    conn = connect(db_path)
    try:
        ts = compute_tc_per_run(conn, run_type, min_candidates)
        summary = tc_summary(ts)
        decomp = tc_decomposition(conn, run_type, min_candidates)
        return {
            "summary": summary,
            "decomposition": decomp,
            "time_series": ts.to_dict("records") if not ts.empty else [],
        }
    finally:
        conn.close()


def _render_summary(result: dict[str, Any]) -> str:
    s = result["summary"]
    if s.get("n_runs", 0) == 0:
        return "No runs with sufficient candidates found."

    lines = [
        "# Transfer Coefficient (TC) report",
        "",
        f"Runs: {s['n_valid']} (min_candidates filter applied)",
        f"TC mean: {s['tc_mean']:+.3f}  median: {s['tc_median']:+.3f}  "
        f"std: {s['tc_std']:.3f}",
        f"TC range: [{s['tc_min']:+.3f}, {s['tc_max']:+.3f}]",
        f"TC rank (Spearman) mean: {s['tc_rank_mean']:+.3f}",
    ]

    if s.get("by_regime"):
        lines += ["", "## By regime"]
        for regime, info in sorted(s["by_regime"].items()):
            lines.append(
                f"  {regime:16s}: n={info['n']:3d}  "
                f"TC mean={info['tc_mean']:+.3f}"
            )

    decomp = result.get("decomposition", {})
    if decomp.get("by_source"):
        lines += ["", "## TC loss decomposition"]
        for src, info in decomp["by_source"].items():
            lines.append(
                f"  {src:12s}: {info['frac_of_total']:.0%} of total abs loss"
            )

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure transfer coefficient (TC) from the run DB"
    )
    parser.add_argument(
        "--db", type=Path, default=None,
        help=f"Path to runs DB (default: {DEFAULT_DB})",
    )
    parser.add_argument(
        "--run-type", default="live", choices=["live", "sim"],
    )
    parser.add_argument(
        "--min-candidates", type=int, default=3,
        help="Minimum candidates per run for TC computation",
    )
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args(argv)

    result = measure_tc(
        db_path=args.db, run_type=args.run_type,
        min_candidates=args.min_candidates,
    )

    if args.json:
        json.dump(result, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    else:
        print(_render_summary(result))

    s = result["summary"]
    if s.get("n_runs", 0) == 0:
        return 2
    tc = s.get("tc_mean", 0)
    if tc < 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
