#!/usr/bin/env python3
"""Kernel-released advisory-lock launcher (#233 review round 4).

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

CRITICAL: the lock's lifetime must equal the PROTECTED WORK's lifetime, not
just this launcher's. Round 3 held the lock in the launcher and ran the
wrapped command via `subprocess.run` as a separate CHILD process. SIGKILL is
uncatchable and is never forwarded to children: if something SIGKILLs the
launcher specifically (rather than its whole process group -- the launcher-
only case, as distinct from a host crash where everything dies together),
the kernel released the launcher's lock instantly, but the already-spawned
child kept running as an orphan with nothing protecting it. A new scheduled
invocation would then see the lock as free and start a SECOND run that
overlaps the still-running orphan -- exactly the same-date-publish race this
lock exists to prevent, reintroduced via a different path.

Round 4 fixes this by making the launcher and the protected work the SAME
process: after acquiring the lock, this script `os.execvp`s the wrapped
command IN PLACE of itself (not `subprocess.run`+wait) -- there is never a
window with two processes, one holding the lock and a different one doing
the work, so there is nothing to orphan. A SIGKILL to "the launcher" IS a
SIGKILL to the actual protected command once exec has run, by construction.
`os.execvp` preserves open file descriptors across the exec by default
UNLESS they are marked close-on-exec -- and PEP 446 (Python 3.4+) makes
`os.open()`'s fd close-on-exec BY DEFAULT, so the lock fd must have
`os.set_inheritable(fd, True)` called on it before the exec call, or the
kernel would close (and thus release) the lock at the exact moment of exec,
before the protected command ever started -- silently defeating the lock.

CAVEAT for future callers of this launcher: the guarantee above is precise
-- the lock's lifetime matches the wrapped command's OWN top-level process
lifetime, because exec makes them the same process. It does NOT protect
against the wrapped command itself forking additional children that never
get exec'd away (e.g. a shell running a multi-statement `-c` script, where
the shell may fork a child for one statement and simply wait on it rather
than exec'ing into it). Such a grandchild inherits the lock fd via fork()
-- which happens independently of exec/close-on-exec, since close-on-exec
only takes effect at exec time, not at fork time -- and can itself become
an orphan holding the kernel flock even after the wrapped command's own
top-level process (and the launcher's original PID) is SIGKILLed. This is
not a concern for the current caller in run_estimate_snapshotter.sh, whose
wrapped command is a single, non-forking `python -m
renquant_base_data.fmp_estimate_revisions` invocation -- but a future
caller wrapping a multi-step shell script should be aware of this residual
risk and keep the wrapped command a single non-forking process, or manage
its own locking for any further forked work.

Only stdlib is used deliberately -- this launcher must run under a plain
`python3` on PATH, not the project's venv interpreter, so that "can the lock
mechanism itself run" never depends on project dependencies being importable.

Usage:
    run_with_lock.py --lock-file PATH --log-file PATH -- <command...>

If the lock is already held, appends a SKIP line to --log-file and exits 0
(not a failure -- another run is already in flight). Otherwise execs into
<command...> (this process BECOMES it), with its stdout+stderr redirected to
--log-file; the wrapped command's own exit code is therefore this process's
exit code, exactly as if it had been run directly.
"""
from __future__ import annotations

import argparse
import fcntl
import os
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
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        with open(args.log_file, "a") as log:
            log.write(
                f"{_now_iso()} SKIP: lock held at {args.lock_file} — "
                "another run is already in flight, not a failure\n"
            )
        os.close(lock_fd)
        return 0

    # The lock is held. From here on the protected command's lifetime MUST
    # equal this process's lifetime (see module docstring) -- so redirect
    # stdout/stderr to the log file, keep the lock fd alive across exec, and
    # replace this process image with the wrapped command. There is no
    # "after exec" on the success path: this function does not return.
    log_fd = os.open(args.log_file, os.O_CREAT | os.O_WRONLY | os.O_APPEND, 0o644)
    os.dup2(log_fd, 1)
    os.dup2(log_fd, 2)
    if log_fd not in (1, 2):
        os.close(log_fd)
    # Clear close-on-exec (PEP 446 sets it by default on os.open() fds) so
    # the lock survives into the execed command -- otherwise the kernel
    # closes it (releasing the lock) at the moment of exec, before the
    # protected command has even started.
    os.set_inheritable(lock_fd, True)
    try:
        os.execvp(command[0], command)
    except OSError as exc:
        # exec itself failed (e.g. command not found) -- we're still the
        # launcher process here, so report failure and release explicitly.
        sys.stderr.write(f"{_now_iso()} FAILED to exec {command!r}: {exc}\n")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(lock_fd)
        return 127


if __name__ == "__main__":
    sys.exit(main())
