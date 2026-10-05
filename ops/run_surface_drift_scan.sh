#!/usr/bin/env bash
# run_surface_drift_scan.sh — launchd wrapper for ops/run_surface_drift_check.py
# (GOAL-5 AC2), daily 07:00 local INCLUDING weekends (the plist has no Weekday
# key: run-surface drift is not session-bound).
#
# WHY A WRAPPER (2026-08-30). The plist used to run the checker directly, which
# left nothing to catch up a slot dropped across a boot: the host booted
# 2026-08-28 10:38 and the 07:00 scan simply did not happen that day — zero
# 2026-08-28 lines in launchd_run_surface_drift.out, while 08-27 and 08-29
# have ~40 each. The same boot swallowed the rq105 06:15/06:25 slots (#1087)
# and the 06:05 dawn preflight. The plist now carries RunAtLoad=true and this
# wrapper applies the SHARED catch-up guard (ops/catchup_guard.sh) to every
# invocation: run iff 07:00 <= local time < 24:00 on ANY calendar day (a
# literal cutoff — the scan's calendar-day behaviour is unchanged; only the
# missed-slot-after-boot catch-up is new) AND today's dated scan log is
# missing; otherwise one stamped line in catchup_guard_run-surface-drift_
# <date>.log and exit 0.
#
# OUTPUT SURFACES. The scan's stdout/stderr still reach launchd's append-only
# StandardOutPath exactly as before (every line is self-stamped by the
# checker), AND are tee'd into the dated file run_surface_drift_<date>.log —
# the guard's idempotency witness. A dated file that exists but is empty is
# the evidence of a firing that could not even start python.
#
# ONE deterministic root, no fallback (check_wrapper_pythonpath_roots): the
# environment is the plist's, restated here so a manual invocation resolves
# exactly what launchd resolves.
set -uo pipefail

RQ_ROOT="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
RQ_ORCH_ROOT="${RQ_ORCH_ROOT:-/Users/renhao/git/github/renquant-orchestrator-run}"
export RQ_ROOT RQ_ORCH_ROOT
export PYTHONPATH="$RQ_ORCH_ROOT/src:$RQ_ORCH_ROOT/ops"
OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$RQ_ROOT/logs/rq104"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d)"
SCAN_LOG="$LOG_DIR/run_surface_drift_$TS.log"

. "$OPS_DIR/catchup_guard.sh"
launchd_catchup_guard run-surface-drift "$TS" "$(date +%H%M)" 0700 2400 \
  "$LOG_DIR/catchup_guard_run-surface-drift_$TS.log" \
  "$SCAN_LOG"
GUARD_RC=$?
case $GUARD_RC in
  0) ;;
  1) exit 0 ;;
  *) echo "FATAL: catch-up guard error rc=$GUARD_RC"; exit 1 ;;
esac

"$RQ_ROOT/.venv/bin/python" "$OPS_DIR/run_surface_drift_check.py" 2>&1 | tee -a "$SCAN_LOG"
RC=${PIPESTATUS[0]}
printf '%s run-surface-drift rc=%s\n' "$(date +%Y-%m-%dT%H:%M:%S)" "$RC" >> "$SCAN_LOG"
exit "$RC"
