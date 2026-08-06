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
import pathlib
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

def _emit(stamp: str, record: str) -> None:
    """Print `record` with `stamp` on EVERY physical line.

    Codex BLOCKER on orch#664: the first version stamped each list ELEMENT.
    A record containing an embedded newline — and several do, e.g. the umbrella
    branch problem quotes a multi-line git ref, and any exception text can — was
    rendered by `print` as one stamped line followed by UNSTAMPED continuation
    lines, recreating exactly the attribution failure this change exists to
    remove. The tests only used single-line fixtures, so they missed it.

    An EMPTY record still emits one stamped line (`<stamp> ` with nothing after)
    rather than nothing: a record that was produced must remain countable, and
    silently dropping it is the same class of loss.
    """
    for physical in (record.splitlines() or [""]):
        print(f"{stamp} {physical}")


def _now_iso(now: "dt.datetime | None" = None) -> str:
    """Local ISO-8601 second-resolution stamp for the START of every output line.

    Injectable so tests pin the format instead of the wall clock.
    """
    return (now or dt.datetime.now()).strftime("%Y-%m-%dT%H:%M:%S")


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


def check_referenced_checkout_freshness() -> tuple[list[str], list[str]]:
    """How far behind `origin/main` is each checkout the scheduled jobs run from?

    This is class 1 in this module's own docstring — "run checkouts drifting from
    their reviewed refs" — and until now nothing scheduled measured it.
    `check_checkout` above compares HEAD against a declared PIN; a checkout with no
    pin, or one whose pin is itself old, passes it while being months stale.

    `ops/referenced_checkout_freshness.py` has done this correctly for a while and
    was wired to nothing: not to a launchd job, not named in the reviewed manifest.
    Measured 2026-08-05 by running it by hand: `renquant-orchestrator-run` was **36
    commits behind** `origin/main` with **21 jobs** running from it, past its own
    declared bound of 20 — so every fix merged that morning was not what ran.

    The distance is counted in the reference (dev) checkout, never in the one being
    measured: a run checkout that has not fetched carries a stale `origin/main` and,
    asked about itself, answers "0 behind". That is the defect, and the probe
    documents having once had it.
    """
    problems: list[str] = []
    infos: list[str] = []
    try:
        import referenced_checkout_freshness as rcf
    except Exception as exc:  # noqa: BLE001
        return ([f"checkout-freshness: probe unimportable ({type(exc).__name__}: {exc}) "
                 f"— NOT a clean result"], infos)
    try:
        report = rcf.scan()
    except Exception as exc:  # noqa: BLE001
        return ([f"checkout-freshness: scan failed ({type(exc).__name__}: {exc}) "
                 f"— could not check is not checked-and-fresh"], infos)

    if not report.get("results"):
        return (["checkout-freshness: no absolute checkout paths found in "
                 "program_args — nothing was measured"], infos)

    # The failing set is the probe's own, not a second enumeration here.
    for r in rcf.failing(report):
        problems.append(
            f"checkout-freshness {r.get('checkout', '?')}: {r.get('status')} — "
            f"{r.get('detail') or 'no detail'} "
            f"({r.get('referenced_by_jobs', '?')} job(s) run from it)"
        )
    for r in report["results"]:
        if r not in rcf.failing(report):
            infos.append(
                f"checkout-freshness {r.get('checkout', '?')}: {r.get('status')} "
                f"({r.get('commits_behind', '-')} behind)"
            )
    return problems, infos


def check_import_resolution() -> tuple[list[str], list[str]]:
    """Do this repo's imported public symbols still resolve where they were reviewed?

    GOAL-3 #623: in four of seven registered twin sites a defect was filed or a fix
    written against a copy that does not run, because nothing in the repo said which
    copy executes. `ops/import_resolution_check.py` pins that, and this is what makes
    the pin a gate rather than a document nobody runs.

    A sibling package that cannot be imported is reported LOUD rather than skipped:
    the orchestrator cannot run without its siblings, so an unimportable one is a
    real run-surface defect, and a check that goes quiet when its input is missing is
    the exact shape #623 catalogues.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, here)
    try:
        import import_resolution_check as irc
    except Exception as exc:  # noqa: BLE001
        return ([f"cannot import ops/import_resolution_check.py: "
                 f"{type(exc).__name__}: {exc} — symbol resolution unverifiable"], [])
    pins_path = pathlib.Path(irc.PINS)
    if not pins_path.exists():
        return ([f"import-resolution pin file missing at {pins_path} — run "
                 f"`ops/import_resolution_check.py --emit` and commit it"], [])
    try:
        pins = json.loads(pins_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return ([f"import-resolution pin file unreadable: "
                 f"{type(exc).__name__}: {exc}"], [])
    problems = irc.verify(pins)
    if problems:
        return ([f"import-resolution: {p}" for p in problems], [])
    return ([], [f"import-resolution OK — {len(irc.PINNED_SYMBOLS)} symbols resolve "
                 f"as reviewed"])


def report_manifested_not_loaded(
    manifest_path: str = MANIFEST, agents_dir: str = LAUNCH_AGENTS,
) -> tuple[list[str], list[str]]:
    """INFO ONLY: manifested jobs that are not loaded, and which KIND of not-loaded.

    `check_launchd_loaded` deliberately does not alarm on an unloaded job, and that
    decision is right: it would fire on every job an operator has deliberately
    unloaded. But saying nothing at all leaves a real gap. A job in the REVIEWED
    manifest that is not loaded is either a manifest nobody updated when the job was
    retired, or a job that silently fell out of launchd -- and **nothing distinguishes
    those two**, which is the containment shape: a persistent run-surface change with
    no durable record.

    So this REPORTS without alarming. The three kinds have different remedies and are
    named separately, because "not loaded" lumps them together and hides that:

      * plist + target present -> loaded once, not now. Retirement or silent unload;
        only a human knows which, and the manifest does not say.
      * plist absent, target present -> ready to install, never installed.
      * plist absent, target absent -> the run checkout has not been synced.

    Measured on the RUN HOST 2026-07-31, 43 manifested jobs: 6 not loaded — 3 of the
    first kind (daily103, open103, preclose103), 1 of the second
    (rq104-model-freshness), 2 of the third (ops-audit, rq104-silent-refusal). The
    last two include the aggregator that DISCOVERED an unrun AC5 sentinel; it does
    not run either. That census is one host on one day, not a property of this code:
    the tests classify a synthetic manifest against a mocked launchd, because a host
    without launchd at all (CI) legitimately reports zero.
    """
    try:
        manifest = json.loads(Path(manifest_path).read_text())["jobs"]
    except Exception as exc:  # noqa: BLE001
        return ([f"launchd manifest unreadable ({manifest_path}: {exc})"], [])
    live = scan_launchd_plists(agents_dir)
    kinds: dict[str, list[str]] = {"retired_or_silently_unloaded": [],
                                   "never_installed": [], "run_checkout_unsynced": []}
    for label in sorted(manifest):
        status, _loaded, _d = read_loaded_program_args(label)
        if status != LOADED_NOT_LOADED:
            continue
        has_plist = label in live
        args = (manifest.get(label) or {}).get("program_args") or []
        tgt = next((a for a in args if str(a).endswith((".sh", ".py"))), None)
        has_target = bool(tgt and os.path.exists(tgt))
        if has_plist and has_target:
            kinds["retired_or_silently_unloaded"].append(label)
        elif has_target:
            kinds["never_installed"].append(label)
        else:
            kinds["run_checkout_unsynced"].append(label)
    infos: list[str] = []
    total = sum(len(v) for v in kinds.values())
    infos.append(f"launchd: {total} of {len(manifest)} manifested job(s) are NOT loaded")
    for kind, labels in kinds.items():
        if labels:
            infos.append(f"launchd not-loaded [{kind}]: {', '.join(sorted(labels))}")
    if kinds["retired_or_silently_unloaded"]:
        infos.append(
            "launchd: the manifest does not record whether those were RETIRED or fell "
            "out of launchd silently — the two are indistinguishable from here, and "
            "only one of them is fine")
    return [], infos

#: The two-line fallback idiom the rq105 wrappers use to pick a checkout:
#:     VAR="<...>-run/src"
#:     [ -d "$VAR" ] || VAR="<...>/src"
#: NOTE the value is NOT `[^"]*`: the wrappers write
#:     RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common-run/src"
#: whose value contains NESTED double quotes, so a character class excluding `"`
#: cannot span it. Matching to end-of-line is what actually reads this shape --
#: my first version excluded quotes and matched nothing, and only the residual
#: assertion below stopped that from reading as "clean".
_FALLBACK_RE = re.compile(
    r'^(?P<var>[A-Z_]+)="(?P<pref>.*-run/src)"[ \t]*\n'
    r'[ \t]*\[ -d "\$(?P=var)" \] \|\| (?P=var)="(?P<fall>.*)"',
    re.M,
)


def _expand(expr: str, repos_root: str) -> str:
    """Resolve the shell expression to a path, best effort.

    Only the shapes the wrappers actually use are handled; anything else is
    returned unchanged and reported as unresolvable rather than assumed fine.
    """
    tail = expr.split("/")[-2:]                       # e.g. ['renquant-common-run','src']
    return os.path.join(repos_root, *tail) if len(tail) == 2 else expr


def _scheduled_wrappers(manifest_path: str, ops_dir: str) -> list[tuple[str, str]]:
    """(job, wrapper path) for every MANIFESTED job, from the manifest — not from
    a regex over whatever happens to be on disk.

    The inventory has to be independent of the defect being looked for. Deriving
    it from the fallback pattern (the first version of this check) made a
    *repaired* fleet indistinguishable from a fleet with no wrappers at all: fix
    every wrapper and the scan finds nothing, which the anti-vacuity guard then
    reports as a problem. A production drift check that cannot go green after the
    documented remediation is not a check, it is a ratchet.
    """
    with open(manifest_path, encoding="utf-8") as fh:
        data = json.load(fh)
    jobs = data.get("jobs") or data
    out: list[tuple[str, str, str]] = []
    for job, spec in sorted(jobs.items()):
        args = (spec or {}).get("program_args") or []
        for a in args:
            if not str(a).endswith(".sh"):
                continue
            local = os.path.join(ops_dir, *str(a).split("/ops/")[-1].split("/")) \
                if "/ops/" in str(a) else None
            if local and os.path.exists(local):
                out.append((job, str(a), local))
            else:                       # wrapper lives outside this repo's ops/
                matches = [str(q) for q in pathlib.Path(ops_dir).rglob(os.path.basename(a))]
                # The DECLARED path is carried alongside the resolved one. Without it
                # an unresolvable entry is just an empty string, and "missing" cannot
                # be told apart from "owned by another repo" -- which is what let the
                # caller treat both as informational.
                out.append((job, str(a), matches[0] if matches else ""))
    return out


def _wrapper_scope_boundaries(manifest_path: str) -> list[dict]:
    """Reviewed declarations of wrappers this scanner deliberately does not inspect.

    Each entry is `{root, owner, why}`. A boundary is a CLAIM that some other surface
    checks that wrapper, so it belongs in the reviewed manifest where changing it
    requires a PR -- not in this file, and never inferred from what happens to be
    missing on disk today. An undeclared missing wrapper is a problem; that is the
    inverted default, and extending this list is the only way to silence one.
    """
    try:
        with open(manifest_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:  # noqa: BLE001 - the caller already reports unreadable manifests
        return []
    out = []
    for b in data.get("wrapper_scope_boundaries") or []:
        if isinstance(b, dict) and b.get("root") and b.get("owner"):
            out.append(b)
    return out


def _owning_boundary(declared: str, boundaries: list[dict]) -> dict | None:
    """The declared boundary owning `declared`, or None.

    Prefix match on a normalised path, longest root first, so a nested root wins over
    the tree containing it -- `RenQuant/.subrepo_runtime/...` must not be absorbed by
    a boundary declared for `RenQuant/`.
    """
    if not declared:
        return None
    d = os.path.normpath(declared)
    for b in sorted(boundaries, key=lambda x: len(str(x["root"])), reverse=True):
        root = os.path.normpath(str(b["root"]))
        if d == root or d.startswith(root.rstrip(os.sep) + os.sep):
            return b
    return None


def _scan_wrapper_text(job: str, text: str, repos_root: str,
                       problems: list[str], infos: list[str],
                       origin: str = "") -> None:
    """The one fallback-idiom scan, shared by the local path and the #682
    read-only cross-repo path so the two can never drift apart."""
    hits = list(_FALLBACK_RE.finditer(text))
    if not hits:
        if "PYTHONPATH" in text:
            infos.append(
                f"pythonpath {job}: declares a deterministic root{origin}")
        return
    for m in hits:
        pref = _expand(m.group("pref"), repos_root)
        fall = _expand(m.group("fall"), repos_root)
        fires = not os.path.isdir(pref)
        problems.append(
            f"pythonpath {job}: resolves a sibling checkout by FALLBACK "
            f"({pref} else {fall}) — which copy executes is decided by "
            f"filesystem state, not by review"
            + (f"; the fallback IS firing today ({pref} is absent)" if fires
               else "; it does not fire today, which does not make it reviewed")
            + origin)


def check_wrapper_pythonpath_roots(
    ops_dir: str | None = None,
    repos_root: str | None = None,
    manifest_path: str | None = None,
) -> tuple[list[str], list[str]]:
    """Does every scheduled wrapper declare ONE deterministic reviewed root?

    GOAL-3 #623 rows R2/R3/R5/R6 share one shape: a defect filed against a copy
    that does not run, because nothing said which copy executes. This checks a
    DIFFERENT object from `check_import_resolution`, which pins the symbols
    resolved in the SCANNER's own process — a wrapper builds its own PYTHONPATH,
    so a symbol can resolve as reviewed here and differently inside the job.

    THE RULE: a wrapper that resolves a sibling checkout with a `[ -d ... ] || VAR=`
    fallback does NOT declare a deterministic root — which copy executes is then
    decided by filesystem state. That is a problem whether or not the fallback
    currently fires; a fallback that happens to land on the right checkout today
    is still unreviewed.

    Measured 2026-07-31: six rq105 wrappers carry

        RQ_COMMON_SRC="<repos>/renquant-common-run/src"
        [ -d "$RQ_COMMON_SRC" ] || RQ_COMMON_SRC="<repos>/renquant-common/src"

    with a comment reading "pinned -run checkout preferred". `renquant-common-run/src`
    does not exist on this machine, so all six silently import the dev checkout,
    which was sitting on branch `fix/ntfy-non-ascii-title`.

    A REMEDIATED WRAPPER PASSES: one explicit root and no fallback yields no
    problem, and the tests carry a fixture proving it. That is the convergence
    property the first version of this check lacked.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    ops_dir = ops_dir or here
    repos_root = repos_root or os.path.dirname(os.path.dirname(here))
    manifest_path = manifest_path or os.path.join(here, "launchd_manifest.json")
    problems: list[str] = []
    infos: list[str] = []

    try:
        inventory = _scheduled_wrappers(manifest_path, ops_dir)
    except Exception as exc:  # noqa: BLE001
        return ([f"pythonpath: cannot read the scheduled inventory from "
                 f"{manifest_path}: {type(exc).__name__}: {exc}"], [])
    if not inventory:
        # The ONLY anti-vacuity condition left, and it is about the inventory --
        # never about whether the defect is still present.
        return (["pythonpath: the manifest lists no shell wrappers — the scan has "
                 "no subjects, which is not the same as a clean fleet"], [])

    n_checked = 0
    n_xrepo = 0
    boundaries = _wrapper_scope_boundaries(manifest_path)
    unowned = 0
    out_of_scope = 0

    for job, declared, path in inventory:
        if not path or not os.path.exists(path):
            owner = _owning_boundary(declared, boundaries)
            if owner is None:
                # INVERTED DEFAULT (codex on #675). Previously this emitted an info
                # line, so a manifested job whose wrapper vanished from this checkout
                # became silently uninspected -- and with every wrapper missing the
                # scan returned CLEAN. That is precisely the unverified-copy failure
                # this check exists to prevent, reproduced inside the check.
                unowned += 1
                problems.append(
                    f"pythonpath {job}: manifested wrapper {declared or '(none)'} is "
                    f"not resolvable in this checkout and is not covered by any "
                    f"declared scope boundary — a scheduled source that no reviewed "
                    f"scan inspects. Either restore it here or declare its owner in "
                    f"`wrapper_scope_boundaries`.")
            elif owner.get("inspect") == "read-only-here":
                # GOAL-5/#682 option 2: the boundary is an INSPECTED_BY claim, not
                # an ownership excuse. The declared path is READ (never written,
                # never git-touched — the standing umbrella rule forbids writes and
                # git, not reads) and gets the SAME fallback scan as a local
                # wrapper. An unreadable subject is a finding: silently skipping it
                # would re-open exactly the uninspected-copy gap #682 measured.
                try:
                    text = open(declared, encoding="utf-8",
                                errors="replace").read()
                except OSError as exc:
                    unowned += 1
                    problems.append(
                        f"pythonpath {job}: boundary {owner['owner']} declares "
                        f"read-only inspection here, but {declared} cannot be "
                        f"read ({exc.__class__.__name__}) — the wrapper is "
                        f"manifested and NO scan is reading it")
                    continue
                n_xrepo += 1
                _scan_wrapper_text(
                    job, text, repos_root, problems, infos,
                    origin=f" [read-only across the repo boundary; "
                           f"owner {owner['owner']}]")
            else:
                out_of_scope += 1
                infos.append(
                    f"pythonpath {job}: wrapper {declared} is owned by "
                    f"{owner['owner']} — OUT OF SCOPE for this scanner and "
                    f"NOT inspected here; {owner['owner']} must check it "
                    f"({owner.get('why', 'no reason recorded')})")
            continue
        text = open(path, encoding="utf-8", errors="replace").read()
        n_checked += 1
        _scan_wrapper_text(job, text, repos_root, problems, infos)
    # COVERAGE IS REPORTED AS A FRACTION, NOT AS A COUNT. "13 inspected" reads like
    # full coverage; "13 of 33" does not. A scan whose reach shrinks silently is the
    # same defect as a job that dies silently -- see the standing "no silent caps"
    # rule. The denominator is the manifest, which is reviewed.
    total = len(inventory)
    infos.append(
        f"pythonpath: {n_checked} of {total} manifested wrapper(s) inspected here "
        f"+ {n_xrepo} inspected read-only across a declared boundary; "
        f"{out_of_scope} out of scope; {unowned} unowned")
    if n_checked + n_xrepo == 0 and total:
        # Anti-vacuity on the OBJECT, not just the subject list: a non-empty
        # inventory with nothing actually read is a clean report about nothing.
        problems.append(
            f"pythonpath: {total} wrapper(s) manifested and NONE inspected — "
            f"a clean result here would be a statement about an empty set")
    return problems, infos


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
    p, i = report_manifested_not_loaded()
    problems += p
    infos += i
    p, i = check_import_resolution()
    problems += p
    infos += i
    p, i = check_referenced_checkout_freshness()
    problems += p
    infos += i
    p, i = check_wrapper_pythonpath_roots()
    problems += p
    infos += i
    p, i = check_sentinel_receipt()
    problems += p
    infos += i

    # Every emitted line carries its own date, FIRST characters of the line.
    #
    # This job's StandardOutPath is an APPEND-ONLY file whose name has no date
    # (logs/rq104/launchd_run_surface_drift.out). Measured 2026-07-31: 0 of its
    # 18 lines began with a date, so no line in it belonged to any run. It had
    # accumulated a CONTAINMENT alarm — "ProgramArguments CHANGED ... silent
    # containment / job swap?" for com.renquant.rq105-batch-scores-export —
    # that was RESOLVED (installed plist and reviewed manifest now agree), and
    # nothing in the file could distinguish it from one raised that morning.
    #
    # A scan whose entire job is noticing WHEN a surface changed must not write
    # findings that cannot be dated. The leading timestamp is the whole fix:
    # it lets a record be framed (a stamped line plus the unstamped lines that
    # follow it) instead of guessed at.
    stamp = _now_iso()
    for line in infos:
        _emit(stamp, f"INFO: {line}")

    if problems:
        alert(
            f"RUN-SURFACE DRIFT: {len(problems)} issue(s)",
            "\n".join(problems),
            rq_root=RQ,
        )
        # Stamp EVERY problem line, not just the first: `alert` gets the plain
        # text (its transport carries its own time), the log gets dated lines.
        for line in problems:
            _emit(stamp, line)
        return 1

    _emit(stamp, "run-surface drift scan OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
