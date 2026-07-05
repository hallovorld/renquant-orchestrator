"""M4-b matched-breadth conviction-floor replay harness.

Implements the matched-breadth evaluation protocol from
``doc/design/2026-07-03-m4b-relative-conviction-floor.md`` (design §4):
replay candidate floor re-derivations against the CURRENT absolute floor
on stored production candidate_scores at MATCHED ADMISSION RATES, scoring
realized forward excess with date-block bootstrap confidence intervals.

This module provides the reusable building blocks for the conviction-floor
replay:

  ``ReplayConfig``              — candidate floor formula params
  ``load_candidate_scores``     — read-only DB loader for scored cross-sections
  ``apply_floor``               — applies candidate/baseline floor to daily data
  ``matched_breadth_compare``   — matches candidate to baseline breadth per day
  ``block_bootstrap_ci``        — block bootstrap CI on return differences
  ``main``                      — CLI entry point

Design constraints (§4, §5):
  - Read-only: never modifies the run DB or any artifact.
  - Matched admission rates: each candidate's parameter is set so its mean
    floor-clearing count matches the baseline's (±0.5).
  - BL-4 side-condition: mu > 0 is enforced on all relative-floor candidates
    (design §2(a)/(b): "AND mu > 0").
  - The baseline is the CURRENT absolute floor (mu >= 0.03, pre-recentering).
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from renquant_orchestrator.expkit.stats import (
    block_bootstrap_conditional_mean,
    bootstrap_admissible,
    summarize_boot,
)
from renquant_orchestrator.runtime_paths import default_data_root

DEFAULT_DB = default_data_root() / "data" / "runs.alpaca.db"

# Pre-registered constants (design §4).
BASELINE_FLOOR = 0.03
BLOCK_PRIMARY = 5
N_BOOT_DEFAULT = 2000
SEED = 20260705
BREADTH_TOL = 0.5


# ------------------------------------------------------------------- config


@dataclass
class ReplayConfig:
    """Configuration for one replay experiment run.

    ``quantile_k``: for candidate (a), the top-K fraction (e.g. 0.20 = top 20%).
        ``admit iff mu >= Quantile_{1-K}(bar mu) AND mu > 0``

    ``mad_k``: for candidate (b), the dispersion multiplier.
        ``admit iff mu >= k * MAD(bar mu) AND mu > 0``
        MAD = median absolute deviation about the per-bar median.

    ``baseline_floor``: the absolute floor for the baseline arm (default 0.03,
        today's production conviction_gate.mu_floor).

    ``start_date`` / ``end_date``: evaluation window (ISO format YYYY-MM-DD).

    ``min_breadth``: minimum per-bar candidate count to include the bar in
        evaluation (bars with fewer than this many scored names are excluded
        from cross-sectional statistics as unreliable — design §2(b) thin-bar
        fallback).
    """

    quantile_k: float | None = None
    mad_k: float | None = None
    baseline_floor: float = BASELINE_FLOOR
    start_date: str | None = None
    end_date: str | None = None
    min_breadth: int = 10
    n_boot: int = N_BOOT_DEFAULT
    block_size: int = BLOCK_PRIMARY
    seed: int = SEED


# ------------------------------------------------------------------- DB loader


def _connect_ro(db_path: Path | None = None) -> sqlite3.Connection:
    """Read-only DB connection — the harness must never mutate the trade DB."""
    if db_path is None:
        db_path = DEFAULT_DB
    uri = f"file:{Path(db_path)}?mode=ro"
    return sqlite3.connect(uri, uri=True)


def load_candidate_scores(
    db_path: Path | str,
    start_date: str | None = None,
    end_date: str | None = None,
    *,
    run_type: str = "live",
    min_candidates: int = 20,
) -> pd.DataFrame:
    """Load daily candidate_scores from the run DB (read-only).

    Returns a DataFrame with columns: date, run_id, ticker, mu, raw_score,
    blocked_by, selected. One canonical run per date (latest created_at
    among runs with >= min_candidates candidates, the M3/#234 dedup
    discipline).

    Forward returns are joined from ticker_forward_returns when available,
    providing fwd_5d, fwd_20d, fwd_60d columns.
    """
    conn = _connect_ro(Path(db_path))
    try:
        # Load candidate scores with pipeline run metadata
        where_parts = ["pr.run_type = ?"]
        params: list[str | int] = [run_type]
        if start_date:
            where_parts.append("pr.run_date >= ?")
            params.append(start_date)
        if end_date:
            where_parts.append("pr.run_date <= ?")
            params.append(end_date)
        where_clause = " AND ".join(where_parts)

        scores_q = f"""
            SELECT cs.run_id, pr.run_date AS date, cs.ticker,
                   cs.mu, cs.raw_score, cs.blocked_by, cs.selected
            FROM candidate_scores cs
            JOIN pipeline_runs pr ON pr.run_id = cs.run_id
            WHERE {where_clause}
              AND cs.mu IS NOT NULL
            ORDER BY pr.run_date, cs.ticker
        """
        scores_df = pd.read_sql(scores_q, conn, params=params)

        if scores_df.empty:
            return scores_df

        # Canonical run dedup: keep only runs with >= min_candidates names,
        # and for each date keep the run with the most candidates (latest
        # run_id as tiebreaker)
        run_counts = scores_df.groupby("run_id").size().reset_index(name="n")
        valid_runs = set(run_counts.loc[run_counts["n"] >= min_candidates, "run_id"])
        scores_df = scores_df[scores_df["run_id"].isin(valid_runs)]

        if scores_df.empty:
            return scores_df

        # One canonical run per date
        run_meta = (
            scores_df[["run_id", "date"]]
            .drop_duplicates()
            .assign(n=scores_df.groupby("run_id")["ticker"].transform("count"))
        )
        # Use run_meta to pick canonical run per date (most candidates, latest run_id)
        canonical = (
            run_meta
            .sort_values(["n", "run_id"], ascending=[False, False])
            .drop_duplicates("date", keep="first")
        )
        canonical_ids = set(canonical["run_id"])
        scores_df = scores_df[scores_df["run_id"].isin(canonical_ids)]

        # Join forward returns when available
        try:
            fwd_q = """
                SELECT as_of_date AS date, ticker, fwd_5d, fwd_20d, fwd_60d
                FROM ticker_forward_returns
            """
            fwd_df = pd.read_sql(fwd_q, conn)
            if not fwd_df.empty:
                scores_df = scores_df.merge(
                    fwd_df, on=["date", "ticker"], how="left",
                )
        except Exception:
            # ticker_forward_returns may not exist in all DBs
            pass

    finally:
        conn.close()

    return scores_df


# ---------------------------------------------------------------- floor logic


def _quantile_floor(mu_series: pd.Series, k: float) -> float:
    """Cross-sectional quantile floor: Q_{1-k} of the bar's mu distribution.

    Returns the (1-k) quantile of the mu values. Names with mu >= this
    threshold AND mu > 0 are admitted (design §2(a)).
    """
    return float(mu_series.quantile(1.0 - k))


def _mad_floor(mu_series: pd.Series, k: float) -> float:
    """Dispersion-scaled floor: k * MAD(bar mu).

    MAD = median absolute deviation about the per-bar median (consistent with
    #162's median-center choice, robust to the heavy raw tails it documents).
    Returns k * MAD. Names with mu >= this threshold AND mu > 0 are admitted
    (design §2(b)).
    """
    median = mu_series.median()
    mad = float((mu_series - median).abs().median())
    return k * mad


def apply_floor(
    scores_df: pd.DataFrame,
    config: ReplayConfig,
) -> pd.DataFrame:
    """Apply candidate floor formula to daily cross-sections.

    For each date's cross-section, computes:
    - ``admitted_baseline``: whether the name clears the baseline absolute floor
      (mu >= config.baseline_floor)
    - ``admitted_candidate``: whether the name clears the candidate floor
      (quantile or MAD formula, with the BL-4 mu > 0 side-condition)
    - ``rank``: per-bar mu rank (descending, 1 = highest mu)

    Returns the input DataFrame with added columns: rank, floor_threshold,
    admitted_baseline, admitted_candidate.
    """
    if scores_df.empty:
        return scores_df.assign(
            rank=pd.Series(dtype=float),
            floor_threshold=pd.Series(dtype=float),
            admitted_baseline=pd.Series(dtype=bool),
            admitted_candidate=pd.Series(dtype=bool),
        )

    results = []
    for date, group in scores_df.groupby("date"):
        if len(group) < config.min_breadth:
            continue

        mu = group["mu"].astype(float)

        # Baseline: absolute floor (today's production rule)
        admitted_baseline = mu >= config.baseline_floor

        # Candidate floor
        if config.quantile_k is not None:
            threshold = _quantile_floor(mu, config.quantile_k)
            # BL-4 side-condition: mu > 0 (design §2(a): "AND mu > 0")
            admitted_candidate = (mu >= threshold) & (mu > 0)
        elif config.mad_k is not None:
            threshold = _mad_floor(mu, config.mad_k)
            # BL-4 side-condition: mu > 0 (design §2(b): "AND mu > 0")
            admitted_candidate = (mu >= threshold) & (mu > 0)
        else:
            # No candidate formula specified; use baseline as candidate too
            threshold = config.baseline_floor
            admitted_candidate = admitted_baseline

        # Rank: descending (1 = highest mu)
        rank = mu.rank(ascending=False, method="min")

        bar_result = group.copy()
        bar_result["rank"] = rank
        bar_result["floor_threshold"] = threshold
        bar_result["admitted_baseline"] = admitted_baseline
        bar_result["admitted_candidate"] = admitted_candidate
        results.append(bar_result)

    if not results:
        return scores_df.head(0).assign(
            rank=pd.Series(dtype=float),
            floor_threshold=pd.Series(dtype=float),
            admitted_baseline=pd.Series(dtype=bool),
            admitted_candidate=pd.Series(dtype=bool),
        )

    return pd.concat(results, ignore_index=True)


# ---------------------------------------------------- parameter calibration


def calibrate_parameter(
    scores_df: pd.DataFrame,
    config: ReplayConfig,
    *,
    tol: float = BREADTH_TOL,
    max_iter: int = 100,
) -> float:
    """Binary-search for the quantile_k or mad_k that matches baseline breadth.

    Finds the parameter value such that the mean per-day candidate admission
    count is within ``tol`` of the mean baseline admission count.  This is the
    core of the matched-breadth protocol: any return delta between arms is
    attributable to the floor FORMULA, not a different admission rate.

    Returns the calibrated parameter value.  Raises ValueError if the search
    fails to converge.
    """
    if scores_df.empty:
        raise ValueError("no dates with sufficient breadth for calibration")

    # Compute mean baseline breadth first
    baseline_breadths: list[int] = []
    for _date, group in scores_df.groupby("date"):
        if len(group) < config.min_breadth:
            continue
        mu = group["mu"].astype(float)
        baseline_breadths.append(int((mu >= config.baseline_floor).sum()))

    if not baseline_breadths:
        raise ValueError("no dates with sufficient breadth for calibration")

    target = float(np.mean(baseline_breadths))
    is_quantile = config.quantile_k is not None

    def _mean_admission(k: float) -> float:
        trial = ReplayConfig(
            quantile_k=k if is_quantile else None,
            mad_k=None if is_quantile else k,
            baseline_floor=config.baseline_floor,
            min_breadth=config.min_breadth,
        )
        admitted = apply_floor(scores_df, trial)
        if admitted.empty:
            return 0.0
        counts = admitted.groupby("date")["admitted_candidate"].sum()
        return float(counts.mean())

    lo, hi = 0.01, 0.99 if is_quantile else 5.0
    for _ in range(max_iter):
        mid = (lo + hi) / 2
        n_mid = _mean_admission(mid)
        if abs(n_mid - target) <= tol:
            return mid
        if is_quantile:
            if n_mid < target:
                lo = mid
            else:
                hi = mid
        else:
            if n_mid < target:
                hi = mid
            else:
                lo = mid

    raise ValueError(
        f"calibration did not converge after {max_iter} iterations "
        f"(target={target:.1f}, last={n_mid:.1f}, param={mid:.4f})"
    )


# ---------------------------------------------------------- matched breadth


def matched_breadth_compare(admitted_df: pd.DataFrame) -> dict[str, Any]:
    """Match candidate admitted set to baseline breadth and compare returns.

    For each day:
    1. Count baseline admitted names (N_baseline).
    2. From the candidate-admitted names, take the top-N_baseline by mu
       (matched breadth — the M4-b protocol).
    3. Compute mean forward return for both sets.

    Returns aggregate statistics including:
    - per_day_stats: list of per-day dicts
    - mean_baseline_breadth: average daily baseline admission count
    - mean_candidate_breadth: average daily candidate admission count
        (before matching)
    - daily_return_baseline / daily_return_candidate: arrays of per-day
      mean forward returns for bootstrap input
    - summary: aggregate comparison statistics
    """
    if admitted_df.empty:
        return {
            "per_day_stats": [],
            "mean_baseline_breadth": 0.0,
            "mean_candidate_breadth": 0.0,
            "daily_return_baseline": np.array([]),
            "daily_return_candidate": np.array([]),
            "summary": {},
        }

    # Determine return column (prefer fwd_20d, the primary horizon per §4)
    ret_col = None
    for col in ("fwd_20d", "fwd_60d", "fwd_10d", "fwd_5d"):
        if col in admitted_df.columns:
            ret_col = col
            break

    per_day: list[dict[str, Any]] = []
    daily_ret_base: list[float] = []
    daily_ret_cand: list[float] = []
    baseline_breadths: list[int] = []
    candidate_breadths: list[int] = []

    for date, group in admitted_df.groupby("date"):
        base_mask = group["admitted_baseline"].astype(bool)
        cand_mask = group["admitted_candidate"].astype(bool)

        n_base = int(base_mask.sum())
        n_cand = int(cand_mask.sum())
        baseline_breadths.append(n_base)
        candidate_breadths.append(n_cand)

        day_stat: dict[str, Any] = {
            "date": date,
            "n_baseline": n_base,
            "n_candidate": n_cand,
        }

        if ret_col is not None and ret_col in group.columns:
            # Baseline returns
            base_names = group.loc[base_mask]
            if not base_names.empty:
                base_rets = base_names[ret_col].dropna()
                day_stat["mean_ret_baseline"] = (
                    float(base_rets.mean()) if not base_rets.empty else None
                )
            else:
                day_stat["mean_ret_baseline"] = None

            # Candidate returns: match to baseline breadth (top-N by mu)
            cand_names = group.loc[cand_mask].sort_values("mu", ascending=False)
            if n_base > 0 and not cand_names.empty:
                matched_cand = cand_names.head(n_base)
                cand_rets = matched_cand[ret_col].dropna()
                day_stat["mean_ret_candidate"] = (
                    float(cand_rets.mean()) if not cand_rets.empty else None
                )
                day_stat["n_matched"] = len(matched_cand)
            else:
                day_stat["mean_ret_candidate"] = None
                day_stat["n_matched"] = 0

            if (day_stat["mean_ret_baseline"] is not None
                    and day_stat["mean_ret_candidate"] is not None):
                daily_ret_base.append(day_stat["mean_ret_baseline"])
                daily_ret_cand.append(day_stat["mean_ret_candidate"])
        else:
            day_stat["mean_ret_baseline"] = None
            day_stat["mean_ret_candidate"] = None

        per_day.append(day_stat)

    base_arr = np.asarray(daily_ret_base, dtype=float)
    cand_arr = np.asarray(daily_ret_cand, dtype=float)

    summary: dict[str, Any] = {}
    if len(base_arr) > 0:
        summary["pooled_mean_baseline"] = float(base_arr.mean())
        summary["pooled_mean_candidate"] = float(cand_arr.mean())
        summary["pooled_delta"] = float(cand_arr.mean() - base_arr.mean())
        summary["n_resolved_dates"] = len(base_arr)
        summary["return_column"] = ret_col
    else:
        summary["n_resolved_dates"] = 0

    return {
        "per_day_stats": per_day,
        "mean_baseline_breadth": (
            float(np.mean(baseline_breadths)) if baseline_breadths else 0.0
        ),
        "mean_candidate_breadth": (
            float(np.mean(candidate_breadths)) if candidate_breadths else 0.0
        ),
        "daily_return_baseline": base_arr,
        "daily_return_candidate": cand_arr,
        "summary": summary,
    }


# -------------------------------------------------------- bootstrap CI


def block_bootstrap_ci(
    daily_returns: np.ndarray,
    *,
    n_boot: int = N_BOOT_DEFAULT,
    block_size: int = BLOCK_PRIMARY,
    seed: int = SEED,
    alpha: float = 0.025,
) -> dict[str, Any]:
    """Block bootstrap confidence interval for mean daily returns.

    Uses ``expkit.stats.block_bootstrap_conditional_mean`` (the gap-respecting
    block bootstrap, C2/C3 bit-identical). The ``block_size`` controls temporal
    dependence — block-5 is the primary (design §4; M3 measured block-13
    degenerate at the expected sample size).

    Returns a dict with CI bounds, bootstrap SE, and admissibility info.
    """
    vals = np.asarray(daily_returns, dtype=float)
    n = int(np.sum(np.isfinite(vals)))

    result: dict[str, Any] = {
        "n_dates": n,
        "block_size": block_size,
        "n_boot": n_boot,
    }

    if n < 2:
        result["admissible"] = False
        result["reason"] = "fewer than 2 finite values"
        return result

    admissible = bootstrap_admissible(n, block_size)
    result["admissible"] = admissible

    if not admissible:
        result["reason"] = (
            f"date-block bootstrap refused: usable blocks "
            f"{n // block_size} < {4} (V3 method note)"
        )
        # Fall back to simple mean + std for reporting
        fin = vals[np.isfinite(vals)]
        result["mean"] = float(fin.mean())
        result["std"] = float(fin.std(ddof=1))
        return result

    # Full mask (unconditional mean)
    in_cell = np.ones(len(vals), dtype=bool)
    boot_means = block_bootstrap_conditional_mean(
        vals, in_cell, block=block_size, n_boot=n_boot, seed=seed,
    )

    if boot_means is None or len(boot_means) == 0:
        result["admissible"] = False
        result["reason"] = "bootstrap returned no finite resamples"
        return result

    summary = summarize_boot(boot_means, alpha_one_sided=alpha)
    if summary is not None:
        result.update(summary)
    result["mean"] = float(vals[np.isfinite(vals)].mean())
    return result


def block_bootstrap_diff_ci(
    baseline_returns: np.ndarray,
    candidate_returns: np.ndarray,
    *,
    n_boot: int = N_BOOT_DEFAULT,
    block_size: int = BLOCK_PRIMARY,
    seed: int = SEED,
    alpha: float = 0.025,
) -> dict[str, Any]:
    """Block bootstrap CI on the paired difference (candidate - baseline).

    The paired-difference design preserves temporal correlation structure and
    is the correct comparison for matched-breadth arms (design §4 statistics:
    "computed via the paired daily difference series ... not two separate CIs
    compared by eye").
    """
    base = np.asarray(baseline_returns, dtype=float)
    cand = np.asarray(candidate_returns, dtype=float)

    if len(base) != len(cand):
        return {"error": "baseline and candidate return arrays differ in length"}

    diff = cand - base
    return block_bootstrap_ci(
        diff, n_boot=n_boot, block_size=block_size, seed=seed, alpha=alpha,
    )


# ------------------------------------------------------------------- CLI


def _render_report(comparison: dict[str, Any], ci: dict[str, Any]) -> str:
    """Render a human-readable text report."""
    lines = [
        "# M4-b Matched-Breadth Conviction Floor Replay",
        "",
    ]

    summary = comparison.get("summary", {})
    lines.append(f"Resolved dates:       {summary.get('n_resolved_dates', 0)}")
    lines.append(
        f"Mean baseline breadth:  {comparison.get('mean_baseline_breadth', 0):.1f}"
    )
    lines.append(
        f"Mean candidate breadth: {comparison.get('mean_candidate_breadth', 0):.1f}"
    )

    if "pooled_mean_baseline" in summary:
        lines += [
            "",
            f"Baseline mean return:  {summary['pooled_mean_baseline']:+.4f}",
            f"Candidate mean return: {summary['pooled_mean_candidate']:+.4f}",
            f"Delta (cand - base):   {summary['pooled_delta']:+.4f}",
            f"Return column:         {summary.get('return_column', 'n/a')}",
        ]

    if ci:
        lines += ["", "## Bootstrap CI (paired difference)"]
        lines.append(f"  Admissible:  {ci.get('admissible', False)}")
        lines.append(f"  N dates:     {ci.get('n_dates', 0)}")
        lines.append(f"  Block size:  {ci.get('block_size', 0)}")
        if "ci95_two_sided" in ci:
            lo, hi = ci["ci95_two_sided"]
            lines.append(f"  95% CI:      [{lo:+.4f}, {hi:+.4f}]")
            excludes_zero = (lo > 0) or (hi < 0)
            lines.append(
                f"  Excludes 0:  {'YES' if excludes_zero else 'no'}"
            )
        if "boot_se" in ci:
            lines.append(f"  Boot SE:     {ci['boot_se']:.4f}")
        if "mean" in ci:
            lines.append(f"  Mean diff:   {ci['mean']:+.4f}")
        if "reason" in ci:
            lines.append(f"  Note:        {ci['reason']}")

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for the M4-b conviction-floor replay harness."""
    parser = argparse.ArgumentParser(
        description=(
            "M4-b matched-breadth conviction-floor replay harness. "
            "Evaluates candidate floor formulas against stored production runs."
        ),
    )
    parser.add_argument(
        "--db", type=Path, default=None,
        help="Path to runs.alpaca.db (read-only; default: auto-resolved)",
    )
    parser.add_argument("--start-date", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end-date", default=None, help="End date (YYYY-MM-DD)")
    parser.add_argument(
        "--quantile-k", type=float, default=None,
        help="Candidate (a) quantile K: admit top-K%% of mu per bar",
    )
    parser.add_argument(
        "--mad-k", type=float, default=None,
        help="Candidate (b) dispersion k: admit mu >= k*MAD(bar mu)",
    )
    parser.add_argument(
        "--baseline-floor", type=float, default=BASELINE_FLOOR,
        help=f"Baseline absolute floor (default: {BASELINE_FLOOR})",
    )
    parser.add_argument(
        "--min-breadth", type=int, default=10,
        help="Minimum per-bar candidate count (default: 10)",
    )
    parser.add_argument(
        "--n-boot", type=int, default=N_BOOT_DEFAULT,
        help=f"Bootstrap resamples (default: {N_BOOT_DEFAULT})",
    )
    parser.add_argument(
        "--block-size", type=int, default=BLOCK_PRIMARY,
        help=f"Block bootstrap block size (default: {BLOCK_PRIMARY})",
    )
    parser.add_argument(
        "--calibrate", action="store_true",
        help="Calibrate the candidate parameter (quantile_k or mad_k) to match "
             "baseline admission rate before comparing returns. This is the "
             "matched-breadth protocol: without it, the harness compares at "
             "the fixed parameter value (exploratory, not matched).",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Output path for JSON results",
    )
    parser.add_argument(
        "--json", action="store_true", dest="as_json",
        help="Print JSON output to stdout",
    )

    args = parser.parse_args(argv)

    db_path = args.db or DEFAULT_DB
    if not Path(db_path).exists():
        print(f"ERROR: DB not found: {db_path}", file=sys.stderr)
        return 1

    config = ReplayConfig(
        quantile_k=args.quantile_k,
        mad_k=args.mad_k,
        baseline_floor=args.baseline_floor,
        start_date=args.start_date,
        end_date=args.end_date,
        min_breadth=args.min_breadth,
        n_boot=args.n_boot,
        block_size=args.block_size,
    )

    # Load scores
    scores = load_candidate_scores(
        db_path,
        start_date=config.start_date,
        end_date=config.end_date,
    )
    if scores.empty:
        print("No candidate scores found in the specified window.", file=sys.stderr)
        return 1

    if args.calibrate and config.quantile_k is None and config.mad_k is None:
        print(
            "ERROR: --calibrate requires --quantile-k or --mad-k to select which "
            "formula to calibrate (the given value is only used to pick the "
            "formula -- calibration replaces it). Without one of these, "
            "--calibrate silently compares the baseline against itself.",
            file=sys.stderr,
        )
        return 1

    # Calibrate parameter to matched breadth if requested
    if args.calibrate and (config.quantile_k is not None or config.mad_k is not None):
        calibrated_k = calibrate_parameter(scores, config)
        if config.quantile_k is not None:
            config = ReplayConfig(**{**asdict(config), "quantile_k": calibrated_k})
        else:
            config = ReplayConfig(**{**asdict(config), "mad_k": calibrated_k})

    # Apply floor
    admitted = apply_floor(scores, config)

    # Matched-breadth comparison
    comparison = matched_breadth_compare(admitted)

    # Bootstrap CI on the paired difference
    ci: dict[str, Any] = {}
    base_rets = comparison["daily_return_baseline"]
    cand_rets = comparison["daily_return_candidate"]
    if len(base_rets) >= 2 and len(cand_rets) >= 2:
        ci = block_bootstrap_diff_ci(
            base_rets, cand_rets,
            n_boot=config.n_boot,
            block_size=config.block_size,
            seed=config.seed,
        )

    # Output
    result = {
        "calibrated": args.calibrate and (
            config.quantile_k is not None or config.mad_k is not None
        ),
        "config": asdict(config),
        "comparison": {
            "per_day_stats": comparison["per_day_stats"],
            "mean_baseline_breadth": comparison["mean_baseline_breadth"],
            "mean_candidate_breadth": comparison["mean_candidate_breadth"],
            "summary": comparison["summary"],
        },
        "bootstrap_ci": ci,
    }

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, default=str) + "\n")
        print(f"Results written to {args.output}")

    if args.as_json:
        json.dump(result, sys.stdout, indent=2, default=str)
        sys.stdout.write("\n")
    elif not args.output:
        print(_render_report(comparison, ci))

    return 0


if __name__ == "__main__":
    sys.exit(main())
