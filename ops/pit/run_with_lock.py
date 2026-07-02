#!/usr/bin/env python3
"""Kernel-released advisory-lock launcher (#233 review round 3).

Wraps an arbitrary command with a non-blocking `fcntl.flock` exclusive lock
on a fixed lock file. This replaces an earlier `mkdir`-based lock that was
released only by a shell `EXIT` trap: a trap does not fire on SIGKILL, a host
crash, or a power loss, so a run interrupted mid-flight left the lock
directory on disk forever, silently skipping every later scheduled run with
no alert.

`flock` is tied to the open file descriptor, not to shell control flow. The
kernel releases it the instant this process's file descriptors are closed --
on normal exit, on an uncaught exception, AND on SIGKILL/host-crash recovery
(the OS reclaims all of a dead process's file descriptors unconditionally).
There is no stale-lock state to detect or reclaim: the lock cannot outlive
the process that holds it.

Only stdlib is used deliberately -- this launcher must run under a plain
`python3` on PATH, not the project's venv interpreter, so that "can the lock
mechanism itself run" never depends on project dependencies being importable.

Usage:
    run_with_lock.py --lock-file PATH --log-file PATH -- <command...>

If the lock is already held, appends a SKIP line to --log-file and exits 0
(not a failure -- another run is already in flight). Otherwise runs
<command...>, appending its stdout+stderr to --log-file, and exits with the
command's own return code.
"""
from __future__ import annotations

import argparse
import fcntl
import os
import subprocess
import sys
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock-file", required=True)
    parser.add_argument("--log-file", required=True)
    parser.add_argument("rest", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)

    if not args.rest or args.rest[0] != "--":
        parser.error("the wrapped command must be passed after a literal '--' separator")
    command = args.rest[1:]
    if not command:
        parser.error("no command given after '--'")

    lock_parent = os.path.dirname(args.lock_file)
    if lock_parent:
        os.makedirs(lock_parent, exist_ok=True)
    log_parent = os.path.dirname(args.log_file)
    if log_parent:
        os.makedirs(log_parent, exist_ok=True)

    # O_CREAT|O_RDWR: create-if-missing, keep the fd open for the lifetime of
    # this process. The lock is bound to THIS fd -- closing it (for any
    # reason, including this process being killed) releases it in the kernel.
    lock_fd = os.open(args.lock_file, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            with open(args.log_file, "a") as log:
                log.write(
                    f"{_now_iso()} SKIP: lock held at {args.lock_file} — "
                    "another run is already in flight, not a failure\n"
                )
            return 0

        with open(args.log_file, "a") as log:
            proc = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        return proc.returncode
    finally:
        # Best-effort explicit release on the clean-exit path. Redundant with
        # the kernel's automatic release-on-close (including on SIGKILL) --
        # this is not what makes the lock crash-safe, it's just tidy.
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(lock_fd)


if __name__ == "__main__":
    sys.exit(main())
