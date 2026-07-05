"""Tests for gate threshold calibration diagnostic."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from renquant_orchestrator.gate_calibration_diagnostic import (
    CalibrationReport,
    GateDiagnostic,
    GateSpec,
    diagnose_gate,
    load_gates_from_config,
    main,
    render_report,
    run_diagnostic,
)


def _make_records(
    mus: list[float],
    n_runs: int = 5,
    *,
    ers: list[float] | None = None,
    ranks: list[float] | None = None,
) -> list[dict]:
    """Create synthetic candidate_scores records across n_runs runs."""
    records = []
    for run_idx in range(n_runs):
        run_id = f"run-{run_idx}"
        for i, mu in enumerate(mus):
            rec = {
                "run_id": run_id,
                "run_date": f"2026-06-{run_idx + 1:02d}",
                "ticker": f"TICK{i}",
                "mu": mu,
                "sigma": 0.10,
                "er": ers[i] if ers else mu * 0.5,
                "raw_score": mu * 2.0,
                "rank": ranks[i] if ranks else float(i + 1),
            }
            records.append(rec)
    return records


class TestDiagnoseGate:
    def test_pass_all_clear(self):
        records = _make_records([0.05, 0.10, 0.15], n_runs=10)
        gate = GateSpec("conviction", "mu", 0.03)
        diag = diagnose_gate(records, gate)
        assert diag.verdict == "PASS"
        assert diag.clearance_rate == 1.0
        assert diag.runs_with_clearance == 10
        assert diag.runs_total == 10

    def test_structural_block_threshold_above_max(self):
        records = _make_records([0.01, 0.02, 0.03], n_runs=10)
        gate = GateSpec("conviction", "mu", 0.50)
        diag = diagnose_gate(records, gate)
        assert diag.verdict == "STRUCTURAL_BLOCK"
        assert diag.clearance_rate == 0.0
        assert diag.runs_with_clearance == 0

    def test_marginal_some_runs_clear(self):
        base_records = _make_records([0.01, 0.02], n_runs=8)
        high_records = _make_records([0.10, 0.20], n_runs=2)
        for i, r in enumerate(high_records):
            r["run_id"] = f"high-{i // 2}"
            r["run_date"] = f"2026-07-{i + 1:02d}"
        records = base_records + high_records
        gate = GateSpec("conviction", "mu", 0.05)
        diag = diagnose_gate(records, gate)
        assert diag.verdict == "MARGINAL"
        assert 0.0 < diag.clearance_rate <= 0.50

    def test_empty_records(self):
        diag = diagnose_gate([], GateSpec("conviction", "mu", 0.03))
        assert diag.verdict == "STRUCTURAL_BLOCK"
        assert diag.runs_total == 0

    def test_below_direction(self):
        records = _make_records([0.01, 0.02], n_runs=5, ranks=[3.0, 5.0])
        gate = GateSpec("veto_rank", "rank", 4.0, direction="below")
        diag = diagnose_gate(records, gate)
        assert diag.verdict == "PASS"
        assert diag.runs_with_clearance == 5

    def test_percentiles_populated(self):
        records = _make_records([0.01, 0.05, 0.10, 0.15, 0.20], n_runs=5)
        gate = GateSpec("conviction", "mu", 0.03)
        diag = diagnose_gate(records, gate)
        assert "p50" in diag.score_percentiles
        assert "p95" in diag.score_percentiles
        assert diag.score_range[0] is not None
        assert diag.score_range[1] is not None

    def test_missing_column_values_skipped(self):
        records = [
            {"run_id": "r1", "ticker": "A", "mu": None, "sigma": 0.1},
            {"run_id": "r1", "ticker": "B", "mu": 0.05, "sigma": 0.1},
        ]
        gate = GateSpec("conviction", "mu", 0.03)
        diag = diagnose_gate(records, gate)
        assert diag.runs_total == 1
        assert diag.runs_with_clearance == 1


class TestLoadGatesFromConfig:
    def test_extracts_conviction_and_rotation(self, tmp_path):
        cfg = {
            "conviction_gate": {"mu_floor": 0.005},
            "rotation": {"initiate_threshold": 0.002},
            "veto_weak_buys": {"rank_floor": 10},
        }
        p = tmp_path / "config.json"
        p.write_text(json.dumps(cfg))
        gates = load_gates_from_config(p)
        names = [g.name for g in gates]
        assert "conviction_mu_floor" in names
        assert "rotation_initiate" in names
        assert "veto_rank_floor" in names
        veto = [g for g in gates if g.name == "veto_rank_floor"][0]
        assert veto.direction == "below"

    def test_empty_config(self, tmp_path):
        p = tmp_path / "config.json"
        p.write_text("{}")
        gates = load_gates_from_config(p)
        assert gates == []


class TestRunDiagnostic:
    def _setup_db(self, tmp_path, mus, n_runs=5):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""CREATE TABLE pipeline_runs (
            run_id TEXT PRIMARY KEY, run_date TEXT, run_type TEXT
        )""")
        conn.execute("""CREATE TABLE candidate_scores (
            run_id TEXT, ticker TEXT, mu REAL, sigma REAL,
            er REAL, raw_score REAL, rank REAL
        )""")
        for run_idx in range(n_runs):
            run_id = f"run-{run_idx}"
            conn.execute(
                "INSERT INTO pipeline_runs VALUES (?, ?, ?)",
                (run_id, f"2026-06-{run_idx + 1:02d}", "live"),
            )
            for i, mu in enumerate(mus):
                conn.execute(
                    "INSERT INTO candidate_scores VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (run_id, f"TICK{i}", mu, 0.10, mu * 0.5, mu * 2.0, float(i + 1)),
                )
        conn.commit()
        conn.close()
        return db

    def test_pass_from_db(self, tmp_path):
        db = self._setup_db(tmp_path, [0.05, 0.10, 0.15])
        gates = [GateSpec("conviction", "mu", 0.03)]
        report = run_diagnostic(db_path=db, gates=gates, n_runs=5)
        assert report.overall_verdict == "PASS"
        assert len(report.gates) == 1
        assert report.gates[0].clearance_rate == 1.0

    def test_structural_block_from_db(self, tmp_path):
        db = self._setup_db(tmp_path, [0.01, 0.02, 0.03])
        gates = [GateSpec("conviction", "mu", 0.50)]
        report = run_diagnostic(db_path=db, gates=gates, n_runs=5)
        assert report.overall_verdict == "STRUCTURAL_BLOCK"

    def test_multiple_gates_worst_wins(self, tmp_path):
        db = self._setup_db(tmp_path, [0.05, 0.10])
        gates = [
            GateSpec("conviction", "mu", 0.03),
            GateSpec("rotation", "er", 99.0),
        ]
        report = run_diagnostic(db_path=db, gates=gates, n_runs=5)
        assert report.overall_verdict == "STRUCTURAL_BLOCK"
        verdicts = {g.name: g.verdict for g in report.gates}
        assert verdicts["conviction"] == "PASS"
        assert verdicts["rotation"] == "STRUCTURAL_BLOCK"

    def test_no_gates_returns_empty(self, tmp_path):
        db = self._setup_db(tmp_path, [0.05])
        report = run_diagnostic(db_path=db, gates=[], n_runs=5)
        assert report.overall_verdict == "PASS"
        assert report.gates == []

    def test_config_path_extracts_gates(self, tmp_path):
        db = self._setup_db(tmp_path, [0.05, 0.10])
        cfg = {"conviction_gate": {"mu_floor": 0.03}}
        cfg_path = tmp_path / "config.json"
        cfg_path.write_text(json.dumps(cfg))
        report = run_diagnostic(db_path=db, config_path=cfg_path, n_runs=5)
        assert len(report.gates) == 1
        assert report.gates[0].name == "conviction_mu_floor"


class TestRenderReport:
    def test_renders_structural_block(self):
        report = CalibrationReport(
            db_path="/tmp/test.db",
            run_type="live",
            n_runs=10,
            overall_verdict="STRUCTURAL_BLOCK",
            gates=[
                GateDiagnostic(
                    name="conviction", column="mu", threshold=0.50,
                    direction="above", verdict="STRUCTURAL_BLOCK",
                    runs_total=10, runs_with_clearance=0,
                    clearance_rate=0.0, candidates_clearing_pct=0.0,
                    score_range=(0.01, 0.03),
                    score_percentiles={"p50": 0.02, "p95": 0.03},
                ),
            ],
        )
        text = render_report(report)
        assert "STRUCTURAL_BLOCK" in text
        assert "STRUCTURAL" in text
        assert "conviction" in text

    def test_renders_pass(self):
        report = CalibrationReport(
            db_path="/tmp/test.db", run_type="live", n_runs=5,
            overall_verdict="PASS", gates=[],
        )
        text = render_report(report)
        assert "PASS" in text


class TestCLI:
    def _setup_db(self, tmp_path, mus):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("""CREATE TABLE pipeline_runs (
            run_id TEXT PRIMARY KEY, run_date TEXT, run_type TEXT
        )""")
        conn.execute("""CREATE TABLE candidate_scores (
            run_id TEXT, ticker TEXT, mu REAL, sigma REAL,
            er REAL, raw_score REAL, rank REAL
        )""")
        for run_idx in range(3):
            run_id = f"run-{run_idx}"
            conn.execute(
                "INSERT INTO pipeline_runs VALUES (?, ?, ?)",
                (run_id, f"2026-06-{run_idx + 1:02d}", "live"),
            )
            for i, mu in enumerate(mus):
                conn.execute(
                    "INSERT INTO candidate_scores VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (run_id, f"TICK{i}", mu, 0.10, mu * 0.5, mu * 2.0, float(i + 1)),
                )
        conn.commit()
        conn.close()
        return db

    def test_cli_pass(self, tmp_path, capsys):
        db = self._setup_db(tmp_path, [0.05, 0.10])
        rc = main([
            "--db", str(db),
            "--gate", "conviction:mu:0.03",
        ])
        assert rc == 0
        out = capsys.readouterr().out
        assert "PASS" in out

    def test_cli_structural_block_exit_code(self, tmp_path, capsys):
        db = self._setup_db(tmp_path, [0.01, 0.02])
        rc = main([
            "--db", str(db),
            "--gate", "conviction:mu:0.50",
        ])
        assert rc == 2
        out = capsys.readouterr().out
        assert "STRUCTURAL_BLOCK" in out

    def test_cli_json_output(self, tmp_path, capsys):
        db = self._setup_db(tmp_path, [0.05, 0.10])
        rc = main([
            "--db", str(db),
            "--gate", "conviction:mu:0.03",
            "--json",
        ])
        assert rc == 0
        data = json.loads(capsys.readouterr().out)
        assert data["overall_verdict"] == "PASS"
        assert len(data["gates"]) == 1

    def test_cli_marginal_exit_code(self, tmp_path):
        db = self._setup_db(tmp_path, [0.01, 0.02])
        # Only 0 of 3 runs clear — structural, not marginal.
        # Make some runs clear to get marginal.
        conn = sqlite3.connect(str(db))
        conn.execute(
            "INSERT INTO pipeline_runs VALUES (?, ?, ?)",
            ("run-clear", "2026-07-01", "live"),
        )
        conn.execute(
            "INSERT INTO candidate_scores VALUES (?, ?, ?, ?, ?, ?, ?)",
            ("run-clear", "TICK0", 0.10, 0.10, 0.05, 0.20, 1.0),
        )
        conn.commit()
        conn.close()
        rc = main([
            "--db", str(db),
            "--gate", "conviction:mu:0.05",
        ])
        assert rc == 1  # MARGINAL: 1/4 = 25%
