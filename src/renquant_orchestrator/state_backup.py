"""State-backup pipeline for RenQuant operator state."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request

from renquant_common import Job, Pipeline, Task

from .runtime_paths import default_github_root, default_repo_root


GITHUB = default_github_root()
DEFAULT_REPO_ROOT = default_repo_root()
DEFAULT_BACKUP_REPO = Path.home() / ".renquant-state-backup"
HARD_LIMIT_BYTES = 99 * 1024 * 1024
WARN_LIMIT_BYTES = 90 * 1024 * 1024


@dataclass
class StateBackupContext:
    repo_root: Path
    backup_repo: Path
    backup_remote: str | None = None
    timestamp: dt.datetime = field(default_factory=lambda: dt.datetime.now(dt.timezone.utc))
    push: bool = True
    dry_run: bool = False
    commands: list[list[str]] = field(default_factory=list)
    copied: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    alerts: list[dict[str, str]] = field(default_factory=list)
    pull_warning: str | None = None
    topic: str = "renquant"
    quiet: bool = False
    committed: bool = False
    pushed: bool = False

    @property
    def data_dir(self) -> Path:
        return self.repo_root / "data"

    @property
    def strategy_dir(self) -> Path:
        return self.repo_root / "backtesting" / "renquant_104"


def post_ntfy(title: str, body: str, topic: str) -> None:
    url = f"https://ntfy.sh/{topic}"
    try:
        req = urllib.request.Request(
            url,
            data=body.encode("utf-8"),
            headers={"Title": title, "Priority": "3", "Tags": "warning"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5).read()
    except (urllib.error.URLError, OSError):
        pass


def _notify(ctx: StateBackupContext, title: str, body: str) -> None:
    ctx.alerts.append({"title": title, "body": body})
    if not ctx.quiet:
        post_ntfy(title, body, ctx.topic)


def _format_process_failure(label: str, returncode: int, stdout: str | None, stderr: str | None) -> str:
    parts = [f"{label} failed rc={returncode}"]
    err = (stderr or "").strip()
    out = (stdout or "").strip()
    if err:
        parts.append(f"stderr={err}")
    if out:
        parts.append(f"stdout={out}")
    return ": ".join(parts)


def _run(
    ctx: StateBackupContext,
    cmd: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    alert_on_failure: bool = False,
) -> subprocess.CompletedProcess:
    ctx.commands.append(cmd)
    if ctx.dry_run:
        return subprocess.CompletedProcess(cmd, 0, "", "")
    try:
        return subprocess.run(cmd, cwd=str(cwd or ctx.backup_repo), text=True, capture_output=True, check=check)
    except subprocess.CalledProcessError as exc:
        message = _format_process_failure(" ".join(cmd), exc.returncode, exc.stdout, exc.stderr)
        ctx.warnings.append(message)
        if alert_on_failure:
            _notify(ctx, "STATE_BACKUP_FAIL", message)
        raise


def _copy_file(ctx: StateBackupContext, src: Path, dst: Path) -> None:
    if not src.exists():
        ctx.skipped.append(str(src))
        return
    if ctx.dry_run:
        ctx.copied.append(str(dst))
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    ctx.copied.append(str(dst))


def backup_sqlite(src: Path, dst: Path) -> bool:
    """Copy a sqlite database with the online backup API.

    Returns False when ``src`` is missing. Raises if sqlite cannot open the
    source; a corrupt DB should fail the backup instead of silently copying.
    """
    if not src.exists():
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{src}?mode=ro", uri=True) as source, sqlite3.connect(dst) as target:
        source.backup(target)
    return True


class EnsureBackupRepoTask(Task):
    def run(self, ctx: StateBackupContext) -> bool | None:
        git_dir = ctx.backup_repo / ".git"
        if git_dir.exists():
            return True
        if not ctx.backup_remote:
            raise FileNotFoundError(
                f"backup repo does not exist and backup_remote is not set: {ctx.backup_repo}"
            )
        if ctx.dry_run:
            ctx.commands.append(["git", "clone", ctx.backup_remote, str(ctx.backup_repo)])
            return True
        ctx.backup_repo.parent.mkdir(parents=True, exist_ok=True)
        result = subprocess.run(
            ["git", "clone", ctx.backup_remote, str(ctx.backup_repo)],
            text=True,
            capture_output=True,
        )
        if result.returncode == 0:
            return True
        ctx.backup_repo.mkdir(parents=True, exist_ok=True)
        _run(ctx, ["git", "init", "-b", "main"], cwd=ctx.backup_repo)
        _run(ctx, ["git", "remote", "add", "origin", ctx.backup_remote], cwd=ctx.backup_repo)
        readme = ctx.backup_repo / "README.md"
        readme.write_text("# RenQuant state backup\n", encoding="utf-8")
        _run(ctx, ["git", "add", "README.md"], cwd=ctx.backup_repo)
        _run(ctx, ["git", "commit", "-m", "init"], cwd=ctx.backup_repo)
        _run(ctx, ["git", "push", "-u", "origin", "main"], cwd=ctx.backup_repo)
        return True


class PullBackupRepoTask(Task):
    def run(self, ctx: StateBackupContext) -> bool | None:
        if ctx.dry_run:
            ctx.commands.append(["git", "pull", "--rebase", "--autostash"])
            return True
        result = _run(ctx, ["git", "pull", "--rebase", "--autostash"], check=False)
        if result.returncode != 0:
            warning = _format_process_failure("git pull --rebase --autostash", result.returncode, result.stdout, result.stderr)
            ctx.warnings.append(warning)
            ctx.pull_warning = warning
        return True


class BackupSqliteTask(Task):
    sources = ("runs.db", "runs.alpaca.db")

    def run(self, ctx: StateBackupContext) -> bool | None:
        for name in self.sources:
            src = ctx.data_dir / name
            dst = ctx.backup_repo / "data" / name
            if ctx.dry_run:
                ctx.copied.append(str(dst))
                continue
            if backup_sqlite(src, dst):
                ctx.copied.append(str(dst))
            else:
                ctx.skipped.append(str(src))
        return True


class CopyLiveStateTask(Task):
    def run(self, ctx: StateBackupContext) -> bool | None:
        for path in sorted(ctx.strategy_dir.glob("live_state.*.json")):
            _copy_file(ctx, path, ctx.backup_repo / path.name)
        return True


class MirrorInsiderTradesTask(Task):
    def run(self, ctx: StateBackupContext) -> bool | None:
        src = ctx.data_dir / "insider_trades"
        dst = ctx.backup_repo / "data" / "insider_trades"
        if not src.exists():
            ctx.skipped.append(str(src))
            return True
        if ctx.dry_run:
            ctx.copied.append(str(dst))
            return True
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        ctx.copied.append(str(dst))
        return True


class CopyExperimentStateTask(Task):
    files = ("stage3_progress.json", "stage3_final_watchlist.json")

    def run(self, ctx: StateBackupContext) -> bool | None:
        for name in self.files:
            _copy_file(ctx, ctx.repo_root / "scripts" / name, ctx.backup_repo / name)
        return True


class CheckFileSizeLimitsTask(Task):
    def run(self, ctx: StateBackupContext) -> bool | None:
        hard: list[str] = []
        warn: list[str] = []
        for path in ctx.backup_repo.rglob("*"):
            if not path.is_file() or ".git" in path.parts:
                continue
            size = path.stat().st_size
            if size > HARD_LIMIT_BYTES:
                hard.append(str(path))
            elif size > WARN_LIMIT_BYTES:
                warn.append(str(path))
        if warn:
            ctx.warnings.append("files near GitHub 100MB limit: " + ", ".join(warn))
        if hard:
            raise ValueError("files exceed GitHub 100MB push limit: " + ", ".join(hard))
        return True


class CommitBackupTask(Task):
    def run(self, ctx: StateBackupContext) -> bool | None:
        _run(ctx, ["git", "add", "-A"])
        diff = _run(ctx, ["git", "diff", "--cached", "--quiet"], check=False)
        if diff.returncode == 0:
            return True
        stamp = ctx.timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")
        _run(ctx, ["git", "commit", "-m", f"backup {stamp}"], alert_on_failure=True)
        ctx.committed = True
        return True


class PushBackupTask(Task):
    def run(self, ctx: StateBackupContext) -> bool | None:
        if not ctx.push or not ctx.committed:
            return True
        _run(ctx, ["git", "push", "origin", "main"], alert_on_failure=True)
        ctx.pushed = True
        if ctx.pull_warning:
            _notify(ctx, "STATE_BACKUP_WARN", f"backup pushed after pull warning; drift suspect: {ctx.pull_warning}")
        return True


class EnsureBackupRepoJob(Job):
    @property
    def tasks(self) -> list[Task]:
        return [EnsureBackupRepoTask(), PullBackupRepoTask()]


class SnapshotStateJob(Job):
    @property
    def tasks(self) -> list[Task]:
        return [BackupSqliteTask(), CopyLiveStateTask(), MirrorInsiderTradesTask(), CopyExperimentStateTask()]


class PersistBackupJob(Job):
    @property
    def tasks(self) -> list[Task]:
        return [CheckFileSizeLimitsTask(), CommitBackupTask(), PushBackupTask()]


def build_pipeline() -> Pipeline:
    return Pipeline([EnsureBackupRepoJob(), SnapshotStateJob(), PersistBackupJob()], name="state-backup")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=DEFAULT_REPO_ROOT)
    parser.add_argument("--backup-repo", type=Path, default=Path(os.environ.get("BACKUP_REPO", DEFAULT_BACKUP_REPO)))
    parser.add_argument("--backup-remote", default=os.environ.get("BACKUP_REMOTE"))
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--topic", default=os.environ.get("NTFY_TOPIC", "renquant"))
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    ctx = StateBackupContext(
        repo_root=args.repo_root.expanduser().resolve(),
        backup_repo=args.backup_repo.expanduser().resolve(),
        backup_remote=args.backup_remote,
        push=not args.no_push,
        dry_run=args.dry_run,
        topic=args.topic,
        quiet=args.quiet,
    )
    error: str | None = None
    rc = 0
    try:
        build_pipeline().run(ctx)
    except Exception as exc:  # noqa: BLE001 - cron entrypoint should emit JSON before failing
        error = str(exc)
        if error and not any(error in warning for warning in ctx.warnings):
            ctx.warnings.append(error)
        rc = 1
    print(json.dumps({
        "alerts": ctx.alerts,
        "backup_repo": str(ctx.backup_repo),
        "committed": ctx.committed,
        "error": error,
        "pushed": ctx.pushed,
        "copied": ctx.copied,
        "skipped": ctx.skipped,
        "warnings": ctx.warnings,
    }, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
