from __future__ import annotations

import gzip
import hashlib
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


def test_run_surfaces_stderr_and_alerts_on_hard_git_failure(tmp_path: Path, monkeypatch) -> None:
    ctx = mod.StateBackupContext(repo_root=tmp_path, backup_repo=tmp_path, quiet=False)
    alerts: list[tuple[str, str, str]] = []
    monkeypatch.setattr(mod, "post_ntfy", lambda title, body, topic: alerts.append((title, body, topic)))

    def fail_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            128,
            args[0],
            output="stdout detail",
            stderr="fatal: could not push",
        )

    monkeypatch.setattr(mod.subprocess, "run", fail_run)

    with pytest.raises(subprocess.CalledProcessError):
        mod._run(ctx, ["git", "push", "origin", "main"], alert_on_failure=True)

    assert "fatal: could not push" in ctx.warnings[0]
    assert ctx.alerts[0]["title"] == "STATE_BACKUP_FAIL"
    assert alerts[0][0] == "STATE_BACKUP_FAIL"
    assert "fatal: could not push" in alerts[0][1]


def test_push_warns_when_pull_failed_but_push_succeeds(tmp_path: Path, monkeypatch) -> None:
    ctx = mod.StateBackupContext(
        repo_root=tmp_path,
        backup_repo=tmp_path,
        committed=True,
        pull_warning="git pull failed rc=1: stderr=diverged",
    )
    alerts: list[tuple[str, str, str]] = []
    monkeypatch.setattr(mod, "post_ntfy", lambda title, body, topic: alerts.append((title, body, topic)))
    monkeypatch.setattr(
        mod,
        "_run",
        lambda ctx, cmd, **kwargs: subprocess.CompletedProcess(cmd, 0, "", ""),
    )

    mod.PushBackupTask().run(ctx)

    assert ctx.pushed is True
    assert ctx.alerts[0]["title"] == "STATE_BACKUP_WARN"
    assert "drift suspect" in ctx.alerts[0]["body"]
    assert alerts[0][0] == "STATE_BACKUP_WARN"


def test_default_repo_root_resolves_via_data_root_env() -> None:
    # The backup source default is wired through the decoupled data-root
    # resolver, not straight to the umbrella runtime root.
    from renquant_orchestrator import runtime_paths

    assert mod.DEFAULT_REPO_ROOT == runtime_paths.default_data_root()


def test_pipeline_backs_up_from_native_data_root_without_umbrella(tmp_path: Path) -> None:
    # A subrepo-/native-owned data root (no umbrella checkout) is a valid
    # backup source: RENQUANT_DATA_ROOT points the job off RenQuant/.
    data_root = tmp_path / "native-state"
    (data_root / "data").mkdir(parents=True)
    (data_root / "backtesting" / "renquant_104").mkdir(parents=True)
    backup = tmp_path / "backup"
    _init_git_repo(backup)
    _write_sqlite(data_root / "data" / "runs.alpaca.db")
    (data_root / "backtesting" / "renquant_104" / "live_state.alpaca.json").write_text(
        json.dumps({"cash": 42}),
        encoding="utf-8",
    )

    ctx = mod.StateBackupContext(repo_root=data_root, backup_repo=backup, push=False)
    result = mod.build_pipeline().run(ctx)

    assert result.ok is True
    assert (backup / "data" / "runs.alpaca.db").exists()
    assert json.loads((backup / "live_state.alpaca.json").read_text()) == {"cash": 42}
    assert ctx.committed is True


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


def test_oversized_sqlite_is_compressed_and_commit_proceeds(tmp_path: Path) -> None:
    # Regression: data/runs.alpaca.db crossed GitHub's 100MB push limit, so the
    # hourly backup copied it raw and then refused to commit (rc=1 forever).
    # Oversized SQLite DBs must be gzipped instead, with the stale raw copy
    # removed so the size gate cannot trip on it.
    repo = _make_repo(tmp_path)
    backup = tmp_path / "backup"
    _init_git_repo(backup)
    big = repo / "data" / "runs.alpaca.db"
    _write_sqlite(big)
    with sqlite3.connect(big) as conn:
        conn.execute("insert into t(value) values (?)", ("x" * 200_000,))
    _write_sqlite(repo / "data" / "runs.db")
    stale_raw = backup / "data" / "runs.alpaca.db"
    stale_raw.parent.mkdir(parents=True)
    stale_raw.write_bytes(b"stale oversized raw copy from a failed run")

    ctx = mod.StateBackupContext(
        repo_root=repo,
        backup_repo=backup,
        push=False,
        # Between the sizes of the two fixture DBs: runs.db (a few pages) stays
        # raw, runs.alpaca.db (~200KB payload) crosses the threshold.
        compress_threshold_bytes=100_000,
    )
    result = mod.build_pipeline().run(ctx)

    assert result.ok is True
    gz = backup / "data" / "runs.alpaca.db.gz"
    assert gz.exists()
    assert not stale_raw.exists()
    assert ctx.committed is True
    (entry,) = ctx.compressed
    assert entry["path"] == str(gz)
    assert str(gz) in ctx.copied
    restored = gzip.decompress(gz.read_bytes())
    assert hashlib.sha256(restored).hexdigest() == entry["sha256"]
    assert entry["uncompressed_bytes"] == len(restored)
    restored_db = tmp_path / "restored.db"
    restored_db.write_bytes(restored)
    with sqlite3.connect(restored_db) as conn:
        assert conn.execute("select count(*) from t").fetchone()[0] == 2
    # The under-threshold DB stays a raw uncompressed copy.
    assert (backup / "data" / "runs.db").exists()
    assert not (backup / "data" / "runs.db.gz").exists()


def test_under_threshold_files_unchanged_and_stale_gz_cleaned(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    backup = tmp_path / "backup"
    _init_git_repo(backup)
    _write_sqlite(repo / "data" / "runs.db")
    live = repo / "backtesting" / "renquant_104" / "live_state.alpaca.json"
    live.write_text(json.dumps({"cash": 1}), encoding="utf-8")
    stale_gz = backup / "data" / "runs.db.gz"
    stale_gz.parent.mkdir(parents=True)
    stale_gz.write_bytes(b"stale gz from an oversized era")

    ctx = mod.StateBackupContext(repo_root=repo, backup_repo=backup, push=False)
    result = mod.build_pipeline().run(ctx)

    assert result.ok is True
    assert ctx.compressed == []
    # Plain-copied files are byte-for-byte identical to the source.
    assert (backup / "live_state.alpaca.json").read_bytes() == live.read_bytes()
    # The under-threshold SQLite DB is stored raw (online-backup copy, same
    # code path as before the oversized policy), never compressed.
    dst = backup / "data" / "runs.db"
    assert mod.is_sqlite_file(dst)
    with sqlite3.connect(dst) as conn:
        assert conn.execute("select value from t").fetchone()[0] == "ok"
    # A DB that shrank back under the threshold drops its stale gz twin.
    assert not stale_gz.exists()


def test_non_sqlite_oversized_still_refuses_commit(tmp_path: Path, monkeypatch, capsys) -> None:
    repo = _make_repo(tmp_path)
    backup = tmp_path / "backup"
    _init_git_repo(backup)
    (repo / "backtesting" / "renquant_104" / "live_state.alpaca.json").write_text(
        json.dumps({"pad": "x" * 64}),
        encoding="utf-8",
    )
    monkeypatch.setattr(mod, "HARD_LIMIT_BYTES", 8)

    rc = mod.main([
        "--repo-root",
        str(repo),
        "--backup-repo",
        str(backup),
        "--no-push",
        "--quiet",
        "--compress-threshold-mb",
        "0.000001",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["committed"] is False
    assert "exceed GitHub 100MB push limit" in payload["error"]


def test_compress_threshold_configurable_via_cli_and_env(monkeypatch) -> None:
    assert mod.parse_args([]).compress_threshold_mb == 95.0
    assert mod.parse_args(["--compress-threshold-mb", "50"]).compress_threshold_mb == 50.0
    monkeypatch.setenv("RQ_BACKUP_COMPRESS_THRESHOLD_MB", "12")
    assert mod.parse_args([]).compress_threshold_mb == 12.0


def test_is_sqlite_file_detects_header(tmp_path: Path) -> None:
    db = tmp_path / "a.db"
    _write_sqlite(db)
    other = tmp_path / "b.bin"
    other.write_bytes(b"not a database")
    assert mod.is_sqlite_file(db) is True
    assert mod.is_sqlite_file(other) is False
    assert mod.is_sqlite_file(tmp_path / "missing") is False


def test_main_prints_json_summary_on_pipeline_failure(monkeypatch, tmp_path: Path, capsys) -> None:
    repo = _make_repo(tmp_path)
    backup = tmp_path / "backup"
    _init_git_repo(backup)

    monkeypatch.setattr(mod, "build_pipeline", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    rc = mod.main([
        "--repo-root",
        str(repo),
        "--backup-repo",
        str(backup),
        "--no-push",
        "--quiet",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["error"] == "boom"
    assert "boom" in payload["warnings"]
