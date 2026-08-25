#!/bin/bash
# rq105: post-close OBSERVE-ONLY shadow real-time serving replay (#221 collector).
# S3-P3 (2026-08-24): now self-produces its feature snapshot via
# build_feature_snapshot.sh (orch#1032) before the availability check.
# Replays today's recorded tick feed at four fixed as-of checkpoints (10:00,
# 12:00, 14:00, 15:30 ET) against the FROZEN batch score vector exported
# pre-market by export_batch_scores.py. Deterministic post-close replay — no
# intraday scheduling fragility; the tick feed is censored to each as-of.
set -u
RQ_ROOT="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
RQ105_ORCH_ROOT="${RQ105_ORCH_ROOT:-/Users/renhao/git/github/renquant-orchestrator-run}"
LOG_DIR="$RQ_ROOT/logs/rq105"
mkdir -p "$LOG_DIR"

# GOAL-1 #622. Two of the three early exits below returned 1 WITHOUT writing a
# dated log, while the third wrote one. That asymmetry made "the job did not run"
# and "the job ran and skipped" indistinguishable from disk: measured 2026-07-31,
# the newest dated log was 2026-07-13 while the job is scheduled Mon-Fri, and the
# only surviving signal was a launchctl exit code that launchd retains until the
# NEXT run. Every exit path now leaves one stamped line.
skip_log() {
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" \
    >> "$LOG_DIR/shadow_serving_$TS.log"
}

# A job that CANNOT succeed today is not a job that FAILED today. Exit 4 says
# "structurally not wired yet"; exit 1 stays "something that should have worked
# did not". The ack ledger can disposition them separately (see the
# acked_exit_codes support added for the sentinel's own row).
EXIT_NOT_WIRED=4
#: The producer FAILED (not a provenance refusal). Deliberately unlisted in
#: ops/agent_inbox.py DESIGNED_EXIT_CODES: an unlisted code is UNKNOWN there by
#: construction, defaulting to "this needs a human" — correct for our own bug.
EXIT_PRODUCER_FAILED=5
TS="$(date +%Y-%m-%d)"
SCORES="$RQ_ROOT/data/rq105/batch_scores_$TS.json"
META="$RQ_ROOT/data/rq105/batch_scores_$TS.meta.json"
FEATURE_SNAPSHOT="$RQ_ROOT/data/rq105/feature_snapshot_$TS.json"
if [ ! -f "$SCORES" ] || [ ! -f "$META" ]; then
  # Canonical sender (campaign B6): topic/.env resolution + RENQUANT_NO_NOTIFY live there.
  . "$RQ_ROOT/scripts/notify.sh" 2>/dev/null || true
  rq_notify "rq105 shadow serving SKIPPED ($TS)" \
    "no frozen batch-score export for today (export_batch_scores 06:15 failed?)" || true
  skip_log "SKIP upstream: no frozen batch-score export ($SCORES / $META missing)"
  exit 1
fi
if [ ! -f "$FEATURE_SNAPSHOT" ]; then
  # S3-P3 (orch#1026/#1030/#1032, 2026-08-24): the producer now EXISTS —
  # build_feature_snapshot.sh bridges the prod-lane served matrix
  # (PersistServedMatrixTask, orch#703) to the FeatureSnapshot contract. Try
  # it exactly once before concluding the snapshot is unavailable. This line
  # replaced a daily "SKIP not-wired: no producer exists" that had fired every
  # session since 2026-08-12.
  "$(dirname "$0")/build_feature_snapshot.sh" --date "$TS"     >> "$LOG_DIR/feature_snapshot_$TS.log" 2>&1
  PRODUCER_RC=$?
fi
# BRANCH ON THE PRODUCER'S EXIT CODE — it is a contract, not a log field.
# build_feature_snapshot.sh documents 3 = expected provenance refusal, and any
# OTHER nonzero = unexpected import/decoder/write/programming failure that is
# explicitly NOT skippable. An earlier revision of this block captured
# PRODUCER_RC and never branched on it, labelling every outcome
# "producer-refused" and exiting the calm skip code — which recreated one layer
# up the exact failure-collapse #1032 removed from the producer's own wrapper
# (codex review 2026-08-24). It mattered most here: this is the surface that
# decides whether anyone is told, so a broken producer could never reach the
# paging path.
if [ "${PRODUCER_RC:-0}" -ne 0 ] && [ "${PRODUCER_RC:-0}" -ne 3 ]; then
  # NOT a refusal: the producer BROKE. Distinct evidence, distinct exit, and it
  # pages — the failure is in our code, and calling it "refused" would be false.
  skip_log "FAIL producer-broken (rc=$PRODUCER_RC): build_feature_snapshot.sh failed for a reason that is NOT a provenance refusal (3) — see feature_snapshot_$TS.log (S3-P3, orch#1032 exit contract)"
  . "$RQ_ROOT/scripts/notify.sh" 2>/dev/null || true
  rq_notify "rq105 feature-snapshot producer FAILED ($TS)" \
    "build_feature_snapshot.sh exited $PRODUCER_RC — not a provenance refusal (3). Import/decoder/write/bug. Serving skipped; see $LOG_DIR/feature_snapshot_$TS.log" 2>/dev/null || true
  # Deliberately NOT $EXIT_NOT_WIRED: ops/agent_inbox.py registers 4 as a
  # designed, non-actionable status. An UNLISTED code is UNKNOWN by
  # construction there, whose default is "this needs a human" — which is
  # exactly right for a producer that broke.
  exit "$EXIT_PRODUCER_FAILED"
fi
# rc=0 MEANS "snapshot written". If it is missing anyway, the producer FALSELY
# REPORTED SUCCESS (or its output-path wiring is broken) — implementation
# breakage, not a refusal, and it must not inherit the calm path. An earlier
# revision merged this case into the refusal branch, which left a producer
# lying about success completely silent (codex review 2026-08-24).
if [ "${PRODUCER_RC:-0}" -eq 0 ] && [ ! -f "$FEATURE_SNAPSHOT" ]; then
  skip_log "FAIL producer-lied (rc=0): build_feature_snapshot.sh reported success but $FEATURE_SNAPSHOT does not exist — false success or broken output path, NOT a provenance refusal — see feature_snapshot_$TS.log (S3-P3, orch#1032 exit contract)"
  . "$RQ_ROOT/scripts/notify.sh" 2>/dev/null || true
  rq_notify "rq105 feature-snapshot producer reported FALSE SUCCESS ($TS)" \
    "build_feature_snapshot.sh exited 0 but wrote no snapshot at $FEATURE_SNAPSHOT. Not a refusal. Serving skipped; see $LOG_DIR/feature_snapshot_$TS.log" 2>/dev/null || true
  exit "$EXIT_PRODUCER_FAILED"
fi
if [ ! -f "$FEATURE_SNAPSHOT" ]; then
  # By elimination this is rc=3: the producer REFUSED (fail-closed provenance —
  # stale/ambiguous served matrix, schema drift; its log carries the specific
  # reason). A refusal is the producer working, so this is the one calm path:
  # recorded, no page, designed skip code. Every other outcome above pages.
  skip_log "SKIP producer-refused (rc=${PRODUCER_RC:-?}): $FEATURE_SNAPSHOT not produced — see feature_snapshot_$TS.log (S3-P3, orch#1032)"
  exit "$EXIT_NOT_WIRED"
fi
PY="$RQ_ROOT/.venv/bin/python"
# Campaign B5: the calendar primitive behind bundle verification now lives in
# renquant_common.market_calendar — put a sibling renquant-common checkout on
# PYTHONPATH BEFORE the verify step (pinned -run checkout preferred; the venv
# install alone may predate market_calendar).
# orch#1016: renquant-common comes from the PINNED runtime, verified against
# subrepos.lock.json before import. No fallback, no env override, fails closed.
RQ105_OPS_DIR="$(dirname "$0")"
. "$RQ105_OPS_DIR/rq105_common_src.sh"
rq105_resolve_common_src || exit 1
# S3-b (orch#1053): the pinned blend scorer loads through the PINNED
# renquant-pipeline (load_blend_scorer does the fail-closed pin verification —
# one shared definition, not re-implemented here). Codex on #1053: putting the
# LOADER code on PYTHONPATH by pathname only would let drifted/dirty/mid-sync
# pipeline code import successfully while every artifact pin still verified —
# artifact verification does not establish loader-code identity. So the
# checkout is verified (lock entry + HEAD==pin + clean tree) BEFORE it joins
# the path, through the same rq105_pinned_common contract as everything else.
PYBIN="$PY"
[ -x "$PYBIN" ] || PYBIN="python3"
if ! RQ_PIPELINE_SRC=$("$PYBIN" "$RQ105_OPS_DIR/rq105_pinned_common.py" \
      --rq-root "$RQ_ROOT" --verify-subrepo renquant-pipeline \
      2>> "$LOG_DIR/shadow_serving_$TS.log"); then
  . "$RQ_ROOT/scripts/notify.sh" 2>/dev/null || true
  rq_notify "rq105 shadow serving FAILED — pinned renquant-pipeline verification refused ($TS)" \
    "rq105_pinned_common --verify-subrepo renquant-pipeline refused (orch#1053); see logs/rq105/shadow_serving_$TS.log" || true
  echo "FATAL: pinned renquant-pipeline verification refused (orch#1053) — refusing to import unverified loader code" \
    >> "$LOG_DIR/shadow_serving_$TS.log"
  exit 1
fi
export PYTHONPATH="$RQ105_ORCH_ROOT/src:$RQ_COMMON_SRC:$RQ_PIPELINE_SRC"
# S3-b: the scorer's config identity comes from the PINNED strategy-104
# checkout, verified lock+HEAD+bytes — the same rq105_pinned_common contract
# the session scheduler uses (orch#1041). Refusal = stop, page-free skip is
# wrong here: an unverifiable config is a broken deploy, not a calm state.
if ! PINNED_STRATEGY_CONFIG=$("$PYBIN" "$RQ105_OPS_DIR/rq105_pinned_common.py" \
      --rq-root "$RQ_ROOT" --subrepo renquant-strategy-104 \
      --verify-file configs/strategy_config.json 2>> "$LOG_DIR/shadow_serving_$TS.log"); then
  . "$RQ_ROOT/scripts/notify.sh" 2>/dev/null || true
  rq_notify "rq105 shadow serving FAILED — pinned strategy-config verification refused ($TS)" \
    "rq105_pinned_common --verify-file refused (orch#1041); see logs/rq105/shadow_serving_$TS.log" || true
  echo "FATAL: pinned strategy-config verification refused (orch#1041)" \
    >> "$LOG_DIR/shadow_serving_$TS.log"
  exit 1
fi
STRATEGY_DIR="$RQ_ROOT/backtesting/renquant_104"
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
  # S3-b (orch#1052): the pinned wiring module builds the verified blend
  # scorer and delegates to the same observe-only collector. The bare module
  # (which refuses with "no scorer wired", rc=2) is no longer the entrypoint.
  "$PY" -m renquant_orchestrator.shadow_serving_pinned \
    --pinned-strategy-config "$PINNED_STRATEGY_CONFIG" \
    --strategy-dir "$STRATEGY_DIR" \
    --as-of "$AS_OF" \
    --feature-snapshot-json "$FEATURE_SNAPSHOT" \
    --batch-scores-json "$SCORES" \
    --batch-run-id "$RUN_ID" \
    --data-root "$RQ_ROOT" \
    >> "$LOG_DIR/shadow_serving_$TS.log" 2>&1 || RC_TOTAL=$?
  # S3-P4 OBSERVE-ONLY (design §4/§4b/§5): the guarded entry loop's decision
  # surface over this tick's rows — batch(T-1, leak-guarded) ∩ intraday, v1
  # guardrails with the cap from the SAME pinned config verified above.
  # Records intents; module contains no broker path (the live emission stage
  # ships with the S3-c operator authorization, never before it).
  "$PY" -m renquant_orchestrator.rq105_entry_loop_shadow \
    --session-date "$TS" \
    --as-of "$AS_OF" \
    --db-path "$RQ_ROOT/data/runs.alpaca.db" \
    --shadow-log "$RQ_ROOT/logs/renquant105_pilot/shadow_realtime_serving.jsonl" \
    --scheduler-log "$RQ_ROOT/logs/renquant105_pilot/intraday_decisions_shadow.jsonl" \
    --pinned-strategy-config "$PINNED_STRATEGY_CONFIG" \
    --data-root "$RQ_ROOT" \
    >> "$LOG_DIR/shadow_serving_$TS.log" 2>&1 || RC_TOTAL=$?
done
if [ $RC_TOTAL -ne 0 ]; then
  . "$RQ_ROOT/scripts/notify.sh" 2>/dev/null || true
  rq_notify "rq105 shadow serving FAILED rc=$RC_TOTAL ($TS)" \
    "see logs/rq105/shadow_serving_$TS.log" || true
fi
exit $RC_TOTAL
