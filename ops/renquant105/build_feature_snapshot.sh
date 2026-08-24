#!/bin/bash
# rq105 S3-P2: emit today's feature_snapshot_<date>.json from the served matrix.
#
# The bridge from PersistServedMatrixTask's artifact (orch#703) to the
# FeatureSnapshot contract run_shadow_serving.sh requires. Exit codes:
#   0  snapshot written
#   3  fail-closed provenance refusal (no/ambiguous/stale source) — the caller
#      logs and skips; producing nothing is CORRECT when provenance fails.
set -uo pipefail
RQ_ROOT="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
ORCH_SRC="$(cd "$(dirname "$0")/../.." && pwd)/src"
PY="${RQ105_PYTHON:-$RQ_ROOT/.venv/bin/python}"
SERVED="$RQ_ROOT/backtesting/renquant_104/logs/served_matrix"
OUT="$RQ_ROOT/data/rq105"
if PYTHONPATH="$ORCH_SRC:${PYTHONPATH:-}" "$PY" -m renquant_orchestrator.feature_snapshot_producer \
    --served-matrix-root "$SERVED" --out-dir "$OUT" "$@"; then
  exit 0
else
  exit 3
fi
