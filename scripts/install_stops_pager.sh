#!/usr/bin/env bash
# install_stops_pager.sh — echo-first installer for the software-stop
# liveness pager (deploy/com.renquant.stops-liveness.plist).
#
# S-FRAC stage-3 ops (#471 operator shortlist item 2). NOTHING here runs at
# merge time: install/uninstall are DRY-RUN by default and print the exact
# commands they would run; add --apply to execute. Installing is a
# separately-granted operator landing step (landing-actions ask-first).
#
# Usage:
#   scripts/install_stops_pager.sh install [--apply]     # copy plist + bootstrap launchd job
#   scripts/install_stops_pager.sh uninstall [--apply]   # bootout + remove plist
#   scripts/install_stops_pager.sh status                # read-only: plist sync + job state + last log
#   scripts/install_stops_pager.sh test-fire [STALE|CORRUPT]
#       one synthetic page to the LIVE ops topic (SLA drill; exits nonzero on
#       delivery failure). Runs immediately — it is itself the landing demo.
#
# Idempotent: install re-copies the plist only when it differs and always
# re-bootstraps (bootout || true first), so re-running converges. All paths
# and the launchctl binary are env-overridable (RENQUANT_STOPS_PAGER_*) for
# the hermetic tests.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.renquant.stops-liveness"
PLIST_SRC="$REPO_ROOT/deploy/$LABEL.plist"
WRAPPER="$REPO_ROOT/scripts/stops_liveness_pager.sh"
AGENT_DIR="${RENQUANT_STOPS_PAGER_AGENT_DIR:-$HOME/Library/LaunchAgents}"
PLIST_DST="$AGENT_DIR/$LABEL.plist"
LAUNCHCTL="${RENQUANT_STOPS_PAGER_LAUNCHCTL:-launchctl}"
# Neutral, orchestrator-owned operational root — sibling to R-PIN's
# ~/.renquant/deploy/ neutral machine-state root (doc/design/
# 2026-07-11-deployment-pin-authority-migration.md §5.2) — NOT the
# umbrella's logs/ tree (Codex review of this package's prior revision,
# 2026-07-11: no new umbrella log path).
LOG_DIR="${RENQUANT_STOPS_PAGER_LOG_DIR:-$HOME/.renquant/ops/stops-liveness}"
GUI_DOMAIN="gui/$(id -u)"

CMD="${1:-}"
APPLY=false
for arg in "$@"; do
    [ "$arg" = "--apply" ] && APPLY=true
done

run() {
    # echo-first: always print the exact command; execute only under --apply.
    echo "+ $*"
    if $APPLY; then
        "$@"
    fi
}

require_sources() {
    if [ ! -f "$PLIST_SRC" ]; then
        echo "ERROR: plist source missing: $PLIST_SRC" >&2
        exit 2
    fi
    if [ ! -f "$WRAPPER" ]; then
        echo "ERROR: pager wrapper missing: $WRAPPER" >&2
        exit 2
    fi
}

# --- fail-closed pre-install registry guard -----------------------------------------
# Codex CHANGES_REQUESTED on PR #481 (2026-07-12T04:32:57Z): "darkness is not
# a runtime safety control ... an operator can run the install command before
# the writer migration and get a false critical alarm." This guard refuses
# `install --apply` unless a versioned, VALID registry file exists at the
# SAME path (data root + broker) the armed pager will read, verified through
# the REAL producing-repo validators (never a re-derived schema — see
# software_stops_registry_contract.py's round-5 correction note).

resolve_pager_env_var() {
    # $1 = env var name. Prefer an already-set environment value (operator
    # override / hermetic test injection); otherwise parse it out of the
    # committed plist's EnvironmentVariables dict — the exact arming-time
    # configuration `install --apply` is about to bootstrap. Prints the
    # resolved value and returns 0, or prints nothing and returns 1.
    local var_name="$1"
    local env_val
    env_val="${!var_name:-}"
    if [ -n "$env_val" ]; then
        printf '%s\n' "$env_val"
        return 0
    fi
    python3 - "$PLIST_SRC" "$var_name" <<'PY'
import plistlib
import sys

plist_path, var_name = sys.argv[1], sys.argv[2]
try:
    with open(plist_path, "rb") as fh:
        plist = plistlib.load(fh)
    value = plist.get("EnvironmentVariables", {}).get(var_name)
except Exception:
    value = None
if not value:
    sys.exit(1)
print(value)
PY
}

guard_registry_before_apply() {
    # Resolve the SAME interpreter + data root the plist is about to arm,
    # resolve the pinned renquant-pipeline / renquant-execution checkouts
    # through the R-PIN Stage-1 runtime inventory (same approach as
    # scripts/stops_liveness_pager.sh's own pin resolution), and refuse to
    # proceed unless a valid registry file already exists there. Returns
    # nonzero (never raises) on any failure; all diagnostics go to stderr.
    local data_root python_bin broker
    if ! data_root="$(resolve_pager_env_var RENQUANT_STOPS_PAGER_DATA_ROOT)"; then
        echo "GUARD FAIL: cannot resolve RENQUANT_STOPS_PAGER_DATA_ROOT (not set in env, not found in $PLIST_SRC EnvironmentVariables)" >&2
        return 1
    fi
    if ! python_bin="$(resolve_pager_env_var RENQUANT_STOPS_PAGER_PYTHON)"; then
        echo "GUARD FAIL: cannot resolve RENQUANT_STOPS_PAGER_PYTHON (not set in env, not found in $PLIST_SRC EnvironmentVariables)" >&2
        return 1
    fi
    broker="${RENQUANT_STOPS_PAGER_BROKER:-alpaca}"

    echo "guard: verifying a valid software-stop registry exists at data_root=$data_root broker=$broker before arming..." >&2
    local guard_out guard_rc
    guard_out="$(RENQUANT_STOPS_PAGER_DATA_ROOT="$data_root" \
        RENQUANT_STOPS_PAGER_BROKER="$broker" \
        PYTHONPATH="$REPO_ROOT/src:${PYTHONPATH:-}" \
        "$python_bin" - <<'PY' 2>&1
import json
import os
import sys
from pathlib import Path

from renquant_orchestrator.deployment_manifest import (
    deploy_state_root,
    load_runtime_inventory,
    state_root_paths,
)

data_root = os.environ["RENQUANT_STOPS_PAGER_DATA_ROOT"]
broker = os.environ.get("RENQUANT_STOPS_PAGER_BROKER", "alpaca")

try:
    inventory = load_runtime_inventory(state_root_paths(deploy_state_root())["inventory"])
except Exception as exc:
    print(
        f"GUARD FAIL: could not load the R-PIN runtime inventory "
        f"({type(exc).__name__}: {exc})",
        file=sys.stderr,
    )
    raise SystemExit(1)

repos = inventory["repos"]
# Same first-party import closure the wrapper resolves (renquant_execution
# imports renquant_pipeline.software_stops, whose package __init__ pulls in
# common/base-data/artifacts/model) — see stops_liveness_pager.sh.
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
    print(f"GUARD FAIL: runtime inventory is missing repos: {missing}", file=sys.stderr)
    raise SystemExit(1)
absent = [name for name in needed if not (Path(repos[name]["path"]) / "src").is_dir()]
if absent:
    print(f"GUARD FAIL: inventory checkout src roots absent on disk: {absent}", file=sys.stderr)
    raise SystemExit(1)

sys.path[0:0] = [str(Path(repos[name]["path"]) / "src") for name in needed]

from renquant_execution.software_stops_liveness import (
    _pipeline_stops_api,
    resolve_registry_path,
)

registry_path = resolve_registry_path(registry=None, data_root=data_root, broker=broker)
if not registry_path.exists():
    print(
        f"GUARD FAIL: no software-stop registry file at {registry_path} "
        "-- no writer has migrated to stamp this path yet. Installing now "
        "would arm a pager against unverified state and could produce a "
        "false critical alarm once the checker runs (Codex review, "
        "2026-07-12T04:32:57Z). Refusing to install.",
        file=sys.stderr,
    )
    raise SystemExit(1)

try:
    api = _pipeline_stops_api()
    api.validate_snapshot(json.loads(registry_path.read_text(encoding="utf-8")))
except Exception as exc:
    print(
        f"GUARD FAIL: registry file at {registry_path} is CORRUPT / "
        f"unparseable ({type(exc).__name__}: {exc}). Refusing to arm the "
        "pager against invalid registry state.",
        file=sys.stderr,
    )
    raise SystemExit(1)

print(f"GUARD OK: valid registry at {registry_path} (broker={broker})")
PY
)"
    guard_rc=$?
    echo "$guard_out" >&2
    return $guard_rc
}

case "$CMD" in
    install)
        require_sources
        $APPLY || echo "DRY-RUN (no --apply): printing the exact landing commands, changing nothing."
        if $APPLY; then
            if ! guard_registry_before_apply; then
                echo "ERROR: registry validity guard failed -- refusing to install (see guard output above). This is a fail-closed safety check (Codex review, 2026-07-12T04:32:57Z): darkness alone is not a runtime safety control. Fix the registry/writer/pin state and retry." >&2
                exit 3
            fi
        else
            echo "(registry validity guard runs at --apply time only; dry-run does not execute it)"
        fi
        run mkdir -p "$LOG_DIR"
        run mkdir -p "$AGENT_DIR"
        if [ -f "$PLIST_DST" ] && cmp -s "$PLIST_SRC" "$PLIST_DST"; then
            echo "plist already in sync: $PLIST_DST"
        else
            run cp "$PLIST_SRC" "$PLIST_DST"
        fi
        # bootout first so re-install converges (ignore "not loaded").
        run "$LAUNCHCTL" bootout "$GUI_DOMAIN/$LABEL" || true
        run "$LAUNCHCTL" bootstrap "$GUI_DOMAIN" "$PLIST_DST"
        if $APPLY; then
            echo "installed: $LABEL (10-minute liveness check, pages ntfy on STALE/CORRUPT/crash)"
            echo "next: scripts/install_stops_pager.sh test-fire STALE  # SLA drill — record response time"
        fi
        ;;
    uninstall)
        $APPLY || echo "DRY-RUN (no --apply): printing the exact commands, changing nothing."
        run "$LAUNCHCTL" bootout "$GUI_DOMAIN/$LABEL" || true
        run rm -f "$PLIST_DST"
        if $APPLY; then
            echo "uninstalled: $LABEL"
        fi
        ;;
    status)
        echo "label:        $LABEL"
        echo "plist source: $PLIST_SRC $([ -f "$PLIST_SRC" ] && echo '[present]' || echo '[MISSING]')"
        if [ -f "$PLIST_DST" ]; then
            if cmp -s "$PLIST_SRC" "$PLIST_DST"; then
                echo "installed:    $PLIST_DST [in sync with repo]"
            else
                echo "installed:    $PLIST_DST [DRIFTED from repo copy — re-run install --apply]"
            fi
        else
            echo "installed:    NOT INSTALLED ($PLIST_DST absent)"
        fi
        if "$LAUNCHCTL" print "$GUI_DOMAIN/$LABEL" >/dev/null 2>&1; then
            echo "launchd job:  LOADED ($GUI_DOMAIN/$LABEL)"
        else
            echo "launchd job:  not loaded"
        fi
        out_log="$LOG_DIR/launchd.out.log"
        if [ -f "$out_log" ]; then
            echo "last checks:"
            tail -n 3 "$out_log" | sed 's/^/  /'
        else
            echo "last checks:  no log yet ($out_log)"
        fi
        ;;
    test-fire)
        require_sources
        kind="${2:-STALE}"
        [ "$kind" = "--apply" ] && kind="STALE"
        echo "+ $WRAPPER --test-fire $kind"
        exec "$WRAPPER" --test-fire "$kind"
        ;;
    *)
        echo "usage: $0 <install|uninstall|status|test-fire [STALE|CORRUPT]> [--apply]" >&2
        exit 64
        ;;
esac
