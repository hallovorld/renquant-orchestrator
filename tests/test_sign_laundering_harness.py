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


def _write_calibrator(tmp_path, xs=None, ys=None):
    """Real calibrator artifact shape: ``expected_return: {"x": [...], "y": [...]}``
    (verified against a live artifact — NOT "breakpoints"/"intercept"+"slope")."""
    path = tmp_path / "calibrator.json"
    er = {}
    if xs is not None:
        er["x"] = xs
    if ys is not None:
        er["y"] = ys
    path.write_text(json.dumps({"expected_return": er}))
    return path


class TestFindNeutralRawFromCalibrator:
    def test_exact_zero_knot(self, tmp_path):
        path = _write_calibrator(
            tmp_path, xs=[-0.5, -0.29, 0.0], ys=[-0.03, 0.0, 0.02],
        )
        assert _find_neutral_raw_from_calibrator(path) == pytest.approx(-0.29, abs=1e-6)

    def test_interpolation(self, tmp_path):
        path = _write_calibrator(tmp_path, xs=[-0.4, -0.2], ys=[-0.02, 0.01])
        neutral = _find_neutral_raw_from_calibrator(path)
        assert neutral is not None and -0.4 < neutral < -0.2

    def test_never_crosses_returns_none(self, tmp_path):
        path = _write_calibrator(tmp_path, xs=[-0.5, -0.3, -0.1], ys=[-0.03, -0.02, -0.01])
        assert _find_neutral_raw_from_calibrator(path) is None

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
        cal = _write_calibrator(tmp_path, xs=[-0.4, -0.29, 0.0], ys=[-0.02, 0.0, 0.03])
        result = measure_sign_laundering(scorer, calibrator_path=cal)
        assert result["neutral_raw"] == pytest.approx(-0.29, abs=1e-6)
        assert result["laundered_count"] == 1

    def test_list_format(self, tmp_path):
        candidates = [{"ticker": "AAPL", "raw_score": -0.15, "mu": 0.02, "sigma": 0.20}, {"ticker": "GOOG", "raw_score": -0.35, "mu": -0.01, "sigma": 0.18}]
        result = measure_sign_laundering(_write_scorer(tmp_path, candidates, fmt="list"), neutral_raw_override=-0.29)
        assert result["total_names"] == 2 and result["laundered_count"] == 1

    def test_override_takes_precedence(self, tmp_path):
        scorer = _write_scorer(tmp_path, {"AAPL": {"raw_score": -0.05, "mu": 0.01, "sigma": 0.20}})
        cal = _write_calibrator(tmp_path, xs=[-0.4, -0.29], ys=[-0.02, 0.0])
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


def _make_db(tmp_path, name, runs, rows):
    """``runs``: list of (run_id, run_date). ``rows``: list of
    (run_id, ticker, raw_score, rank_score, mu)."""
    db_path = tmp_path / name
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE pipeline_runs (run_id TEXT PRIMARY KEY, run_date DATE, run_type TEXT, regime TEXT, portfolio_value REAL)")
    conn.execute("CREATE TABLE candidate_scores (run_id TEXT, ticker TEXT, role TEXT, kelly_target_pct REAL, qp_target_w REAL, mu REAL, sigma REAL, raw_score REAL, rank_score REAL, blocked_by TEXT, selected INTEGER, qp_status TEXT)")
    for run_id, run_date in runs:
        conn.execute(
            "INSERT INTO pipeline_runs VALUES (?, ?, ?, ?, ?)",
            (run_id, run_date, "live", "BULL_CALM", 100000),
        )
    conn.executemany(
        "INSERT INTO candidate_scores "
        "(run_id, ticker, role, mu, sigma, raw_score, rank_score, selected) "
        "VALUES (?,?,?,?,?,?,?,?)",
        [(run_id, ticker, "candidate", mu, 0.2, raw, rank, 1)
         for run_id, ticker, raw, rank, mu in rows],
    )
    conn.commit()
    conn.close()
    return db_path


@pytest.fixture()
def laundering_db(tmp_path):
    # raw_score is the real calibrator-input axis; rank_score is a decoy
    # field carrying deliberately different values so a test can prove the
    # harness reads raw_score, not rank_score (Codex review round 1).
    return _make_db(
        tmp_path, "test.db",
        runs=[("run-1", "2026-06-30"), ("run-2", "2026-07-01")],
        rows=[
            ("run-1", "AAPL", -0.35, -0.35, -0.02),
            ("run-1", "GOOG", -0.25, -0.35, 0.01),
            ("run-1", "MSFT", -0.15, 0.05, 0.02),
            ("run-1", "AMZN", 0.10, -0.20, 0.03),
            ("run-2", "AAPL", -0.40, -0.40, -0.01),
            ("run-2", "GOOG", -0.10, -0.10, 0.02),
            ("run-2", "MSFT", -0.20, -0.20, 0.01),
        ],
    )


def test_audit_history_basic(laundering_db):
    records = audit_laundering_history(db_path=laundering_db, n_runs=10)
    assert len(records) == 2
    for r in records:
        assert "laundered_count" in r and r["neutral_raw"] < 0
        assert r["neutral_raw_source"] == "per_run_estimate"


def test_audit_history_n_runs_limit(laundering_db):
    records = audit_laundering_history(db_path=laundering_db, n_runs=1)
    assert len(records) == 1 and records[0]["run_date"] == "2026-07-01"


def test_audit_history_uses_raw_score_not_rank_score(tmp_path):
    # neutral_raw=-0.29 (override, stable). Ground truth via raw_score:
    #   AAPL raw=-0.35 (< neutral, outside (neutral,0)) -> not laundered
    #   GOOG raw=-0.25 (in (-0.29,0)), mu=+0.01 -> LAUNDERED
    #   MSFT raw=-0.15 (in (-0.29,0)), mu=+0.02 -> LAUNDERED
    #   AMZN raw=+0.10 (outside (neutral,0))    -> not laundered
    # If the harness wrongly read rank_score instead: GOOG's rank_score
    # -0.35 falls outside the zone (would read not-laundered) and AMZN's
    # rank_score -0.20 falls inside with mu>0 (would read laundered) —
    # a different, wrong count (1 instead of 2).
    db_path = _make_db(
        tmp_path, "raw_vs_rank.db",
        runs=[("run-1", "2026-06-30")],
        rows=[
            ("run-1", "AAPL", -0.35, -0.35, -0.02),
            ("run-1", "GOOG", -0.25, -0.35, 0.01),
            ("run-1", "MSFT", -0.15, 0.05, 0.02),
            ("run-1", "AMZN", 0.10, -0.20, 0.03),
        ],
    )
    records = audit_laundering_history(
        db_path=db_path, n_runs=10, neutral_raw_override=-0.29,
    )
    assert len(records) == 1
    assert records[0]["laundered_count"] == 2
    assert records[0]["neutral_raw_source"] == "override"


def test_audit_history_calibrator_neutral_raw_stable_across_samples(tmp_path):
    # Two days with very different cross-sectional distributions (day 2's
    # scores are all shifted well positive) but calibrator-bound neutral_raw
    # must be IDENTICAL on both days — proving the reference doesn't drift
    # with the sample being audited, unlike the old per-run estimate.
    cal_path = _write_calibrator(
        tmp_path, xs=[-0.5, -0.29, 0.0], ys=[-0.03, 0.0, 0.02],
    )
    db_path = _make_db(
        tmp_path, "stable.db",
        runs=[("run-1", "2026-06-30"), ("run-2", "2026-07-01")],
        rows=[
            ("run-1", "AAPL", -0.35, -0.35, -0.02),
            ("run-1", "GOOG", -0.20, -0.20, 0.01),
            ("run-2", "MSFT", 0.50, 0.50, 0.02),
            ("run-2", "AMZN", 0.80, 0.80, 0.03),
        ],
    )
    records = audit_laundering_history(
        db_path=db_path, n_runs=10, calibrator_path=cal_path,
    )
    assert len(records) == 2
    neutrals = [r["neutral_raw"] for r in records]
    assert neutrals[0] == pytest.approx(-0.29, abs=1e-6)
    assert neutrals[1] == pytest.approx(-0.29, abs=1e-6)
    assert all(r["neutral_raw_source"] == "calibrator" for r in records)


def test_audit_history_empty_db(tmp_path):
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE pipeline_runs (run_id TEXT PRIMARY KEY, run_date DATE, run_type TEXT, regime TEXT, portfolio_value REAL)")
    conn.execute("CREATE TABLE candidate_scores (run_id TEXT, ticker TEXT, role TEXT, kelly_target_pct REAL, qp_target_w REAL, mu REAL, sigma REAL, raw_score REAL, rank_score REAL, blocked_by TEXT, selected INTEGER, qp_status TEXT)")
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
