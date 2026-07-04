#!/bin/zsh
# rq105 Stage-1 SHADOW-ONLY intraday session scheduler (#208 §8 row 3).
# Runs from a PINNED orchestrator checkout (RQ105_ORCH_ROOT), never the working
# tree. The scheduler self-loops on the config tick cadence with an internal
# NYSE session gate (half-day aware); launchd starts it pre-open each weekday
# and it exits after the close (or immediately, while the feature is
# default-OFF: config disabled / env flag unset / kill-switch file present).
#
# TRIPLE GATE — nothing runs until ALL THREE hold:
#   1. pinned strategy config: intraday_decisioning.enabled = true
#   2. env flag RENQUANT_INTRADAY_DECISIONING=1 (set below ONLY by the
#      operator editing this file at activation; default: NOT exported)
#   3. kill-switch file absent (data/rq105/intraday_decisioning.KILL —
#      touch it to halt mid-session before the next tick)
# Shadow mode is runtime-asserted in the module: it NEVER submits anything.
set -u
RQ_ROOT="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
RQ105_ORCH_ROOT="${RQ105_ORCH_ROOT:-/Users/renhao/git/github/renquant-orchestrator-run}"
LOG_DIR="$RQ_ROOT/logs/rq105"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d)"
export PYTHONPATH="$RQ105_ORCH_ROOT/src"
# NOTE: RENQUANT_INTRADAY_DECISIONING is deliberately NOT exported here.
# Activation (a recorded landing step) uncomments the next line:
# export RENQUANT_INTRADAY_DECISIONING=1
"$RQ_ROOT/.venv/bin/python" -m renquant_orchestrator.intraday_session_scheduler \
  --env-file "$RQ_ROOT/.env" \
  --data-root "$RQ_ROOT" \
  --data-manifest "$RQ_ROOT/data/rq105/data_manifest.json" \
  --artifact-manifest "$RQ_ROOT/data/rq105/artifact_manifest.json" \
  --log-level INFO \
  >> "$LOG_DIR/session_scheduler_$TS.log" 2>&1
RC=$?
if [ $RC -ne 0 ]; then
  # Canonical sender (campaign B6): topic/.env resolution + RENQUANT_NO_NOTIFY live there.
  . "$RQ_ROOT/scripts/notify.sh" 2>/dev/null || true
  rq_notify "rq105 session scheduler FAILED rc=$RC" \
    "see logs/rq105/session_scheduler_$TS.log" || true
fi
exit $RC
