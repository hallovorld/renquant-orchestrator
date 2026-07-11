#!/usr/bin/env bash
# stops_liveness_pager.sh — software-stop registry liveness pager wrapper.
#
# S-FRAC stage-3 ops (#471 operator shortlist item 2). Scheduled by
# deploy/com.renquant.stops-liveness.plist (10-minute StartInterval). Invokes
# the EXECUTION-repo liveness checker
# (renquant_execution.software_stops_liveness — renquant-execution#29) which
# does the actual watchdog arithmetic against the PINNED runtime module
# (renquant_pipeline.software_stops — the same code the sell-only loop uses
# to stamp the heartbeat, so checker and stamper can never disagree).
#
# OWNERSHIP SPLIT (Codex review of this package's prior revision,
# 2026-07-11): the prior revision invoked a THIN umbrella script through
# the deprecated umbrella's own Python virtualenv, creating a new
# production dependency on that umbrella. That checker moved to
# renquant-execution (a proper broker/order-management runtime-monitoring
# module). This wrapper resolves the pinned renquant-execution /
# renquant-pipeline / renquant-common checkouts through the R-PIN Stage-1
# RUNTIME INVENTORY (~/.renquant/deploy/runtime-inventory.json, override
# RENQUANT_DEPLOY_STATE_ROOT) read via the orchestrator's own reader API
# (renquant_orchestrator.deployment_manifest.load_runtime_inventory — one
# reader implementation, never ad-hoc JSON parsing), and runs
# `python -m renquant_execution.software_stops_liveness` — never a
# hardcoded umbrella path or venv, and no dependency on the umbrella's
# pin lock file either: the inventory is the NEUTRAL per-host
# repo-name -> checkout-path map (used exactly as that — Stage 1 defines
# no pin-authority semantics, and this job consumes none).
#
#   renquant-pipeline    — registry data model + staleness arithmetic
#                          (software_stops.py) + decision-time arming task.
#                          Unchanged, not touched by this package.
#   renquant-execution   — the liveness CHECKER
#                          (software_stops_liveness.py, renquant-execution#29).
#   renquant-orchestrator (HERE) — pinned schedule + notification-consumer
#                          wrapper. Does not reimplement checker logic.
#
# Why a wrapper (and why the checker's own --ntfy-topic is NOT used):
#   The checker's builtin ntfy post is best-effort (a delivery failure only
#   prints to stderr). The wrapper owns paging via curl -f so a delivery
#   failure is DETECTABLE (exit 70) — and a checker CRASH (import error
#   after a pin move, pin-resolution failure, etc.) also pages instead of
#   dying silently, which is exactly the failure class #471 flagged.
#
# RUNTIME CONTRACT (same discipline as scripts/shadow_ab_daily.sh, Codex r2
# on #460): every python interpreter and data-root input is an EXPLICIT
# externally-supplied value; this script has NO default that points at the
# deprecated RenQuant umbrella (or at any sibling directory). The plist
# supplies the values as reviewed arming-time configuration; the script
# fails closed (hard abort, matching shadow_ab_daily.sh's own required-var
# checks) when one is missing.
#
# STILL-OPEN BLOCKER — data-root authority (Codex round-3 review,
# 2026-07-11): the round-2 rework above fixed CODE resolution (which
# checkouts run the checker), but RENQUANT_STOPS_PAGER_DATA_ROOT is STILL,
# as a matter of fact, configured to the deprecated umbrella in the
# committed plist — Codex correctly held that an explicit umbrella data
# root is a production dependency even when imports resolve through pins.
# This package does NOT fix that (the writer — the live sell-only loop —
# lives in the umbrella; migrating it is a separate, live-tree, R-PIN
# landing change, out of scope for an orchestrator-only PR). What this
# revision adds instead: renquant_orchestrator.software_stops_registry_contract
# defines the NEUTRAL runtime-state-root convention (mirrors
# deployment_manifest.deploy_state_root exactly) and a versioned
# registry-file envelope a migrated writer would stamp; this wrapper
# classifies the resolved data root against that neutral contract every
# run and prints a CLEARLY LABELED "WARNING: LEGACY/UNVERSIONED ..." line
# to stderr whenever it is NOT the neutral root (today, every run, since
# the writer migration has not landed) — see this package's progress doc,
# "BLOCKING FOLLOW-UP", for what remains. The check is informational only:
# it never changes the paging decision below.
#
# Required environment (supplied by the plist):
#   RENQUANT_STOPS_PAGER_PYTHON      interpreter to run the checker with
#                                    (must have the pinned renquant-execution
#                                    + renquant-pipeline + renquant-common
#                                    stack importable via the PYTHONPATH
#                                    this script constructs)
#   RENQUANT_STOPS_PAGER_DATA_ROOT   explicit runtime data root the
#                                    software-stop registry lives under
#                                    (passed straight through as
#                                    --data-root; today this is wherever
#                                    the live sell-only loop writes it —
#                                    migrating that anchor off the
#                                    umbrella is R-PIN territory, out of
#                                    scope here)
# Optional:
#   RENQUANT_STOPS_PAGER_BROKER        broker tag (default: alpaca)
#   RENQUANT_STOPS_PAGER_NTFY_BASE     ntfy base URL (default: https://ntfy.sh)
#   RENQUANT_STOPS_PAGER_NTFY_TOPIC    ntfy topic (default: renquant — the
#                                      LIVE ops topic, same as the live
#                                      sell-only loop's alerts)
#   RENQUANT_STOPS_PAGER_CHECKER_CMD   TEST-ONLY override: when set, this
#                                      whole command replaces the pin-resolved
#                                      "$PYTHON -m
#                                      renquant_execution.software_stops_liveness"
#                                      invocation (hermetic tests substitute a
#                                      fake checker so they never touch a
#                                      real lock file, git, or renquant_pipeline).
#
# Exit codes:
#   0   OK (no page needed)
#   1   STALE   — page delivered (checker exit propagated)
#   2   CORRUPT — page delivered (checker exit propagated)
#   70  page delivery FAILED (alarm or test-fire could not reach ntfy)
#   *   checker crashed (or pin resolution failed) with that code — ERROR
#       page delivered
#
# Test-fire mode (delivery + response drill, #471 shortlist item 2):
#   stops_liveness_pager.sh --test-fire STALE
# emits ONE clearly-marked synthetic page to the live ops topic and exits
# nonzero (70) on delivery failure, 0 on delivered. This measures ACTUAL
# delivery latency + operator response time as evidence for the stage-3
# sign-off decision — see doc/progress/2026-07-11-stops-liveness-pager-package.md
# for why the honest current envelope (~18-28min) does not itself satisfy
# the design's 15-minute target, and what happens after this drill.
set -uo pipefail

ORCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NTFY_BASE="${RENQUANT_STOPS_PAGER_NTFY_BASE:-https://ntfy.sh}"
# LIVE ops topic — same channel as the live sell-only loop's alerts
# (umbrella scripts/intraday_sell_104.sh NTFY_TOPIC="renquant").
NTFY_TOPIC="${RENQUANT_STOPS_PAGER_NTFY_TOPIC:-renquant}"
BROKER="${RENQUANT_STOPS_PAGER_BROKER:-alpaca}"
TITLE="RenQuant SOFTWARE-STOP watchdog"

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
end-to-end and measure the ACTUAL delivery latency + operator response \
time. NOTE: the current alarm envelope is ~18-28 minutes after the first \
missed pass, which does NOT meet the S-FRAC design's 15-minute target — \
this drill's measured numbers are evidence for the operator sign-off \
decision (tighten the arming-side max_staleness_minutes, or accept this \
envelope) BEFORE any stage-3 / #55 enablement decision. RECORD your \
response time."
    echo "test-fire: posting synthetic $kind page to $NTFY_BASE/$NTFY_TOPIC"
    if page "$TITLE [TEST-FIRE]" "$body"; then
        echo "test-fire: page DELIVERED at $(stamp) — record delivery latency + operator response time"
        exit 0
    fi
    echo "test-fire: PAGE DELIVERY FAILED to $NTFY_BASE/$NTFY_TOPIC" >&2
    exit 70
fi

if [ -n "${RENQUANT_STOPS_PAGER_CHECKER_CMD:-}" ]; then
    # TEST-ONLY escape hatch — see header doc. Production never sets this.
    out="$(eval "$RENQUANT_STOPS_PAGER_CHECKER_CMD" 2>&1)"
    code=$?
else
    PYTHON="${RENQUANT_STOPS_PAGER_PYTHON:?RENQUANT_STOPS_PAGER_PYTHON must be supplied (no default runtime — RUNTIME CONTRACT)}"
    DATA_ROOT="${RENQUANT_STOPS_PAGER_DATA_ROOT:?RENQUANT_STOPS_PAGER_DATA_ROOT must be supplied (explicit registry data root — RUNTIME CONTRACT)}"

    # Resolve the pinned renquant-execution / renquant-pipeline /
    # renquant-common checkouts through the R-PIN Stage-1 RUNTIME INVENTORY
    # (~/.renquant/deploy/runtime-inventory.json; RENQUANT_DEPLOY_STATE_ROOT
    # override honored by the reader itself) via the orchestrator's own
    # reader API — deployment_manifest.load_runtime_inventory validates the
    # schema and fail-closes on an unreadable/invalid inventory. The
    # inventory is the NEUTRAL per-host repo-name -> path map: no umbrella
    # lock file, no sibling-directory guessing. deployment_manifest.py is
    # stdlib-only, so this resolution step runs before any pinned
    # PYTHONPATH exists.
    export PYTHONPATH="$ORCH_DIR/src:${PYTHONPATH:-}"
    # NOTE: stdout carries ONLY the final ":"-joined roots line on success;
    # errors go to stderr so they never corrupt the PYTHONPATH we parse
    # below — they still surface in the launchd stderr log for debugging.
    pin_out="$("$PYTHON" - <<'PY'
import os
import sys
from pathlib import Path

from renquant_orchestrator.deployment_manifest import (
    deploy_state_root,
    load_runtime_inventory,
    state_root_paths,
)

inventory = load_runtime_inventory(state_root_paths(deploy_state_root())["inventory"])
repos = inventory["repos"]
# The full first-party import closure, all from pinned checkouts: the
# checker imports renquant_pipeline.software_stops, and the pipeline
# package __init__ pulls renquant_artifacts / renquant_base_data /
# renquant_model / renquant_common. Verified live 2026-07-11: with these
# on PYTHONPATH the checker runs green under the bare conda interpreter —
# no venv and no umbrella-venv editable installs required.
# (NOTE for editors: no apostrophes or backticks inside this heredoc —
# bash 3.2 command-substitution parsing treats them as quote openers.)
needed = (
    "renquant-common",
    "renquant-base-data",
    "renquant-artifacts",
    "renquant-model",
    "renquant-pipeline",
    "renquant-execution",
)
missing = [name for name in needed if name not in repos]
if missing:
    print(f"runtime inventory is missing repos: {missing}", file=sys.stderr)
    raise SystemExit(1)
absent = [
    name for name in needed if not (Path(repos[name]["path"]) / "src").is_dir()
]
if absent:
    print(f"inventory checkout src roots absent on disk: {absent}", file=sys.stderr)
    raise SystemExit(1)
# Guard against a stale pin: python -m with a missing module exits 1,
# which would masquerade as a STALE verdict downstream. Verified live
# 2026-07-11: the pinned renquant-execution checkout predates
# renquant-execution#29, so without this check the very first scheduled
# run would page a FALSE "STALE" instead of the honest resolution failure.
module_file = (
    Path(repos["renquant-execution"]["path"])
    / "src" / "renquant_execution" / "software_stops_liveness.py"
)
if not module_file.is_file():
    print(
        f"pinned renquant-execution checkout lacks the liveness checker "
        f"({module_file}) — pin not yet advanced past renquant-execution#29",
        file=sys.stderr,
    )
    raise SystemExit(1)

# ---- registry-root observability (Codex round-3 review of PR #481,
# 2026-07-11): CODE now resolves through pins, but RENQUANT_STOPS_PAGER_DATA_ROOT
# (below) is still an explicit, reviewed plist value naming wherever the live
# sell-only loop writes the registry file TODAY — which is still the
# deprecated umbrella. That is a real production dependency, not a harmless
# default, even though this script hardcodes none. This checks the resolved
# data root against the neutral runtime-state-root contract
# (renquant_orchestrator.software_stops_registry_contract — the READ-side
# half of the contract Codex required; the writer migration itself is a
# separate, out-of-scope, R-PIN landing change, see this ops packages
# progress doc, BLOCKING FOLLOW-UP section) and prints a CLEARLY LABELED
# warning to stderr when it is not neutral — informational only, never a
# gate: it must not change the paging decision below. This makes the
# current interim state OBSERVABLE on every run instead of silently
# accepted.
# (NOTE for editors: same bash-3.2-in-command-substitution rule as above —
# no apostrophes or backticks anywhere in this heredoc.)
data_root_env = os.environ.get("RENQUANT_STOPS_PAGER_DATA_ROOT")
if data_root_env:
    from renquant_orchestrator.software_stops_registry_contract import (
        classify_data_root,
    )

    root_verdict = classify_data_root(data_root_env)
    if not root_verdict.neutral:
        print(f"WARNING: {root_verdict.message}", file=sys.stderr)

print(":".join(str(Path(repos[name]["path"]) / "src") for name in needed))
PY
)"
    pin_rc=$?
    if [ "$pin_rc" -ne 0 ]; then
        out="PIN RESOLUTION FAILED (exit=$pin_rc) — runtime-inventory resolution; see launchd stderr log for the missing repo/inventory detail"
        code=90
    else
        export PYTHONPATH="$pin_out:$ORCH_DIR/src:${PYTHONPATH:-}"
        out="$("$PYTHON" -m renquant_execution.software_stops_liveness \
            --data-root "$DATA_ROOT" --broker "$BROKER" 2>&1)"
        code=$?
    fi
fi
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
        # Checker crashed (import error, bad env, pin-resolution failure,
        # ...): registry state is UNKNOWN, which is itself a liveness
        # failure — page, don't die dark.
        body="ERROR: software-stop liveness checker crashed (exit=$code) at $(stamp). \
Registry state UNKNOWN — treat as a liveness failure and investigate. \
Output: $out"
        if page "$TITLE" "$body"; then
            exit "$code"
        fi
        echo "PAGE DELIVERY FAILED (checker exit=$code) to $NTFY_BASE/$NTFY_TOPIC" >&2
        exit 70
        ;;
esac
