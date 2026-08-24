#!/bin/bash
# rq105 S3-P2: emit today's feature_snapshot_<date>.json from the served matrix.
#
# The bridge from PersistServedMatrixTask's artifact (orch#703) to the
# FeatureSnapshot contract run_shadow_serving.sh requires. Exit codes:
#   0  snapshot written
#   3  fail-closed PROVENANCE REFUSAL (absent / ambiguous / stale / internally
#      inconsistent source) — the caller logs and skips; producing nothing is
#      CORRECT when provenance fails.
#   other nonzero  UNEXPECTED failure (import, decoder, write, bug). NOT
#      skippable: the caller must not read it as a normal missing input.
set -uo pipefail
RQ_ROOT="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
ORCH_SRC="$(cd "$(dirname "$0")/../.." && pwd)/src"
PY="${RQ105_PYTHON:-$RQ_ROOT/.venv/bin/python}"
SERVED="$RQ_ROOT/backtesting/renquant_104/logs/served_matrix"
OUT="$RQ_ROOT/data/rq105"
# PASS THE CODE THROUGH. The previous form was `if …; then exit 0; else exit 3`,
# which mapped EVERY nonzero — import errors, parquet decoder failures, write
# failures, programming errors — onto 3, the code documented as an expected
# provenance refusal. S3-P3 would then treat implementation breakage as "no
# input today" and skip quietly. The module now exits 3 for a refusal and
# something else for anything unexpected; this must not flatten that again
# (codex review 2026-08-24).
PYTHONPATH="$ORCH_SRC:${PYTHONPATH:-}" "$PY" -m renquant_orchestrator.feature_snapshot_producer \
    --served-matrix-root "$SERVED" --out-dir "$OUT" "$@"
rc=$?
if [ "$rc" -ne 0 ] && [ "$rc" -ne 3 ]; then
  echo "build_feature_snapshot: UNEXPECTED failure (rc=$rc) — NOT a provenance" \
       "refusal; do not treat this as a normal missing input" >&2
fi
exit "$rc"
