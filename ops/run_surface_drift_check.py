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
  c. launchd EFFECT: a manifested job must be RUNNING the definition on
     disk. Editing a plist does not reload it, so a reviewed change can
     land on disk and never take effect while (b) reports clean.

Intentional persistent changes belong IN the manifest / refs (update them
in the same reviewed change); an emergency containment that skips that
step gets alarmed daily BY DESIGN — that is the reminder to lift it or
legitimize it (see the CONTAINMENT PROTOCOL in CLAUDE.md).

Read-only: plain git queries + file reads; never mutates any checkout.
"""
from __future__ import annotations

import hashlib
import datetime as dt
import json
import os
import plistlib
import re
import subprocess
import sys
import time
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


#: launchctl's exit code for "no such service in this domain". Measured
#: 2026-07-29 on this machine: a deliberately-unloaded manifested job
#: (com.renquant.daily103) and a label that has never existed BOTH return 113
#: with an empty stdout and `Bad request. Could not find service … in domain`
#: on stderr, while a loaded job returns 0. So 113 identifies "not loaded"
#: exactly, and every OTHER failure is the checker's problem, not the job's.
LAUNCHCTL_NOT_FOUND_RC = 113

#: read_loaded_program_args statuses.
LOADED_OK = "ok"                    # args read successfully
LOADED_NOT_LOADED = "not_loaded"    # job genuinely absent from the domain
LOADED_UNREADABLE = "unreadable"    # launchctl failed in some other way
LOADED_UNPARSED = "unparsed"        # launchctl succeeded, output not understood


def read_loaded_program_args(label: str) -> tuple[str, list[str] | None, str]:
    """ProgramArguments launchd is ACTUALLY running, not what is on disk.

    Editing a plist does not change the running job: launchd keeps serving the
    definition it loaded until something re-bootstraps it. So a reviewed change
    can land in the manifest, land on disk, and never take effect — with the
    manifest-vs-disk check reporting clean the whole time.

    Measured 2026-07-29: the rq105 export plist was switched to the wrapper at
    06:29:53, 14 minutes AFTER that morning's 06:15:04 run had already produced
    `score_source=prod` from the old definition. It happened to have been
    re-bootstrapped, but nothing in this scan verified that — it was
    established by hand, comparing three timestamps.

    Returns ``(status, args, detail)``. The status distinction matters more
    than it looks: an earlier revision collapsed "not loaded" and "could not
    read launchctl" into a single ``None``, so a permission change, a macOS
    output-shape change, or a broken invocation would have silently disabled
    this check across every job while the scan still reported clean — the
    exact false-negative class this check exists to close.
    """
    try:
        res = subprocess.run(
            ["launchctl", "print", f"gui/{os.getuid()}/{label}"],
            capture_output=True, text=True, timeout=20,
        )
    except Exception as exc:  # noqa: BLE001
        return LOADED_UNREADABLE, None, f"launchctl invocation failed: {exc}"
    if res.returncode == LAUNCHCTL_NOT_FOUND_RC:
        return LOADED_NOT_LOADED, None, "not loaded in this domain"
    if res.returncode != 0:
        return (LOADED_UNREADABLE, None,
                f"launchctl exit {res.returncode}: "
                f"{(res.stderr or '').strip()[:160]}")
    # `arguments = {\n\t\targ\n\t\targ\n\t}` — take the first such block.
    out = res.stdout
    m = re.search(r"^\s*arguments\s*=\s*\{\s*$", out, flags=re.MULTILINE)
    if not m:
        return (LOADED_UNPARSED, None,
                "launchctl succeeded but no `arguments = {` block was found "
                "(output shape changed?)")
    args: list[str] = []
    for line in out[m.end():].splitlines()[1:]:
        stripped = line.strip()
        if stripped == "}":
            break
        if stripped:
            args.append(stripped)
    if not args:
        return LOADED_UNPARSED, None, "`arguments` block present but empty"
    return LOADED_OK, args, ""


def check_launchd_loaded(
    manifest_path: str = MANIFEST, agents_dir: str = LAUNCH_AGENTS,
) -> list[str]:
    """Manifested jobs must be RUNNING the definition that is on disk.

    Separate from `check_launchd_surface` on purpose: that one answers "did
    someone change the surface behind review", this one answers "is the
    reviewed surface actually in force". A job can pass the first and fail the
    second indefinitely, which is the silent half of a run-surface change.

    A job that is genuinely NOT LOADED is not reported — that is a liveness
    question, and inventing a drift alarm for it would fire on every job the
    operator has deliberately unloaded. But a job whose loaded state could not
    be READ is reported, because a checker that cannot see is indistinguishable
    from a checker that sees nothing wrong, and only one of those is safe to
    stay quiet about.
    """
    problems: list[str] = []
    try:
        manifest = json.loads(Path(manifest_path).read_text())["jobs"]
    except Exception as exc:  # noqa: BLE001
        return [f"launchd manifest unreadable ({manifest_path}: {exc})"]
    live = scan_launchd_plists(agents_dir)

    for label in sorted(manifest):
        disk = live.get(label, {}).get("program_args")
        if disk is None:
            continue                      # already reported by the disk check
        status, loaded, detail = read_loaded_program_args(label)
        if status == LOADED_NOT_LOADED:
            continue                      # deliberate: a liveness question
        if status in (LOADED_UNREADABLE, LOADED_UNPARSED):
            problems.append(
                f"launchd: cannot determine what {label} is actually running "
                f"({status}: {detail}) — the loaded-vs-disk check is BLIND for "
                f"this job, so a plist edited without re-bootstrapping would "
                f"not be caught. Fix the checker, do not ignore this."
            )
            continue
        if loaded != disk:
            problems.append(
                f"launchd: {label} is RUNNING a different program than its "
                f"plist on disk (loaded={loaded} != disk={disk}) — the plist "
                f"was edited without re-bootstrapping, so the reviewed change "
                f"is NOT in force. Reload the job or revert the file."
            )
    return problems


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

def check_umbrella_branch() -> list[str]:
    """The umbrella LIVE tree must be on `main`.

    The working tree's CONTENT is deliberately outside this scan's alarm
    scope (operator edit surface; artifact integrity = AC4), but the BRANCH
    NAME is run-surface state: the daily wrapper hard-refuses non-main
    checkouts, so a stray branch silently disables the 13:55 decision run
    until the guard fires mid-day (2026-07-17: a leftover working branch
    from PR prep blocked the daily; content was identical to main, only the
    ref name was wrong). Catch it at the 07:00 scan instead.
    """
    head_file = Path(RQ) / ".git" / "HEAD"
    try:
        head = head_file.read_text(encoding="utf-8").strip()
    except OSError as exc:
        return [f"umbrella: cannot read {head_file}: {exc}"]
    if head == "ref: refs/heads/main":
        return []
    return [
        f"umbrella live tree not on main ({head!r}) — the daily wrapper "
        "will refuse to run; restore with git checkout main (never reset "
        "--hard: uncommitted operational fixes may be present)"
    ]


STALE_FETCH_DAYS = 7


def _resolve_ref(repo: str, ref: str) -> str | None:
    """Resolve a ref to a sha WITHOUT invoking git in `repo`.

    This scan reads the umbrella's git metadata as FILES on purpose. Running
    git in the live tree is forbidden here (a sub-agent's `git reset --hard`
    in this shared checkout is why), and a read-only-looking git invocation is
    one typo away from a writing one. Loose ref first, then packed-refs.
    """
    loose = Path(repo) / ".git" / ref
    try:
        text = loose.read_text(encoding="utf-8").strip()
        if text:
            return text.split()[0]
    except OSError:
        pass
    packed = Path(repo) / ".git" / "packed-refs"
    try:
        for line in packed.read_text(encoding="utf-8").splitlines():
            if line.startswith("#") or line.startswith("^"):
                continue
            parts = line.split()
            if len(parts) == 2 and parts[1] == ref:
                return parts[0]
    except OSError:
        pass
    return None


def check_umbrella_deploy_lag(now: float | None = None) -> tuple[list[str], list[str]]:
    """The umbrella live tree must actually BE the merged main, not just on it.

    `check_umbrella_branch` verifies the branch NAME. That is not enough: the
    daily run consumes local sibling checkouts by path, so a tree sitting on
    `main` at an OLD commit runs old code while every dashboard says the fix
    merged. Measured 2026-07-29: the live umbrella sat 9 commits behind
    origin/main, so `scripts/train_production_model.py --panel` (merged in
    umbrella#543) was absent from the tree that actually runs -- and the
    branch-name check passed clean the whole time.

    Two signals, because the first one alone can lie:
      (a) refs/heads/main != refs/remotes/origin/main  -> merged-but-not-deployed
      (b) the fetched remote ref is itself stale        -> (a) cannot be trusted,
          since origin/main here is only as fresh as the last fetch INTO this
          tree, and this scan will not fetch (that is a write).
    """
    problems: list[str] = []
    infos: list[str] = []
    live = _resolve_ref(RQ, "refs/heads/main")
    fetched = _resolve_ref(RQ, "refs/remotes/origin/main")

    if live is None:
        return ([f"umbrella: cannot resolve refs/heads/main under {RQ}/.git "
                 "(neither loose nor packed) -- deploy lag is unmeasurable"], infos)
    if fetched is None:
        return ([f"umbrella: no refs/remotes/origin/main under {RQ}/.git, so "
                 f"deploy lag is unmeasurable; live main is {live[:8]}. Fetch "
                 "once in the live tree (operator action -- this scan does not "
                 "write) to arm this check."], infos)

    # Fetch freshness first: a stale fetch makes an EQUAL comparison meaningless,
    # so report it even when (a) looks clean.
    stamp = None
    for candidate in (Path(RQ) / ".git" / "FETCH_HEAD",
                      Path(RQ) / ".git" / "refs" / "remotes" / "origin" / "main"):
        try:
            stamp = candidate.stat().st_mtime
            break
        except OSError:
            continue
    age_days = None
    if stamp is not None:
        age_days = ((now if now is not None else time.time()) - stamp) / 86400.0

    if live != fetched:
        problems.append(
            f"umbrella live tree is NOT the fetched origin/main: "
            f"refs/heads/main={live[:8]} vs origin/main={fetched[:8]}. Merged "
            f"umbrella changes are DARK on the daily run until this tree syncs. "
            f"Sync is an operator action (git -C {RQ} pull --ff-only after a "
            f"read-only preflight); NEVER `checkout -- .` or `reset --hard`, "
            f"which has clobbered uncommitted operational fixes before."
        )
    elif age_days is not None:
        infos.append(f"umbrella deploy lag: none (main == origin/main "
                     f"{live[:8]}), fetched {age_days:.1f}d ago")

    if age_days is not None and age_days > STALE_FETCH_DAYS:
        problems.append(
            f"umbrella origin/main ref is {age_days:.1f}d old (> "
            f"{STALE_FETCH_DAYS}d): the deploy-lag comparison above is against "
            f"a stale remote and can report 'in sync' while upstream has moved."
        )
    return problems, infos


def check_sentinel_receipt(now: float | None = None) -> tuple[list[str], list[str]]:
    """Is the rq104 degradation sentinel actually running? (GOAL-1, issue #622)

    This check lives HERE and not in the sentinel because a process cannot attest
    to its own liveness — if it is dead it is not running to notice. The drift scan
    is a separate launchd job, so it is still alive when the sentinel is not.

    The three cases that used to be one observable:

    * receipt absent          -> the sentinel has never completed a firing. LOUD.
    * receipt stale           -> it has stopped firing. LOUD.
    * receipt says internal   -> it is crashing. LOUD, and this is the case that was
      error                      previously invisible behind the acked exit 1.
    * receipt says alarms     -> INFO only. That is the sentinel's own designed
                                 signal and it delivers its own alert; double-
                                 alarming here would train the reader to ignore both.
    """
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    "renquant104"))
    try:
        from sentinel_receipt import (
            KNOWN_OUTCOMES,
            MAX_RECEIPT_AGE_S,
            RECEIPT_SCHEMA_VERSION,
            read_receipt,
            receipt_path,
        )
    except Exception as exc:  # noqa: BLE001
        return ([f"cannot import the sentinel receipt module: "
                 f"{type(exc).__name__}: {exc} — sentinel liveness unverifiable"], [])

    path = receipt_path()
    data, err = read_receipt(path)
    if err is not None:
        return ([f"rq104 sentinel receipt at {path} is unreadable ({err}) — cannot "
                 f"distinguish a crashed sentinel from an alarming one"], [])
    if data is None:
        return ([f"rq104 sentinel receipt absent at {path} — the sentinel has not "
                 f"completed a firing since this check was deployed, so its exit 1 "
                 f"cannot be read as either an alarm or a crash"], [])

    written = data.get("written_at")
    try:
        age = (now if now is not None else time.time()) - dt.datetime.fromisoformat(
            str(written)).timestamp()
    except Exception:  # noqa: BLE001
        return ([f"rq104 sentinel receipt has an unparseable written_at "
                 f"({written!r}) — liveness unverifiable"], [])

    # Validate the receipt BEFORE trusting any field in it. A missing, misspelled or
    # future `outcome`, or an unrecognised schema version, means liveness has NOT
    # been established --- it must never fall through to "clean". Codex BLOCKER on
    # #625: the first version treated any fresh non-error outcome as healthy, so a
    # malformed receipt suppressed the failure this guard exists to surface. That is
    # the guard-passes-on-absent-input shape #623 catalogues, in the guard I wrote to
    # fix an instance of it.
    version = data.get("schema_version")
    if version != RECEIPT_SCHEMA_VERSION:
        return ([f"rq104 sentinel receipt has schema_version {version!r}, expected "
                 f"{RECEIPT_SCHEMA_VERSION!r} — refusing to interpret an "
                 f"unrecognised receipt as healthy"], [])

    outcome = data.get("outcome")
    if outcome not in KNOWN_OUTCOMES:
        return ([f"rq104 sentinel receipt carries outcome {outcome!r}, which is not "
                 f"one of {sorted(KNOWN_OUTCOMES)} — liveness NOT established "
                 f"(a missing or misspelled outcome must not read as clean)"], [])

    if age > MAX_RECEIPT_AGE_S:
        return ([f"rq104 sentinel receipt is {age / 86400:.1f} days old "
                 f"(limit {MAX_RECEIPT_AGE_S / 86400:.0f}d, outcome={outcome!r}) — "
                 f"the sentinel has stopped firing"], [])
    if outcome == "internal_error":
        return ([f"rq104 sentinel FAILED INTERNALLY at {written}: "
                 f"{data.get('error')!r} — this is a crash, not its alarm signal"], [])
    if outcome == "alarms":
        return ([], [f"rq104 sentinel fired at {written} with "
                     f"{data.get('alarm_count')} alarm(s) — it delivers its own "
                     f"alert; recorded here only as liveness"])
    return ([], [])


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
    problems += check_umbrella_branch()
    p, i = check_umbrella_deploy_lag()
    problems += p
    infos += i
    problems += check_launchd_surface()
    problems += check_launchd_loaded()
    p, i = check_sentinel_receipt()
    problems += p
    infos += i

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
