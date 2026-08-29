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
#   2. env flag RENQUANT_INTRADAY_DECISIONING=1 — exported below ONLY when
#      the operator-owned ARMING FILE validates (default: file absent, so
#      NOT exported; see the arming block below)
#   3. kill-switch file absent (data/rq105/intraday_decisioning.KILL —
#      touch it to halt mid-session before the next tick)
# Shadow mode is runtime-asserted in the module: it NEVER submits anything.
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
# orch#1016: renquant-common comes from the PINNED runtime, verified against
# subrepos.lock.json before import. No fallback, no env override, fails closed.
RQ105_OPS_DIR="$(dirname "$0")"
. "$RQ105_OPS_DIR/rq105_common_src.sh"
rq105_resolve_common_src || exit 1
SUBREPO="$RQ_ROOT/.subrepo_runtime/repos"
# orch#1016: $RQ_COMMON_SRC IS $SUBREPO/renquant-common/src now (resolved and
# pin-verified above), so the duplicate entry is gone. It previously sat
# AFTER a mutable sibling checkout, which shadowed the pinned copy that was
# already on this line — the pin was present and losing.
export PYTHONPATH="$RQ105_ORCH_ROOT/src:$RQ_COMMON_SRC:$SUBREPO/renquant-pipeline/src:$SUBREPO/renquant-base-data/src:$SUBREPO/renquant-model/src:$SUBREPO/renquant-artifacts/src:$SUBREPO/renquant-execution/src:$SUBREPO/renquant-strategy-104/src:$SUBREPO/renquant-backtesting/src"
# orch#1085: boot catch-up (same shape as run_batch_scores_export.sh). The
# plist carries RunAtLoad=true; the guard makes every invocation idempotent:
# run iff $TS is an NYSE session AND 06:25 <= local time < that session's
# ACTUAL local close (rq105_catchup_cutoff.py, the same NYSE calendar the
# scheduler gates on — r2, codex: no fixed 13:00, no weekday-only test) AND
# today's dated wrapper log is absent (this wrapper writes
# session_scheduler_<date>.log on every real run, armed or not — the arming
# verdict is its first line). A scheduler started mid-session is the designed
# case: it self-gates on the NYSE session and exits after the close. Skips
# stamp catchup_guard_session-scheduler_<date>.log, never the evidence log.
# Sits AFTER the pin resolver and the PYTHONPATH export on purpose: the
# cutoff helper imports the calendar from exactly the pinned code this job
# runs.
. "$RQ105_OPS_DIR/rq105_catchup_guard.sh"
rq105_catchup_guard session-scheduler "$TS" "$(date +%H%M)" 0625 \
  "$LOG_DIR/catchup_guard_session-scheduler_$TS.log" \
  "$LOG_DIR/session_scheduler_$TS.log"
GUARD_RC=$?
case $GUARD_RC in
  0) ;;
  1) exit 0 ;;
  *) echo "FATAL: catch-up guard error rc=$GUARD_RC" >> "$LOG_DIR/session_scheduler_$TS.log"; exit 1 ;;
esac
# ARMING (gate 2). RENQUANT_INTRADAY_DECISIONING is NOT a committed default.
# It is exported ONLY when the operator-owned runtime file (outside git, so a
# recovery checkout or sync cannot silently extinguish an authorized
# activation — the 2026-08-12..08-26 dirty-tree export nearly died exactly
# that way on 08-24, #1044) validates fail-closed:
#   $RQ_ROOT/data/rq105/intraday_decisioning.armed.json
#   {"armed": true, "operator": "...", "armed_at": "...", "authority": "..."}
# Creating/editing/removing that file is a recorded OPERATOR landing step;
# agents never write it. Disarm = delete it or set "armed": false. The
# kill-switch (gate 3) remains the mid-session halt, unchanged.
ARMING_FILE="$RQ_ROOT/data/rq105/intraday_decisioning.armed.json"
if ARMED_PROVENANCE=$(python3 -m renquant_orchestrator.rq105_arming "$ARMING_FILE" 2>>"$LOG_DIR/session_scheduler_$TS.log"); then
  export RENQUANT_INTRADAY_DECISIONING=1
  echo "[session-scheduler] intraday decisioning ARMED ($ARMED_PROVENANCE)" >> "$LOG_DIR/session_scheduler_$TS.log"
fi
# orch#1041: pass the PINNED strategy config EXPLICITLY, fail closed if absent.
# Without this flag, default_strategy_config_path() resolves the SIBLING dev
# checkout (~/git/github/renquant-strategy-104) in preference to the pinned
# runtime — measured: every activated session's manifest fingerprints the
# sibling's config (c6d1abe2…), and the pinned copy was never even a
# candidate. Same defect class as orch#1016; same fix shape as #1037: the
# reviewed surface is the pinned runtime, no fallback, refuse rather than
# silently run the wrong config. NOTE: the session manifest's
# strategy_config_fingerprint will change on the first post-deploy session —
# that discontinuity is the fix landing, and the §9.4 LIVE draft requires a
# session under the NEW fingerprint before it can be signed.
# Existence is NOT pin verification [codex on the first draft]: the resolver
# proves (1) subrepos.lock.json names renquant-strategy-104, (2) the runtime
# checkout HEAD equals that pin, and (3) the config bytes equal the pinned
# blob (a dirty file in a pinned checkout is exactly as unreviewed as a
# sibling tree). ONE implementation shared with the renquant-common check
# (#1037); the scheduler has NO fallback — refusal stops the job.
PIN_PY="$RQ_ROOT/.venv/bin/python"; [ -x "$PIN_PY" ] || PIN_PY="python3"
if ! PINNED_STRATEGY_CONFIG="$("$PIN_PY" "$RQ105_OPS_DIR/rq105_pinned_common.py" \
      --rq-root "$RQ_ROOT" --subrepo renquant-strategy-104 \
      --verify-file configs/strategy_config.json 2>> "$LOG_DIR/session_scheduler_$TS.log")" \
   || [ -z "$PINNED_STRATEGY_CONFIG" ]; then
  echo "FATAL: pinned strategy-config verification refused (orch#1041) — see above" \
    >> "$LOG_DIR/session_scheduler_$TS.log"
  exit 1
fi
"$RQ_ROOT/.venv/bin/python" -m renquant_orchestrator.intraday_session_scheduler \
  --env-file "$RQ_ROOT/.env" \
  --data-root "$RQ_ROOT" \
  --strategy-config "$PINNED_STRATEGY_CONFIG" \
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
