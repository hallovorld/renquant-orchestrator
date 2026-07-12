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
# Test-only override (hermetic tests point this at a throwaway plist so the
# --apply registry guard below can be exercised against controlled
# EnvironmentVariables without touching the real committed plist). Production
# never sets this — see require_sources.
PLIST_SRC="${RENQUANT_STOPS_PAGER_PLIST_SRC:-$REPO_ROOT/deploy/$LABEL.plist}"
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
#
# Round-6 correction (Codex CHANGES_REQUESTED, 2026-07-12T10:57:11Z): the
# first cut of this guard let an ambient environment variable
# (RENQUANT_STOPS_PAGER_DATA_ROOT / _PYTHON already exported in the
# operator's shell) win over the plist's own EnvironmentVariables value. That
# is exactly the divergence bug the guard exists to prevent: launchd does
# NOT inherit the interactive shell environment — it only ever sees the
# EnvironmentVariables baked into the COPIED plist — so an ambient override
# could pass the guard against a valid registry while the job that actually
# gets bootstrapped is armed against a totally different (missing/corrupt)
# path. Fixed: the guard now derives data root and interpreter EXCLUSIVELY
# from $PLIST_SRC (the exact file about to be copied to $PLIST_DST) — no
# ambient-env fallback, no unpersisted guard input, period.
#
# Round-7 correction (Codex CHANGES_REQUESTED, 2026-07-12T11:33:56Z): the
# round-5/6 guard imported renquant_execution's PRIVATE
# `_pipeline_stops_api()` (and `resolve_registry_path`) in-process. A
# leading-underscore name is an implementation detail, not a versioned
# cross-repo contract — a future pin advance could turn this arming-time
# safety check into an import failure or silently change its validation
# semantics. Fixed: the guard now only resolves PYTHONPATH itself (reading
# paths off the R-PIN runtime inventory is a legitimate orchestrator-owned
# concern that imports nothing from renquant_execution/renquant_pipeline),
# then shells out to the pinned renquant-execution's PUBLIC CLI surface —
# `python -m renquant_execution.software_stops_liveness --validate-registry`
# (renquant-execution#30) — exactly the ownership boundary
# scripts/stops_liveness_pager.sh's own liveness check already obeys. The
# guard interprets ONLY that subprocess's exit code
# (0=REGISTRY_VALID / 1=REGISTRY_MISSING / 2=REGISTRY_CORRUPT) and combined
# stdout+stderr message — no in-process import of execution/pipeline
# internals anywhere in guard_registry_before_apply().

plist_env_var() {
    # $1 = env var name. Parses it out of $PLIST_SRC's EnvironmentVariables
    # dict ONLY — the exact arming-time configuration `install --apply` is
    # about to copy verbatim into the launchd job. Deliberately ignores any
    # same-named variable already set in the calling shell: an ambient
    # override here would validate a path different from what gets armed
    # (round-6 correction above). Prints the resolved value and returns 0,
    # or prints nothing and returns 1.
    local var_name="$1"
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

resolve_pinned_pythonpath() {
    # $1 = python_bin. PYTHONPATH resolution ONLY: reads the R-PIN Stage-1
    # runtime inventory and validates the pinned checkouts (missing repos /
    # absent src dirs / stale-pin module-file tripwire for
    # renquant_execution.software_stops_liveness specifically — the exact
    # same check scripts/stops_liveness_pager.sh's own resolver heredoc
    # performs). This step is a pure orchestrator-owned path-resolution
    # concern: it imports NOTHING from renquant_execution or
    # renquant_pipeline, it only reads paths off disk. Prints ONLY the
    # ":"-joined PYTHONPATH on success; all diagnostics go to stderr,
    # nonzero exit on any failure.
    local python_bin="$1"
    PYTHONPATH="$REPO_ROOT/src:${PYTHONPATH:-}" "$python_bin" - <<'PY'
import sys
from pathlib import Path

from renquant_orchestrator.deployment_manifest import (
    deploy_state_root,
    load_runtime_inventory,
    state_root_paths,
)

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

# Stale-pin tripwire: `python -m <missing module>` exits 1, which would
# masquerade as REGISTRY_MISSING downstream — classify it here instead,
# same discipline as stops_liveness_pager.sh's own resolver.
module_file = (
    Path(repos["renquant-execution"]["path"])
    / "src" / "renquant_execution" / "software_stops_liveness.py"
)
if not module_file.is_file():
    print(
        f"GUARD FAIL: pinned renquant-execution checkout lacks the liveness "
        f"checker ({module_file}) -- pin not yet advanced past "
        "renquant-execution#29",
        file=sys.stderr,
    )
    raise SystemExit(1)

print(":".join(str(Path(repos[name]["path"]) / "src") for name in needed))
PY
}

guard_registry_before_apply() {
    # Resolve the SAME interpreter + data root the plist is about to arm,
    # resolve the pinned checkouts' PYTHONPATH (resolve_pinned_pythonpath,
    # above — no execution/pipeline imports), then shell out to the pinned
    # renquant-execution's PUBLIC `--validate-registry` CLI mode
    # (renquant-execution#30) and refuse to proceed unless it reports
    # REGISTRY_VALID (exit 0). Returns nonzero (never raises) on any
    # failure — missing registry, corrupt registry, or a resolution/CLI
    # crash are all treated as fail-closed; all diagnostics go to stderr.
    local data_root python_bin broker
    if ! data_root="$(plist_env_var RENQUANT_STOPS_PAGER_DATA_ROOT)"; then
        echo "GUARD FAIL: cannot resolve RENQUANT_STOPS_PAGER_DATA_ROOT from $PLIST_SRC EnvironmentVariables (ambient env is deliberately ignored here — see round-6 correction above)" >&2
        return 1
    fi
    if ! python_bin="$(plist_env_var RENQUANT_STOPS_PAGER_PYTHON)"; then
        echo "GUARD FAIL: cannot resolve RENQUANT_STOPS_PAGER_PYTHON from $PLIST_SRC EnvironmentVariables (ambient env is deliberately ignored here — see round-6 correction above)" >&2
        return 1
    fi
    # Same exclusively-from-plist rule applies to broker: if a future plist
    # revision starts carrying RENQUANT_STOPS_PAGER_BROKER, an ambient
    # fallback here would silently reintroduce the same divergence bug this
    # round fixes for data root/interpreter. The committed plist does not
    # set it today, so this resolves to the package-wide "alpaca" default
    # either way — but derive it the same way, not via ambient env.
    broker="$(plist_env_var RENQUANT_STOPS_PAGER_BROKER || true)"
    broker="${broker:-alpaca}"

    echo "guard: verifying a valid software-stop registry exists at data_root=$data_root broker=$broker before arming..." >&2

    # (a) PYTHONPATH resolution — see resolve_pinned_pythonpath() above.
    local pinned_src_paths resolve_rc
    pinned_src_paths="$(resolve_pinned_pythonpath "$python_bin")"
    resolve_rc=$?
    if [ "$resolve_rc" -ne 0 ]; then
        return 1
    fi

    # (b) plain subprocess invocation of the pinned renquant-execution's
    # PUBLIC CLI surface — no import, no in-process call into execution or
    # pipeline internals.
    local validate_out validate_rc
    validate_out="$(PYTHONPATH="$pinned_src_paths:$REPO_ROOT/src:${PYTHONPATH:-}" \
        "$python_bin" -m renquant_execution.software_stops_liveness \
        --validate-registry --data-root "$data_root" --broker "$broker" 2>&1)"
    validate_rc=$?

    case "$validate_rc" in
        0)
            echo "GUARD OK: $validate_out (broker=$broker)" >&2
            return 0
            ;;
        1)
            echo "GUARD FAIL: $validate_out -- no writer has migrated to stamp this path yet. Installing now would arm a pager against unverified state and could produce a false critical alarm once the checker runs (Codex review, 2026-07-12T04:32:57Z). Refusing to install." >&2
            return 1
            ;;
        2)
            echo "GUARD FAIL: $validate_out -- refusing to arm the pager against invalid registry state." >&2
            return 1
            ;;
        *)
            echo "GUARD FAIL: renquant_execution --validate-registry exited $validate_rc (crash / pin-resolution failure): $validate_out" >&2
            return 1
            ;;
    esac
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
