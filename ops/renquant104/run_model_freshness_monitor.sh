#!/usr/bin/env bash
# RQ104 model-freshness monitor — Pillar 1 of the 2026-06-30 governance design
# (RFC #210), scheduled at last.
#
# WHY THIS WRAPPER EXISTS. `src/renquant_orchestrator/model_freshness_monitor.py`
# has been complete since the #210 batch and is the Phase-1 deliverable the design
# says "ships now". Measured 2026-07-30: it has exactly ONE call site in the whole
# tree (`cli.py`, a subcommand), NO entry among the 40 jobs in
# `ops/launchd_manifest.json`, and has never written a single output file. It is
# textbook deployed-but-dark — the tiers, the thresholds and the ntfy body were all
# built, and nothing ever fired them.
#
# WHAT IT WOULD HAVE BEEN SAYING. Running it observe-only on 2026-07-30 returns
# exit 3 with two populations in genuine BREACH:
#   * tournament   141/142 artifacts at age 37d against a 28d rail (SPY missing)
#   * shadow-panel effective_selection_cutoff_date=2026-02-10, age 170d vs 35d
#   * prod-panel   UNKNOWN, fail-closed: the artifact stamps no binding data
#                  cutoff, and the monitor refuses `trained_date` as a freshness
#                  axis by design (a fresh build over stale data is not fresh).
#
# OBSERVE-ONLY, DELIBERATELY. This job reads artifacts and notifies. It promotes
# nothing, fits nothing, retrains nothing and writes no production state. The
# 28-day CEILING (lowering `model_staleness_days` 60 -> 28) stays deferred exactly
# as design §5 requires — tightening a gate before a validated remediation path
# exists makes gating strictly worse. Scheduling the monitor is not the ceiling.
#
# EXIT CODES pass through the monitor's own tier mapping, measured 2026-07-30:
#   0 healthy | 1 warn (14-21d) | 2 escalate (21-24d) | 3 breach (>28d) or UNKNOWN
# launchd records the code; the liveness scan reads the dated log below as
# evidence. Both are needed: a nonzero code alone cannot distinguish "breach" from
# "crashed", which is the #622 lesson.
# EVIDENCE ORDERING — codex BLOCKER on orch#638, and the reason the whole file is
# shaped this way. The first version created the dated log FIRST and then did env
# setup. So a failure in setup left a freshly-mtimed evidence file and no monitor
# run, and the liveness scan — which scores this job on exactly that glob — would
# report it alive. That is the fifth instance on this programme of a check passing
# because its subject is not what the reader assumes, and here I built it into the
# evidence itself.
#
# The ordering below makes the dated file's EXISTENCE proof that the monitor ran:
#   1. establish every prerequisite, failing fast and LOUDLY on each one
#   2. run the monitor into a temp file — nothing is at the evidence path yet
#   3. only after the process has returned, rename the temp file into place
# A rename is atomic, so a reader never sees a partial log and never sees a log for
# a run that did not happen.
set -uo pipefail

REPO_DIR="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
PYTHON="$REPO_DIR/.venv/bin/python"
LOG_DIR="$REPO_DIR/logs/rq104"
LOG="$LOG_DIR/model_freshness_$(date +%F).log"

# --- 1. prerequisites. Every failure below exits non-zero WITHOUT creating $LOG. --
# stderr goes to the launchd StandardErrorPath, which is the correct surface for a
# job that never got far enough to produce its own evidence.
fail() { echo "PREREQ FAILED: $*" >&2; exit 4; }

[ -d "$REPO_DIR" ]                 || fail "umbrella root absent: $REPO_DIR"
[ -x "$PYTHON" ]                   || fail "interpreter not executable: $PYTHON"
[ -r "$REPO_DIR/scripts/subrepo_env.sh" ] || fail "subrepo_env.sh unreadable"

set -a; source "$REPO_DIR/.env" 2>/dev/null; set +a   # optional by design
source "$REPO_DIR/scripts/subrepo_env.sh"          || fail "sourcing subrepo_env.sh"
renquant_load_subrepo_env "$REPO_DIR"              || fail "renquant_load_subrepo_env"
SUBREPO_ROOT="$(renquant_subrepo_root "$REPO_DIR" "$(dirname "$REPO_DIR")")" \
    || fail "renquant_subrepo_root"
[ -n "$SUBREPO_ROOT" ] && [ -d "$SUBREPO_ROOT" ] || fail "subrepo root unusable: '$SUBREPO_ROOT'"
export RENQUANT_SUBREPO_ROOT="$SUBREPO_ROOT"
PP="$(renquant_subrepo_pythonpath "$SUBREPO_ROOT" renquant-orchestrator renquant-common renquant-base-data renquant-artifacts renquant-model renquant-pipeline renquant-execution renquant-strategy-104 renquant-backtesting)" \
    || fail "renquant_subrepo_pythonpath"
export PYTHONPATH="$PP:${PYTHONPATH:-}"

# The module must be IMPORTABLE before we commit to producing evidence. Without this
# a PYTHONPATH that resolves to the wrong checkout still reaches step 3 and lands a
# log for a run that only ever raised ModuleNotFoundError.
"$PYTHON" -c "import renquant_orchestrator.model_freshness_monitor" 2>/dev/null \
    || fail "model_freshness_monitor not importable under the resolved PYTHONPATH"

mkdir -p "$LOG_DIR" || fail "cannot create $LOG_DIR"

# --- 2. run into a TEMP file. The evidence path stays untouched until step 3. -----
TMP="$(mktemp "${LOG}.XXXXXX")" || fail "cannot create temp log beside $LOG"
trap 'rm -f "$TMP"' EXIT

{
  echo "=== model-freshness monitor start $(date '+%F %T %Z') ==="
  echo "--- observe-only: reads artifacts + notifies; promotes/fits/retrains nothing"
} >>"$TMP" 2>&1

# The exit code is the payload, so it must NOT be swallowed by the pipe into tee.
# `set -o pipefail` is on, but tee is the LAST element, so ${PIPESTATUS[0]} is the
# only faithful read of the monitor's own status.
"$PYTHON" -m renquant_orchestrator.model_freshness_monitor --notify 2>&1 | tee -a "$TMP"
RC="${PIPESTATUS[0]}"

# --- 3. terminal marker, THEN publish. Both only after the process returned. ------
{
  echo "--- monitor exit=$RC (0 healthy | 1 warn | 2 escalate | 3 breach/unknown)"
  echo "=== model-freshness monitor end $(date '+%F %T %Z') ==="
} >>"$TMP" 2>&1

mv -f "$TMP" "$LOG" || { echo "could not publish evidence to $LOG" >&2; exit 5; }
trap - EXIT

exit "$RC"
