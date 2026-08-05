#!/usr/bin/env bash
# fleet_lane_sentinel_daily.sh — the SCHEDULED surface for the fleet lane
# sentinel (GOAL-1, orch#801 round 2).
#
# WHY THIS EXISTS. The checker alone is a diagnostic; a diagnostic nobody runs
# is the deployed-but-dark gap the sentinel was written to close (codex on
# orch#801, correctly). This wrapper is the operational half: it fires after
# the daily fleet lanes have written their records, classifies every lane for
# THAT session date, and pages when a lane is FAIL_CLOSED or MISSING.
#
# EVIDENCE CONTRACT (the momentum_train_weekly.sh pattern, orch#754 trail):
# exec-redirect FIRST so a pre-exec death cannot vanish; every exit path writes
# a terminal marker, so log EXISTENCE proves the wrapper fired and log CONTENT
# carries the verdict.
#
# SESSION DATE: passed explicitly to the checker (never left to the checker's
# own default) so a wrapper firing after midnight UTC still classifies the
# session it was scheduled for.
set -uo pipefail

RQ_ROOT="${RENQUANT_REPO_ROOT:-/Users/renhao/git/github/RenQuant}"
ORCH_RUN="${RQ_ORCH_RUN_DIR:-/Users/renhao/git/github/renquant-orchestrator-run}"
PYTHON="$RQ_ROOT/.venv/bin/python"
SENTINEL="$ORCH_RUN/ops/renquant104/fleet_lane_sentinel.py"
SESSION_DATE="${1:-$(date +%Y-%m-%d)}"
LOG_DIR="$RQ_ROOT/logs/rq104"
LOG="$LOG_DIR/fleet_lane_sentinel_${SESSION_DATE}.log"

mkdir -p "$LOG_DIR" || { echo "FATAL: cannot create $LOG_DIR" >&2; exit 2; }
exec >>"$LOG" 2>&1

echo "=== fleet_lane_sentinel session=$SESSION_DATE started at $(date) ==="

notify() {
    local title="$1" body="$2"
    if [ -n "${RQ_FLEET_SENTINEL_NOTIFY_LOG:-}" ]; then
        printf '%s: %s\n' "$title" "$body" >> "$RQ_FLEET_SENTINEL_NOTIFY_LOG"
    fi
    curl -s -H "Title: $title" -d "$body" \
        "https://ntfy.sh/${NTFY_TOPIC:-renquant}" >/dev/null 2>&1 || true
}

refuse() {
    echo "REFUSED: $*"
    notify "RenQuant 104 FLEET-SENTINEL-REFUSED" "$* (session $SESSION_DATE)"
    echo "=== fleet_lane_sentinel REFUSED at $(date) ==="
    exit 2
}

[ -x "$PYTHON" ] || refuse "interpreter not executable: $PYTHON"
[ -f "$SENTINEL" ] || refuse "sentinel not in the run checkout: $SENTINEL"

"$PYTHON" "$SENTINEL" --date "$SESSION_DATE"
RC=$?

if [ "$RC" -eq 0 ]; then
    echo "=== fleet_lane_sentinel OK (all lanes accounted for) at $(date) ==="
    exit 0
fi
if [ "$RC" -eq 1 ]; then
    # Actionable lane state(s). The alarm carries the lane lines themselves so
    # the operator does not need the log to know WHICH lane and WHY.
    ACTIONABLE="$(grep -E '^\[(FAIL_CLOSED|MISSING)\]' "$LOG" | tail -5 | tr '\n' ' ')"
    notify "RenQuant 104 FLEET-LANE-ALARM" \
        "session $SESSION_DATE: ${ACTIONABLE:-actionable lane state (see $LOG)}"
    echo "=== fleet_lane_sentinel ALARM (rc=$RC) at $(date) ==="
    exit 1
fi
notify "RenQuant 104 FLEET-SENTINEL-ERROR" \
    "checker exited rc=$RC on session $SESSION_DATE — see $LOG"
echo "=== fleet_lane_sentinel ERROR rc=$RC at $(date) ==="
exit "$RC"
