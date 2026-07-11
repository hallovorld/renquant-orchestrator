#!/usr/bin/env bash
# stops_liveness_pager.sh — software-stop registry liveness pager wrapper.
#
# S-FRAC stage-3 ops (#471 operator shortlist item 2). Scheduled by
# deploy/com.renquant.stops-liveness.plist (10-minute StartInterval); the
# umbrella checker (RenQuant/scripts/check_software_stops_liveness.py) does
# the actual watchdog arithmetic against the PINNED runtime module
# (renquant_pipeline.software_stops — the same code the sell-only loop uses
# to stamp the heartbeat, so checker and stamper can never disagree).
#
# Why a wrapper (and why the checker's own --ntfy-topic is NOT used):
#   1. rq105 ops convention (tests/test_rq105_ops_wrappers.py): plists call a
#      shell wrapper so PYTHONPATH is set up consistently — the checker
#      imports the pinned renquant_pipeline, which is NOT installed in the
#      umbrella venv (verified 2026-07-11: bare invocation ModuleNotFoundError).
#   2. The checker's builtin _post_ntfy is best-effort (a delivery failure
#      only prints to stderr). The wrapper owns paging via curl -f so a
#      delivery failure is DETECTABLE (exit 70) — and a checker CRASH
#      (import error after a pin move, etc.) also pages instead of dying
#      silently, which is exactly the failure class #471 flagged.
#
# Exit codes:
#   0   OK (no page needed)
#   1   STALE   — page delivered (checker exit propagated)
#   2   CORRUPT — page delivered (checker exit propagated)
#   70  page delivery FAILED (alarm or test-fire could not reach ntfy)
#   *   checker crashed with that code — ERROR page delivered
#
# Test-fire mode (SLA drill, #471 shortlist item 2 / design §3.4):
#   stops_liveness_pager.sh --test-fire STALE
# emits ONE clearly-marked synthetic page to the live ops topic and exits
# nonzero (70) on delivery failure, 0 on delivered. Record the operator
# response time against the §3.4 SLA (page <=15m of missed pass; runbook
# response <=60m of page).
#
# Every default below is env-overridable (RENQUANT_STOPS_PAGER_*) so the
# hermetic tests can substitute a fake checker and a local ntfy recorder.
set -uo pipefail

RQ_ROOT="${RENQUANT_STOPS_PAGER_RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
PYTHON="${RENQUANT_STOPS_PAGER_PYTHON:-$RQ_ROOT/.venv/bin/python}"
CHECKER="${RENQUANT_STOPS_PAGER_CHECKER:-$RQ_ROOT/scripts/check_software_stops_liveness.py}"
SUBREPO_RT="${RENQUANT_STOPS_PAGER_SUBREPO_ROOT:-$RQ_ROOT/.subrepo_runtime/repos}"
NTFY_BASE="${RENQUANT_STOPS_PAGER_NTFY_BASE:-https://ntfy.sh}"
# LIVE ops topic — same channel as the live sell-only loop's alerts
# (umbrella scripts/intraday_sell_104.sh NTFY_TOPIC="renquant").
NTFY_TOPIC="${RENQUANT_STOPS_PAGER_NTFY_TOPIC:-renquant}"
BROKER="${RENQUANT_STOPS_PAGER_BROKER:-alpaca}"
TITLE="RenQuant SOFTWARE-STOP watchdog"

# Pinned runtime modules: the checker imports renquant_pipeline (+ the market
# calendar from renquant_common), neither installed in the umbrella venv.
export PYTHONPATH="$SUBREPO_RT/renquant-pipeline/src:$SUBREPO_RT/renquant-common/src:${PYTHONPATH:-}"

page() { # $1 = title, $2 = body; returns curl's status (nonzero = not delivered)
    curl -fsS --max-time 15 \
        -H "Title: $1" \
        -H "Priority: urgent" \
        -H "Tags: rotating_light" \
        -d "$2" \
        "$NTFY_BASE/$NTFY_TOPIC" >/dev/null
}

stamp() { date "+%Y-%m-%dT%H:%M:%S%z"; }

if [ "${1:-}" = "--test-fire" ]; then
    kind="${2:-STALE}"
    body="[TEST-FIRE $kind] $(stamp) synthetic software-stop pager drill — \
NOT a real alarm, no position is unprotected. Purpose: prove the page path \
end-to-end and measure operator response vs the S-FRAC design §3.4 SLA \
(page <=15m of a missed sell-only pass; runbook response <=60m of the page). \
RECORD your response time."
    echo "test-fire: posting synthetic $kind page to $NTFY_BASE/$NTFY_TOPIC"
    if page "$TITLE [TEST-FIRE]" "$body"; then
        echo "test-fire: page DELIVERED at $(stamp) — record operator response time vs the 15m/60m SLA"
        exit 0
    fi
    echo "test-fire: PAGE DELIVERY FAILED to $NTFY_BASE/$NTFY_TOPIC" >&2
    exit 70
fi

out="$("$PYTHON" "$CHECKER" --broker "$BROKER" 2>&1)"
code=$?
echo "$(stamp) checker exit=$code: $out"

case "$code" in
    0)
        exit 0
        ;;
    1|2)
        # STALE / CORRUPT: the checker's message is the page body (it already
        # carries the registry path, heartbeat age, budget, and runbook line).
        if page "$TITLE" "$out"; then
            exit "$code"
        fi
        echo "PAGE DELIVERY FAILED (checker exit=$code) to $NTFY_BASE/$NTFY_TOPIC" >&2
        exit 70
        ;;
    *)
        # Checker crashed (import error, bad env, ...): registry state is
        # UNKNOWN, which is itself a liveness failure — page, don't die dark.
        body="ERROR: software-stop liveness checker crashed (exit=$code) at $(stamp). \
Registry state UNKNOWN — treat as a liveness failure and run the §3.4 runbook. \
Output: $out"
        if page "$TITLE" "$body"; then
            exit "$code"
        fi
        echo "PAGE DELIVERY FAILED (checker exit=$code) to $NTFY_BASE/$NTFY_TOPIC" >&2
        exit 70
        ;;
esac
