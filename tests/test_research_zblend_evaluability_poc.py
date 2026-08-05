import importlib.util
import sqlite3
from pathlib import Path
from typing import Optional


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "research_zblend_evaluability_poc.py"
SPEC = importlib.util.spec_from_file_location("zblend_evaluability_poc", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def _create_db(path: Path, scorer: str, scores: dict[str, float], label: Optional[float]) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE pipeline_runs (run_id TEXT, run_date TEXT, run_type TEXT, created_at TEXT);
        CREATE TABLE candidate_scores (run_id TEXT, ticker TEXT, panel_score REAL, active_scorer TEXT);
        CREATE TABLE ticker_forward_returns (as_of_date TEXT, ticker TEXT, fwd_60d REAL);
        """
    )
    conn.execute(
        "INSERT INTO pipeline_runs VALUES ('run-1', '2026-08-04', 'live', '2026-08-04 21:00:00')"
    )
    conn.executemany(
        "INSERT INTO candidate_scores VALUES ('run-1', ?, ?, ?)",
        [(ticker, score, scorer) for ticker, score in scores.items()],
    )
    conn.executemany(
        "INSERT INTO ticker_forward_returns VALUES ('2026-08-04', ?, ?)",
        [(ticker, label) for ticker in scores],
    )
    conn.commit()
    conn.close()


def _scores(offset: float = 0.0) -> dict[str, float]:
    return {f"T{index:03d}": float(index) + offset for index in range(80)}


def test_audit_rejects_contaminated_baseline_and_unmatured_outcome(tmp_path: Path) -> None:
    prod = tmp_path / "prod.db"
    blend = tmp_path / "blend.db"
    _create_db(prod, "blend", _scores(), None)
    _create_db(blend, "blend", _scores(0.1), None)

    result = MODULE.audit(prod, blend, "2026-08-04")

    assert result["evaluation_status"] == "NOT_EVALUABLE"
    assert result["not_evaluable_reasons"] == [
        "production_arm_is_not_an_independent_panel_baseline",
        "requested_forward_outcome_is_not_mature",
    ]
    assert result["production"]["active_scorer_observed_counts"] == {"blend": 80}
    assert result["score_comparison"]["top_k_intersection_count"] == 10
    assert result["score_comparison"]["rank_correlation_spearman"] == 1.0


def test_audit_marks_single_mature_independent_session_descriptive_only(tmp_path: Path) -> None:
    prod = tmp_path / "prod.db"
    blend = tmp_path / "blend.db"
    _create_db(prod, "panel", _scores(), 0.02)
    _create_db(blend, "blend", _scores(0.1), 0.02)

    result = MODULE.audit(prod, blend, "2026-08-04", top_k=5)

    assert result["evaluation_status"] == "DESCRIPTIVE_ONLY_SINGLE_SESSION"
    assert result["not_evaluable_reasons"] == []
    assert result["outcome_readiness"] == {
        "finite_value_count": 80,
        "outcome_column": "fwd_60d",
        "status": "MATURED",
    }
    assert len(result["production"]["db_sha256"]) == 64
