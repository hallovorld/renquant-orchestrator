"""Tests for scripts/check_sizing_fidelity.py — sizing-fidelity diagnostic."""
from __future__ import annotations

import sqlite3
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.check_sizing_fidelity import main


@pytest.fixture()
def fake_db(tmp_path: Path) -> Path:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_path = data_dir / "runs.alpaca.db"
    db = sqlite3.connect(str(db_path))
    db.executescript(textwrap.dedent("""\
        CREATE TABLE ticker_daily_state (
            date TEXT, ticker TEXT, blocked_by TEXT,
            kelly_target_pct REAL, mu REAL, sigma REAL
        );
        CREATE TABLE candidate_scores (
            run_id TEXT, ticker TEXT, blocked_by TEXT
        );
        CREATE TABLE pipeline_runs (
            run_id TEXT, run_date TEXT, cash REAL, portfolio_value REAL
        );
        INSERT INTO pipeline_runs VALUES ('r1', '2026-07-06', 7800, 10000);
        INSERT INTO ticker_daily_state VALUES
            ('2026-07-06', 'BLK', 'size_insufficient_cash', 0.07, 0.04, 0.28);
        INSERT INTO candidate_scores VALUES ('r1', 'BLK', 'size_insufficient_cash');
        INSERT INTO candidate_scores VALUES ('r1', 'AAPL', 'veto:rank_score_below_floor');
        INSERT INTO candidate_scores VALUES ('r1', 'MSFT', 'veto:rank_score_below_floor');
    """))
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
    db.executescript(textwrap.dedent("""\
        CREATE TABLE ticker_daily_state (
            date TEXT, ticker TEXT, blocked_by TEXT,
            kelly_target_pct REAL, mu REAL, sigma REAL
        );
        CREATE TABLE candidate_scores (
            run_id TEXT, ticker TEXT, blocked_by TEXT
        );
        CREATE TABLE pipeline_runs (
            run_id TEXT, run_date TEXT, cash REAL, portfolio_value REAL
        );
        INSERT INTO pipeline_runs VALUES ('r1', '2026-07-06', 2000, 10000);
    """))
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
