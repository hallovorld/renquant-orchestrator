#!/usr/bin/env bash
# momentum_train_weekly.sh — weekly momentum TRAIN job (GOAL-7 slice 5, the
# REVIEWED-SURFACE half; renquant-model
# doc/design/2026-08-02-momentum-pipeline-architecture.md build-order item 5).
#
# WHAT IT RUNS. The momentum TRAIN CLI (renquant-model
# tools/momentum_train_run.py, model#196) once a week with --asof = the firing
# date: the CLI reads the live ohlcv/panel surfaces with per-file digest
# RECORDING, trains the v0 residual-momentum artifact, and publishes it per the
# model#197 serving-path convention:
#   <strategy serving root>/artifacts/momentum/<cutoff>/momentum_residual_v0.json
# alongside the append-only artifact ledger. The serving root is the SAME root
# the s104 config's artifact_path entries resolve under
# (RenQuant/backtesting/renquant_104 — verified 2026-08-02: artifacts/prod/ and
# artifacts/shadow/ both live there), so the slice-4 shadow_models entry
# (artifacts/momentum/...) resolves the moment the first artifact lands. All
# artifact writes happen BY THIS JOB at run time — never by agent hands.
#
# TWO LANES, ONE JOB (model#199 build item 2). After the v0 step, the SAME CLI
# runs again with --params-version v1_fast (the frozen 63/5 fast clock,
# model#200) into its OWN publish set:
#   <strategy serving root>/artifacts/momentum_fast/<cutoff>/momentum_residual_v0.json
# plus its OWN independent digest-chained ledger — the s104 fast shadow entry
# pins artifacts/momentum_fast/momentum_artifact_ledger.jsonl. The dated
# basename stays momentum_residual_v0.json in BOTH lanes: it is the serving
# loader's hardcoded path convention (pipeline
# momentum_residual_scorer.MOMENTUM_DATED_ARTIFACT_BASENAME), not an identity
# claim — identity is the artifact's kind/params_version/content_sha256, which
# ARE v1_fast in the fast lane's publish set.
#
# FAST LANE IS NON-FATAL BY DESIGN. v0 is bound for the prod MoE; the fast
# lane is a shadow patrol. The fast step runs AFTER v0 regardless of v0's
# outcome, its rc is logged (fast_rc in the end marker) but NEVER propagated:
# launchd records the v0 rc, so a fast-lane failure can never block or mask
# the slow artifact. A silently-dead fast lane is still LOUD downstream: the
# s104 fast shadow entry's daily health record goes unresolved/stale, which is
# the shadow-scorer sentinel's surface. If the pinned CLI predates the
# --params-version flag (pin not yet advanced past the model-side #199-item-2
# PR), the fast step exits 2 (usage) into this log — a loud, dated refusal —
# while v0 is untouched.
#
# MERGED-BUT-DARK BY DESIGN. This wrapper + its manifest/plist entries are the
# reviewed surface only. Installing the plist, advancing the model/s104 pins
# and syncing the run checkouts is ONE operator grant
# (doc/progress/2026-08-02-momentum-train-launchd-surface.md, ordered per
# model#197: job installed -> first artifact -> s104 config -> pin advance).
# Until that grant, nothing schedules this file.
#
# ONE DETERMINISTIC ROOT (the #675/#751 rule). Model code comes from the PINNED
# runtime checkout materialised by the umbrella:
#   /Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/renquant-model
# That path is governed by the umbrella pin (subrepos.lock.json), so THIS JOB
# IS ONLY AS FRESH AS THE RUN-SURFACE SYNC — if the pin has not been advanced
# past model#196 and re-materialised, the CLI is absent and this wrapper
# REFUSES loudly below (rc 64) into the dated log. There is deliberately NO
# `[ -d ... ] || VAR=` fallback to a dev checkout: which copy executes is
# decided by review, not by filesystem state. The drift scan reads every
# manifested wrapper each firing and alarms on that idiom.
#
# EVIDENCE CONTRACT — exec-redirect FIRST, deliberately unlike
# run_model_freshness_monitor.sh. The conditional-retrain diagnosis (orch#754
# trail) showed the cost of setup work before the exec-redirect: a pre-exec
# death lands only in launchd's shared .err and the dated log never appears —
# "died before acting" becomes indistinguishable from "never fired". Here the
# ONLY pre-exec step is creating the log directory; every later refusal and the
# CLI's own output land in the dated log, and every exit path writes a terminal
# marker with its rc. The #638 evidence-ordering concern (a fresh log for a run
# that never happened) is answered by CONTENT, not existence: the log always
# carries an explicit verdict line (REFUSED: ... or the CLI's JSON status) plus
# the end marker — the liveness glob proves the wrapper FIRED; the log body
# says what happened.
#
# EXIT CODES. 64 = wrapper-level refusal (prereq missing), distinct from every
# CLI code so launchd's recorded code attributes the failure to the right
# layer. The wrapper's exit code is the V0 lane's CLI code, untouched:
# 0 trained | 2 usage | 3 surfaces missing | 4 artifact for this cutoff
# already exists (append-only refusal) | 5 ledger refused the append. The
# fast lane's code is recorded in the log's fast_rc marker ONLY (non-fatal
# shadow lane — see above).
set -uo pipefail

RQ_ROOT="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
PYTHON="$RQ_ROOT/.venv/bin/python"
MODEL_RUNTIME="$RQ_ROOT/.subrepo_runtime/repos/renquant-model"
TRAIN_CLI="$MODEL_RUNTIME/tools/momentum_train_run.py"
SERVING_ROOT="$RQ_ROOT/backtesting/renquant_104"
OUT_ROOT="$SERVING_ROOT/artifacts/momentum"
OUT_ROOT_FAST="$SERVING_ROOT/artifacts/momentum_fast"
LOG_DIR="$RQ_ROOT/logs/rq104"
ASOF="$(date +%F)"
LOG="$LOG_DIR/momentum_train_${ASOF}.log"

# The ONLY pre-exec step: the redirect target's directory must exist. A failure
# here is the one case that can land outside the dated log (launchd's .err).
mkdir -p "$LOG_DIR" || { echo "cannot create log dir $LOG_DIR" >&2; exit 64; }

exec >>"$LOG" 2>&1
echo "=== momentum-train-weekly start $(date '+%F %T %Z') asof=$ASOF ==="

refuse() {
    echo "REFUSED: $*"
    echo "=== momentum-train-weekly end rc=64 $(date '+%F %T %Z') ==="
    exit 64
}

[ -x "$PYTHON" ] || refuse "interpreter not executable: $PYTHON"
[ -d "$MODEL_RUNTIME" ] || refuse "pinned model runtime checkout absent: $MODEL_RUNTIME — run-surface sync not current"
[ -f "$TRAIN_CLI" ] || refuse "train CLI absent: $TRAIN_CLI — the pinned model checkout predates model#196; advance the umbrella model pin and re-materialise .subrepo_runtime before this job can act"

# One deterministic reviewed root; the CLI self-inserts the same src/ relative
# to its own (pinned) location, so wrapper and CLI agree by construction.
export PYTHONPATH="$MODEL_RUNTIME/src"

# LANE 1 — v0, the slow 252/21 lane bound for the prod MoE. Invocation
# deliberately flag-free: byte-identical to the pre-#199 reviewed command, so
# this lane's meaning cannot change under an old OR new pinned CLI.
"$PYTHON" "$TRAIN_CLI" --asof "$ASOF" --out-root "$OUT_ROOT"
RC=$?
echo "--- train CLI exit=$RC (0 trained | 2 usage | 3 surfaces missing | 4 artifact exists | 5 ledger refused)"

# LANE 2 — v1_fast, the 63/5 fast shadow patrol (model#199 item 2). Runs
# regardless of the v0 rc (independent lanes), own out-root + own ledger,
# NON-FATAL: fast_rc is logged below but never propagated — launchd must
# record the v0 verdict. exit 2 here also covers a pinned CLI that predates
# the --params-version flag (loud in this log, invisible to the v0 rc).
"$PYTHON" "$TRAIN_CLI" --asof "$ASOF" --params-version v1_fast --out-root "$OUT_ROOT_FAST"
RC_FAST=$?
echo "--- fast train CLI exit=$RC_FAST (v1_fast shadow lane, NON-FATAL: same code table; 2 usage also = pinned CLI predates --params-version)"
echo "=== momentum-train-weekly end rc=$RC fast_rc=$RC_FAST $(date '+%F %T %Z') ==="
exit "$RC"
