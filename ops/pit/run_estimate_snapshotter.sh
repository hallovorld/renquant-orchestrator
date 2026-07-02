#!/bin/bash
# PIT N2: daily forward snapshot of FMP analyst estimates/consensus/targets
# (base-data #27 collector; #231 N2 — TIME-IRREVERSIBLE accrual; #205 design).
# Writes ONLY the dedicated data/estimate_snapshots/<date>/ path (never canonical).
# Runs from a PINNED base-data run checkout, never a working tree.
#
# Concurrency: renquant_base_data.fmp_estimate_revisions's own module docstring
# REQUIRES the scheduler wrap it in a lock so two runs (a launchd fire racing a
# manual invocation, or two launchd fires if a prior run overran) can't race the
# same date-dir publish. Locking is delegated to run_with_lock.py, which takes a
# kernel-released fcntl.flock on a fixed lock FILE (not a shell mkdir/trap
# lock): the OS releases the lock the instant the launcher process's file
# descriptors close, on ANY exit path including SIGKILL or a host crash — so a
# run killed mid-flight can never leave a stale lock that silently skips every
# later scheduled run (see run_with_lock.py's docstring for the full rationale;
# this replaces #233 round 2's mkdir-based lock, which could not survive that).
set -u
RQ_ROOT="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
BD_RUN_ROOT="${BD_RUN_ROOT:-/Users/renhao/git/github/renquant-base-data-run}"
LOG_DIR="$RQ_ROOT/logs/pit_snapshots"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d)"
LOCK_FILE="${PIT_SNAPSHOT_LOCK_FILE:-/tmp/snapshot_fmp_estimates.lock}"
LOG_FILE="$LOG_DIR/estimate_snapshot_$TS.log"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# The lock launcher is stdlib-only by design (see its docstring) and must run
# under a plain interpreter on PATH, not the project venv, so the locking
# mechanism itself never depends on project dependencies being importable.
LOCK_PYTHON="${PIT_LOCK_PYTHON:-python3}"

export PYTHONPATH="$BD_RUN_ROOT/src"
"$LOCK_PYTHON" "$SCRIPT_DIR/run_with_lock.py" \
  --lock-file "$LOCK_FILE" --log-file "$LOG_FILE" -- \
  "$RQ_ROOT/.venv/bin/python" -m renquant_base_data.fmp_estimate_revisions \
  --env "$RQ_ROOT/.env" \
  --out "$RQ_ROOT/data/estimate_snapshots"
RC=$?
if [ $RC -ne 0 ]; then
  source "$RQ_ROOT/.env" 2>/dev/null || true
  [ -n "${NTFY_TOPIC:-}" ] && curl -s -H "Title: PIT estimate snapshot FAILED rc=$RC ($TS)" \
    -d "see logs/pit_snapshots/estimate_snapshot_$TS.log — every missed day is UNRECOVERABLE" \
    "ntfy.sh/$NTFY_TOPIC" >/dev/null
fi
exit $RC
