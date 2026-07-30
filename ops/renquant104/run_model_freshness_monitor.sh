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
set -uo pipefail

REPO_DIR="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
PYTHON="$REPO_DIR/.venv/bin/python"
LOG_DIR="$REPO_DIR/logs/rq104"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/model_freshness_$(date +%F).log"

set -a; source "$REPO_DIR/.env" 2>/dev/null; set +a
source "$REPO_DIR/scripts/subrepo_env.sh"
renquant_load_subrepo_env "$REPO_DIR"
SUBREPO_ROOT="$(renquant_subrepo_root "$REPO_DIR" "$(dirname "$REPO_DIR")")"
export RENQUANT_SUBREPO_ROOT="$SUBREPO_ROOT"
export PYTHONPATH="$(renquant_subrepo_pythonpath "$SUBREPO_ROOT" renquant-orchestrator renquant-common renquant-base-data renquant-artifacts renquant-model renquant-pipeline renquant-execution renquant-strategy-104 renquant-backtesting):${PYTHONPATH:-}"

{
  echo "=== model-freshness monitor start $(date '+%F %T %Z') ==="
  echo "--- observe-only: reads artifacts + notifies; promotes/fits/retrains nothing"
} >>"$LOG" 2>&1

# The exit code is the payload, so it must NOT be swallowed by the pipe into tee.
# `set -o pipefail` is on, but tee is the LAST element, so ${PIPESTATUS[0]} is the
# only faithful read of the monitor's own status.
"$PYTHON" -m renquant_orchestrator.model_freshness_monitor --notify 2>&1 | tee -a "$LOG"
RC="${PIPESTATUS[0]}"

{
  echo "--- monitor exit=$RC (0 healthy | 1 warn | 2 escalate | 3 breach/unknown)"
  echo "=== model-freshness monitor end $(date '+%F %T %Z') ==="
} >>"$LOG" 2>&1

exit "$RC"
