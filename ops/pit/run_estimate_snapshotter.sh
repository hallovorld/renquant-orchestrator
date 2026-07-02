#!/bin/zsh
# PIT N2: daily forward snapshot of FMP analyst estimates/consensus/targets
# (base-data #27 collector; #231 N2 — TIME-IRREVERSIBLE accrual; #205 design).
# Writes ONLY the dedicated data/estimate_snapshots/<date>/ path (never canonical).
# Runs from a PINNED base-data run checkout, never a working tree.
#
# Concurrency: renquant_base_data.fmp_estimate_revisions's own module docstring
# REQUIRES the scheduler wrap it in a lock so two runs (a launchd fire racing a
# manual invocation, or two launchd fires if a prior run overran) can't race the
# same date-dir publish. macOS does not ship the `flock(1)` CLI by default (only
# the `flock(2)` syscall), so this uses `mkdir` as the non-blocking atomic lock
# primitive instead (mkdir is atomic on any POSIX filesystem — a second `mkdir`
# on an existing dir fails immediately, no waiting, no external dependency).
set -u
RQ_ROOT="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
BD_RUN_ROOT="${BD_RUN_ROOT:-/Users/renhao/git/github/renquant-base-data-run}"
LOG_DIR="$RQ_ROOT/logs/pit_snapshots"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d)"
LOCK_DIR="${PIT_SNAPSHOT_LOCK_DIR:-/tmp/snapshot_fmp_estimates.lockdir}"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "$(date -u +%FT%TZ) SKIP: lock held at $LOCK_DIR — another run is already in flight, not a failure" \
    >> "$LOG_DIR/estimate_snapshot_$TS.log"
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null' EXIT

export PYTHONPATH="$BD_RUN_ROOT/src"
"$RQ_ROOT/.venv/bin/python" -m renquant_base_data.fmp_estimate_revisions \
  --env "$RQ_ROOT/.env" \
  --out "$RQ_ROOT/data/estimate_snapshots" \
  >> "$LOG_DIR/estimate_snapshot_$TS.log" 2>&1
RC=$?
if [ $RC -ne 0 ]; then
  source "$RQ_ROOT/.env" 2>/dev/null || true
  [ -n "${NTFY_TOPIC:-}" ] && curl -s -H "Title: PIT estimate snapshot FAILED rc=$RC ($TS)" \
    -d "see logs/pit_snapshots/estimate_snapshot_$TS.log — every missed day is UNRECOVERABLE" \
    "ntfy.sh/$NTFY_TOPIC" >/dev/null
fi
exit $RC
