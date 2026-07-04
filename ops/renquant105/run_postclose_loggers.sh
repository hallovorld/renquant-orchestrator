#!/bin/zsh
# rq105 N1: post-close OBSERVE-ONLY loggers for today's session (#208 Stage-1, #231 N1):
#   1) intraday_pairing_logger  — paired batch-vs-intraday arrival observations
#   2) entry_timing_shadow      — pre-registered timing-policy shadow rows
# shadow_realtime_serving is NOT scheduled here: its --batch-scores-json producer
# is an open wiring item (see README §open-items).
set -u
RQ_ROOT="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
RQ105_ORCH_ROOT="${RQ105_ORCH_ROOT:-/Users/renhao/git/github/renquant-orchestrator-run}"
LOG_DIR="$RQ_ROOT/logs/rq105"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d)"
export PYTHONPATH="$RQ105_ORCH_ROOT/src"
PY="$RQ_ROOT/.venv/bin/python"
RC_TOTAL=0
for MOD in intraday_pairing_logger entry_timing_shadow; do
  "$PY" -m "renquant_orchestrator.$MOD" --date "$TS" \
    >> "$LOG_DIR/${MOD}_$TS.log" 2>&1
  RC=$?
  if [ $RC -ne 0 ]; then
    RC_TOTAL=$RC
    # Canonical sender (campaign B6): topic/.env resolution + RENQUANT_NO_NOTIFY live there.
    . "$RQ_ROOT/scripts/notify.sh" 2>/dev/null || true
    rq_notify "rq105 $MOD FAILED rc=$RC ($TS)" \
      "see logs/rq105/${MOD}_$TS.log" || true
  fi
done
exit $RC_TOTAL
