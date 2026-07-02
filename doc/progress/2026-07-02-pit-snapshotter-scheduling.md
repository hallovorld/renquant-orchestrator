# PIT estimate-snapshot scheduling (N2 landing package) — ops PR

STATUS:   ops scaffolding for review (repo files only — nothing installed/executed by this PR;
          installation is the landing step per the direction-loop charter).
REVISION: r1.
WHAT:     `ops/pit/` — daily wrapper for the merged base-data #27 forward snapshotter
          (`fmp_estimate_revisions`, writes only the dedicated `data/estimate_snapshots/<date>/`
          path), a liveness check (ntfy on weekday miss — a missed day is UNRECOVERABLE under
          the PIT no-backfill invariant), two launchd plists (14:30 / 15:00 PT weekdays), and a
          README (install / dry-run smoke / N2 AC). Pinned run checkouts only.
WHY/DIR:  #231 N2 is the time-irreversible NOW item: the revision signal (the G106 stack's
          cross-family leg, POC-D) is un-buildable until an as-of history accrues forward;
          base-data #27 built the collector but nothing schedules it — the same
          built-but-dark pathology as N1. Scheduling ownership is orchestrator's per the #27
          docstring and #210's ownership split.
EVIDENCE: base-data #27 MERGED (`fmp_estimate_revisions.py`, 693 lines + tests; PIT hard
          invariant documented in its docstring); FMP `stable` analyst-estimates endpoint
          returns data on the existing key (probed 2026-07-02 — the v3 endpoint is
          legacy-deprecated); `--min-coverage` will surface plan-lock gaps, with the authorized
          N3 Starter upgrade as the remedy.
NEXT:     Round 3 (below) replaced the mkdir/trap lock with a kernel-released fcntl.flock
          launcher after codex flagged the trap as not SIGKILL/crash-safe; awaiting re-review.
          Once approved: lander runs the README install; N2 AC clock starts at first successful
          dated snapshot; N3 coverage verdict falls out of the first real run's
          `--min-coverage` report.

## Round 2 (Codex CHANGES_REQUESTED — repeated #232's defects + missed the collector's own contract)

**Finding.** This package repeated several defects #232 already found on the sibling N1 package,
plus a gap specific to this collector: (1) `renquant_base_data.fmp_estimate_revisions`'s own
docstring REQUIRES the scheduler wrap it in a lock so two overlapping runs (a launchd fire racing
a manual invocation, or two launchd fires if a prior run overran) can't race the same date-dir
publish, but `run_estimate_snapshotter.sh` invoked it directly with no guard; (2) the README never
created `logs/pit_snapshots` before `launchctl load`ing plists whose `StandardOutPath`/
`StandardErrorPath` point into it — launchd does not create a missing parent; (3)
`pit_liveness_check.py` accepted "any one parquet + any filename containing 'manifest'" instead of
validating the collector's actual publication contract (all four endpoint manifests present,
non-zero-byte, `status=="ok"`, `as_of`==today); (4) no tests existed for the plists, wrapper, date
semantics, or liveness behavior, and the date was hard-wired to `date.today()` instead of
injectable for deterministic testing.

**Fix.**
- `ops/pit/run_estimate_snapshotter.sh`: non-blocking `mkdir`-based atomic lock (macOS ships no
  `flock(1)` CLI, only the `flock(2)` syscall; `mkdir` is atomic on any POSIX filesystem — a second
  `mkdir` on an existing dir fails immediately). A losing run logs a `SKIP` line and exits 0 (not a
  failure — "another run is already in flight").
- `ops/pit/README.md`: install step now creates `logs/pit_snapshots` via `mkdir -p` BEFORE any
  `launchctl` call; updated to current-macOS verbs (`bootstrap`/`bootout`/`kickstart` against
  `gui/$(id -u)`, replacing deprecated `load`/`unload`).
- `ops/pit/pit_liveness_check.py`: rewritten around `ENDPOINTS` (mirrors
  `fmp_estimate_revisions.ENDPOINTS`) and `check_endpoint_manifest()` — validates, per endpoint,
  that `{endpoint}.manifest.json` exists, is non-zero-byte, parses as JSON, has `status=="ok"`,
  `as_of` equal to the date being checked, and that the parquet file its own manifest names
  actually exists and is non-zero-byte. Session-day gating now uses the real NYSE calendar
  (`renquant_orchestrator.intraday_quote_logger.default_session_calendar` — the SAME
  `pandas_market_calendars`-backed primitive #232's rq105 liveness check and
  `renquant_execution.preopen_cancel_gate` already use), fail-closed (treats the day as a session
  day, never silently skips, if the calendar check itself errors). New `--as-of` flag injects the
  effective date for deterministic testing; production/launchd invocation always omits it and uses
  `date.today()`.
- New `tests/test_pit_snapshotter_scheduling.py` (18 tests): plist schedule assertions
  (`plistlib`-parsed, Mon-Fri only, exact documented PT Hour/Minute); NYSE holiday-gating
  (including the fail-closed-on-calendar-error path); the full endpoint-manifest contract
  (missing/zero-byte/corrupt/wrong-status/wrong-as_of/missing-referenced-parquet, each as its own
  failure mode, plus the all-four-present success path); `--as-of` overriding `date.today()`.

**Evidence:** `uv venv --python 3.10` + `uv pip install pytest pandas_market_calendars pandas`
(this repo's checked-out system `python3` is 3.9, which cannot import
`renquant_orchestrator.intraday_quote_logger`'s dependency chain — PEP 604 `str | None` syntax
requires 3.10+; a pre-existing environment fact, not introduced by this round — CI runs on a
correctly-versioned interpreter) → `python -m pytest tests/test_pit_snapshotter_scheduling.py -q`
→ 18 passed. `py_compile` clean on both Python files; `bash -n` clean on the wrapper script.

**Scope:** unchanged — ops scaffolding only, nothing installed/executed by this PR; the N1a/N1b
activation-gating pattern #232 landed (mechanical guard on merged prerequisite SHAs before live
bootstrap) does not apply here in the same way since N2 has no #224/#227-equivalent blocking
prerequisite named in the roadmap — flagging this as worth a second look if `#229`'s dependency
DAG is later extended to cover N2 explicitly.

**Round 2 (CI fix, 2026-07-02):** the GitHub Actions Ubuntu runner has no `/bin/zsh` (macOS-only
in practice), so the 3 concurrency tests that invoked the wrapper via a hardcoded `/bin/zsh` path
failed CI with `FileNotFoundError: [Errno 2] No such file or directory: '/bin/zsh'` even though
local runs (on macOS) passed. The wrapper script's own content has no zsh-specific syntax — it's
portable POSIX/bash (`set -u`, `mkdir`/`trap`/`source`, standard `[ ]` tests) — so the fix is a
straight portability correction, not a behavior change: shebang `#!/bin/zsh` → `#!/bin/bash`
(available on both macOS and the Linux CI runner), the 3 test invocations updated to match, and
the launchd plist's `ProgramArguments` updated for consistency (macOS ships both shells; bash is
now the one actually declared everywhere). 18/18 tests still pass locally after the fix.

**Round 3 (Codex CHANGES_REQUESTED — mkdir lock is not crash-safe):**

**Finding.** The round-2 `mkdir`-based lock is released only by a shell `trap ... EXIT`, which
does not fire on SIGKILL, a host crash, or power loss (uncatchable/unrunnable in all three
cases). Any of those happening while the lock is held leaves `$LOCK_DIR` on disk forever; every
subsequent scheduled run then sees the lock "held," logs a benign `SKIP` line, and exits 0 —
silently and permanently halting this non-backfillable dataset with no alert, indistinguishable
from a healthy day. Separately, the claimed "concurrency test" was sequential precreate-directory
/ run / remove-directory, never two actually-overlapping processes — it could not have caught this
class of bug even if it had existed.

**Fix — kernel-released lock, not shell-released.**
- New `ops/pit/run_with_lock.py`: a small stdlib-only Python launcher (`fcntl.flock(fd,
  LOCK_EX|LOCK_NB)` on a fixed lock file). `flock` is bound to the OPEN FILE DESCRIPTOR, not to
  shell control flow — the kernel releases it unconditionally the instant the process's file
  descriptors close, on normal exit, an uncaught exception, or SIGKILL. There is no stale-lock
  state to reclaim, because the lock literally cannot outlive the process holding it. Deliberately
  depends on nothing outside the stdlib, so it runs under a plain `python3` on PATH — the locking
  mechanism itself never needs the project venv/dependencies to be importable.
- `ops/pit/run_estimate_snapshotter.sh`: delegates locking to the new launcher instead of doing
  `mkdir`/`trap` itself (`PIT_SNAPSHOT_LOCK_FILE` replaces `PIT_SNAPSHOT_LOCK_DIR`; new
  `PIT_LOCK_PYTHON` override, default `python3`). Log-dir creation, the date-stamped log file, the
  ntfy-on-failure path, and the exit-code propagation are all unchanged — only the locking
  primitive itself moved. No plist change was needed: `ProgramArguments` still points at the
  `.sh` wrapper, which now shells out to the launcher internally.
- `tests/test_pit_snapshotter_scheduling.py`: replaced the fake "concurrency" test with (a) a
  genuine overlap test — two wrapper invocations started via `subprocess.Popen` with no wait
  between them, against a stub collector that sleeps 1s (wide enough race window to be
  non-flaky); asserts exactly one of the two reaches the collector and both still exit 0; (b) a
  genuine crash-recovery test — a launcher process is started holding the lock (wrapping `sleep
  30`), confirmed via a polling helper to actually hold the flock, then killed with real SIGKILL
  (`Popen.kill()`); a fresh invocation started immediately after must acquire the lock right away.
  Also added a direct exit-code-propagation test for the launcher. 20/20 tests pass.

**Manual verification (beyond the automated test):** hand-ran the exact SIGKILL scenario outside
pytest — spawned the launcher holding the lock, confirmed it alive, sent SIGKILL, reaped it (exit
code -9), then immediately ran a second invocation: it acquired the lock and completed in 0.025s
with no `SKIP` in its log. This is the core property the whole fix exists to guarantee, so it was
checked by hand once rather than trusting the automated test alone.

**Scope:** locking mechanism only; the four-endpoint publication-validation logic
(`pit_liveness_check.py`) is unchanged from round 2, as codex's review noted could remain as-is.
