#!/usr/bin/env python3
"""Run-surface drift scan (GOAL-5 AC2: run surface == reviewed surface).

Two invisible-divergence classes enabled the 2026-07-16 incident:

  1. Run checkouts drifting from their reviewed refs — the
     renquant-orchestrator-run checkout sat ~130 commits behind origin/main
     carrying six uncommitted hotfixes; nothing tracked either fact.
  2. launchd job definitions living outside git — a sell-only containment
     wrapper silently replaced the daily104 ProgramArguments on 07-15 and
     starved the book for a day with zero durable record.

This checker makes both loud within one scheduled firing:

  a. git checkouts: every subrepos.lock.json runtime repo must sit exactly
     at its pinned commit and be clean; the orchestrator-run checkout must
     sit on origin/main (fetched ref as of the last fetch) and be clean.
     Tracked modifications alarm; untracked files are reported as info.
  b. launchd surface: the ProgramArguments of every com.renquant.* plist
     in ~/Library/LaunchAgents must match the committed manifest
     (ops/launchd_manifest.json). A swapped program, a new unmanifested
     job, or a manifested job missing from disk all alarm.

Intentional persistent changes belong IN the manifest / refs (update them
in the same reviewed change); an emergency containment that skips that
step gets alarmed daily BY DESIGN — that is the reminder to lift it or
legitimize it (see the CONTAINMENT PROTOCOL in CLAUDE.md).

Read-only: plain git queries + file reads; never mutates any checkout.
"""
from __future__ import annotations

import hashlib
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from liveness_common import alert  # noqa: E402

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
ORCH_RUN = os.environ.get("RQ_ORCH_ROOT", "/Users/renhao/git/github/renquant-orchestrator-run")
LOCK_FILE = os.path.join(RQ, "subrepos.lock.json")
RUNTIME_ROOT = os.path.join(RQ, ".subrepo_runtime", "repos")
LAUNCH_AGENTS = os.path.expanduser("~/Library/LaunchAgents")
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "launchd_manifest.json")
LABEL_PREFIX = "com.renquant."


# ---------------------------------------------------------------------------
# git surface
# ---------------------------------------------------------------------------

def _git(repo: str, *args: str) -> str | None:
    """Read-only git query; None on any failure (caller decides severity)."""
    try:
        res = subprocess.run(
            ["git", "-C", repo, *args],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:  # noqa: BLE001
        return None
    if res.returncode != 0:
        return None
    return res.stdout.strip()


def classify_status(porcelain: str) -> tuple[list[str], list[str]]:
    """Split `git status --porcelain` into (tracked_changes, untracked)."""
    tracked, untracked = [], []
    for line in porcelain.splitlines():
        if not line.strip():
            continue
        (untracked if line.startswith("??") else tracked).append(line.strip())
    return tracked, untracked


def check_checkout(repo: str, expected_commit: str | None, label: str) -> tuple[list[str], list[str]]:
    """Return (problems, infos) for one checkout."""
    problems: list[str] = []
    infos: list[str] = []
    if not os.path.isdir(repo):
        return [f"{label}: checkout missing ({repo})"], infos
    head = _git(repo, "rev-parse", "HEAD")
    if head is None:
        return [f"{label}: not a readable git checkout ({repo})"], infos
    if expected_commit and head != expected_commit:
        problems.append(
            f"{label}: HEAD {head[:12]} != expected {expected_commit[:12]}"
        )
    porcelain = _git(repo, "status", "--porcelain")
    if porcelain is None:
        problems.append(f"{label}: git status failed")
    else:
        tracked, untracked = classify_status(porcelain)
        if tracked:
            problems.append(
                f"{label}: {len(tracked)} uncommitted tracked change(s): "
                + "; ".join(tracked[:5])
                + ("; …" if len(tracked) > 5 else "")
            )
        if untracked:
            infos.append(f"{label}: {len(untracked)} untracked path(s) (info)")
    return problems, infos


def check_git_surfaces() -> tuple[list[str], list[str]]:
    problems: list[str] = []
    infos: list[str] = []

    # runtime repos vs subrepos.lock.json pins
    try:
        lock = json.loads(Path(LOCK_FILE).read_text())
        entries = lock.get("subrepos", [])
    except Exception as exc:  # noqa: BLE001
        return [f"subrepos.lock.json unreadable ({exc})"], infos
    for entry in entries:
        name = entry.get("name", "?")
        commit = entry.get("commit")
        repo = os.path.join(RUNTIME_ROOT, name)
        if not os.path.isdir(repo):
            # not every locked repo is materialized in the runtime root
            continue
        p, i = check_checkout(repo, commit, f"runtime/{name}")
        problems += p
        infos += i

    # orchestrator-run vs its fetched origin/main
    expected = _git(ORCH_RUN, "rev-parse", "origin/main")
    p, i = check_checkout(ORCH_RUN, expected, "orchestrator-run")
    problems += p
    infos += i
    return problems, infos


# ---------------------------------------------------------------------------
# launchd surface
# ---------------------------------------------------------------------------

def program_args_digest(program_args: list[str]) -> str:
    return hashlib.sha256(json.dumps(program_args).encode()).hexdigest()


def _plist_load(path: str) -> dict | None:
    try:
        with open(path, "rb") as fh:
            return plistlib.load(fh)
    except Exception:  # noqa: BLE001
        # plistlib's expat rejects `--` inside XML comments, which two of the
        # heavily-annotated plists contain; plutil is lenient — normalize
        # through it as the fallback.
        try:
            res = subprocess.run(
                ["plutil", "-convert", "xml1", "-o", "-", "--", path],
                capture_output=True, timeout=30,
            )
            if res.returncode != 0:
                return None
            return plistlib.loads(res.stdout)
        except Exception:  # noqa: BLE001
            return None


def read_plist_program_args(path: str) -> list[str] | None:
    data = _plist_load(path)
    if data is None:
        return None
    args = data.get("ProgramArguments")
    if isinstance(args, list):
        return [str(a) for a in args]
    # launchd also accepts a bare `Program` string
    prog = data.get("Program")
    return [str(prog)] if isinstance(prog, str) else None


def scan_launchd_plists(agents_dir: str = LAUNCH_AGENTS) -> dict[str, dict]:
    """label -> {program_args, program_args_sha256} for com.renquant.* plists.
    Disabled/backup files (*.disabled*, *.bak*) are not live surface."""
    out: dict[str, dict] = {}
    for p in sorted(Path(agents_dir).glob(f"{LABEL_PREFIX}*.plist")):
        name = p.name
        if ".bak" in name or ".disabled" in name:
            continue
        label = name[: -len(".plist")]
        args = read_plist_program_args(str(p))
        if args is None:
            out[label] = {"program_args": None, "program_args_sha256": None}
            continue
        out[label] = {
            "program_args": args,
            "program_args_sha256": program_args_digest(args),
        }
    return out


def check_launchd_surface(
    manifest_path: str = MANIFEST, agents_dir: str = LAUNCH_AGENTS,
) -> list[str]:
    problems: list[str] = []
    try:
        manifest = json.loads(Path(manifest_path).read_text())["jobs"]
    except Exception as exc:  # noqa: BLE001
        return [f"launchd manifest unreadable ({manifest_path}: {exc})"]
    live = scan_launchd_plists(agents_dir)

    for label, spec in sorted(manifest.items()):
        if label not in live:
            problems.append(f"launchd: manifested job {label} missing from disk")
            continue
        got = live[label]["program_args_sha256"]
        if got is None:
            problems.append(f"launchd: {label} plist unreadable / no ProgramArguments")
        elif got != spec["program_args_sha256"]:
            problems.append(
                f"launchd: {label} ProgramArguments CHANGED "
                f"(disk={live[label]['program_args']} != manifest="
                f"{spec['program_args']}) — silent containment / job swap?"
            )
    for label in sorted(set(live) - set(manifest)):
        problems.append(
            f"launchd: unmanifested com.renquant job on disk: {label} "
            f"(add to ops/launchd_manifest.json via a reviewed change)"
        )
    return problems


def generate_manifest(agents_dir: str = LAUNCH_AGENTS) -> dict:
    return {
        "_comment": (
            "Reviewed-good launchd surface (GOAL-5 AC2). Every com.renquant.* "
            "job's ProgramArguments is pinned here; the drift scan alarms on "
            "any divergence. Intentional changes update this file in the same "
            "reviewed PR."
        ),
        "jobs": scan_launchd_plists(agents_dir),
    }


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--emit-manifest", action="store_true",
        help="print a fresh manifest for the CURRENT plists and exit "
             "(output is committed via a reviewed PR, never auto-written)",
    )
    args = parser.parse_args(argv)

    if args.emit_manifest:
        print(json.dumps(generate_manifest(), indent=2))
        return 0

    problems: list[str] = []
    infos: list[str] = []

    p, i = check_git_surfaces()
    problems += p
    infos += i
    problems += check_launchd_surface()

    for line in infos:
        print(f"INFO: {line}")

    if problems:
        alert(
            f"RUN-SURFACE DRIFT: {len(problems)} issue(s)",
            "\n".join(problems),
            rq_root=RQ,
        )
        print("\n".join(problems))
        return 1

    print("run-surface drift scan OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
