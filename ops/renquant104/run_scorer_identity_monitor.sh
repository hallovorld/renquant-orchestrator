#!/bin/bash
# rq104: run-over-run scorer-identity diff alarm (#274 monitoring gap).
# Diffs the stamped scorer identity (panel artifact sha + trained_date +
# booster content hash, calibrator, shadow lanes) of consecutive canonical run
# bundles; an identity change with NO recorded promote/rollback event is a
# CRITICAL silent model swap (the 2026-06-26 class of event). Read-only:
# runs DB opened mode=ro, artifacts only read and hashed.
set -u
RQ_ROOT="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
RQ104_ORCH_ROOT="${RQ104_ORCH_ROOT:-/Users/renhao/git/github/renquant-orchestrator-run}"
LOG_DIR="$RQ_ROOT/logs/rq104"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d)"
LOG="$LOG_DIR/scorer_identity_$TS.log"

PY="$RQ_ROOT/.venv/bin/python"
export PYTHONPATH="$RQ104_ORCH_ROOT/src"
OUT=$("$PY" -m renquant_orchestrator.scorer_identity_monitor \
  --repo-root "$RQ_ROOT" \
  --notify 2>&1)
RC=$?
{
  echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) rc=$RC ==="
  echo "$OUT"
} >> "$LOG"

# The module posts its own CRITICAL/WARN ntfy alerts (behind --notify). The
# wrapper only alerts when the module CRASHED before reaching its verdict
# (no "scorer_identity_check:" status line) — a crashed monitor must never
# fail silent (that is the exact failure mode this alarm exists to close).
if [ $RC -ne 0 ] && ! printf '%s' "$OUT" | grep -q "scorer_identity_check:"; then
  source "$RQ_ROOT/.env" 2>/dev/null || true
  [ -n "${NTFY_TOPIC:-}" ] && curl -s -H "Title: rq104 scorer-identity monitor CRASHED rc=$RC ($TS)" \
    -d "see logs/rq104/scorer_identity_$TS.log" "ntfy.sh/$NTFY_TOPIC" >/dev/null
fi
exit $RC
