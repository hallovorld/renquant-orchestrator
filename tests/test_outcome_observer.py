"""Tests for outcome_observer — S5 Path B forward-outcome scheduled observer."""
from __future__ import annotations

import datetime
import sqlite3

import pytest

from renquant_orchestrator.ledger_attribution import connect_attribution, write_outcomes
from renquant_orchestrator.decision_ledger import connect, write_verdicts
from renquant_orchestrator.outcome_observer import (
    CALENDAR_BUFFER,
    HORIZONS,
    MAX_HORIZON,
    _trading_days_after,
    observe_outcomes,
    pending_decisions,
)


@pytest.fixture
def ledger_db():
    conn = connect_attribution(":memory:")
    yield conn
    conn.close()


@pytest.fixture
def runs_db():
    conn = sqlite3.connect(":memory:")
    conn.executescript("""
    CREATE TABLE candidate_scores (
        run_date TEXT, ticker TEXT, close_price REAL,
        blocked_by TEXT, selected INTEGER DEFAULT 0
    );
    CREATE TABLE ticker_forward_returns (
        run_date TEXT, ticker TEXT,
        fwd_5d_ret REAL, fwd_20d_ret REAL, fwd_60d_ret REAL
    );
    """)
    yield conn
    conn.close()


def _write_decision(ledger_db, as_of, scope, gate, verdict="allow"):
    write_verdicts(ledger_db, run_id=f"run-{as_of}", as_of=as_of, verdicts=[
        {"scope": scope, "gate": gate, "verdict": verdict,
         "reason": "test", "inputs": {}},
    ])


def _write_candidate(runs_db, run_date, ticker, close_price):
    runs_db.execute(
        "INSERT INTO candidate_scores (run_date, ticker, close_price) VALUES (?,?,?)",
        (run_date, ticker, close_price),
    )
    runs_db.commit()


def _write_fwd_returns(runs_db, run_date, ticker, fwd_5d=None, fwd_20d=None, fwd_60d=None):
    runs_db.execute(
        "INSERT INTO ticker_forward_returns VALUES (?,?,?,?,?)",
        (run_date, ticker, fwd_5d, fwd_20d, fwd_60d),
    )
    runs_db.commit()


class TestTradingDaysAfter:
    def test_weekday_skip(self):
        result = _trading_days_after("2026-07-01", 1)
        assert result == "2026-07-02"

    def test_weekend_skip(self):
        result = _trading_days_after("2026-07-03", 1)
        assert result == "2026-07-06"

    def test_five_days(self):
        result = _trading_days_after("2026-07-01", 5)
        assert result == "2026-07-08"

    def test_custom_calendar(self):
        def cal(d, n):
            return "2026-12-31"
        assert _trading_days_after("2026-01-01", 5, cal) == "2026-12-31"


class TestPendingDecisions:
    def test_empty_ledger(self, ledger_db):
        assert pending_decisions(ledger_db) == []

    def test_recent_decisions_excluded(self, ledger_db):
        today = datetime.date.today().isoformat()
        _write_decision(ledger_db, today, "AAPL", "ConvictionGate")
        result = pending_decisions(ledger_db)
        assert len(result) == 0

    def test_old_decisions_returned(self, ledger_db):
        old = (datetime.date.today() - datetime.timedelta(days=CALENDAR_BUFFER + 1)).isoformat()
        _write_decision(ledger_db, old, "AAPL", "ConvictionGate")
        result = pending_decisions(ledger_db)
        assert len(result) == 1
        assert result[0]["scope"] == "AAPL"
        assert result[0]["gate"] == "ConvictionGate"

    def test_already_observed_excluded(self, ledger_db):
        old = (datetime.date.today() - datetime.timedelta(days=CALENDAR_BUFFER + 1)).isoformat()
        _write_decision(ledger_db, old, "AAPL", "ConvictionGate")
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        write_outcomes(ledger_db, [{
            "as_of": old, "scope": "AAPL", "ticker": "AAPL",
            "gate": "ConvictionGate", "verdict": "allow",
            "fwd_5d_ret": 0.01, "fwd_20d_ret": 0.02, "fwd_60d_ret": 0.05,
            "entry_price": 100.0, "exit_price_5d": 101.0,
            "exit_price_20d": 102.0, "exit_price_60d": 105.0,
            "recorded_at": now, "metadata": {},
        }])
        result = pending_decisions(ledger_db)
        assert len(result) == 0

    def test_max_as_of_filter(self, ledger_db):
        _write_decision(ledger_db, "2025-01-01", "AAPL", "ConvictionGate")
        _write_decision(ledger_db, "2025-06-01", "MSFT", "VolGate")
        result = pending_decisions(ledger_db, max_as_of="2025-03-01")
        assert len(result) == 1
        assert result[0]["scope"] == "AAPL"


class TestObserveOutcomes:
    def test_no_pending(self, ledger_db, runs_db):
        result = observe_outcomes(ledger_db, runs_db)
        assert result == []

    def test_writes_outcomes_from_fwd_returns(self, ledger_db, runs_db):
        old = (datetime.date.today() - datetime.timedelta(days=CALENDAR_BUFFER + 1)).isoformat()
        _write_decision(ledger_db, old, "AAPL", "ConvictionGate")
        _write_candidate(runs_db, old, "AAPL", 150.0)
        _write_fwd_returns(runs_db, old, "AAPL", fwd_5d=0.02, fwd_20d=0.05, fwd_60d=0.10)

        result = observe_outcomes(ledger_db, runs_db, max_as_of=old)
        assert len(result) == 1
        r = result[0]
        assert r["ticker"] == "AAPL"
        assert r["fwd_5d_ret"] == 0.02
        assert r["fwd_20d_ret"] == 0.05
        assert r["fwd_60d_ret"] == 0.10
        assert r["entry_price"] == 150.0
        assert abs(r["exit_price_5d"] - 153.0) < 0.01
        assert abs(r["exit_price_20d"] - 157.5) < 0.01
        assert abs(r["exit_price_60d"] - 165.0) < 0.01

    def test_dry_run_no_write(self, ledger_db, runs_db):
        old = (datetime.date.today() - datetime.timedelta(days=CALENDAR_BUFFER + 1)).isoformat()
        _write_decision(ledger_db, old, "AAPL", "ConvictionGate")
        _write_fwd_returns(runs_db, old, "AAPL", fwd_5d=0.01, fwd_20d=0.03, fwd_60d=0.08)

        result = observe_outcomes(ledger_db, runs_db, dry_run=True, max_as_of=old)
        assert len(result) == 1

        still_pending = pending_decisions(ledger_db, max_as_of=old)
        assert len(still_pending) == 1

    def test_idempotent(self, ledger_db, runs_db):
        old = (datetime.date.today() - datetime.timedelta(days=CALENDAR_BUFFER + 1)).isoformat()
        _write_decision(ledger_db, old, "AAPL", "ConvictionGate")
        _write_fwd_returns(runs_db, old, "AAPL", fwd_5d=0.01, fwd_20d=0.03, fwd_60d=0.08)

        r1 = observe_outcomes(ledger_db, runs_db, max_as_of=old)
        assert len(r1) == 1
        r2 = observe_outcomes(ledger_db, runs_db, max_as_of=old)
        assert len(r2) == 0

    def test_no_fwd_returns_skipped(self, ledger_db, runs_db):
        old = (datetime.date.today() - datetime.timedelta(days=CALENDAR_BUFFER + 1)).isoformat()
        _write_decision(ledger_db, old, "AAPL", "ConvictionGate")
        _write_candidate(runs_db, old, "AAPL", 150.0)

        result = observe_outcomes(ledger_db, runs_db, max_as_of=old)
        assert len(result) == 0

    def test_partial_fwd_returns_accepted(self, ledger_db, runs_db):
        old = (datetime.date.today() - datetime.timedelta(days=CALENDAR_BUFFER + 1)).isoformat()
        _write_decision(ledger_db, old, "AAPL", "ConvictionGate")
        _write_fwd_returns(runs_db, old, "AAPL", fwd_5d=0.01, fwd_20d=None, fwd_60d=None)

        result = observe_outcomes(ledger_db, runs_db, max_as_of=old)
        assert len(result) == 1
        assert result[0]["fwd_5d_ret"] == 0.01
        assert result[0]["fwd_20d_ret"] is None

    def test_multiple_gates_per_ticker(self, ledger_db, runs_db):
        old = (datetime.date.today() - datetime.timedelta(days=CALENDAR_BUFFER + 1)).isoformat()
        _write_decision(ledger_db, old, "AAPL", "ConvictionGate")
        _write_decision(ledger_db, old, "AAPL", "VolGate", verdict="block")
        _write_fwd_returns(runs_db, old, "AAPL", fwd_5d=0.01, fwd_20d=0.03, fwd_60d=0.06)

        result = observe_outcomes(ledger_db, runs_db, max_as_of=old)
        assert len(result) == 2
        gates = {r["gate"] for r in result}
        assert gates == {"ConvictionGate", "VolGate"}

    def test_book_scope_skipped_for_prices(self, ledger_db, runs_db):
        old = (datetime.date.today() - datetime.timedelta(days=CALENDAR_BUFFER + 1)).isoformat()
        _write_decision(ledger_db, old, "book", "WfSanityGate")
        result = observe_outcomes(ledger_db, runs_db, max_as_of=old)
        assert len(result) == 0

    def test_multiple_dates(self, ledger_db, runs_db):
        old1 = (datetime.date.today() - datetime.timedelta(days=CALENDAR_BUFFER + 10)).isoformat()
        old2 = (datetime.date.today() - datetime.timedelta(days=CALENDAR_BUFFER + 5)).isoformat()
        _write_decision(ledger_db, old1, "AAPL", "ConvictionGate")
        _write_decision(ledger_db, old2, "MSFT", "ConvictionGate")
        _write_fwd_returns(runs_db, old1, "AAPL", fwd_5d=0.01, fwd_20d=0.02, fwd_60d=0.05)
        _write_fwd_returns(runs_db, old2, "MSFT", fwd_5d=-0.01, fwd_20d=-0.02, fwd_60d=-0.03)

        result = observe_outcomes(ledger_db, runs_db, max_as_of=old2)
        assert len(result) == 2
        tickers = {r["ticker"] for r in result}
        assert tickers == {"AAPL", "MSFT"}


class TestConstants:
    def test_horizons(self):
        assert HORIZONS == (5, 20, 60)

    def test_max_horizon(self):
        assert MAX_HORIZON == 60

    def test_calendar_buffer(self):
        assert CALENDAR_BUFFER == 96
