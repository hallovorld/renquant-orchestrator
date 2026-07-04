"""Tests for the sign-laundering measurement harness (M4-b)."""
from __future__ import annotations

import json
import sqlite3

import pytest

from renquant_orchestrator.sign_laundering_harness import (
    _estimate_neutral_raw_from_scores,
    _find_neutral_raw_from_calibrator,
    audit_laundering_history,
    main,
    measure_sign_laundering,
)


def _write_scorer(tmp_path, candidates, fmt="dict"):
    path = tmp_path / "scorer.json"
    if fmt == "dict":
        path.write_text(json.dumps({"candidates": candidates}))
    elif fmt == "list":
        path.write_text(json.dumps({"scores": candidates}))
    return path


def _write_calibrator(tmp_path, breakpoints=None, intercept=None, slope=None):
    path = tmp_path / "calibrator.json"
    cal = {}
    if breakpoints is not None:
        cal["breakpoints"] = breakpoints
    if intercept is not None:
        cal["intercept"] = intercept
    if slope is not None:
        cal["slope"] = slope
    path.write_text(json.dumps(cal))
    return path


class TestFindNeutralRawFromCalibrator:
    def test_breakpoints_linear_cross(self, tmp_path):
        bp = [{"raw": -0.5, "mu": -0.03}, {"raw": -0.29, "mu": 0.0}, {"raw": 0.0, "mu": 0.02}]
        path = _write_calibrator(tmp_path, breakpoints=bp)
        assert _find_neutral_raw_from_calibrator(path) == pytest.approx(-0.29, abs=1e-6)

    def test_breakpoints_interpolation(self, tmp_path):
        bp = [{"raw": -0.4, "mu": -0.02}, {"raw": -0.2, "mu": 0.01}]
        path = _write_calibrator(tmp_path, breakpoints=bp)
        neutral = _find_neutral_raw_from_calibrator(path)
        assert neutral is not None and -0.4 < neutral < -0.2

    def test_intercept_slope_fallback(self, tmp_path):
        path = _write_calibrator(tmp_path, intercept=0.05, slope=0.2)
        assert _find_neutral_raw_from_calibrator(path) == pytest.approx(-0.25, abs=1e-6)

    def test_no_info_returns_none(self, tmp_path):
        assert _find_neutral_raw_from_calibrator(_write_calibrator(tmp_path)) is None


class TestEstimateNeutralFromScores:
    def test_finds_sign_change(self):
        by_ticker = {"A": {"raw": -0.35, "mu": -0.02}, "B": {"raw": -0.25, "mu": 0.01}}
        neutral = _estimate_neutral_raw_from_scores(by_ticker)
        assert neutral is not None and -0.35 < neutral < -0.25

    def test_no_sign_change(self):
        assert _estimate_neutral_raw_from_scores({"A": {"raw": -0.35, "mu": 0.01}, "B": {"raw": -0.25, "mu": 0.02}}) is None

    def test_insufficient_data(self):
        assert _estimate_neutral_raw_from_scores({"A": {"raw": -0.3, "mu": 0.01}}) is None


class TestMeasureSignLaundering:
    def test_typical_laundering(self, tmp_path):
        candidates = {
            "AAPL": {"raw_score": -0.15, "mu": 0.02, "sigma": 0.20},
            "GOOG": {"raw_score": -0.35, "mu": -0.01, "sigma": 0.18},
            "MSFT": {"raw_score": 0.10, "mu": 0.03, "sigma": 0.15},
            "AMZN": {"raw_score": -0.10, "mu": 0.01, "sigma": 0.22},
        }
        result = measure_sign_laundering(_write_scorer(tmp_path, candidates), neutral_raw_override=-0.29)
        assert result["total_names"] == 4
        assert result["laundered_count"] == 2
        assert set(result["laundered_names"]) == {"AAPL", "AMZN"}
        assert result["laundering_rate"] == pytest.approx(0.5)
        assert result["by_ticker"]["AAPL"]["laundered"] is True
        assert result["by_ticker"]["GOOG"]["laundered"] is False

    def test_all_above_neutral(self, tmp_path):
        candidates = {"AAPL": {"raw_score": 0.10, "mu": 0.03, "sigma": 0.20}, "GOOG": {"raw_score": 0.20, "mu": 0.05, "sigma": 0.18}}
        result = measure_sign_laundering(_write_scorer(tmp_path, candidates), neutral_raw_override=-0.29)
        assert result["laundered_count"] == 0

    def test_all_below_neutral(self, tmp_path):
        candidates = {"AAPL": {"raw_score": -0.40, "mu": -0.03, "sigma": 0.20}, "GOOG": {"raw_score": -0.50, "mu": -0.05, "sigma": 0.18}}
        result = measure_sign_laundering(_write_scorer(tmp_path, candidates), neutral_raw_override=-0.29)
        assert result["laundered_count"] == 0

    def test_with_calibrator(self, tmp_path):
        scorer = _write_scorer(tmp_path, {"AAPL": {"raw_score": -0.15, "mu": 0.02, "sigma": 0.20}, "GOOG": {"raw_score": -0.35, "mu": -0.01, "sigma": 0.18}})
        cal = _write_calibrator(tmp_path, breakpoints=[{"raw": -0.4, "mu": -0.02}, {"raw": -0.29, "mu": 0.0}, {"raw": 0.0, "mu": 0.03}])
        result = measure_sign_laundering(scorer, calibrator_path=cal)
        assert result["neutral_raw"] == pytest.approx(-0.29, abs=1e-6)
        assert result["laundered_count"] == 1

    def test_list_format(self, tmp_path):
        candidates = [{"ticker": "AAPL", "raw_score": -0.15, "mu": 0.02, "sigma": 0.20}, {"ticker": "GOOG", "raw_score": -0.35, "mu": -0.01, "sigma": 0.18}]
        result = measure_sign_laundering(_write_scorer(tmp_path, candidates, fmt="list"), neutral_raw_override=-0.29)
        assert result["total_names"] == 2 and result["laundered_count"] == 1

    def test_override_takes_precedence(self, tmp_path):
        scorer = _write_scorer(tmp_path, {"AAPL": {"raw_score": -0.05, "mu": 0.01, "sigma": 0.20}})
        cal = _write_calibrator(tmp_path, breakpoints=[{"raw": -0.4, "mu": -0.02}, {"raw": -0.29, "mu": 0.0}])
        result = measure_sign_laundering(scorer, calibrator_path=cal, neutral_raw_override=-0.10)
        assert result["neutral_raw"] == -0.10 and result["laundered_count"] == 1

    def test_auto_detect(self, tmp_path):
        candidates = {"A": {"raw_score": -0.35, "mu": -0.02, "sigma": 0.2}, "B": {"raw_score": -0.25, "mu": 0.01, "sigma": 0.2}, "C": {"raw_score": -0.28, "mu": 0.005, "sigma": 0.2}}
        result = measure_sign_laundering(_write_scorer(tmp_path, candidates))
        assert result["neutral_raw"] is not None and -0.35 < result["neutral_raw"] < -0.25

    def test_empty_scorer(self, tmp_path):
        result = measure_sign_laundering(_write_scorer(tmp_path, {}), neutral_raw_override=-0.29)
        assert result["total_names"] == 0 and result["laundering_rate"] == 0.0

    def test_rank_score_fallback(self, tmp_path):
        result = measure_sign_laundering(_write_scorer(tmp_path, {"AAPL": {"rank_score": -0.15, "mu": 0.02, "sigma": 0.20}}), neutral_raw_override=-0.29)
        assert result["by_ticker"]["AAPL"]["raw"] == -0.15

    def test_positive_neutral(self, tmp_path):
        candidates = {"A": {"raw_score": 0.05, "mu": -0.01, "sigma": 0.2}, "B": {"raw_score": 0.15, "mu": 0.02, "sigma": 0.2}}
        result = measure_sign_laundering(_write_scorer(tmp_path, candidates), neutral_raw_override=0.10)
        assert result["laundered_count"] == 1 and "A" in result["laundered_names"]


@pytest.fixture()
def laundering_db(tmp_path):
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE pipeline_runs (run_id TEXT PRIMARY KEY, run_date DATE, run_type TEXT, regime TEXT, portfolio_value REAL)")
    conn.execute("CREATE TABLE candidate_scores (run_id TEXT, ticker TEXT, role TEXT, kelly_target_pct REAL, qp_target_w REAL, mu REAL, sigma REAL, rank_score REAL, blocked_by TEXT, selected INTEGER, qp_status TEXT)")
    conn.execute("INSERT INTO pipeline_runs VALUES (?, ?, ?, ?, ?)", ("run-1", "2026-06-30", "live", "BULL_CALM", 100000))
    conn.execute("INSERT INTO pipeline_runs VALUES (?, ?, ?, ?, ?)", ("run-2", "2026-07-01", "live", "BULL_CALM", 101000))
    scores = [
        ("run-1", "AAPL", "candidate", None, None, -0.02, 0.20, -0.35, None, 1, None),
        ("run-1", "GOOG", "candidate", None, None, 0.01, 0.18, -0.25, None, 1, None),
        ("run-1", "MSFT", "candidate", None, None, 0.02, 0.15, -0.15, None, 1, None),
        ("run-1", "AMZN", "candidate", None, None, 0.03, 0.22, 0.10, None, 1, None),
        ("run-2", "AAPL", "candidate", None, None, -0.01, 0.20, -0.40, None, 1, None),
        ("run-2", "GOOG", "candidate", None, None, 0.02, 0.18, -0.10, None, 1, None),
        ("run-2", "MSFT", "candidate", None, None, 0.01, 0.15, -0.20, None, 1, None),
    ]
    conn.executemany("INSERT INTO candidate_scores VALUES (?,?,?,?,?,?,?,?,?,?,?)", scores)
    conn.commit()
    conn.close()
    return db_path


def test_audit_history_basic(laundering_db):
    records = audit_laundering_history(db_path=laundering_db, n_runs=10)
    assert len(records) == 2
    for r in records:
        assert "laundered_count" in r and r["neutral_raw"] < 0


def test_audit_history_n_runs_limit(laundering_db):
    records = audit_laundering_history(db_path=laundering_db, n_runs=1)
    assert len(records) == 1 and records[0]["run_date"] == "2026-07-01"


def test_audit_history_empty_db(tmp_path):
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE pipeline_runs (run_id TEXT PRIMARY KEY, run_date DATE, run_type TEXT, regime TEXT, portfolio_value REAL)")
    conn.execute("CREATE TABLE candidate_scores (run_id TEXT, ticker TEXT, role TEXT, kelly_target_pct REAL, qp_target_w REAL, mu REAL, sigma REAL, rank_score REAL, blocked_by TEXT, selected INTEGER, qp_status TEXT)")
    conn.commit()
    conn.close()
    assert audit_laundering_history(db_path=db_path) == []


class TestCli:
    def test_measure_text(self, tmp_path, capsys):
        rc = main(["measure", str(_write_scorer(tmp_path, {"AAPL": {"raw_score": -0.15, "mu": 0.02, "sigma": 0.20}, "GOOG": {"raw_score": -0.35, "mu": -0.01, "sigma": 0.18}})), "--neutral-raw", "-0.29"])
        assert "Sign-Laundering Report" in capsys.readouterr().out and rc == 1

    def test_measure_json(self, tmp_path, capsys):
        rc = main(["measure", str(_write_scorer(tmp_path, {"AAPL": {"raw_score": -0.15, "mu": 0.02, "sigma": 0.20}})), "--neutral-raw", "-0.29", "--json"])
        data = json.loads(capsys.readouterr().out)
        assert "laundered_count" in data and rc == 1

    def test_measure_low_rate(self, tmp_path):
        candidates = {f"T{i}": {"raw_score": 0.10 + i * 0.01, "mu": 0.02, "sigma": 0.2} for i in range(20)}
        assert main(["measure", str(_write_scorer(tmp_path, candidates)), "--neutral-raw", "-0.29"]) == 0

    def test_history_text(self, laundering_db, capsys):
        rc = main(["history", "--db", str(laundering_db)])
        assert "Sign-Laundering History" in capsys.readouterr().out and rc == 0

    def test_history_json(self, laundering_db, capsys):
        rc = main(["history", "--db", str(laundering_db), "--json"])
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list) and len(data) == 2 and rc == 0
