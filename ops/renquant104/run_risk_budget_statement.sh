#!/bin/bash
# rq104: monthly risk-budget statement (107 sprint D3). OBSERVE-ONLY.
# Budgets: DD 15% HARD (G* bar) / beta 0.6 planning (RS-1) / per-name
# concentration per regime cap / sleeve DD sub-budget (#157). Read-only:
# runs DB opened mode=ro; strategy config, sleeve log and ohlcv only read.
# Exit codes from the module: 0 ok / 2 WARN (>80% of any budget) /
# 1 CRITICAL (>=100%). The wrapper ntfy-alerts on WARN/CRITICAL and on a
# crash that never reached a verdict (a crashed monitor must not fail silent).
set -u
RQ_ROOT="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
RQ104_ORCH_ROOT="${RQ104_ORCH_ROOT:-/Users/renhao/git/github/renquant-orchestrator-run}"
OUT_DIR="${RISK_BUDGET_OUT_DIR:-$HOME/renquant-data/research/risk_budget}"
LOG_DIR="$RQ_ROOT/logs/rq104"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d)"
LOG="$LOG_DIR/risk_budget_$TS.log"

PY="$RQ_ROOT/.venv/bin/python"
export PYTHONPATH="$RQ104_ORCH_ROOT/src"
OUT=$("$PY" -m renquant_orchestrator.risk_budget.report --out-dir "$OUT_DIR" 2>&1)
RC=$?
{
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) rc=$RC ==="
  echo "$OUT"
} >> "$LOG"

notify() {
  # Canonical sender (campaign B6): topic/.env resolution + RENQUANT_NO_NOTIFY live there.
  . "$RQ_ROOT/scripts/notify.sh" 2>/dev/null || true
  rq_notify "$1" "$2" || true
}

STATUS_LINE=$(printf '%s' "$OUT" | grep "risk_budget_statement:" | head -1)
if [ -z "$STATUS_LINE" ]; then
  # crashed before a verdict — never fail silent
  notify "rq104 risk-budget statement CRASHED rc=$RC ($TS)" \
    "see logs/rq104/risk_budget_$TS.log"
elif [ $RC -eq 1 ]; then
  notify "rq104 risk-budget CRITICAL ($TS)" "$STATUS_LINE"
elif [ $RC -eq 2 ]; then
  notify "rq104 risk-budget WARN ($TS)" "$STATUS_LINE"
fi
exit $RC
