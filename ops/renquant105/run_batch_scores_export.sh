#!/bin/zsh
# rq105: pre-market batch score export (#208 §6, N1 open item #1).
# Runs from a PINNED orchestrator checkout (RQ105_ORCH_ROOT), never the working
# tree. Reads the latest daily FULL run from the prior session and writes frozen
# batch scores for today's shadow serving.
#
# The plist previously ran the python script directly without a shell wrapper,
# which meant no PYTHONPATH, no .env, and no subrepo paths — any import outside
# the venv's installed packages would fail silently.
set -u
RQ_ROOT="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
RQ105_ORCH_ROOT="${RQ105_ORCH_ROOT:-/Users/renhao/git/github/renquant-orchestrator-run}"
LOG_DIR="$RQ_ROOT/logs/rq105"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d)"
RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common-run/src"
[ -d "$RQ_COMMON_SRC" ] || RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common/src"
export PYTHONPATH="$RQ105_ORCH_ROOT/src:$RQ_COMMON_SRC"
# 2026-07-28 operator directive ("105 直接换成 blend 模型"): the frozen batch
# vector comes from the BLEND composite lane (runs.alpaca_shadow_blend.db —
# daily_104.sh Step 5 scores the full funnel with the pinned
# strategy_config.shadow_blend.json profile; pipeline#218 kind=blend,
# z(prod panel-ltr) + z(clf top-decile), both pins fail-closed).
# ONE-LINE REVERT: change "blend" back to "prod" below (or set
# RQ105_SCORE_SOURCE=prod in the environment; the env override wins).
export RQ105_SCORE_SOURCE="${RQ105_SCORE_SOURCE:-blend}"
"$RQ_ROOT/.venv/bin/python" "$RQ105_ORCH_ROOT/ops/renquant105/export_batch_scores.py" \
  >> "$LOG_DIR/batch_scores_export_$TS.log" 2>&1
RC=$?
if [ $RC -ne 0 ]; then
  . "$RQ_ROOT/scripts/notify.sh" 2>/dev/null || true
  rq_notify "rq105 batch scores export FAILED rc=$RC ($TS)" \
    "see logs/rq105/batch_scores_export_$TS.log" || true
fi
exit $RC
