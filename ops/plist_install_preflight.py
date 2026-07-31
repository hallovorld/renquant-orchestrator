#!/usr/bin/env python3
"""Refuse to bootstrap a plist whose target does not exist in the RUN checkout.

A committed plist is a *declaration*. Installing it is a separate act, and the two
can disagree: `deploy/com.renquant.ops-audit.plist` points at
`renquant-orchestrator-run/ops/run_ops_audit.sh`, which was merged to `main` by
orch#650 and — measured 2026-07-31 — is **still absent from the run checkout**,
because that checkout syncs on its own schedule. `launchctl bootstrap` accepts such
a plist happily; the job then fails on every firing.

That is the merged-is-not-deployed shape arriving through launchd instead of through
a pin, and it is invisible to every check that reads the repo rather than the machine:
the manifest is right, the plist is right, the wrapper is on `main`, and the job is
dead.

So the precondition is checked against the **run checkout launchd will actually
execute**, per job, before anything is installed:

  * the target script exists;
  * it is executable WHEN it is argv[0]. Most jobs here run `/bin/bash <script>`, so
    the interpreter is executed and the script is a mere argument; requiring the bit
    unconditionally refused three jobs that are installed and running today;
  * the plist's `ProgramArguments` agree with the reviewed manifest entry, so the
    thing being preflighted is the thing that was reviewed.

Read-only. Exits 0 when every requested job is installable, 2 when any is not, and
NEVER installs anything itself — installation is an operator action.
"""
from __future__ import annotations

import argparse
import json
import os
import plistlib
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MANIFEST = REPO / "ops" / "launchd_manifest.json"
DEPLOY = REPO / "deploy"

#: The checkout launchd executes from. NOT this repo: a wrapper present here and
#: absent there is exactly the failure this module exists to catch.
DEFAULT_RUN_ROOT = Path("/Users/renhao/git/github/renquant-orchestrator-run")
RUN_ROOT = Path(os.environ.get("RQ_RUN_ROOT", str(DEFAULT_RUN_ROOT)))

EXIT_OK, EXIT_NOT_INSTALLABLE = 0, 2

#: Prefix marking "not on the reviewed surface" as distinct from "not installable".
#: The installer may proceed past this; it may never proceed past a missing target.
UNMANIFESTED = "UNMANIFESTED"

#: "Could not check here", distinct from "checked and it will fail". Non-blocking,
#: because a machine with no run checkout is not a machine that installs anything.
UNVERIFIABLE = "UNVERIFIABLE"


def target_of(args: list[str]) -> str | None:
    """The script a plist would run: the last argument that looks like a path."""
    for a in reversed(args or []):
        if "/" in str(a):
            return str(a)
    return None


def _needs_exec_bit(args: list[str] | None) -> bool:
    """Does the target have to carry the exec bit?

    Only when it is argv[0]. Most jobs here run `/bin/bash <script>` or
    `<python> <script>`, where the INTERPRETER is executed and the script is just an
    argument -- a mode 0644 file works fine. My first version required the bit
    unconditionally and refused three jobs that are installed and running right now
    (degradation-sentinel, shadow-scorer-sentinel, run-surface-drift). A preflight
    that refuses working jobs gets switched off, and then it protects nothing.
    """
    args = args or []
    if len(args) < 2:
        return True                      # the script IS argv[0]
    head = os.path.basename(str(args[0]))
    return not (head in {"bash", "sh", "zsh"} or head.startswith("python"))


def check_job(label: str, *, run_root: Path | None = None,
              manifest: dict | None = None) -> list[str]:
    """Reasons `label` cannot be installed right now. Empty list == installable."""
    run_root = run_root or RUN_ROOT
    jobs = manifest if manifest is not None else json.loads(
        MANIFEST.read_text(encoding="utf-8"))["jobs"]
    problems: list[str] = []

    plist = DEPLOY / f"{label}.plist"
    if not plist.exists():
        return [f"{label}: no committed plist at {plist}"]
    if label not in jobs:
        # NOT an installability problem, and conflating the two broke the supported
        # installer. `com.renquant.stops-liveness` has a committed plist and an
        # installer but no manifest entry, so gating installation on manifest
        # membership made that job permanently un-installable.
        #
        # These are different questions: "can this be installed without failing on
        # every firing" (this module) versus "is this job on the reviewed surface"
        # (the drift scan's unmanifested check, which already reports it). Answering
        # the second here does not make the first safer; it just refuses a job for a
        # reason the caller cannot act on at install time.
        #
        # Reported, never silent -- with a marker so a caller can tell an
        # unreviewed-surface finding from an unrunnable target.
        # NOT an early return. Returning here skipped the target check entirely, so
        # an unmanifested job with a MISSING target reported installable -- exactly
        # the bootstrap-into-guaranteed-failure this module exists to stop, reopened
        # by the fix for a different problem. Caught by the anti-vacuity test below
        # it. The note is collected and the target is still checked; only the
        # manifest-agreement comparison is skipped, because there is nothing to
        # compare against.
        problems.append(
            f"{UNMANIFESTED}: {label} has a committed plist but no entry in the "
            f"reviewed manifest — the drift scan owns that finding; this "
            f"preflight cannot judge whether its target is the reviewed one")

    try:
        pl = plistlib.loads(plist.read_bytes())
    except Exception as exc:  # noqa: BLE001
        return [f"{label}: plist unreadable ({type(exc).__name__}: {exc})"]

    if label in jobs and pl.get("ProgramArguments") != jobs[label].get("program_args"):
        problems.append(
            f"{label}: plist ProgramArguments disagree with the reviewed manifest — "
            f"preflighting an unreviewed command would certify the wrong thing")

    tgt = target_of(pl.get("ProgramArguments"))
    if tgt is None:
        problems.append(f"{label}: plist names no script to run")
        return problems

    # The plist carries an ABSOLUTE path. Resolve it against `run_root` by EXISTENCE
    # rather than by comparing roots:
    #
    #   * my first version re-rooted unconditionally and mangled an already-correct
    #     absolute path into `<root>/<basename>`, reporting a present file as missing;
    #   * my second version re-rooted only when `run_root != RUN_ROOT`, which cannot
    #     be exercised through `main()` at all — that path passes no run_root, so the
    #     two are equal by construction and the branch is dead. A resolution rule that
    #     the production entry point can never reach is not a rule.
    #
    # Existence-based: take the path as written if it is there, else try it under the
    # requested root. Both misses are then a genuinely missing target.
    p = Path(tgt)
    if not p.exists():
        for cand in (run_root / Path(tgt).name,
                     run_root / str(Path(tgt)).lstrip("/")):
            if cand.exists():
                p = cand
                break
        else:
            try:
                rel = Path(tgt).relative_to(DEFAULT_RUN_ROOT)
                if (run_root / rel).exists():
                    p = run_root / rel
            except ValueError:
                pass

    if not run_root.exists():
        # NOT a refusal. If the run checkout is absent ENTIRELY, this is not the
        # deploy machine — a CI runner, a fresh clone — and every job would be
        # reported un-installable, which turned four existing installer tests red.
        # "There is no run checkout here" and "the target is missing from the run
        # checkout" are different facts, and only the second predicts a job that
        # fails on every firing.
        problems.append(
            f"{UNVERIFIABLE}: no run checkout at {run_root} — installability of "
            f"{label} was NOT checked. On the deploy machine this is a refusal; "
            f"here there is nothing to check against")
    elif not p.exists():
        problems.append(
            f"{label}: target {p} does NOT exist in the run checkout. It may be "
            f"merged to main and simply not synced there — installing now would "
            f"bootstrap a job that fails on every firing")
    elif _needs_exec_bit(pl.get("ProgramArguments")) and not os.access(p, os.X_OK):
        problems.append(
            f"{label}: target {p} is argv[0] but is not executable — it fails at "
            f"runtime exactly as an absent one does")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("labels", nargs="*",
                    help="jobs to preflight; default = every committed plist")
    a = ap.parse_args(argv)

    labels = a.labels or sorted(p.stem for p in DEPLOY.glob("*.plist"))
    if not labels:
        print("FATAL: no plists to preflight — nothing was checked", file=sys.stderr)
        return EXIT_NOT_INSTALLABLE

    bad: list[str] = []
    notes: list[str] = []
    for label in labels:
        probs = check_job(label)
        # UNMANIFESTED is surfaced but does not block: it is a reviewed-surface
        # finding the drift scan owns, not a statement that the target is unrunnable.
        non_blocking = (UNMANIFESTED, UNVERIFIABLE)
        blocking = [x for x in probs if not x.startswith(non_blocking)]
        notes.extend(x for x in probs if x.startswith(non_blocking))
        if blocking:
            bad.extend(blocking)
        else:
            print(f"  INSTALLABLE  {label}")
    for n in notes:
        print(f"  NOTE         {n}")
    for b in bad:
        print(f"  REFUSED      {b}")
    if bad:
        print(f"\nplist-install-preflight: {len(bad)} job(s) NOT installable — "
              f"sync the run checkout (or fix the target) before bootstrapping")
        return EXIT_NOT_INSTALLABLE
    print(f"\nplist-install-preflight: {len(labels)} job(s) installable")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
