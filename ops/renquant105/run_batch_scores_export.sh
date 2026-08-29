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
RQ105_OPS_DIR="$(dirname "$0")"
# orch#1085: boot catch-up. The plist carries RunAtLoad=true, so launchd also
# invokes this wrapper at every bootstrap (boot/login) — a 06:15 slot missed
# across a boot (2026-08-28: host up at 10:38, no export, serving chain
# no-op'd all day) is caught up here. The guard applies to EVERY invocation:
# run iff Mon-Fri AND 06:15 <= local time < 13:00 AND today's bundle is
# missing; otherwise one stamped line in catchup_guard_batch-scores-export_
# <date>.log (NOT this job's evidence log) and exit 0. 13:00 is the NYSE
# close in local PT: a "pre-market frozen" vector exported after the session
# would be a post-hoc artifact even when its content is identical.
. "$RQ105_OPS_DIR/rq105_catchup_guard.sh"
rq105_catchup_guard batch-scores-export "$(date +%u)" "$(date +%H%M)" 0615 1300 \
  "$LOG_DIR/catchup_guard_batch-scores-export_$TS.log" \
  "$RQ_ROOT/data/rq105/batch_scores_$TS.json" \
  "$RQ_ROOT/data/rq105/batch_scores_$TS.meta.json"
GUARD_RC=$?
case $GUARD_RC in
  0) ;;
  1) exit 0 ;;
  *) echo "FATAL: catch-up guard error rc=$GUARD_RC" >> "$LOG_DIR/batch_scores_export_$TS.log"; exit 1 ;;
esac
# orch#1016: renquant-common comes from the PINNED runtime, verified against
# subrepos.lock.json before import. No fallback, no env override, fails closed.
. "$RQ105_OPS_DIR/rq105_common_src.sh"
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
