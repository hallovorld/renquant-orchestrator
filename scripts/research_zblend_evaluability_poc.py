#!/usr/bin/env python3
"""Read-only audit of whether a daily zblend comparison is evaluable.

This is deliberately not a return backtest.  It verifies that a claimed
panel-versus-blend daily comparison has an independent baseline, describes the
two score books, and reports whether the requested forward label has matured.
It writes one deterministic JSON artifact and never mutates either run bundle.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any, Optional


MIN_FULL_RUN_CANDIDATES = 80
DEFAULT_TOP_K = 10
DEFAULT_OUTCOME_COLUMN = "fwd_60d"


def _connect_read_only(path: Path) -> sqlite3.Connection:
    """Open the run bundle read-only; analysis must not create journal files."""
    return sqlite3.connect(f"file:{path.resolve()}?mode=ro&immutable=1", uri=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def _latest_full_run(conn: sqlite3.Connection, run_date: str) -> dict[str, str]:
    row = conn.execute(
        """
        SELECT p.run_id, p.run_date, p.created_at
        FROM pipeline_runs AS p
        JOIN (
            SELECT run_id, COUNT(*) AS candidate_count
            FROM candidate_scores
            GROUP BY run_id
        ) AS c ON c.run_id = p.run_id
        WHERE p.run_type = 'live'
          AND p.run_date = ?
          AND c.candidate_count >= ?
        ORDER BY p.created_at DESC, p.run_id DESC
        LIMIT 1
        """,
        (run_date, MIN_FULL_RUN_CANDIDATES),
    ).fetchone()
    if row is None:
        raise ValueError(
            f"No full live run with at least {MIN_FULL_RUN_CANDIDATES} candidates "
            f"for {run_date}."
        )
    return {"run_id": str(row[0]), "run_date": str(row[1])[:10], "created_at": str(row[2])}


def _load_scores(conn: sqlite3.Connection, run_id: str) -> dict[str, dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT ticker, panel_score, active_scorer
        FROM candidate_scores
        WHERE run_id = ? AND panel_score IS NOT NULL
        """,
        (run_id,),
    ).fetchall()
    if not rows:
        raise ValueError(f"Run {run_id} has no finite panel_score rows.")
    return {
        str(ticker): {"score": float(score), "active_scorer": str(scorer or "")}
        for ticker, score, scorer in rows
        if score is not None and math.isfinite(float(score))
    }


def _top_k(scores: dict[str, dict[str, Any]], top_k: int) -> list[str]:
    return [
        ticker
        for ticker, _ in sorted(
            scores.items(), key=lambda item: (-float(item[1]["score"]), item[0])
        )[:top_k]
    ]


def _average_ranks(values: dict[str, float]) -> dict[str, float]:
    """Ascending average ranks for Spearman correlation, including ties."""
    ranked = sorted(values.items(), key=lambda item: (item[1], item[0]))
    ranks: dict[str, float] = {}
    index = 0
    while index < len(ranked):
        end = index + 1
        while end < len(ranked) and ranked[end][1] == ranked[index][1]:
            end += 1
        average_rank = (index + 1 + end) / 2.0
        for ticker, _ in ranked[index:end]:
            ranks[ticker] = average_rank
        index = end
    return ranks


def _pearson(left: list[float], right: list[float]) -> Optional[float]:
    if len(left) < 2:
        return None
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    left_scale = math.sqrt(sum((x - left_mean) ** 2 for x in left))
    right_scale = math.sqrt(sum((y - right_mean) ** 2 for y in right))
    if left_scale == 0 or right_scale == 0:
        return None
    return numerator / (left_scale * right_scale)


def _score_comparison(
    prod_scores: dict[str, dict[str, Any]], blend_scores: dict[str, dict[str, Any]], top_k: int
) -> dict[str, Any]:
    prod_names = set(prod_scores)
    blend_names = set(blend_scores)
    common = sorted(prod_names & blend_names)
    prod_top = _top_k(prod_scores, top_k)
    blend_top = _top_k(blend_scores, top_k)
    prod_rank = _average_ranks({ticker: prod_scores[ticker]["score"] for ticker in common})
    blend_rank = _average_ranks({ticker: blend_scores[ticker]["score"] for ticker in common})
    rank_correlation = _pearson(
        [prod_rank[ticker] for ticker in common], [blend_rank[ticker] for ticker in common]
    )
    deltas = [abs(prod_scores[ticker]["score"] - blend_scores[ticker]["score"]) for ticker in common]
    union_size = len(prod_names | blend_names)
    top_union = set(prod_top) | set(blend_top)
    return {
        "blend_candidate_count": len(blend_names),
        "common_candidate_count": len(common),
        "mean_absolute_score_delta": round(sum(deltas) / len(deltas), 12),
        "prod_candidate_count": len(prod_names),
        "rank_correlation_spearman": None if rank_correlation is None else round(rank_correlation, 12),
        "top_k": top_k,
        "top_k_intersection_count": len(set(prod_top) & set(blend_top)),
        "top_k_jaccard": round(len(set(prod_top) & set(blend_top)) / len(top_union), 12),
        "top_k_overlap": sorted(set(prod_top) & set(blend_top)),
        "top_k_prod": prod_top,
        "top_k_blend": blend_top,
        "universe_jaccard": round(len(common) / union_size, 12) if union_size else None,
    }


def _outcome_readiness(conn: sqlite3.Connection, run_date: str, outcome_column: str) -> dict[str, Any]:
    columns = _table_columns(conn, "ticker_forward_returns")
    if outcome_column not in columns:
        return {"status": "COLUMN_MISSING", "outcome_column": outcome_column, "finite_value_count": 0}
    row = conn.execute(
        f"SELECT COUNT({outcome_column}) FROM ticker_forward_returns WHERE as_of_date = ?",
        (run_date,),
    ).fetchone()
    count = int(row[0] or 0)
    return {
        "finite_value_count": count,
        "outcome_column": outcome_column,
        "status": "MATURED" if count else "UNMATURED",
    }


def audit(
    prod_db: Path,
    blend_db: Path,
    run_date: str,
    top_k: int = DEFAULT_TOP_K,
    outcome_column: str = DEFAULT_OUTCOME_COLUMN,
) -> dict[str, Any]:
    """Return a provenance-bearing descriptive audit for one requested date."""
    with _connect_read_only(prod_db) as prod_conn, _connect_read_only(blend_db) as blend_conn:
        prod_run = _latest_full_run(prod_conn, run_date)
        blend_run = _latest_full_run(blend_conn, run_date)
        prod_scores = _load_scores(prod_conn, prod_run["run_id"])
        blend_scores = _load_scores(blend_conn, blend_run["run_id"])
        readiness = _outcome_readiness(prod_conn, run_date, outcome_column)

    prod_observed = Counter(row["active_scorer"] for row in prod_scores.values() if row["active_scorer"])
    blend_observed = Counter(row["active_scorer"] for row in blend_scores.values() if row["active_scorer"])
    prod_scorers = sorted(prod_observed)
    blend_scorers = sorted(blend_observed)
    reasons: list[str] = []
    if prod_scorers != ["panel"]:
        reasons.append("production_arm_is_not_an_independent_panel_baseline")
    if blend_scorers != ["blend"]:
        reasons.append("shadow_arm_is_not_an_unambiguous_blend_treatment")
    if readiness["status"] != "MATURED":
        reasons.append("requested_forward_outcome_is_not_mature")

    return {
        "audit_kind": "zblend_daily_evaluability",
        "evaluation_status": "NOT_EVALUABLE" if reasons else "DESCRIPTIVE_ONLY_SINGLE_SESSION",
        "not_evaluable_reasons": reasons,
        "outcome_readiness": readiness,
        "production": {
            "active_scorer_missing_score_count": len(prod_scores) - sum(prod_observed.values()),
            "active_scorer_observed_counts": dict(sorted(prod_observed.items())),
            "active_scorers": prod_scorers,
            "db_name": prod_db.name,
            "db_sha256": _sha256(prod_db),
            "run": prod_run,
        },
        "score_comparison": _score_comparison(prod_scores, blend_scores, top_k),
        "shadow": {
            "active_scorer_missing_score_count": len(blend_scores) - sum(blend_observed.values()),
            "active_scorer_observed_counts": dict(sorted(blend_observed.items())),
            "active_scorers": blend_scorers,
            "db_name": blend_db.name,
            "db_sha256": _sha256(blend_db),
            "run": blend_run,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prod-db", required=True, type=Path)
    parser.add_argument("--blend-db", required=True, type=Path)
    parser.add_argument("--run-date", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K)
    parser.add_argument("--outcome-column", default=DEFAULT_OUTCOME_COLUMN)
    args = parser.parse_args()
    if args.top_k < 1:
        parser.error("--top-k must be positive")

    result = audit(args.prod_db, args.blend_db, args.run_date, args.top_k, args.outcome_column)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
