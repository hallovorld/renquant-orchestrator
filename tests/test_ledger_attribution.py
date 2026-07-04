"""Tests for the decision-ledger attribution engine (107 skeleton)."""
from __future__ import annotations

import pytest

from renquant_orchestrator.decision_ledger import write_verdicts
from renquant_orchestrator.ledger_attribution import (
    connect_attribution,
    gate_information_value,
    gate_value_report,
    outcome_coverage,
    write_outcomes,
)


def _db():
    return connect_attribution(":memory:")


def _seed_verdicts(conn):
    write_verdicts(conn, "run-001", "2026-07-01", [
        {"scope": "daily", "gate": "P-WF-GATE", "verdict": "allow", "reason": "clean"},
        {"scope": "daily", "gate": "P-VOL-GATE", "verdict": "block", "reason": "vol>60%"},
    ])
    write_verdicts(conn, "run-002", "2026-07-02", [
        {"scope": "daily", "gate": "P-WF-GATE", "verdict": "block", "reason": "placebo leak"},
        {"scope": "daily", "gate": "P-VOL-GATE", "verdict": "allow", "reason": "vol ok"},
    ])


def _seed_outcomes(conn):
    write_outcomes(conn, [
        {
            "as_of": "2026-07-01", "scope": "daily", "ticker": "AAPL",
            "gate": "P-WF-GATE", "verdict": "allow",
            "fwd_5d_ret": 0.02, "fwd_20d_ret": 0.05, "fwd_60d_ret": 0.08,
            "entry_price": 200.0, "recorded_at": "2026-08-01T00:00:00Z",
        },
        {
            "as_of": "2026-07-01", "scope": "daily", "ticker": "MSFT",
            "gate": "P-VOL-GATE", "verdict": "block",
            "fwd_5d_ret": -0.03, "fwd_20d_ret": -0.07, "fwd_60d_ret": -0.10,
            "entry_price": 450.0, "recorded_at": "2026-08-01T00:00:00Z",
        },
        {
            "as_of": "2026-07-02", "scope": "daily", "ticker": "GOOG",
            "gate": "P-WF-GATE", "verdict": "block",
            "fwd_5d_ret": -0.01, "fwd_20d_ret": -0.02, "fwd_60d_ret": 0.01,
            "entry_price": 180.0, "recorded_at": "2026-08-01T00:00:00Z",
        },
        {
            "as_of": "2026-07-02", "scope": "daily", "ticker": "AMZN",
            "gate": "P-VOL-GATE", "verdict": "allow",
            "fwd_5d_ret": 0.01, "fwd_20d_ret": 0.03, "fwd_60d_ret": 0.06,
            "entry_price": 200.0, "recorded_at": "2026-08-01T00:00:00Z",
        },
    ])


def test_write_outcomes_returns_count() -> None:
    conn = _db()
    n = write_outcomes(conn, [
        {
            "as_of": "2026-07-01", "scope": "daily", "ticker": "AAPL",
            "gate": "G1", "verdict": "allow",
            "fwd_20d_ret": 0.05, "recorded_at": "2026-08-01T00:00:00Z",
        },
    ])
    assert n == 1


def test_write_outcomes_idempotent() -> None:
    conn = _db()
    outcome = {
        "as_of": "2026-07-01", "scope": "daily", "ticker": "AAPL",
        "gate": "G1", "verdict": "allow",
        "fwd_20d_ret": 0.05, "recorded_at": "2026-08-01T00:00:00Z",
    }
    assert write_outcomes(conn, [outcome]) == 1
    assert write_outcomes(conn, [outcome]) == 0


def test_gate_value_report_basic() -> None:
    conn = _db()
    _seed_outcomes(conn)
    report = gate_value_report(conn, horizon=20)
    by_key = {(r["gate"], r["verdict"]): r for r in report}

    assert ("P-WF-GATE", "allow") in by_key
    assert ("P-WF-GATE", "block") in by_key
    assert by_key[("P-WF-GATE", "allow")]["avg_fwd_ret"] == pytest.approx(0.05)
    assert by_key[("P-WF-GATE", "block")]["avg_fwd_ret"] == pytest.approx(-0.02)
    assert by_key[("P-WF-GATE", "allow")]["hit_rate"] == pytest.approx(1.0)
    assert by_key[("P-WF-GATE", "block")]["hit_rate"] == pytest.approx(0.0)


def test_gate_value_report_filters_by_gate() -> None:
    conn = _db()
    _seed_outcomes(conn)
    report = gate_value_report(conn, horizon=20, gate="P-VOL-GATE")
    gates = {r["gate"] for r in report}
    assert gates == {"P-VOL-GATE"}


def test_gate_value_report_filters_by_date_range() -> None:
    conn = _db()
    _seed_outcomes(conn)
    report = gate_value_report(
        conn, horizon=20, start_date="2026-07-02", end_date="2026-07-02",
    )
    assert all(r["n"] == 1 for r in report)


def test_gate_value_report_invalid_horizon() -> None:
    conn = _db()
    with pytest.raises(ValueError, match="horizon must be"):
        gate_value_report(conn, horizon=10)


def test_gate_information_value_positive_means_gate_helps() -> None:
    conn = _db()
    _seed_outcomes(conn)
    voi = gate_information_value(conn, "P-WF-GATE", horizon=20)
    assert voi["gate"] == "P-WF-GATE"
    assert voi["allow_n"] == 1
    assert voi["block_n"] == 1
    assert voi["value_of_information"] == pytest.approx(0.07)
    assert voi["allow_avg_ret"] == pytest.approx(0.05)
    assert voi["block_avg_ret"] == pytest.approx(-0.02)


def test_gate_information_value_vol_gate() -> None:
    conn = _db()
    _seed_outcomes(conn)
    voi = gate_information_value(conn, "P-VOL-GATE", horizon=20)
    assert voi["value_of_information"] == pytest.approx(0.10)


def test_outcome_coverage_reports_join_ratio() -> None:
    conn = _db()
    _seed_verdicts(conn)
    _seed_outcomes(conn)
    cov = outcome_coverage(conn, "2026-07-01", "2026-07-02")
    assert len(cov) == 2
    for row in cov:
        assert row["n_verdicts"] >= 1
        assert 0 <= row["coverage_ratio"] <= 1.0


def test_outcome_coverage_bounded_with_multi_ticker_outcomes() -> None:
    """coverage_ratio must not exceed 1.0 even when multiple tickers have
    outcomes for the same gate|scope on one date."""
    conn = _db()
    _seed_verdicts(conn)
    _seed_outcomes(conn)
    write_outcomes(conn, [
        {
            "as_of": "2026-07-01", "scope": "daily", "ticker": "GOOG",
            "gate": "P-WF-GATE", "verdict": "allow",
            "fwd_20d_ret": 0.03, "recorded_at": "2026-08-01T00:00:00Z",
        },
        {
            "as_of": "2026-07-01", "scope": "daily", "ticker": "AMZN",
            "gate": "P-WF-GATE", "verdict": "allow",
            "fwd_20d_ret": 0.04, "recorded_at": "2026-08-01T00:00:00Z",
        },
    ])
    cov = outcome_coverage(conn, "2026-07-01", "2026-07-01")
    assert len(cov) == 1
    assert cov[0]["coverage_ratio"] == pytest.approx(1.0)
    assert cov[0]["n_verdicts"] == 2
    assert cov[0]["n_covered"] == 2


def test_outcome_coverage_collapses_same_day_reruns_by_design() -> None:
    """Two same-day runs (distinct run_id) of the same gate/scope must NOT be
    double-counted as 2 separate covered decisions from one outcome cluster.

    decision_outcomes carries no run_id (an outcome is a per-ticker realized
    market return, not tied to which run evaluated the gate), so there is no
    principled way to attribute the one outcome record to run-001 specifically
    and not run-002. The metric intentionally collapses same-day reruns of a
    (scope, gate) into one (as_of, scope, gate) unit — asserting n_covered=2
    here would be the exact overclaim Codex flagged (one outcome cluster
    "covering" two distinct runs)."""
    conn = _db()
    write_verdicts(conn, "run-001", "2026-07-01", [
        {"scope": "daily", "gate": "P-WF-GATE", "verdict": "allow", "reason": "ok"},
    ])
    write_verdicts(conn, "run-002", "2026-07-01", [
        {"scope": "daily", "gate": "P-WF-GATE", "verdict": "block", "reason": "rerun"},
    ])
    write_outcomes(conn, [
        {
            "as_of": "2026-07-01", "scope": "daily", "ticker": "AAPL",
            "gate": "P-WF-GATE", "verdict": "allow",
            "fwd_20d_ret": 0.02, "recorded_at": "2026-08-01T00:00:00Z",
        },
    ])
    cov = outcome_coverage(conn, "2026-07-01", "2026-07-01")
    assert len(cov) == 1
    assert cov[0]["n_verdicts"] == 1
    assert cov[0]["n_covered"] == 1
    assert cov[0]["coverage_ratio"] == pytest.approx(1.0)


def test_outcome_coverage_partial_when_gate_missing_outcomes() -> None:
    """If only one of two gates has outcome records, ratio is 0.5."""
    conn = _db()
    _seed_verdicts(conn)
    write_outcomes(conn, [
        {
            "as_of": "2026-07-01", "scope": "daily", "ticker": "AAPL",
            "gate": "P-WF-GATE", "verdict": "allow",
            "fwd_20d_ret": 0.02, "recorded_at": "2026-08-01T00:00:00Z",
        },
    ])
    cov = outcome_coverage(conn, "2026-07-01", "2026-07-01")
    assert len(cov) == 1
    assert cov[0]["coverage_ratio"] == pytest.approx(0.5)
    assert cov[0]["n_verdicts"] == 2
    assert cov[0]["n_covered"] == 1


def test_outcome_coverage_empty_db() -> None:
    conn = _db()
    cov = outcome_coverage(conn, "2026-07-01", "2026-07-02")
    assert cov == []


def test_multiple_horizons() -> None:
    conn = _db()
    _seed_outcomes(conn)
    for h in (5, 20, 60):
        report = gate_value_report(conn, horizon=h)
        assert len(report) > 0


def test_write_outcomes_with_metadata() -> None:
    conn = _db()
    n = write_outcomes(conn, [
        {
            "as_of": "2026-07-01", "scope": "daily", "ticker": "AAPL",
            "gate": "G1", "verdict": "allow",
            "fwd_20d_ret": 0.05, "recorded_at": "2026-08-01T00:00:00Z",
            "metadata": {"source": "price_db", "adj_type": "split"},
        },
    ])
    assert n == 1
    cur = conn.execute("SELECT metadata_json FROM decision_outcomes")
    row = cur.fetchone()
    import json
    meta = json.loads(row[0])
    assert meta["source"] == "price_db"
