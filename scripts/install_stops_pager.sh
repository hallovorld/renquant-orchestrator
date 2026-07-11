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

case "$CMD" in
    install)
        require_sources
        $APPLY || echo "DRY-RUN (no --apply): printing the exact landing commands, changing nothing."
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
