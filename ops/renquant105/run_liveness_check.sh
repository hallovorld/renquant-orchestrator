#!/bin/zsh
# rq105: mid-session liveness check (14:00 ET weekdays).
# Runs from a PINNED orchestrator checkout (RQ105_ORCH_ROOT), never the working
# tree. Checks that all rq105 components are producing fresh data and alerts
# via ntfy if any are stale.
#
# The plist previously ran the python script directly without a shell wrapper,
# which meant no PYTHONPATH — imports of renquant_common.notify and
# renquant_orchestrator.intraday_* would fail on first use.
set -u
RQ_ROOT="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
RQ105_ORCH_ROOT="${RQ105_ORCH_ROOT:-/Users/renhao/git/github/renquant-orchestrator-run}"
LOG_DIR="$RQ_ROOT/logs/rq105"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d)"
RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common-run/src"
[ -d "$RQ_COMMON_SRC" ] || RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common/src"
export PYTHONPATH="$RQ105_ORCH_ROOT/src:$RQ_COMMON_SRC"
"$RQ_ROOT/.venv/bin/python" "$RQ105_ORCH_ROOT/ops/renquant105/rq105_liveness_check.py" \
  >> "$LOG_DIR/liveness_$TS.log" 2>&1
RC=$?
if [ $RC -ne 0 ]; then
  . "$RQ_ROOT/scripts/notify.sh" 2>/dev/null || true
  rq_notify "rq105 liveness check FAILED rc=$RC ($TS)" \
    "see logs/rq105/liveness_$TS.log" || true
fi
exit $RC
