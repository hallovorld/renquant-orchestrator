#!/bin/zsh
# rq105 N1: session-long intraday quote logger (OBSERVE-ONLY; #208 Stage-1, #231 N1).
# Runs from a PINNED orchestrator checkout (RQ105_ORCH_ROOT), never the working tree.
# The logger self-loops on --cadence with an internal NYSE session gate; launchd
# starts it pre-open each weekday and it exits after the close.
set -u
RQ_ROOT="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
RQ105_ORCH_ROOT="${RQ105_ORCH_ROOT:-/Users/renhao/git/github/renquant-orchestrator-run}"
LOG_DIR="$RQ_ROOT/logs/rq105"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d)"
# Campaign B5: the orchestrator session-calendar primitive now lives in
# renquant_common.market_calendar — put a sibling renquant-common checkout on
# PYTHONPATH (pinned -run checkout preferred; the venv install alone may
# predate market_calendar).
RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common-run/src"
[ -d "$RQ_COMMON_SRC" ] || RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common/src"
export PYTHONPATH="$RQ105_ORCH_ROOT/src:$RQ_COMMON_SRC"
"$RQ_ROOT/.venv/bin/python" -m renquant_orchestrator.intraday_quote_logger \
  --env-file "$RQ_ROOT/.env" \
  --data-root "$RQ_ROOT" \
  --log-level INFO \
  >> "$LOG_DIR/quote_logger_$TS.log" 2>&1
RC=$?
if [ $RC -ne 0 ]; then
  source "$RQ_ROOT/.env" 2>/dev/null || true
  [ -n "${NTFY_TOPIC:-}" ] && curl -s -H "Title: rq105 quote logger FAILED rc=$RC" \
    -d "see logs/rq105/quote_logger_$TS.log" "ntfy.sh/$NTFY_TOPIC" >/dev/null
fi
exit $RC
