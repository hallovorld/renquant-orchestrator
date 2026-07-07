"""Tests for scripts/check_sizing_fidelity.py — sizing-fidelity diagnostic.

Codex review on PR #407 found two real measurement gaps: (1) the block
breakdown wasn't restricted to canonical daily FULL runs (could mix partial/
monitor/non-canonical rows), and (2) the fractional-shares conclusion was
based only on a `blocked_by = 'size_insufficient_cash'` string count, which
misses whole-share quantization loss that surfaces under other labels (or no
label at all). These tests prove both are fixed."""
from __future__ import annotations

import sqlite3
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.check_sizing_fidelity import main, MIN_FULL_RUN_CANDIDATES


def _base_schema() -> str:
    return textwrap.dedent("""\
        CREATE TABLE ticker_daily_state (
            date TEXT, ticker TEXT, blocked_by TEXT,
            kelly_target_pct REAL, mu REAL, sigma REAL
        );
        CREATE TABLE candidate_scores (
            run_id TEXT, ticker TEXT, blocked_by TEXT,
            selected INTEGER, kelly_target_pct REAL
        );
        CREATE TABLE pipeline_runs (
            run_id TEXT, run_date TEXT, created_at TEXT,
            cash REAL, portfolio_value REAL
        );
        CREATE TABLE trades (
            run_id TEXT, ticker TEXT, action TEXT, target_pct REAL
        );
    """)


def _fill_candidates(db, run_id: str, n: int) -> None:
    """Pad candidate_scores up to MIN_FULL_RUN_CANDIDATES with inert rows,
    so the run counts as canonical."""
    for i in range(n):
        db.execute(
            "INSERT INTO candidate_scores (run_id, ticker, blocked_by, "
            "selected, kelly_target_pct) VALUES (?, ?, NULL, 0, NULL)",
            (run_id, f"PAD{i}"),
        )


@pytest.fixture()
def fake_db(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "runs.alpaca.db"
    db = sqlite3.connect(str(db_path))
    db.executescript(_base_schema())

    run_id = "r1-live-1"
    db.execute(
        "INSERT INTO pipeline_runs VALUES (?, '2026-07-06', "
        "'2026-07-06T20:00:00', 7800, 10000)",
        (run_id,),
    )
    db.execute(
        "INSERT INTO ticker_daily_state VALUES "
        "('2026-07-06', 'BLK', 'size_insufficient_cash', 0.07, 0.04, 0.28)"
    )
    db.execute(
        "INSERT INTO candidate_scores (run_id, ticker, blocked_by, selected, "
        "kelly_target_pct) VALUES (?, 'BLK', 'size_insufficient_cash', 1, 0.07)",
        (run_id,),
    )
    db.execute(
        "INSERT INTO candidate_scores (run_id, ticker, blocked_by, selected, "
        "kelly_target_pct) VALUES (?, 'AAPL', 'veto:rank_score_below_floor', 0, NULL)",
        (run_id,),
    )
    db.execute(
        "INSERT INTO candidate_scores (run_id, ticker, blocked_by, selected, "
        "kelly_target_pct) VALUES (?, 'MSFT', 'veto:rank_score_below_floor', 0, NULL)",
        (run_id,),
    )
    _fill_candidates(db, run_id, MIN_FULL_RUN_CANDIDATES)
    db.commit()
    db.close()
    return tmp_path


def test_detects_size_insufficient(fake_db: Path, capsys: pytest.CaptureFixture) -> None:
    rc = main(["--repo-dir", str(fake_db)])
    assert rc == 1
    out = capsys.readouterr().out
    assert "size_insufficient_cash" in out
    assert "BLK" in out


def test_shows_block_breakdown(fake_db: Path, capsys: pytest.CaptureFixture) -> None:
    main(["--repo-dir", str(fake_db)])
    out = capsys.readouterr().out
    assert "veto_weak_buys" in out
    assert "size_insufficient" in out


def test_reports_cash_drag(fake_db: Path, capsys: pytest.CaptureFixture) -> None:
    main(["--repo-dir", str(fake_db)])
    out = capsys.readouterr().out
    assert "78.0%" in out
    assert "WARN" in out


def test_clean_when_no_blocks(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "runs.alpaca.db"
    db = sqlite3.connect(str(db_path))
    db.executescript(_base_schema())
    db.execute(
        "INSERT INTO pipeline_runs VALUES ('r1-live-1', '2026-07-06', "
        "'2026-07-06T20:00:00', 2000, 10000)"
    )
    _fill_candidates(db, "r1-live-1", MIN_FULL_RUN_CANDIDATES)
    db.commit()
    db.close()
    rc = main(["--repo-dir", str(tmp_path)])
    assert rc == 0


def test_path_uses_default_data_root() -> None:
    """Verify default path goes through runtime_paths, not hardcoded."""
    import scripts.check_sizing_fidelity as mod

    with patch.object(mod, "default_data_root") as mock_ddr:
        mock_ddr.return_value = Path("/nonexistent/path")
        rc = main([])
        mock_ddr.assert_called_once()
        assert rc == 1


class TestCanonicalRunFiltering:
    def test_excludes_partial_monitor_run_from_block_breakdown(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """A partial/monitor run (too few candidate_scores rows to be
        canonical) must NOT contribute to the block breakdown — this is
        exactly the mixing bug Codex flagged (pre-fix: any run_id with a
        matching run_date was included regardless of completeness)."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_path = data_dir / "runs.alpaca.db"
        db = sqlite3.connect(str(db_path))
        db.executescript(_base_schema())

        # Genuine canonical run: full candidate count, no blocks.
        db.execute(
            "INSERT INTO pipeline_runs VALUES ('full-live-1', '2026-07-06', "
            "'2026-07-06T20:00:00', 2000, 10000)"
        )
        _fill_candidates(db, "full-live-1", MIN_FULL_RUN_CANDIDATES)

        # Partial/monitor run on the SAME date: far too few rows to be
        # canonical, but stuffed with a distinctive blocked_by label that
        # must NOT leak into the breakdown.
        db.execute(
            "INSERT INTO pipeline_runs VALUES ('monitor-live-1', "
            "'2026-07-06', '2026-07-06T20:05:00', 2000, 10000)"
        )
        db.execute(
            "INSERT INTO candidate_scores (run_id, ticker, blocked_by, "
            "selected, kelly_target_pct) VALUES ('monitor-live-1', 'ZZZ', "
            "'partial_run_only_reason', 0, NULL)"
        )
        db.commit()
        db.close()

        main(["--repo-dir", str(tmp_path)])
        out = capsys.readouterr().out
        assert "partial_run_only_reason" not in out
        assert "CANONICAL RUNS: 1 in last" in out

    def test_dedupes_to_latest_run_per_date(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Two genuinely-full runs on the same date: only the one with the
        latest created_at counts as canonical (matches
        tc_measurement._canonical_daily_runs semantics)."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_path = data_dir / "runs.alpaca.db"
        db = sqlite3.connect(str(db_path))
        db.executescript(_base_schema())

        db.execute(
            "INSERT INTO pipeline_runs VALUES ('early-live-1', '2026-07-06', "
            "'2026-07-06T10:00:00', 2000, 10000)"
        )
        db.execute(
            "INSERT INTO candidate_scores (run_id, ticker, blocked_by, "
            "selected, kelly_target_pct) VALUES ('early-live-1', 'ZZZ', "
            "'early_run_reason', 0, NULL)"
        )
        _fill_candidates(db, "early-live-1", MIN_FULL_RUN_CANDIDATES)

        db.execute(
            "INSERT INTO pipeline_runs VALUES ('late-live-1', '2026-07-06', "
            "'2026-07-06T20:00:00', 2000, 10000)"
        )
        _fill_candidates(db, "late-live-1", MIN_FULL_RUN_CANDIDATES)
        db.commit()
        db.close()

        main(["--repo-dir", str(tmp_path)])
        out = capsys.readouterr().out
        assert "early_run_reason" not in out
        assert "CANONICAL RUNS: 1 in last" in out


class TestQuantizationLoss:
    def test_captures_gap_under_different_blocked_by_label(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """A QP-selected candidate that ends up under-deployed for a
        DIFFERENT (or absent) blocked_by reason must still be counted as
        quantization loss — the exact gap the label-count metric alone
        would miss."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_path = data_dir / "runs.alpaca.db"
        db = sqlite3.connect(str(db_path))
        db.executescript(_base_schema())

        run_id = "r1-live-1"
        db.execute(
            "INSERT INTO pipeline_runs VALUES (?, '2026-07-06', "
            "'2026-07-06T20:00:00', 2000, 10000)",
            (run_id,),
        )
        # Model wanted 5% of the book, and the candidate WAS submitted to
        # the broker (broker_pending_submitted — a genuine sizing-stage
        # label, not size_insufficient_cash), but the actual trade only got
        # 2% (whole-share rounding truncated the submitted size). This is
        # exactly the case Codex says the label-count metric alone misses.
        db.execute(
            "INSERT INTO candidate_scores (run_id, ticker, blocked_by, "
            "selected, kelly_target_pct) VALUES (?, 'AVGO', "
            "'broker_pending_submitted', 1, 0.05)",
            (run_id,),
        )
        db.execute(
            "INSERT INTO trades (run_id, ticker, action, target_pct) "
            "VALUES (?, 'AVGO', 'buy', 0.02)",
            (run_id,),
        )
        # Model wanted 3%, got fully dropped (0 shares), no blocked_by at all.
        db.execute(
            "INSERT INTO candidate_scores (run_id, ticker, blocked_by, "
            "selected, kelly_target_pct) VALUES (?, 'GS', NULL, 1, 0.03)",
            (run_id,),
        )
        _fill_candidates(db, run_id, MIN_FULL_RUN_CANDIDATES)
        db.commit()
        db.close()

        main(["--repo-dir", str(tmp_path)])
        out = capsys.readouterr().out
        assert "candidates surviving to sizing: 2" in out
        assert "Candidates with executed < intended: 2" in out
        # Total gap = (0.05-0.02) + (0.03-0.0) = 0.06
        assert "0.06" in out
        assert "NO blocked_by label" in out
        assert "DIFFERENT label" in out

    def test_excludes_admission_stage_rejection_from_sizing_population(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """A candidate rejected at admission (correlation cap — a genuine
        _PRE_SELECTION_BLOCKERS reason) must NOT count as sizing-stage
        quantization loss even if it has a positive kelly_target_pct — it
        never reached the sizing stage at all. This mirrors a real gap
        found when investigating the live DB directly: post-2026-05-22 live
        data has ``qp_admission_panel``/``qp_admission_rank`` blocked_by
        values that are genuine admission-stage rejections, not sizing
        effects, and must be excluded the same way."""
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_path = data_dir / "runs.alpaca.db"
        db = sqlite3.connect(str(db_path))
        db.executescript(_base_schema())

        run_id = "r1-live-1"
        db.execute(
            "INSERT INTO pipeline_runs VALUES (?, '2026-07-06', "
            "'2026-07-06T20:00:00', 2000, 10000)",
            (run_id,),
        )
        db.execute(
            "INSERT INTO candidate_scores (run_id, ticker, blocked_by, "
            "selected, kelly_target_pct) VALUES (?, 'NVDA', "
            "'correlation', 0, 0.06)",
            (run_id,),
        )
        _fill_candidates(db, run_id, MIN_FULL_RUN_CANDIDATES)
        db.commit()
        db.close()

        main(["--repo-dir", str(tmp_path)])
        out = capsys.readouterr().out
        assert "candidates surviving to sizing: 0" in out

    def test_no_gap_when_fully_deployed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        data_dir = tmp_path / "data"
        data_dir.mkdir()
        db_path = data_dir / "runs.alpaca.db"
        db = sqlite3.connect(str(db_path))
        db.executescript(_base_schema())

        run_id = "r1-live-1"
        db.execute(
            "INSERT INTO pipeline_runs VALUES (?, '2026-07-06', "
            "'2026-07-06T20:00:00', 2000, 10000)",
            (run_id,),
        )
        db.execute(
            "INSERT INTO candidate_scores (run_id, ticker, blocked_by, "
            "selected, kelly_target_pct) VALUES (?, 'AVGO', NULL, 1, 0.05)",
            (run_id,),
        )
        db.execute(
            "INSERT INTO trades (run_id, ticker, action, target_pct) "
            "VALUES (?, 'AVGO', 'buy', 0.05)",
            (run_id,),
        )
        _fill_candidates(db, run_id, MIN_FULL_RUN_CANDIDATES)
        db.commit()
        db.close()

        rc = main(["--repo-dir", str(tmp_path)])
        out = capsys.readouterr().out
        assert "Candidates with executed < intended: 0" in out


class TestEvidenceArtifact:
    def test_writes_evidence_json(
        self, fake_db: Path, tmp_path: Path
    ) -> None:
        evidence_path = tmp_path / "evidence" / "out.json"
        main(["--repo-dir", str(fake_db), "--evidence-out", str(evidence_path)])
        assert evidence_path.exists()
        import json
        payload = json.loads(evidence_path.read_text())
        assert "canonical_run_ids" in payload
        assert "quantization_loss" in payload
        assert "block_breakdown" in payload
