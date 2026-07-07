"""Tests for scripts/check_score_db_health.py (Codex review on PR #404 — the
script defaulted --repo-dir to a hardcoded ``~/git/github/RenQuant`` umbrella
path instead of the orchestrator-owned runtime_paths convention). This file
proves the default now genuinely resolves via
``runtime_paths.default_data_root()`` rather than a hardcoded guess, and that
an explicit --repo-dir still overrides it."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import check_score_db_health as checker  # noqa: E402


def _make_runs_db(root: Path, broker: str = "alpaca") -> Path:
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    db_path = data_dir / f"runs.{broker}.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        "CREATE TABLE score_distribution (date TEXT, ticker TEXT)"
    )
    conn.execute("INSERT INTO score_distribution VALUES ('2026-07-06', 'AAPL')")
    conn.execute("CREATE TABLE score_percentiles_daily (date TEXT, pct REAL)")
    conn.execute("INSERT INTO score_percentiles_daily VALUES ('2026-07-06', 0.5)")
    conn.commit()
    conn.close()
    return db_path


class TestRepoDirResolution:
    def test_default_repo_dir_uses_default_data_root_not_hardcoded_umbrella(
        self, tmp_path, monkeypatch
    ):
        """Omitting --repo-dir must resolve via the canonical
        default_data_root() — not a hardcoded ~/git/github/RenQuant guess."""
        fake_root = tmp_path / "fake_data_root"
        _make_runs_db(fake_root)

        with mock.patch.object(
            checker, "default_data_root", return_value=fake_root
        ) as mocked:
            rc = checker.main([])

        mocked.assert_called_once()
        assert rc == 0

    def test_explicit_repo_dir_overrides_default(self, tmp_path):
        """An explicit --repo-dir must be used as-is, not replaced by the
        default resolution."""
        explicit_root = tmp_path / "explicit_root"
        _make_runs_db(explicit_root)

        rc = checker.main(["--repo-dir", str(explicit_root)])

        assert rc == 0
