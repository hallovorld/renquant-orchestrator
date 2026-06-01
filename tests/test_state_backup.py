from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess

import pytest

from renquant_orchestrator import state_backup as mod


def _init_git_repo(path: Path) -> None:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, check=True)


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "RenQuant"
    (repo / "data").mkdir(parents=True)
    (repo / "backtesting" / "renquant_104").mkdir(parents=True)
    (repo / "scripts").mkdir()
    return repo


def _write_sqlite(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("create table t(id integer primary key, value text)")
        conn.execute("insert into t(value) values ('ok')")


def test_pipeline_shape_groups_repo_snapshot_and_persist_jobs() -> None:
    pipeline = mod.build_pipeline()

    assert pipeline.name == "state-backup"
    assert [type(job).__name__ for job in pipeline.jobs] == [
        "EnsureBackupRepoJob",
        "SnapshotStateJob",
        "PersistBackupJob",
    ]


def test_backup_sqlite_uses_readable_copy(tmp_path: Path) -> None:
    src = tmp_path / "runs.db"
    dst = tmp_path / "backup" / "runs.db"
    _write_sqlite(src)

    assert mod.backup_sqlite(src, dst) is True

    with sqlite3.connect(dst) as conn:
        assert conn.execute("select value from t").fetchone()[0] == "ok"


def test_state_backup_pipeline_copies_state_and_commits_without_push(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    backup = tmp_path / "backup"
    _init_git_repo(backup)
    _write_sqlite(repo / "data" / "runs.db")
    _write_sqlite(repo / "data" / "runs.alpaca.db")
    (repo / "backtesting" / "renquant_104" / "live_state.alpaca.json").write_text(
        json.dumps({"cash": 100}),
        encoding="utf-8",
    )
    insider = repo / "data" / "insider_trades"
    insider.mkdir()
    (insider / "AAPL.parquet").write_bytes(b"parquet")
    (repo / "scripts" / "stage3_progress.json").write_text("{}", encoding="utf-8")

    ctx = mod.StateBackupContext(repo_root=repo, backup_repo=backup, push=False)

    result = mod.build_pipeline().run(ctx)

    assert result.ok is True
    assert (backup / "data" / "runs.db").exists()
    assert (backup / "data" / "runs.alpaca.db").exists()
    assert json.loads((backup / "live_state.alpaca.json").read_text()) == {"cash": 100}
    assert (backup / "data" / "insider_trades" / "AAPL.parquet").read_bytes() == b"parquet"
    assert (backup / "stage3_progress.json").exists()
    assert ctx.committed is True
    assert ctx.pushed is False
    log = subprocess.run(
        ["git", "log", "--oneline", "-1"],
        cwd=backup,
        text=True,
        check=True,
        capture_output=True,
    ).stdout
    assert "backup " in log


def test_size_guard_fails_before_commit(tmp_path: Path, monkeypatch) -> None:
    repo = _make_repo(tmp_path)
    backup = tmp_path / "backup"
    _init_git_repo(backup)
    payload = backup / "too-large.bin"
    payload.write_bytes(b"x" * 16)
    monkeypatch.setattr(mod, "HARD_LIMIT_BYTES", 8)

    ctx = mod.StateBackupContext(repo_root=repo, backup_repo=backup, push=False)

    with pytest.raises(ValueError, match="files exceed GitHub 100MB push limit"):
        mod.CheckFileSizeLimitsTask().run(ctx)


def test_main_prints_json_summary(monkeypatch, tmp_path: Path, capsys) -> None:
    repo = _make_repo(tmp_path)
    backup = tmp_path / "backup"
    _init_git_repo(backup)

    rc = mod.main([
        "--repo-root",
        str(repo),
        "--backup-repo",
        str(backup),
        "--no-push",
    ])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["backup_repo"] == str(backup.resolve())
    assert payload["pushed"] is False
