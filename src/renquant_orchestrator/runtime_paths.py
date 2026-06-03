"""Runtime path and pin helpers for scheduled multirepo entrypoints."""
from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


CACHE_PATH = Path(
    os.environ.get("RENQUANT_SUBREPO_PIN_CACHE", "/tmp/renquant_subrepo_pin_guard_cache.json")
)
STRICT_PIN_ENVS = (
    "RENQUANT_STRICT_SUBREPO_PATHS",
    "RENQUANT_STRICT_SUBREPO_PINS",
    "RENQUANT_OPS_FAIL_CLOSED",
)
STRICT_CLEAN_ENV = "RENQUANT_STRICT_SUBREPO_CLEAN"


@dataclass(frozen=True)
class PinIssue:
    repo: str
    path: str
    reason: str
    kind: str = "pin"

    def format(self) -> str:
        return f"{self.repo} ({self.path}): {self.reason}"


def resolve_subrepo_root(repo_root: Path) -> Path:
    """Return runtime root, current assembly repos dir, or sibling checkout root."""
    if root := os.environ.get("RENQUANT_SUBREPO_ROOT"):
        return _abs_path(repo_root, root)

    assembly_dir = os.environ.get("RENQUANT_ASSEMBLY_DIR")
    if assembly_dir:
        repos = _abs_path(repo_root, assembly_dir) / "repos"
        if repos.exists():
            return repos

    env_path = Path(
        os.environ.get(
            "RENQUANT_SUBREPO_ENV",
            str(repo_root / ".subrepo_assembly" / "current.env"),
        )
    )
    if root := _read_export(env_path, "RENQUANT_SUBREPO_ROOT"):
        return _abs_path(repo_root, root)
    if assembly_dir := _read_export(env_path, "RENQUANT_ASSEMBLY_DIR"):
        repos = _abs_path(repo_root, assembly_dir) / "repos"
        if repos.exists():
            return repos

    current_json = repo_root / ".subrepo_assembly" / "current.json"
    if current_json.exists():
        try:
            current = Path(json.loads(current_json.read_text(encoding="utf-8"))["current"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            current = None
        if current is not None and (current / "repos").exists():
            return current / "repos"

    if root := _lock_local_path_root(repo_root):
        return root

    return repo_root.parent


def resolve_subrepo_src_roots(
    *,
    lock_file: Path,
    names: Iterable[str],
    siblings: Path,
    root_override: str | None = None,
    check_dirty: bool = False,
) -> tuple[list[Path], list[PinIssue]]:
    """Resolve source roots and collect pin-drift issues."""
    payload = json.loads(lock_file.read_text(encoding="utf-8"))
    lock_entries = {str(e["name"]): e for e in payload.get("subrepos", [])}
    roots: list[Path] = []
    issues: list[PinIssue] = []

    for name in names:
        entry = lock_entries.get(name)
        if entry is None:
            issues.append(PinIssue(name, str(lock_file), "missing from subrepos.lock.json", "path"))
            continue

        repo_path = next(
            (
                candidate
                for candidate in _candidate_repo_paths(
                    name=name,
                    entry=entry,
                    siblings=siblings,
                    root_override=root_override,
                )
                if (candidate / "src").is_dir()
            ),
            None,
        )
        if repo_path is None:
            issues.append(PinIssue(name, "", "missing local src root", "path"))
            continue

        roots.append(repo_path / "src")
        try:
            head, remote = _pin_metadata(repo_path)
        except subprocess.CalledProcessError as exc:
            issues.append(PinIssue(name, str(repo_path), f"git metadata failed: {exc}"))
            continue

        expected = str(entry.get("commit", ""))
        if expected and not head.startswith(expected):
            issues.append(
                PinIssue(
                    name,
                    str(repo_path),
                    f"HEAD {head[:12]} does not match lock commit {expected}",
                )
            )
        expected_remote = str(entry.get("remote", ""))
        if expected_remote and _norm_remote(remote) != _norm_remote(expected_remote):
            issues.append(
                PinIssue(
                    name,
                    str(repo_path),
                    f"remote {remote} does not match lock remote {expected_remote}",
                )
            )
        if check_dirty:
            try:
                dirty = bool(_git(repo_path, "status", "--porcelain"))
            except subprocess.CalledProcessError as exc:
                issues.append(PinIssue(name, str(repo_path), f"git dirty check failed: {exc}", "dirty"))
                continue
            if dirty:
                issues.append(PinIssue(name, str(repo_path), "working tree is dirty", "dirty"))

    return roots, issues


def enforce_or_warn(issues: list[PinIssue]) -> None:
    if not issues:
        return
    message = "[multirepo] subrepo pin drift:\n" + "\n".join(
        f"  - {issue.format()}" for issue in issues
    )
    fatal = [
        issue
        for issue in issues
        if (issue.kind == "dirty" and strict_clean_enabled())
        or (issue.kind != "dirty" and _strict_pin_enabled())
    ]
    if fatal:
        print(message, file=sys.stderr)
        raise SystemExit(2)
    print(
        message
        + "\n[multirepo] set RENQUANT_STRICT_SUBREPO_PATHS=1 to fail closed "
        "on missing/pin/remote drift, or RENQUANT_OPS_FAIL_CLOSED=1 for "
        "all ops entrypoints; set RENQUANT_STRICT_SUBREPO_CLEAN=1 "
        "to also fail on dirty in-progress worktrees.",
        file=sys.stderr,
    )


def strict_clean_enabled() -> bool:
    return os.environ.get(STRICT_CLEAN_ENV) == "1"


def _read_export(path: Path, name: str) -> str | None:
    if not path.exists():
        return None
    prefix = f"export {name}="
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith(prefix):
            return shlex.split(line[len("export ") :], posix=True)[0].split("=", 1)[1]
    return None


def _abs_path(repo_root: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else repo_root / path


def _lock_local_path_root(repo_root: Path) -> Path | None:
    lock_path = repo_root / "subrepos.lock.json"
    if not lock_path.exists():
        return None
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    parents: set[Path] = set()
    n_local_paths = 0
    n_existing = 0
    for entry in lock.get("subrepos", []):
        raw = entry.get("local_path")
        if not raw:
            continue
        n_local_paths += 1
        path = _abs_path(repo_root, str(raw))
        if not (path / "src").is_dir():
            continue
        n_existing += 1
        parents.add(path.parent)
    if n_local_paths > 0 and n_existing == n_local_paths and len(parents) == 1:
        return next(iter(parents))
    return None


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(("git", "-C", str(repo), *args), text=True).strip()


def _strict_pin_enabled() -> bool:
    return any(os.environ.get(name) == "1" for name in STRICT_PIN_ENVS)


def _norm_remote(remote: str) -> str:
    return remote.removesuffix(".git").rstrip("/")


def _candidate_repo_paths(
    *,
    name: str,
    entry: dict,
    siblings: Path,
    root_override: str | None,
) -> list[Path]:
    candidates: list[Path] = []
    if root_override:
        candidates.append(Path(root_override) / name)
    if entry.get("local_path"):
        candidates.append(Path(str(entry["local_path"])))
    candidates.append(siblings / name)
    return candidates


def _git_dir(repo: Path) -> Path:
    dotgit = repo / ".git"
    if dotgit.is_file():
        text = dotgit.read_text(encoding="utf-8").strip()
        if text.startswith("gitdir:"):
            target = Path(text.split(":", 1)[1].strip())
            return target if target.is_absolute() else (repo / target).resolve()
    return dotgit


def _stat_fingerprint(path: Path) -> str | None:
    try:
        st = path.stat()
    except FileNotFoundError:
        return None
    return f"{path}:{st.st_mtime_ns}:{st.st_size}"


def _repo_fingerprint(repo: Path) -> list[str]:
    git_dir = _git_dir(repo)
    paths = [git_dir / "HEAD", git_dir / "config", git_dir / "packed-refs"]
    head = git_dir / "HEAD"
    try:
        head_text = head.read_text(encoding="utf-8").strip()
    except OSError:
        head_text = ""
    if head_text.startswith("ref:"):
        paths.append(git_dir / head_text.split(":", 1)[1].strip())
    return [fp for path in paths if (fp := _stat_fingerprint(path)) is not None]


def _read_cache() -> dict:
    if os.environ.get("RENQUANT_SUBREPO_PIN_CACHE") == "0":
        return {}
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write_cache(cache: dict) -> None:
    if os.environ.get("RENQUANT_SUBREPO_PIN_CACHE") == "0":
        return
    try:
        CACHE_PATH.write_text(json.dumps(cache, sort_keys=True), encoding="utf-8")
    except OSError:
        pass


def _pin_metadata(repo: Path) -> tuple[str, str]:
    key = str(repo.resolve())
    fingerprint = _repo_fingerprint(repo)
    cache = _read_cache()
    cached = cache.get(key)
    if cached and cached.get("fingerprint") == fingerprint:
        return str(cached["head"]), str(cached["remote"])

    head = _git(repo, "log", "-1", "--format=%H")
    remote = _git(repo, "remote", "get-url", "origin")
    cache[key] = {"fingerprint": fingerprint, "head": head, "remote": remote}
    _write_cache(cache)
    return head, remote
