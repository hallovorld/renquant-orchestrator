#!/usr/bin/env bash
# RQ104 dawn readonly-funnel preflight (GOAL-5 AC5, D2; PR #565 codex CR).
# Runs the full inference funnel ~8h before the 13:55 PT daily and alerts on the
# known daily-killer classes. Uses live.runner --preflight (dry-run): the runner
# drives the funnel to a decision line but places NO orders, persists NO DB/state,
# promotes nothing, and sends NO notification, then emits a machine-readable
# `preflight_attestation:` line. `--broker readonly-alpaca` alone only constrains
# BROKER writes — --once could STILL open/create the runs DB, allocate a run id,
# persist live_state, run the score-distribution DB writer, and ntfy. --preflight
# is the true read-only probe. This guard FAILS CLOSED unless the runner attests
# no-write/no-notify AND reached a decision.
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

# Run through the SAME multirepo bridge the real order run uses
# (daily_104.sh:410 `-m renquant_orchestrator daily-bridge`), NOT `-m live.runner`
# directly. WHY (2026-08-10): the direct `-m live.runner` path resolves the
# top-level `kernel` package to the umbrella-VENDORED June-vintage kernel
# (RenQuant/backtesting/renquant_104/kernel/) which predates RFC#210 and hard-
# refuses a fresh governance-served passed=False artifact — so this readonly
# probe emitted a P-WF-GATE HARD refuse that the actual order path (which routes
# kernel.* through the PINNED subrepos and honors RFC#210) does NOT produce. The
# probe is only faithful if it previews the gate the order run will actually
# evaluate. The bridge bootstraps the pinned subrepos, aliases the lifted
# kernel.* modules to the sibling subrepos, then delegates to live.runner.main()
# with the same argv (so `live` still resolves; cwd=umbrella preserved below).
# Instant rollback: replace the bridge prefix with `-m live.runner`.
cd "$REPO_DIR"

# --preflight (NOT --once): drive the funnel to a decision line with zero
# persistence / order / promotion / notification side effects. readonly-alpaca
# still gives real account/holdings reads for a faithful probe.
"$PYTHON" -m renquant_orchestrator daily-bridge --repo-dir "$REPO_DIR" \
  --strategy renquant_104 --broker readonly-alpaca \
  --strategy-config-path "$REPO_DIR/.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json" \
  --preflight > "$LOG" 2>&1
RUNNER_RC=$?
echo "runner rc=$RUNNER_RC (attestation + analyzer own the verdict)" >> "$LOG"

# FAIL CLOSED unless the runner attested a clean no-write/no-notify probe that
# reached a decision (preflight_attestation persisted:false notified:false
# reached_decision:true). A missing/negative attestation (crash, hang, truncated
# run, or any side effect reached) alerts and exits non-zero here — the probe is
# not trustworthy, so the analyzer's content verdict below is not even reached.
if ! "$PYTHON" "$OPS_DIR/dawn_preflight_attest.py" --log "$LOG"; then
  exit 1
fi

exec "$PYTHON" "$OPS_DIR/dawn_funnel_analyze.py" --log "$LOG"
