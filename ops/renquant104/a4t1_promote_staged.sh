#!/usr/bin/env bash
# a4t1_promote_staged.sh — the ONLY production path that consumes the A4-T1
# candidate exception (RFC#210 A4-T1, run 20260831T141820Z).
#
# Called by the umbrella scripts/weekly_wf_promote.sh --promote-staged branch
# IN PLACE OF `python -m renquant_backtesting.wf_gate.freshness_fallback
# --prod ... --staging ... --stamp` (which, since renquant-backtesting#128,
# exits 1 for the candidate exception: the direct CLI has no ledger and must
# not promote it). identify -> validate against the committed authorization
# record -> atomic consume -> stamp all happen inside
# `renquant_orchestrator a4t1-promote`; this wrapper validates arguments,
# records the JSON verdict next to the other promote logs, and propagates the
# exit code: 0 = PROMOTED (the caller may pair-promote), anything else =
# production unchanged.
#
#   usage: a4t1_promote_staged.sh <RUN_ID> <ACTIVE_ART> <STAGING_ART>
#   env:   PYTHON   (default /Users/renhao/git/github/RenQuant/.venv/bin/python)
#          LOG_DIR  (default $PWD/logs/weekly_wf_promote)
#          RQ_A4T1_AS_OF  TEST SEAM ONLY (YYYY-MM-DD): forwarded as --as-of.
#                   Unset in production, where the CLI resolves the wall clock
#                   and the authorization record's temporal_bounds decide. It
#                   exists because the end-to-end test drives THIS script, and
#                   a wall-clock exception window makes such a test pass until
#                   the window closes and fail every day after — which is what
#                   happened on 2026-09-08, one day past the 09-07 bound, on
#                   every orchestrator PR including doc-only ones.
#          PYTHONPATH must resolve renquant_orchestrator AND the pinned
#          renquant_backtesting (the umbrella exports it from .subrepo_runtime).
set -euo pipefail

usage() {
    echo "usage: $0 <RUN_ID> <ACTIVE_ART> <STAGING_ART>   (RUN_ID = YYYYMMDDTHHMMSSZ)" >&2
    exit 2
}
[ $# -eq 3 ] || usage
RUN_ID="$1"; ACTIVE_ART="$2"; STAGING_ART="$3"

case "$RUN_ID" in
    [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z) ;;
    *) echo "a4t1-promote REFUSED: RUN_ID must match YYYYMMDDTHHMMSSZ exactly; got '$RUN_ID'" >&2; exit 2 ;;
esac
[ -f "$ACTIVE_ART" ] || { echo "a4t1-promote REFUSED: active artifact not found: $ACTIVE_ART" >&2; exit 2; }
[ -f "$STAGING_ART" ] || { echo "a4t1-promote REFUSED: staging artifact not found: $STAGING_ART" >&2; exit 2; }
case "$STAGING_ART" in
    *"weekly_${RUN_ID}.staging.json") ;;
    *) echo "a4t1-promote REFUSED: staging artifact does not carry RUN_ID ${RUN_ID}: $STAGING_ART" >&2; exit 2 ;;
esac

PYTHON="${PYTHON:-/Users/renhao/git/github/RenQuant/.venv/bin/python}"
LOG_DIR="${LOG_DIR:-$PWD/logs/weekly_wf_promote}"
mkdir -p "$LOG_DIR"
OUT="$LOG_DIR/${RUN_ID}.a4t1_promote.json"

AS_OF_ARGS=()
if [ -n "${RQ_A4T1_AS_OF:-}" ]; then
    case "$RQ_A4T1_AS_OF" in
        [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) AS_OF_ARGS=(--as-of "$RQ_A4T1_AS_OF") ;;
        *) echo "a4t1-promote REFUSED: RQ_A4T1_AS_OF must be YYYY-MM-DD; got '$RQ_A4T1_AS_OF'" >&2; exit 2 ;;
    esac
fi

set +e
"$PYTHON" -m renquant_orchestrator a4t1-promote --prod "$ACTIVE_ART" --staging "$STAGING_ART" \
    ${AS_OF_ARGS[@]+"${AS_OF_ARGS[@]}"} | tee "$OUT"
RC=${PIPESTATUS[0]}
set -e
echo "a4t1-promote: exit $RC (verdict recorded at $OUT)" >&2
exit "$RC"
