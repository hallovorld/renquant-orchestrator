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
# orch#1016: which renquant-common runs is a REVIEWED decision, not a
# filesystem accident. Single resolver, no fallback, fails closed.
. "$(dirname "$0")/rq105_common_src.sh"
rq105_resolve_common_src || exit 1
export PYTHONPATH="$RQ105_ORCH_ROOT/src:$RQ_COMMON_SRC"
# 2026-08-05 operator directive ("105 应该用 104 prod 的模型"): the frozen batch
# vector comes from the PROD lane (runs.alpaca.db) — the same run that placed
# the day's real orders. This SUPERSEDES the 2026-07-28 directive
# ("105 直接换成 blend 模型") that pointed it at the isolated shadow-blend lane
# DB (runs.alpaca_shadow_blend.db); that lane keeps running, rq105 just stops
# sourcing from it.
#
# Note what this no longer means: since the z-blend fullbook went live, PROD
# itself scores with a two-component composite `[VERIFIED 2026-08-05 — 17 of
# the last 40 live prod runs carry two resolved component pins]`. "prod" here
# names the LANE whose vector rq105 replays, not "the single-artifact model".
# ONE-LINE REVERT: change "prod" back to "blend" below (or set
# RQ105_SCORE_SOURCE=blend in the environment; the env override wins).
export RQ105_SCORE_SOURCE="${RQ105_SCORE_SOURCE:-prod}"
"$RQ_ROOT/.venv/bin/python" "$RQ105_ORCH_ROOT/ops/renquant105/export_batch_scores.py" \
  >> "$LOG_DIR/batch_scores_export_$TS.log" 2>&1
RC=$?
if [ $RC -ne 0 ]; then
  . "$RQ_ROOT/scripts/notify.sh" 2>/dev/null || true
  rq_notify "rq105 batch scores export FAILED rc=$RC ($TS)" \
    "see logs/rq105/batch_scores_export_$TS.log" || true
fi
exit $RC
