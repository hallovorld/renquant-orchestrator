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
# The reviewed launchd surface (GOAL-5 AC2). The plist about to be armed must
# carry EXACTLY the ProgramArguments this manifest pins for $LABEL, or the
# daily run-surface drift scan (ops/run_surface_drift_check.py) raises a
# "silent containment / job swap?" alarm on the very first firing after
# install. Test-only override, same discipline as RENQUANT_STOPS_PAGER_PLIST_SRC.
MANIFEST_SRC="${RENQUANT_STOPS_PAGER_MANIFEST:-$REPO_ROOT/ops/launchd_manifest.json}"
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
#
# 2026-08-29 READINESS (Codex CHANGES_REQUESTED on PR #1078,
# 2026-08-29T07:54:11Z): VALID is bootstrap, not evidence. A seeded registry
# (orchestrator `... software_stops_registry_contract seed`) is schema-VALID
# with `last_evaluated_at: null`, and the execution checker reports a valid
# zero-stop registry as OK whether or not a writer ever touched it — so a
# guard that stops at VALID would arm the pager against a file the sell-only
# loop has never evaluated. The guard now additionally requires READY from
# the orchestrator-owned classifier
# (`python -m renquant_orchestrator.software_stops_registry_contract readiness`,
# which imports ONLY the pipeline's PUBLIC registry_path_for /
# validate_software_stop_snapshot / compute_staleness): a non-null, parseable
# heartbeat within the staleness budget at the SAME data root + broker the
# plist arms. Distinct non-zero exits (10 UNSEEDED / 11 UNINITIALIZED /
# 12 STALE / 13 CORRUPT / 3 pipeline-import failure) are all refusals.
# `install` (dry-run) prints the same verdict as a preview without enforcing.

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

registry_readiness_probe() {
    # $1 = python_bin, $2 = pinned src PYTHONPATH, $3 = data_root, $4 = broker.
    # Plain subprocess invocation of THIS repo's readiness classifier (see the
    # 2026-08-29 READINESS note above). Prints its one-line verdict; returns
    # its exit code: 0 READY / 10 UNSEEDED / 11 UNINITIALIZED / 12 STALE /
    # 13 CORRUPT / 3 pipeline-import failure / 1 usage.
    PYTHONPATH="$2:$REPO_ROOT/src:${PYTHONPATH:-}" \
        "$1" -m renquant_orchestrator.software_stops_registry_contract \
        readiness --data-root "$3" --broker "$4" 2>&1
}

preview_registry_readiness() {
    # Dry-run companion of guard_registry_before_apply: prints (stdout) the
    # readiness verdict --apply WOULD enforce and never fails — dry-run is
    # echo-only by contract. A verdict that cannot be computed on this
    # machine is reported as such with the reason, never hidden.
    local data_root python_bin broker pinned_src_paths out rc
    data_root="$(plist_env_var RENQUANT_STOPS_PAGER_DATA_ROOT || true)"
    python_bin="$(plist_env_var RENQUANT_STOPS_PAGER_PYTHON || true)"
    broker="$(plist_env_var RENQUANT_STOPS_PAGER_BROKER || true)"
    broker="${broker:-alpaca}"
    if [ -z "$data_root" ] || [ -z "$python_bin" ]; then
        echo "registry readiness (preview; --apply requires READY): could not be evaluated -- $PLIST_SRC lacks RENQUANT_STOPS_PAGER_DATA_ROOT and/or RENQUANT_STOPS_PAGER_PYTHON"
        return 0
    fi
    if ! pinned_src_paths="$(resolve_pinned_pythonpath "$python_bin" 2>/dev/null)"; then
        echo "registry readiness (preview; --apply requires READY): could not be evaluated -- pinned checkouts not resolvable from the R-PIN runtime inventory on this machine (data_root=$data_root broker=$broker)"
        return 0
    fi
    out="$(registry_readiness_probe "$python_bin" "$pinned_src_paths" "$data_root" "$broker")"
    rc=$?
    echo "registry readiness (preview; --apply requires READY): $out [exit $rc]"
    return 0
}

guard_registry_before_apply() {
    # Resolve the SAME interpreter + data root the plist is about to arm,
    # resolve the pinned checkouts' PYTHONPATH (resolve_pinned_pythonpath,
    # above — no execution/pipeline imports), then shell out to the pinned
    # renquant-execution's PUBLIC `--validate-registry` CLI mode
    # (renquant-execution#30) and refuse to proceed unless it reports
    # REGISTRY_VALID (exit 0); THEN require READY from this repo's own
    # readiness classifier (registry_readiness_probe, 2026-08-29 note above).
    # Returns nonzero (never raises) on any failure — missing, corrupt,
    # unseeded, uninitialized (seed-only), stale, or a resolution/CLI crash
    # are all treated as fail-closed; all diagnostics go to stderr.
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

    echo "guard: verifying a VALID and READY software-stop registry exists at data_root=$data_root broker=$broker before arming..." >&2

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
            echo "guard: registry VALID ($validate_out) -- now requiring READY: a real writer heartbeat at this exact path within the staleness budget..." >&2
            local ready_out ready_rc
            ready_out="$(registry_readiness_probe "$python_bin" "$pinned_src_paths" "$data_root" "$broker")"
            ready_rc=$?
            if [ "$ready_rc" -eq 0 ]; then
                echo "GUARD OK: $ready_out -- registry VALID and READY (broker=$broker)" >&2
                return 0
            fi
            echo "GUARD FAIL: $ready_out -- registry is schema-VALID but NOT READY (readiness exit $ready_rc). A seeded or never-evaluated file is bootstrap, not arming evidence: installing requires a real sell-only-loop heartbeat at this exact path (Codex review on #1078, 2026-08-29T07:54:11Z). Refusing to install." >&2
            return 1
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

guard_manifest_agreement() {
    # $1 = "apply" | "dry-run". Fail-closed agreement check between the plist
    # about to be copied ($PLIST_SRC — the round-6 rule: the armed file, never
    # ambient env) and the reviewed launchd manifest ($MANIFEST_SRC):
    #   * $LABEL must be manifested;
    #   * ProgramArguments must equal the manifest's program_args;
    #   * the manifest digest must equal what the drift scan's own
    #     program_args_digest computes for those arguments (one implementation,
    #     imported from ops/run_surface_drift_check.py — never re-derived here).
    # Under --apply it additionally requires the program the job will exec
    # (the last ProgramArguments entry, the wrapper in the PINNED run checkout)
    # to exist and be executable on THIS machine: a manifested path that is
    # absent here would arm a job that launchd spawns and immediately fails,
    # dark, every 10 minutes. Dry-run skips only that machine-state check so
    # the echo-first preview works on any checkout (CI included).
    local mode="$1"
    # PYTHONDONTWRITEBYTECODE: importing the scanner must not leave
    # ops/__pycache__ behind in the checkout this runs from — at landing time
    # that is the PINNED run checkout, which the drift scan audits for
    # untracked files. A guard is read-only or it is not a guard.
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="$REPO_ROOT/ops:${PYTHONPATH:-}" \
        python3 - "$PLIST_SRC" "$MANIFEST_SRC" "$LABEL" "$mode" <<'PY'
import json
import os
import plistlib
import sys

from run_surface_drift_check import program_args_digest

plist_path, manifest_path, label, mode = sys.argv[1:5]
try:
    with open(plist_path, "rb") as fh:
        args = [str(a) for a in plistlib.load(fh).get("ProgramArguments", [])]
except Exception as exc:  # noqa: BLE001
    print(f"MANIFEST GUARD FAIL: cannot read ProgramArguments from {plist_path}: {exc}", file=sys.stderr)
    sys.exit(1)
try:
    with open(manifest_path, encoding="utf-8") as fh:
        jobs = json.load(fh)["jobs"]
except Exception as exc:  # noqa: BLE001
    print(f"MANIFEST GUARD FAIL: cannot read the launchd manifest {manifest_path}: {exc}", file=sys.stderr)
    sys.exit(1)
spec = jobs.get(label)
if not spec:
    print(f"MANIFEST GUARD FAIL: {label} is not declared in {manifest_path} -- declare it via a reviewed change before arming", file=sys.stderr)
    sys.exit(1)
if not args or args != list(spec.get("program_args") or []):
    print(f"MANIFEST GUARD FAIL: plist ProgramArguments {args} != manifest program_args {spec.get('program_args')} -- the drift scan would alarm 'silent containment / job swap?' on the first firing after install", file=sys.stderr)
    sys.exit(1)
digest = program_args_digest(args)
if digest != spec.get("program_args_sha256"):
    print(f"MANIFEST GUARD FAIL: manifest program_args_sha256 {spec.get('program_args_sha256')} != program_args_digest {digest} for {args}", file=sys.stderr)
    sys.exit(1)
if mode == "apply":
    target = args[-1]
    if not (os.path.isfile(target) and os.access(target, os.X_OK)):
        print(f"MANIFEST GUARD FAIL: the program this job would exec is not an executable file on this machine: {target} (sync the pinned run checkout first)", file=sys.stderr)
        sys.exit(1)
print(f"MANIFEST GUARD OK: {label} ProgramArguments == manifest ({digest[:12]}...)", file=sys.stderr)
PY
}

case "$CMD" in
    install)
        require_sources
        $APPLY || echo "DRY-RUN (no --apply): printing the exact landing commands, changing nothing."
        if ! guard_manifest_agreement "$($APPLY && echo apply || echo dry-run)"; then
            echo "ERROR: plist/manifest agreement guard failed -- refusing to $($APPLY && echo install || echo preview) (see guard output above). Fix deploy/$LABEL.plist or ops/launchd_manifest.json in the same reviewed change." >&2
            exit 4
        fi
        if $APPLY; then
            if ! guard_registry_before_apply; then
                echo "ERROR: registry validity guard failed -- refusing to install (see guard output above). This is a fail-closed safety check (Codex review, 2026-07-12T04:32:57Z): darkness alone is not a runtime safety control. Fix the registry/writer/pin state and retry." >&2
                exit 3
            fi
        else
            echo "(registry VALID+READY guard is enforced at --apply time only; dry-run previews the readiness verdict below without enforcing it)"
            preview_registry_readiness
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
