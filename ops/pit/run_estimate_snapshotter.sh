#!/bin/zsh
# PIT N2: daily forward snapshot of FMP analyst estimates/consensus/targets
# (base-data #27 collector; #231 N2 — TIME-IRREVERSIBLE accrual; #205 design).
# Writes ONLY the dedicated data/estimate_snapshots/<date>/ path (never canonical).
# Runs from a PINNED base-data run checkout, never a working tree.
set -u
RQ_ROOT="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
BD_RUN_ROOT="${BD_RUN_ROOT:-/Users/renhao/git/github/renquant-base-data-run}"
LOG_DIR="$RQ_ROOT/logs/pit_snapshots"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d)"
export PYTHONPATH="$BD_RUN_ROOT/src"
"$RQ_ROOT/.venv/bin/python" -m renquant_base_data.fmp_estimate_revisions \
  --env "$RQ_ROOT/.env" \
  --out "$RQ_ROOT/data/estimate_snapshots" \
  >> "$LOG_DIR/estimate_snapshot_$TS.log" 2>&1
RC=$?
if [ $RC -ne 0 ]; then
  source "$RQ_ROOT/.env" 2>/dev/null || true
  [ -n "${NTFY_TOPIC:-}" ] && curl -s -H "Title: PIT estimate snapshot FAILED rc=$RC ($TS)" \
    -d "see logs/pit_snapshots/estimate_snapshot_$TS.log — every missed day is UNRECOVERABLE" \
    "ntfy.sh/$NTFY_TOPIC" >/dev/null
fi
exit $RC
