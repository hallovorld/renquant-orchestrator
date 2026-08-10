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

# ONE runtime root for everything below: the pin check, the strategy config, and
# the bridge (via the exported RENQUANT_SUBREPO_ROOT) must all bind the SAME
# resolved root. renquant_subrepo_root honors RENQUANT_SUBREPO_ROOT / an assembly
# dir; hard-coding `.subrepo_runtime/repos` here would let the check green-light
# one root while the bridge imports another (codex #968 r1). Fail closed if the
# pinned strategy config is not present under that resolved root.
STRATEGY_CONFIG="$(renquant_strategy_config "$SUBREPO_ROOT")" || {
  echo "ABORT: strategy_config.json not found under resolved SUBREPO_ROOT=$SUBREPO_ROOT — refusing to probe."
  exit 1
}

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

# PIN IDENTITY (codex #968 r1): read-only, FAIL-CLOSED. Switching to the bridge
# fixes the module namespace, but the monitor must also preview the SAME pinned
# runtime the 13:55 order path aligns to — daily_104.sh sources
# preflight_pin_align.sh (subrepo_assemble --sync --dry-run) before its bridge.
# A stale-but-importable runtime here would recreate the monitor-vs-order
# divergence at the PIN level. This verifies the SAME resolved SUBREPO_ROOT the
# bridge imports from matches subrepos.lock.json and emits a receipt, but NEVER
# checks out / mutates / deploys (a monitor must not deploy) — it reuses
# subrepo_assemble's own pin predicates.
PIN_RECEIPT="$LOG_DIR/dawn_pin_identity_$(date +%F).json"
if ! "$PYTHON" "$OPS_DIR/dawn_pin_identity_check.py" \
      --repo-dir "$REPO_DIR" \
      --runtime-root "$SUBREPO_ROOT" \
      --lock "$REPO_DIR/subrepos.lock.json" \
      --entrypoint dawn_funnel_preflight \
      --receipt-out "$PIN_RECEIPT"; then
  echo "ABORT: dawn preflight runtime pins not aligned to subrepos.lock.json (receipt: $PIN_RECEIPT) — the monitor would preview a runtime DIFFERENT from the 13:55 order path; refusing to probe."
  exit 1
fi

# --preflight (NOT --once): drive the funnel to a decision line with zero
# persistence / order / promotion / notification side effects. readonly-alpaca
# still gives real account/holdings reads for a faithful probe.
"$PYTHON" -m renquant_orchestrator daily-bridge --repo-dir "$REPO_DIR" \
  --strategy renquant_104 --broker readonly-alpaca \
  --strategy-config-path "$STRATEGY_CONFIG" \
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
