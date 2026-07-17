#!/usr/bin/env bash
# RQ104 dawn readonly-funnel preflight (GOAL-5 AC5, D2).
# Runs the full inference funnel read-only ~8h before the 13:55 PT daily
# and alerts on the known daily-killer classes. NEVER places orders
# (readonly-alpaca broker) and never mutates live state.
set -uo pipefail

REPO_DIR="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
PYTHON="$REPO_DIR/.venv/bin/python"
OPS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$REPO_DIR/logs/rq104"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/dawn_funnel_preflight_$(date +%F).log"

set -a; source "$REPO_DIR/.env" 2>/dev/null; set +a
source "$REPO_DIR/scripts/subrepo_env.sh"
renquant_load_subrepo_env "$REPO_DIR"
SUBREPO_ROOT="$(renquant_subrepo_root "$REPO_DIR" "$(dirname "$REPO_DIR")")"
export RENQUANT_SUBREPO_ROOT="$SUBREPO_ROOT"
export PYTHONPATH="$(renquant_subrepo_pythonpath "$SUBREPO_ROOT" renquant-orchestrator renquant-common renquant-base-data renquant-artifacts renquant-model renquant-pipeline renquant-execution renquant-strategy-104 renquant-backtesting):${PYTHONPATH:-}"

"$PYTHON" -m live.runner --strategy renquant_104 --broker readonly-alpaca \
  --strategy-config-path "$REPO_DIR/.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json" \
  --once > "$LOG" 2>&1
RUNNER_RC=$?
echo "runner rc=$RUNNER_RC (analyzer owns the verdict)" >> "$LOG"

exec "$PYTHON" "$OPS_DIR/dawn_funnel_analyze.py" --log "$LOG"
