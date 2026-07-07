#!/bin/bash
# rq105: post-close OBSERVE-ONLY shadow real-time serving replay (#221 collector).
# Replays today's recorded tick feed at four fixed as-of checkpoints (10:00,
# 12:00, 14:00, 15:30 ET) against the FROZEN batch score vector exported
# pre-market by export_batch_scores.py. Deterministic post-close replay — no
# intraday scheduling fragility; the tick feed is censored to each as-of.
set -u
RQ_ROOT="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
RQ105_ORCH_ROOT="${RQ105_ORCH_ROOT:-/Users/renhao/git/github/renquant-orchestrator-run}"
LOG_DIR="$RQ_ROOT/logs/rq105"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d)"
SCORES="$RQ_ROOT/data/rq105/batch_scores_$TS.json"
META="$RQ_ROOT/data/rq105/batch_scores_$TS.meta.json"
if [ ! -f "$SCORES" ] || [ ! -f "$META" ]; then
  # Canonical sender (campaign B6): topic/.env resolution + RENQUANT_NO_NOTIFY live there.
  . "$RQ_ROOT/scripts/notify.sh" 2>/dev/null || true
  rq_notify "rq105 shadow serving SKIPPED ($TS)" \
    "no frozen batch-score export for today (export_batch_scores 06:15 failed?)" || true
  exit 1
fi
PY="$RQ_ROOT/.venv/bin/python"
# Campaign B5: the calendar primitive behind bundle verification now lives in
# renquant_common.market_calendar — put a sibling renquant-common checkout on
# PYTHONPATH BEFORE the verify step (pinned -run checkout preferred; the venv
# install alone may predate market_calendar).
RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common-run/src"
[ -d "$RQ_COMMON_SRC" ] || RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common/src"
export PYTHONPATH="$RQ105_ORCH_ROOT/src:$RQ_COMMON_SRC"
# Verify the on-disk bundle is genuinely today's, sourced from the correct
# prior session, and unmodified before trusting it — session_date match +
# source_run_date match against the real prior NYSE session + score-content-
# hash match (Codex #236 round 2: the wrapper previously trusted a
# stale/tampered bundle blindly; round 3: added the source_run_date check so
# a bundle correctly stamped session_date=today but sourced from a stale
# multi-day-old run is also caught here, not just at export time).
if ! VERIFY_OUT=$("$PY" "$RQ105_ORCH_ROOT/ops/renquant105/batch_scores_bundle.py" verify "$SCORES" "$META" "$TS" 2>&1); then
  . "$RQ_ROOT/scripts/notify.sh" 2>/dev/null || true
  rq_notify "rq105 shadow serving SKIPPED — bundle verification failed ($TS)" \
    "$VERIFY_OUT" || true
  echo "$VERIFY_OUT" >> "$LOG_DIR/shadow_serving_$TS.log"
  exit 1
fi
RUN_ID=$(python3 -c "import json;print(json.load(open('$META'))['run_id'])")
RC_TOTAL=0
for T in 10:00 12:00 14:00 15:30; do
  AS_OF=$("$PY" -c "import datetime,zoneinfo; h,m='${T}'.split(':'); print(datetime.datetime.combine(datetime.date.today(), datetime.time(int(h),int(m)), tzinfo=zoneinfo.ZoneInfo('America/New_York')).isoformat())")
  "$PY" -m renquant_orchestrator.shadow_realtime_serving \
    --as-of "$AS_OF" \
    --batch-scores-json "$SCORES" \
    --batch-run-id "$RUN_ID" \
    --data-root "$RQ_ROOT" \
    >> "$LOG_DIR/shadow_serving_$TS.log" 2>&1 || RC_TOTAL=$?
done
if [ $RC_TOTAL -ne 0 ]; then
  . "$RQ_ROOT/scripts/notify.sh" 2>/dev/null || true
  rq_notify "rq105 shadow serving FAILED rc=$RC_TOTAL ($TS)" \
    "see logs/rq105/shadow_serving_$TS.log" || true
fi
exit $RC_TOTAL
