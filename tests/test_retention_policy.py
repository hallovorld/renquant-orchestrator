"""Tests for S11 artifact retention policy and pruning."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from renquant_orchestrator.retention_policy import (
    ArtifactFamily,
    DEFAULT_FAMILIES,
    PruneResult,
    prune_stale_artifacts,
    main,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _touch(path: Path, *, mtime_offset: float = 0.0) -> Path:
    """Create a file and optionally shift its mtime by offset seconds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}")
    if mtime_offset:
        t = time.time() + mtime_offset
        import os
        os.utime(path, (t, t))
    return path


def _make_staging_panel_ltr(root: Path, n: int) -> list[Path]:
    """Create n staging panel-ltr files with distinct timestamps."""
    prod = root / "artifacts" / "prod"
    prod.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(n):
        ts = f"2026060{i}T120000Z"
        p = prod / f"panel-ltr.alpha158_fund.weekly_{ts}.staging.json"
        _touch(p, mtime_offset=-n + i)  # oldest first
        paths.append(p)
    return paths


def _make_staging_calibration(root: Path, n: int) -> list[Path]:
    prod = root / "artifacts" / "prod"
    prod.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(n):
        ts = f"2026060{i}T120000Z"
        p = prod / f"panel-rank-calibration.weekly_{ts}.staging.json"
        _touch(p, mtime_offset=-n + i)
        paths.append(p)
    return paths


def _make_rollback_snapshots(root: Path, n: int) -> list[Path]:
    prod = root / "artifacts" / "prod"
    prod.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(n):
        date = f"2026-06-{i + 1:02d}"
        prefix = "panel-ltr.alpha158_fund" if i % 2 == 0 else "panel-rank-calibration"
        cadence = "weekly" if i % 3 != 0 else "monthly"
        p = prod / f"{prefix}.{cadence}_rollback_{date}.json"
        _touch(p, mtime_offset=-n + i)
        paths.append(p)
    return paths


def _make_lock_backups(root: Path, n: int) -> list[Path]:
    paths = []
    for i in range(n):
        ts = f"2026060{i}T12000{i}"
        p = root / f"subrepos.lock.json.promote-bak.{ts}"
        _touch(p, mtime_offset=-n + i)
        paths.append(p)
    return paths


# ---------------------------------------------------------------------------
# Family identification
# ---------------------------------------------------------------------------


class TestFamilyIdentification:
    """Verify that glob patterns correctly identify artifact families."""

    def test_staging_panel_ltr_identified(self, tmp_path: Path) -> None:
        paths = _make_staging_panel_ltr(tmp_path, 6)
        results = prune_stale_artifacts(tmp_path, families=(DEFAULT_FAMILIES[0],))
        assert len(results) == 1
        assert results[0].family == "staging_panel_ltr"
        assert results[0].total_found == 6

    def test_staging_calibration_identified(self, tmp_path: Path) -> None:
        paths = _make_staging_calibration(tmp_path, 5)
        results = prune_stale_artifacts(tmp_path, families=(DEFAULT_FAMILIES[1],))
        assert len(results) == 1
        assert results[0].family == "staging_calibration"
        assert results[0].total_found == 5

    def test_rollback_snapshots_identified(self, tmp_path: Path) -> None:
        paths = _make_rollback_snapshots(tmp_path, 10)
        results = prune_stale_artifacts(tmp_path, families=(DEFAULT_FAMILIES[2],))
        assert len(results) == 1
        assert results[0].family == "rollback_snapshots"
        assert results[0].total_found == 10

    def test_lock_backups_identified(self, tmp_path: Path) -> None:
        paths = _make_lock_backups(tmp_path, 7)
        results = prune_stale_artifacts(tmp_path, families=(DEFAULT_FAMILIES[3],))
        assert len(results) == 1
        assert results[0].family == "lock_backups"
        assert results[0].total_found == 7

    def test_no_false_positives_on_prod_artifacts(self, tmp_path: Path) -> None:
        """The actual promoted artifacts (panel-ltr.alpha158_fund.json) must
        NOT be matched by the staging/rollback globs."""
        prod = tmp_path / "artifacts" / "prod"
        prod.mkdir(parents=True, exist_ok=True)
        (prod / "panel-ltr.alpha158_fund.json").write_text("{}")
        (prod / "panel-rank-calibration.json").write_text("{}")

        results = prune_stale_artifacts(tmp_path)
        for r in results:
            assert r.total_found == 0, f"family {r.family} incorrectly matched promoted artifacts"


# ---------------------------------------------------------------------------
# Retention window enforcement
# ---------------------------------------------------------------------------


class TestRetentionWindow:
    """Verify keep-N-newest, prune-older logic."""

    def test_keeps_n_newest_staging(self, tmp_path: Path) -> None:
        _make_staging_panel_ltr(tmp_path, 6)
        results = prune_stale_artifacts(tmp_path, families=(DEFAULT_FAMILIES[0],))
        r = results[0]
        assert r.kept == 4
        assert len(r.prunable) == 2

    def test_keeps_all_when_under_limit(self, tmp_path: Path) -> None:
        _make_staging_panel_ltr(tmp_path, 3)
        results = prune_stale_artifacts(tmp_path, families=(DEFAULT_FAMILIES[0],))
        r = results[0]
        assert r.kept == 3
        assert len(r.prunable) == 0

    def test_keeps_all_when_exactly_at_limit(self, tmp_path: Path) -> None:
        _make_staging_panel_ltr(tmp_path, 4)
        results = prune_stale_artifacts(tmp_path, families=(DEFAULT_FAMILIES[0],))
        r = results[0]
        assert r.kept == 4
        assert len(r.prunable) == 0

    def test_rollback_keeps_8(self, tmp_path: Path) -> None:
        _make_rollback_snapshots(tmp_path, 12)
        results = prune_stale_artifacts(tmp_path, families=(DEFAULT_FAMILIES[2],))
        r = results[0]
        assert r.kept == 8
        assert len(r.prunable) == 4

    def test_lock_backup_keeps_5(self, tmp_path: Path) -> None:
        _make_lock_backups(tmp_path, 8)
        results = prune_stale_artifacts(tmp_path, families=(DEFAULT_FAMILIES[3],))
        r = results[0]
        assert r.kept == 5
        assert len(r.prunable) == 3

    def test_prunable_are_oldest(self, tmp_path: Path) -> None:
        """The prunable list must contain the OLDEST files (lowest mtime)."""
        paths = _make_staging_panel_ltr(tmp_path, 6)
        results = prune_stale_artifacts(tmp_path, families=(DEFAULT_FAMILIES[0],))
        r = results[0]
        # The helper creates files with ascending mtime; paths[0] is oldest.
        prunable_mtimes = [p.stat().st_mtime for p in r.prunable]
        # All prunable mtimes should be less than all kept mtimes.
        kept_paths = [p for p in paths if p not in r.prunable]
        kept_mtimes = [p.stat().st_mtime for p in kept_paths]
        if prunable_mtimes and kept_mtimes:
            assert max(prunable_mtimes) < min(kept_mtimes)


# ---------------------------------------------------------------------------
# Dry-run vs execute
# ---------------------------------------------------------------------------


class TestDryRunVsExecute:
    """Verify dry-run returns paths without deleting, execute mode removes."""

    def test_dry_run_does_not_delete(self, tmp_path: Path) -> None:
        paths = _make_staging_panel_ltr(tmp_path, 6)
        results = prune_stale_artifacts(tmp_path, dry_run=True, families=(DEFAULT_FAMILIES[0],))
        r = results[0]
        assert len(r.prunable) == 2
        assert r.deleted is False
        # All files still exist.
        for p in paths:
            assert p.exists()

    def test_execute_deletes_prunable(self, tmp_path: Path) -> None:
        paths = _make_staging_panel_ltr(tmp_path, 6)
        results = prune_stale_artifacts(tmp_path, dry_run=False, families=(DEFAULT_FAMILIES[0],))
        r = results[0]
        assert r.deleted is True
        assert len(r.prunable) == 2
        # Prunable files are gone.
        for p in r.prunable:
            assert not p.exists()
        # Kept files still exist.
        remaining = list((tmp_path / "artifacts" / "prod").glob(
            "panel-ltr.alpha158_fund.weekly_*.staging.json"
        ))
        assert len(remaining) == 4

    def test_execute_with_nothing_to_prune(self, tmp_path: Path) -> None:
        _make_staging_panel_ltr(tmp_path, 2)
        results = prune_stale_artifacts(tmp_path, dry_run=False, families=(DEFAULT_FAMILIES[0],))
        r = results[0]
        assert r.deleted is False
        assert len(r.prunable) == 0


# ---------------------------------------------------------------------------
# Empty directory / missing directory
# ---------------------------------------------------------------------------


class TestEmptyAndMissing:
    """Handle repos with no artifacts gracefully."""

    def test_empty_root(self, tmp_path: Path) -> None:
        results = prune_stale_artifacts(tmp_path)
        assert len(results) == len(DEFAULT_FAMILIES)
        for r in results:
            assert r.total_found == 0
            assert len(r.prunable) == 0
            assert r.deleted is False

    def test_missing_artifacts_dir(self, tmp_path: Path) -> None:
        # Root exists but artifacts/ does not.
        results = prune_stale_artifacts(tmp_path)
        for r in results:
            assert r.total_found == 0

    def test_backtesting_prefix_scanned(self, tmp_path: Path) -> None:
        """Files under backtesting/renquant_104/ are also found."""
        bt_prod = tmp_path / "backtesting" / "renquant_104" / "artifacts" / "prod"
        bt_prod.mkdir(parents=True, exist_ok=True)
        for i in range(6):
            ts = f"2026060{i}T120000Z"
            _touch(bt_prod / f"panel-ltr.alpha158_fund.weekly_{ts}.staging.json",
                   mtime_offset=-6 + i)
        results = prune_stale_artifacts(tmp_path, families=(DEFAULT_FAMILIES[0],))
        assert results[0].total_found == 6
        assert len(results[0].prunable) == 2


# ---------------------------------------------------------------------------
# All families together
# ---------------------------------------------------------------------------


class TestAllFamilies:
    """Run the full default scan with all families populated."""

    def test_full_scan(self, tmp_path: Path) -> None:
        _make_staging_panel_ltr(tmp_path, 6)
        _make_staging_calibration(tmp_path, 5)
        _make_rollback_snapshots(tmp_path, 10)
        _make_lock_backups(tmp_path, 7)

        results = prune_stale_artifacts(tmp_path)
        by_name = {r.family: r for r in results}

        assert by_name["staging_panel_ltr"].total_found == 6
        assert len(by_name["staging_panel_ltr"].prunable) == 2

        assert by_name["staging_calibration"].total_found == 5
        assert len(by_name["staging_calibration"].prunable) == 1

        assert by_name["rollback_snapshots"].total_found == 10
        assert len(by_name["rollback_snapshots"].prunable) == 2

        assert by_name["lock_backups"].total_found == 7
        assert len(by_name["lock_backups"].prunable) == 2


# ---------------------------------------------------------------------------
# Custom family override
# ---------------------------------------------------------------------------


class TestCustomFamily:
    """Callers can override families for targeted pruning."""

    def test_custom_keep_2(self, tmp_path: Path) -> None:
        _make_staging_panel_ltr(tmp_path, 5)
        custom = (ArtifactFamily(
            name="staging_panel_ltr",
            glob_pattern="artifacts/prod/panel-ltr.alpha158_fund.weekly_*.staging.json",
            keep=2,
            description="test",
        ),)
        results = prune_stale_artifacts(tmp_path, families=custom)
        assert results[0].kept == 2
        assert len(results[0].prunable) == 3


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


class TestCLI:
    """Test the CLI entry point via main()."""

    def test_dry_run_cli(self, tmp_path: Path, capsys) -> None:
        _make_staging_panel_ltr(tmp_path, 6)
        _make_lock_backups(tmp_path, 7)

        rc = main(["--repo", str(tmp_path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "DRY-RUN" in out
        assert "staging_panel_ltr" in out

    def test_execute_cli(self, tmp_path: Path, capsys) -> None:
        _make_staging_panel_ltr(tmp_path, 6)

        rc = main(["--repo", str(tmp_path), "--execute"])
        assert rc == 0
        out = capsys.readouterr().out
        assert "EXECUTE" in out
        remaining = list((tmp_path / "artifacts" / "prod").glob(
            "panel-ltr.alpha158_fund.weekly_*.staging.json"
        ))
        assert len(remaining) == 4

    def test_json_output(self, tmp_path: Path, capsys) -> None:
        _make_staging_panel_ltr(tmp_path, 6)

        rc = main(["--repo", str(tmp_path), "--json"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["dry_run"] is True
        families = {f["family"]: f for f in payload["families"]}
        assert families["staging_panel_ltr"]["total_found"] == 6
        assert families["staging_panel_ltr"]["prunable_count"] == 2

    def test_missing_repo_returns_1(self, capsys) -> None:
        rc = main(["--repo", "/nonexistent/path"])
        assert rc == 1

    def test_nothing_to_prune(self, tmp_path: Path, capsys) -> None:
        rc = main(["--repo", str(tmp_path)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "nothing to prune" in out


class TestCLIIntegration:
    """Test via the top-level CLI dispatch."""

    def test_prune_artifacts_via_main_cli(self, tmp_path: Path, capsys) -> None:
        from renquant_orchestrator.cli import main as cli_main

        _make_staging_panel_ltr(tmp_path, 6)
        rc = cli_main(["prune-artifacts", "--repo", str(tmp_path), "--json"])
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["dry_run"] is True
        families = {f["family"]: f for f in payload["families"]}
        assert families["staging_panel_ltr"]["prunable_count"] == 2
