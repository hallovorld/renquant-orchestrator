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
# NOTE: RENQUANT_INTRADAY_DECISIONING is deliberately NOT exported here.
# Activation (a recorded landing step) uncomments the next line:
# ACTIVATED 2026-08-12 (G-H task#28, operator-authorized; shadow/never-submit
# runtime-asserted; revert = re-comment). Re-applied 2026-08-24 after the #1044
# ff-merge conflicted with the stashed copy (UU caught pre-schedule; resolution:
# take main's verified block cleanly, then re-apply ONLY this line).
export RENQUANT_INTRADAY_DECISIONING=1
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
