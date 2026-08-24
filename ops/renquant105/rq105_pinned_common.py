#!/usr/bin/env python3
"""Resolve renquant-common from the PINNED runtime, or refuse.

orch#1016, second pass. The first attempt replaced a two-checkout fallback with
one *named sibling* checkout. Codex was right that this does not satisfy the
operating model it claimed to enforce:

  * a directory NAME is not a revision. The sibling `renquant-common/` is a
    mutable working tree — edited freely, on whatever branch someone last used —
    and checking that `src/` exists says nothing about what is in it;
  * `run_session_scheduler.sh` already put `$SUBREPO/renquant-common/src` (the
    pinned runtime copy) on PYTHONPATH — *after* the mutable sibling, which
    therefore SHADOWED it. Consolidating on the sibling would have entrenched
    that;
  * an env-overridable checkout name means an unreviewed process environment can
    still choose the code, while the scan reports the choice as reviewed.

So the answer is the copy the umbrella already pins, verified against the pin
before anything imports it:

    <RQ_ROOT>/.subrepo_runtime/repos/renquant-common          # the checkout
    <RQ_ROOT>/subrepos.lock.json  -> subrepos[renquant-common].commit

ONE implementation, used by both the shell wrappers (via --print-src) and the
python entrypoints (via resolve_pinned_common_src), because two implementations
of a pin check are two chances to disagree about what is pinned.

Refuses — never falls back — on: missing runtime checkout, missing/unreadable
lock, no lock entry, unreadable HEAD, or HEAD != pin. A job that cannot show it
is running reviewed code must stop, not guess.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

#: Fixed by construction. Deliberately NOT env-overridable: the whole finding is
#: that an unreviewed environment must not be able to choose which code runs.
#: RQ_ROOT stays configurable — it is the deployment root every wrapper already
#: parameterises, and the pin is verified INSIDE whichever root is given.
RUNTIME_RELPATH = os.path.join(".subrepo_runtime", "repos", "renquant-common")
LOCK_RELNAME = "subrepos.lock.json"
SUBREPO_NAME = "renquant-common"


class PinRefusal(RuntimeError):
    """Resolution failed. Never means 'try another copy'."""


def pinned_commit(rq_root: str) -> str:
    lock_path = os.path.join(rq_root, LOCK_RELNAME)
    try:
        with open(lock_path, encoding="utf-8") as fh:
            lock = json.load(fh)
    except (OSError, ValueError) as exc:
        raise PinRefusal(f"cannot read the pin from {lock_path}: {exc}") from exc
    for entry in lock.get("subrepos") or []:
        if entry.get("name") == SUBREPO_NAME:
            commit = str(entry.get("commit") or "").strip()
            if not commit:
                raise PinRefusal(
                    f"{lock_path} has a {SUBREPO_NAME} entry with no commit — a pin "
                    f"that names no revision pins nothing")
            return commit
    raise PinRefusal(f"{lock_path} has no {SUBREPO_NAME} entry")


def checkout_head(checkout: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", checkout, "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=30, check=True)
    except (OSError, subprocess.SubprocessError) as exc:
        raise PinRefusal(
            f"cannot read HEAD of {checkout}: {exc} — an unverifiable checkout is "
            f"not a verified one") from exc
    return out.stdout.strip()


def resolve_pinned_common_src(rq_root: str) -> str:
    """The pinned renquant-common src path, verified against the lock.

    Raises PinRefusal rather than returning any other copy.
    """
    checkout = os.path.join(rq_root, RUNTIME_RELPATH)
    src = os.path.join(checkout, "src")
    if not os.path.isdir(src):
        raise PinRefusal(
            f"pinned runtime checkout missing at {src}. Refusing to fall back to a "
            f"sibling working tree — which code runs is a reviewed decision "
            f"(orch#1016). Restore the runtime with the umbrella's subrepo assemble.")
    want = pinned_commit(rq_root)
    have = checkout_head(checkout)
    if have != want:
        raise PinRefusal(
            f"pinned runtime checkout is at {have}, but {LOCK_RELNAME} pins {want}. "
            f"A directory name is not a revision — refusing to import an unpinned "
            f"copy. Re-sync the runtime, or land a reviewed pin bump.")
    return src


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--rq-root", default=os.environ.get(
        "RQ_ROOT", "/Users/renhao/git/github/RenQuant"))
    ap.add_argument("--print-src", action="store_true",
                    help="print the verified src path, or exit non-zero")
    args = ap.parse_args()
    try:
        src = resolve_pinned_common_src(args.rq_root)
    except PinRefusal as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        return 1
    if args.print_src:
        print(src)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
