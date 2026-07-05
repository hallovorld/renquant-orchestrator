"""Tests for decision outcome validator — gate accuracy measurement."""
from __future__ import annotations

import json
import sqlite3

import pytest

from renquant_orchestrator.decision_ledger import DDL as LEDGER_DDL
from renquant_orchestrator.decision_outcome_validator import (
    GateAccuracy,
    compute_gate_accuracy,
    load_joined_data,
    main,
    validate,
)
from renquant_orchestrator.ledger_attribution import OUTCOMES_DDL


def _make_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.executescript(LEDGER_DDL)
    conn.executescript(OUTCOMES_DDL)
    return conn


def _insert_ledger(conn, as_of, scope, gate, verdict, reason="test"):
    conn.execute(
        "INSERT OR IGNORE INTO decision_ledger VALUES (?,?,?,?,?,?,?)",
        (f"run-{as_of}", as_of, scope, gate, verdict, reason, "{}"),
    )
    conn.commit()


def _insert_outcome(conn, as_of, scope, ticker, gate, verdict,
                    fwd_5d=None, fwd_20d=None, fwd_60d=None):
    conn.execute(
        "INSERT OR IGNORE INTO decision_outcomes VALUES "
        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (as_of, scope, ticker, gate, verdict,
         fwd_5d, fwd_20d, fwd_60d,
         100.0, None, None, None,
         "2026-07-04T00:00:00Z", "{}"),
    )
    conn.commit()


def _populate_good_gate(conn):
    """Gate correctly allows winners and blocks losers."""
    for i in range(6):
        date = f"2026-06-{10 + i:02d}"
        _insert_ledger(conn, date, "book", "ConvictionGate", "allow")
        _insert_outcome(conn, date, "book", f"WIN{i}", "ConvictionGate",
                        "allow", fwd_20d=0.02 + i * 0.005)
    for i in range(4):
        date = f"2026-06-{20 + i:02d}"
        _insert_ledger(conn, date, "book", "ConvictionGate", "block")
        _insert_outcome(conn, date, "book", f"LOSE{i}", "ConvictionGate",
                        "block", fwd_20d=-0.03 - i * 0.005)


def _populate_over_restrictive_gate(conn):
    """Gate blocks too many profitable trades (but allowed avg > blocked avg)."""
    for i in range(5):
        date = f"2026-06-{10 + i:02d}"
        _insert_ledger(conn, date, "book", "VolGate", "allow")
        _insert_outcome(conn, date, "book", f"A{i}", "VolGate",
                        "allow", fwd_20d=0.04)
    for i in range(7):
        date = f"2026-06-{20 + i:02d}"
        _insert_ledger(conn, date, "book", "VolGate", "block")
        ret = 0.015 if i < 5 else -0.03
        _insert_outcome(conn, date, "book", f"B{i}", "VolGate",
                        "block", fwd_20d=ret)


def _populate_under_restrictive_gate(conn):
    """Gate allows too many losing trades."""
    for i in range(8):
        date = f"2026-06-{10 + i:02d}"
        _insert_ledger(conn, date, "book", "WashSale", "allow")
        ret = -0.02 if i < 5 else 0.03
        _insert_outcome(conn, date, "book", f"A{i}", "WashSale",
                        "allow", fwd_20d=ret)
    for i in range(2):
        date = f"2026-06-{20 + i:02d}"
        _insert_ledger(conn, date, "book", "WashSale", "block")
        _insert_outcome(conn, date, "book", f"B{i}", "WashSale",
                        "block", fwd_20d=-0.05)


def _populate_value_destructive_gate(conn):
    """Gate is value-destructive: blocked outperform allowed."""
    for i in range(5):
        date = f"2026-06-{10 + i:02d}"
        _insert_ledger(conn, date, "book", "BadGate", "allow")
        _insert_outcome(conn, date, "book", f"A{i}", "BadGate",
                        "allow", fwd_20d=-0.03)
    for i in range(5):
        date = f"2026-06-{20 + i:02d}"
        _insert_ledger(conn, date, "book", "BadGate", "block")
        _insert_outcome(conn, date, "book", f"B{i}", "BadGate",
                        "block", fwd_20d=0.05)


class TestComputeGateAccuracy:
    def test_correct_gate(self):
        conn = _make_db()
        _populate_good_gate(conn)
        rows = load_joined_data(conn, horizon=20)
        ga = compute_gate_accuracy(rows, "ConvictionGate")
        assert ga.verdict == "PASS"
        assert ga.allow_n == 6
        assert ga.block_n == 4
        assert ga.allow_profitable == 6
        assert ga.block_profitable == 0
        assert ga.accuracy == 1.0
        assert ga.value_of_gate is not None and ga.value_of_gate > 0

    def test_over_restrictive_gate(self):
        conn = _make_db()
        _populate_over_restrictive_gate(conn)
        rows = load_joined_data(conn, horizon=20)
        ga = compute_gate_accuracy(rows, "VolGate")
        assert ga.verdict == "OVER_RESTRICTIVE"
        assert ga.block_profitable == 5
        assert ga.block_n == 7

    def test_under_restrictive_gate(self):
        conn = _make_db()
        _populate_under_restrictive_gate(conn)
        rows = load_joined_data(conn, horizon=20)
        ga = compute_gate_accuracy(rows, "WashSale")
        assert ga.verdict == "UNDER_RESTRICTIVE"
        assert ga.allow_n == 8
        assert ga.allow_profitable == 3

    def test_value_destructive_gate(self):
        conn = _make_db()
        _populate_value_destructive_gate(conn)
        rows = load_joined_data(conn, horizon=20)
        ga = compute_gate_accuracy(rows, "BadGate")
        assert ga.verdict == "VALUE_DESTRUCTIVE"
        assert ga.value_of_gate is not None and ga.value_of_gate < 0

    def test_insufficient_data(self):
        conn = _make_db()
        _insert_ledger(conn, "2026-06-10", "book", "TinyGate", "allow")
        _insert_outcome(conn, "2026-06-10", "book", "X", "TinyGate",
                        "allow", fwd_20d=0.01)
        rows = load_joined_data(conn, horizon=20)
        ga = compute_gate_accuracy(rows, "TinyGate")
        assert ga.verdict == "INSUFFICIENT_DATA"

    def test_empty_rows(self):
        ga = compute_gate_accuracy([], "NoGate")
        assert ga.verdict == "INSUFFICIENT_DATA"
        assert ga.allow_n == 0
        assert ga.block_n == 0


class TestValidate:
    def test_multiple_gates(self):
        conn = _make_db()
        _populate_good_gate(conn)
        _populate_over_restrictive_gate(conn)
        report = validate(conn, horizon=20)
        assert report.total_joined_rows > 0
        assert len(report.gates) == 2
        gate_verdicts = {g.gate: g.verdict for g in report.gates}
        assert gate_verdicts["ConvictionGate"] == "PASS"
        assert gate_verdicts["VolGate"] == "OVER_RESTRICTIVE"
        assert report.overall_verdict == "WARNING"

    def test_all_pass(self):
        conn = _make_db()
        _populate_good_gate(conn)
        report = validate(conn, horizon=20)
        assert report.overall_verdict == "PASS"

    def test_value_destructive_is_fail(self):
        conn = _make_db()
        _populate_value_destructive_gate(conn)
        report = validate(conn, horizon=20)
        assert report.overall_verdict == "FAIL"

    def test_empty_db(self):
        conn = _make_db()
        report = validate(conn, horizon=20)
        assert report.overall_verdict == "INSUFFICIENT_DATA"
        assert report.total_joined_rows == 0

    def test_gate_filter(self):
        conn = _make_db()
        _populate_good_gate(conn)
        _populate_over_restrictive_gate(conn)
        report = validate(conn, horizon=20, gate="ConvictionGate")
        assert len(report.gates) == 1
        assert report.gates[0].gate == "ConvictionGate"

    def test_date_filter(self):
        conn = _make_db()
        _populate_good_gate(conn)
        report = validate(conn, horizon=20, start_date="2026-06-15")
        assert report.total_joined_rows < 10

    def test_horizon_5(self):
        conn = _make_db()
        for i in range(6):
            date = f"2026-06-{10 + i:02d}"
            _insert_ledger(conn, date, "book", "G", "allow")
            _insert_outcome(conn, date, "book", f"T{i}", "G",
                            "allow", fwd_5d=0.01)
        report = validate(conn, horizon=5)
        assert report.horizon == 5
        assert report.gates[0].allow_n == 6


class TestCLI:
    def test_missing_db(self, tmp_path, capsys):
        rc = main(["--db", str(tmp_path / "nope.db")])
        assert rc == 1
        assert "not found" in capsys.readouterr().err

    def test_missing_tables(self, tmp_path, capsys):
        db_path = tmp_path / "empty.db"
        sqlite3.connect(str(db_path)).close()
        rc = main(["--db", str(db_path)])
        assert rc == 1
        assert "decision_ledger" in capsys.readouterr().err

    def test_json_output(self, tmp_path, capsys):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(LEDGER_DDL)
        conn.executescript(OUTCOMES_DDL)
        _populate_good_gate(conn)
        conn.close()

        rc = main(["--db", str(db_path), "--json"])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["overall_verdict"] == "PASS"
        assert len(data["gates"]) == 1

    def test_strict_returns_nonzero_on_warning(self, tmp_path, capsys):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(LEDGER_DDL)
        conn.executescript(OUTCOMES_DDL)
        _populate_over_restrictive_gate(conn)
        conn.close()

        rc = main(["--db", str(db_path), "--strict"])
        assert rc == 2

    def test_text_output(self, tmp_path, capsys):
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(LEDGER_DDL)
        conn.executescript(OUTCOMES_DDL)
        _populate_good_gate(conn)
        conn.close()

        rc = main(["--db", str(db_path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "PASS" in out
        assert "ConvictionGate" in out
