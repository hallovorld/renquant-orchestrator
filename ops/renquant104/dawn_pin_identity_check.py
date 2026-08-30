#!/usr/bin/env python3
"""Read-only pin-identity check + runtime receipt for the dawn preflight monitor.

#968 r1 (codex P1): switching the monitor to the multirepo bridge fixes the
MODULE namespace, but the monitor must also prove it previews the SAME pinned
runtime the 13:55 order path aligns to. The order entrypoint sources
``scripts/preflight_pin_align.sh`` (``subrepo_assemble.py --sync --dry-run``)
before the bridge — it verifies/aligns ``.subrepo_runtime/repos`` to
``subrepos.lock.json`` and ABORTS on drift. A monitor that skips this can
resolve a stale-but-importable runtime and report a gate verdict from a
DIFFERENT runtime than the order path executes — recreating the monitor-vs-order
divergence at the pin level.

This is the READ-ONLY, FAIL-CLOSED equivalent: it verifies each runtime subrepo
checkout matches the lock and emits a receipt, but NEVER checks out / fetches /
mutates (a monitor must not deploy).

TWO VERDICTS, NOT ONE (2026-08-30). The first version folded "HEAD != lock" and
"working tree has any porcelain line" into a single ``ok`` and the wrapper
printed "pins not aligned" for both. The order path's own predicate is
``subrepo_assemble._is_pinned`` ALONE: ``_ensure_repo`` returns as soon as
HEAD equals the lock commit and consults ``_is_dirty`` only on the un-pinned
sync path — so the 13:55 daily printed "Subrepo checkouts aligned to pins."
on 2026-08-26/27/28 while this monitor aborted seven sessions (08-19..08-27,
every receipt ``pinned: true, dirty: true``) over renquant-model's
auto-generated ``README.md``. Dark for a cosmetic reason, under a message that
named a mismatch which did not exist.

* ``PIN_MISMATCH`` — a runtime HEAD is not the lock commit, a repo is missing,
  or the lock is unreadable. Exit 1; the caller must NOT probe.
* ``TREE_DIRTY`` — every HEAD equals its lock commit, but a tracked/untracked
  path is dirty. Split by an EXPLICIT allow-list (``classify_dirty_path``):
  docs / README / generated files outside ``src/`` are NON-BLOCKING (exit 0
  with a ``WARN`` line naming them — the order path would run this exact
  tree); anything under ``src/`` or ``configs/``, any ``.py``, or any path the
  allow-list does not name is BLOCKING (``TREE_DIRTY_BLOCKING``, exit 2):
  unreviewed code in the pinned runtime is a containment condition and must
  be loud, not previewed. Closed by default — a path the list does not
  recognise blocks.

Both fields (``pin_mismatch``, ``tree_dirty``) plus the per-repo dirty paths
are in the receipt on every exit, so the divergence is visible.

Exit 0 = proceed (OK, or TREE_DIRTY within the allow-list).
Exit 1 = PIN_MISMATCH (also: missing repo / unreadable lock / probe error).
Exit 2 = TREE_DIRTY_BLOCKING.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath

VERDICT_OK = "OK"
VERDICT_PIN_MISMATCH = "PIN_MISMATCH"
VERDICT_TREE_DIRTY = "TREE_DIRTY"
VERDICT_TREE_DIRTY_BLOCKING = "TREE_DIRTY_BLOCKING"

EXIT_PROCEED = 0
EXIT_PIN_MISMATCH = 1
EXIT_TREE_DIRTY_BLOCKING = 2

#: A dirty path under any of these is ALWAYS blocking, whatever its suffix —
#: ``src/`` is the import path, ``configs/`` is what the funnel reads. A README
#: under ``src/`` ships inside the package and blocks too.
BLOCKING_DIR_PREFIXES: tuple[str, ...] = ("src/", "configs/", "config/")
#: Suffixes that block anywhere: code and the files code reads.
BLOCKING_SUFFIXES: tuple[str, ...] = (".py", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini", ".sh")
#: The explicit NON-BLOCKING allow-list. Docs and READMEs (the renquant-model
#: README is an auto-generated docs table), anything under a docs directory,
#: and bytecode caches. Nothing else.
ALLOWED_DIRTY_SUFFIXES: tuple[str, ...] = (".md", ".rst")
ALLOWED_DIRTY_DIR_PREFIXES: tuple[str, ...] = ("doc/", "docs/")
ALLOWED_DIRTY_BASENAME_PREFIXES: tuple[str, ...] = ("README",)
GENERATED_DIRTY_PARTS: tuple[str, ...] = ("__pycache__",)
GENERATED_DIRTY_SUFFIXES: tuple[str, ...] = (".pyc",)


def classify_dirty_path(path: str) -> bool:
    """True when a dirty ``path`` (repo-relative, as ``git status --porcelain``
    prints it) BLOCKS the probe. Closed by default: only the explicit
    allow-list above is non-blocking, and the blocking rules win over it."""
    p = PurePosixPath(path.strip().strip('"'))
    rel = p.as_posix()
    if any(rel.startswith(pre) for pre in BLOCKING_DIR_PREFIXES):
        return True
    if any(part in GENERATED_DIRTY_PARTS for part in p.parts) or p.suffix in GENERATED_DIRTY_SUFFIXES:
        return False
    if p.suffix.lower() in BLOCKING_SUFFIXES:
        return True
    if any(rel.startswith(pre) for pre in ALLOWED_DIRTY_DIR_PREFIXES):
        return False
    if p.suffix.lower() in ALLOWED_DIRTY_SUFFIXES:
        return False
    if p.name.upper().startswith(ALLOWED_DIRTY_BASENAME_PREFIXES):
        return False
    return True


def porcelain_paths(porcelain: str) -> list[str]:
    """Repo-relative paths from ``git status --porcelain`` output; a rename
    ``R  old -> new`` contributes its NEW path (that is what is on disk)."""
    out: list[str] = []
    for line in porcelain.splitlines():
        if len(line) < 4:
            continue
        body = line[3:]
        if " -> " in body:
            body = body.split(" -> ", 1)[1]
        out.append(body.strip())
    return out


def _git(repo: Path, *args: str, raw: bool = False) -> str:
    """One read-only git read; '' on any failure (caller treats '' as not-ok).
    ``raw`` keeps leading whitespace: ``status --porcelain`` lines start with
    the two status columns and `` M README.md`` stripped reads ``M README.md``,
    whose path column is then off by one."""
    try:
        out = subprocess.run(["git", "-C", str(repo), *args],
                             capture_output=True, text=True, check=False)
        return out.stdout.rstrip("\n") if raw else out.stdout.strip()
    except Exception:  # noqa: BLE001
        return ""


def _repo_verdict(row: dict) -> str:
    if row.get("error") or not row["present"] or not row["pinned"]:
        return VERDICT_PIN_MISMATCH
    if row["blocking_dirty_files"]:
        return VERDICT_TREE_DIRTY_BLOCKING
    if row["dirty"]:
        return VERDICT_TREE_DIRTY
    return VERDICT_OK


def check(lock_path: Path, runtime_root: Path, repo_dir: Path | None = None) -> "tuple[str, list[dict]]":
    """Return ``(verdict, repos)`` — per-repo pin identity, READ-ONLY.

    Pin predicate == subrepo_assemble's ``_is_pinned``: runtime
    ``git log -1 --format=%H`` startswith the lock ``commit``. Dirtiness is
    ``git status --porcelain`` (``_is_dirty``), reported SEPARATELY and split
    by ``classify_dirty_path``. Any exception on a repo is captured as a
    PIN_MISMATCH row (fail-closed), never raised. ``repo_dir`` is unused (kept
    for call-site symmetry with the order path's aligner).

    The overall verdict is the worst per-repo verdict, PIN_MISMATCH >
    TREE_DIRTY_BLOCKING > TREE_DIRTY > OK.
    """
    lock = json.loads(Path(lock_path).read_text())
    repos: list[dict] = []
    for entry in lock["subrepos"]:
        name = entry.get("name", "?")
        lock_commit = str(entry.get("commit") or "")
        row = {"name": name, "lock_commit": lock_commit,
               "runtime_head": None, "present": False, "pinned": False,
               "dirty": None, "dirty_files": [], "blocking_dirty_files": [],
               "verdict": None, "ok": False, "error": None}
        try:
            path = Path(runtime_root) / name  # == subrepo_assemble._repo_path(runtime_root)
            row["present"] = path.exists()
            if row["present"]:
                head = _git(path, "log", "-1", "--format=%H")
                row["runtime_head"] = head or None
                # _is_pinned: expected non-empty AND head startswith expected
                row["pinned"] = bool(lock_commit) and bool(head) and head.startswith(lock_commit)
                # _is_dirty: status --porcelain non-empty; '' from a non-repo => not a repo => mismatch
                is_repo = bool(_git(path, "rev-parse", "--git-dir"))
                if not is_repo:
                    row["pinned"] = False
                    row["error"] = "not a git repository"
                status = _git(path, "status", "--porcelain", raw=True)
                row["dirty"] = bool(status)
                row["dirty_files"] = porcelain_paths(status)
                row["blocking_dirty_files"] = [f for f in row["dirty_files"] if classify_dirty_path(f)]
        except Exception as exc:  # noqa: BLE001 — fail-closed on any probe error
            row["error"] = f"{type(exc).__name__}: {exc}"
        row["verdict"] = _repo_verdict(row)
        row["ok"] = row["verdict"] in (VERDICT_OK, VERDICT_TREE_DIRTY)
        repos.append(row)
    return overall_verdict(repos), repos


_SEVERITY = {VERDICT_OK: 0, VERDICT_TREE_DIRTY: 1, VERDICT_TREE_DIRTY_BLOCKING: 2, VERDICT_PIN_MISMATCH: 3}


def overall_verdict(repos: list[dict]) -> str:
    worst = VERDICT_OK
    for r in repos:
        v = r.get("verdict") or VERDICT_PIN_MISMATCH
        if _SEVERITY[v] > _SEVERITY[worst]:
            worst = v
    return worst


def exit_code_for(verdict: str) -> int:
    if verdict == VERDICT_PIN_MISMATCH:
        return EXIT_PIN_MISMATCH
    if verdict == VERDICT_TREE_DIRTY_BLOCKING:
        return EXIT_TREE_DIRTY_BLOCKING
    return EXIT_PROCEED


def build_receipt(entrypoint: str, runtime_root: Path, lock_path: Path,
                  verdict: str, repos: list[dict], now_iso: str) -> dict:
    dirty = {r["name"]: r["dirty_files"] for r in repos if r.get("dirty_files")}
    blocking = {r["name"]: r["blocking_dirty_files"] for r in repos if r.get("blocking_dirty_files")}
    return {
        "receipt": "dawn_pin_identity_v2",
        "entrypoint": entrypoint,
        "runtime_root": str(runtime_root),
        "lock": str(lock_path),
        "checked_at": now_iso,
        "ok": verdict in (VERDICT_OK, VERDICT_TREE_DIRTY),
        "verdict": verdict,
        "pin_mismatch": verdict == VERDICT_PIN_MISMATCH,
        "tree_dirty": bool(dirty),
        "tree_dirty_blocking": verdict == VERDICT_TREE_DIRTY_BLOCKING,
        "dirty_files": dirty,
        "blocking_dirty_files": blocking,
        "repos": repos,
    }


def warn_lines(receipt: dict) -> list[str]:
    """Human lines for a non-blocking dirty tree — printed so the wrapper's
    stdout names the files instead of silently continuing."""
    if not receipt["tree_dirty"] or receipt["verdict"] != VERDICT_TREE_DIRTY:
        return []
    return [f"WARN: TREE_DIRTY (non-blocking, docs/README/generated only) — "
            f"{name}: {', '.join(files)}; pins all equal the lock, the probe continues"
            for name, files in receipt["dirty_files"].items()]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--repo-dir", required=True, type=Path,
                    help="umbrella repo dir (holds scripts/subrepo_assemble.py)")
    ap.add_argument("--runtime-root", required=True, type=Path,
                    help="the .subrepo_runtime/repos root to verify")
    ap.add_argument("--lock", required=True, type=Path,
                    help="subrepos.lock.json path")
    ap.add_argument("--entrypoint", default="dawn_funnel_preflight")
    ap.add_argument("--receipt-out", default=None, type=Path)
    ap.add_argument("--now", default=None,
                    help="ISO timestamp override (tests); default utcnow")
    a = ap.parse_args(argv)

    now_iso = a.now or _dt.datetime.now(_dt.timezone.utc).isoformat()
    try:
        verdict, repos = check(a.lock, a.runtime_root, a.repo_dir)
    except Exception as exc:  # noqa: BLE001 — unreadable lock / import failure => fail-closed
        verdict = VERDICT_PIN_MISMATCH
        repos = [{"error": f"{type(exc).__name__}: {exc}", "ok": False,
                  "verdict": VERDICT_PIN_MISMATCH, "dirty_files": [], "blocking_dirty_files": []}]

    receipt = build_receipt(a.entrypoint, a.runtime_root, a.lock, verdict, repos, now_iso)
    out = json.dumps(receipt, indent=2)
    print(out)
    for line in warn_lines(receipt):
        print(line)
    if a.receipt_out:
        a.receipt_out.write_text(out + "\n")
    return exit_code_for(verdict)


if __name__ == "__main__":
    sys.exit(main())
