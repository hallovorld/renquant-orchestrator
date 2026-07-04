"""Tests for the PIT estimate-revision snapshot collector (N2)."""
from __future__ import annotations

import datetime as dt
import json
import subprocess
from pathlib import Path

import pytest

from renquant_orchestrator import pit_revision_collector as mod


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "RenQuant"
    (repo / "data").mkdir(parents=True)
    return repo


def test_dry_run_returns_command_without_subprocess(tmp_path) -> None:
    repo = _repo(tmp_path)
    result = mod.collect_snapshot(repo, dry_run=True)
    assert result["status"] == "dry_run"
    assert mod.COLLECTOR_MODULE in " ".join(result["command"])
    assert str(repo / mod.DEFAULT_OUTPUT_DIR) in result["command"]


def test_collect_invokes_base_data_module(monkeypatch, tmp_path) -> None:
    repo = _repo(tmp_path)
    out_dir = repo / mod.DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True)

    today = dt.date.today().isoformat()
    snapshot_file = out_dir / f"estimates_{today}.parquet"
    snapshot_file.write_bytes(b"fake-parquet-content")

    def fake_run(cmd, cwd=None, env=None, capture_output=False, text=False):
        return subprocess.CompletedProcess(cmd, 0, stdout="ok\n", stderr="")

    monkeypatch.setattr(mod.subprocess, "run", fake_run)

    result = mod.collect_snapshot(repo)
    assert result["snapshot_date"] == today
    assert result["n_files"] >= 1
    assert "content_sha256" in result
    assert len(result["content_sha256"]) == 64

    prov_dir = repo / mod.DEFAULT_PROVENANCE_DIR
    assert prov_dir.exists()
    prov_files = list(prov_dir.glob("*.json"))
    assert len(prov_files) == 1


def test_collect_raises_on_nonzero_rc(monkeypatch, tmp_path) -> None:
    repo = _repo(tmp_path)

    def fail_run(cmd, cwd=None, env=None, capture_output=False, text=False):
        return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="boom")

    monkeypatch.setattr(mod.subprocess, "run", fail_run)

    with pytest.raises(RuntimeError, match="PIT revision collector failed"):
        mod.collect_snapshot(repo)


def test_collect_with_universe_override(monkeypatch, tmp_path) -> None:
    repo = _repo(tmp_path)
    (repo / mod.DEFAULT_OUTPUT_DIR).mkdir(parents=True)
    seen_cmds: list[list[str]] = []

    def capture_run(cmd, cwd=None, env=None, capture_output=False, text=False):
        seen_cmds.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr(mod.subprocess, "run", capture_run)
    mod.collect_snapshot(repo, universe_file="/tmp/my_universe.json")

    assert any("--universe" in c for c in seen_cmds)
    assert any("/tmp/my_universe.json" in c for c in seen_cmds)


def test_freshness_missing_dir(tmp_path) -> None:
    repo = _repo(tmp_path)
    report = mod.check_freshness(repo)
    assert report["fresh"] is False
    assert report["reason"] == "output_dir_missing"


def test_freshness_empty_dir(tmp_path) -> None:
    repo = _repo(tmp_path)
    (repo / mod.DEFAULT_OUTPUT_DIR).mkdir(parents=True)
    report = mod.check_freshness(repo)
    assert report["fresh"] is False
    assert report["reason"] == "no_snapshots"


def test_freshness_recent_snapshot(tmp_path) -> None:
    repo = _repo(tmp_path)
    out_dir = repo / mod.DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True)

    today = dt.date.today().isoformat()
    (out_dir / f"estimates_{today}.parquet").write_bytes(b"data")

    report = mod.check_freshness(repo)
    assert report["fresh"] is True
    assert report["gap_days"] == 0


def test_freshness_stale_snapshot(tmp_path) -> None:
    repo = _repo(tmp_path)
    out_dir = repo / mod.DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True)

    old_date = (dt.date.today() - dt.timedelta(days=5)).isoformat()
    (out_dir / f"estimates_{old_date}.parquet").write_bytes(b"data")

    report = mod.check_freshness(repo, max_gap_days=2)
    assert report["fresh"] is False
    assert report["gap_days"] == 5


def test_main_dry_run(tmp_path) -> None:
    repo = _repo(tmp_path)
    rc = mod.main(["--repo-dir", str(repo), "--dry-run"])
    assert rc == 0


def test_main_check_freshness_missing(tmp_path) -> None:
    repo = _repo(tmp_path)
    rc = mod.main(["--repo-dir", str(repo), "--check-freshness"])
    assert rc == 1


def test_main_check_freshness_fresh(tmp_path) -> None:
    repo = _repo(tmp_path)
    out_dir = repo / mod.DEFAULT_OUTPUT_DIR
    out_dir.mkdir(parents=True)
    today = dt.date.today().isoformat()
    (out_dir / f"estimates_{today}.parquet").write_bytes(b"data")
    rc = mod.main(["--repo-dir", str(repo), "--check-freshness"])
    assert rc == 0


def test_scheduled_job_inventory_includes_pit() -> None:
    from renquant_orchestrator.scheduled_jobs import scheduled_jobs

    ids = [j.job_id for j in scheduled_jobs()]
    assert "daily_pit_revision_snapshot" in ids


def test_job_runner_dispatches_pit() -> None:
    from renquant_orchestrator.job_runner import _MODULE_JOBS

    assert "daily_pit_revision_snapshot" in _MODULE_JOBS
    assert _MODULE_JOBS["daily_pit_revision_snapshot"] == "renquant_orchestrator.pit_revision_collector"
