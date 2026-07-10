#!/usr/bin/env bash
# shadow_ab_daily.sh — D6-§2a two-arm shadow experiment, one paired session.
#
# Invoked by launchd (deploy/com.renquant.shadow-ab-daily.plist, 14:35 PT —
# post-close, after the daily prod cycle) — NOT installed by merging this PR;
# arming/installation is a separately-granted operator landing step.
#
# Env recipe mirrors the working scripts/check_readonly_e2e.sh pattern (and
# the verified 2026-07-10 manual session): umbrella .env for credentials +
# subrepo_env.sh for the full PINNED-subrepo PYTHONPATH. The experiment path
# itself never invokes umbrella code — the umbrella checkout supplies only
# env/data/artifact roots.
#
# SAFE BY CONSTRUCTION: the shadow-ab runner is readonly (readonly account
# snapshot fetch; native chain builds a readonly execution payload; per-arm
# state isolated under the experiment root). Prod state/db are never written.
# A failure here must never affect the prod cycle — launchd runs this
# independently and the exit code only marks the session-pair invalid.
set -uo pipefail

REPO_DIR="${RENQUANT_REPO_DIR:-/Users/renhao/git/github/RenQuant}"
PYTHON="${RENQUANT_PYTHON:-$REPO_DIR/.venv/bin/python}"
OUTPUT_ROOT="${RENQUANT_SHADOW_AB_ROOT:-$HOME/renquant-shadow-ab}"
NTFY_TOPIC="${RENQUANT_SHADOW_AB_NTFY_TOPIC:-renquant-shadow-ab}"   # DEDICATED topic (never the live one)
SESSION_DATE="${RENQUANT_SHADOW_AB_SESSION_DATE:-$(date +%F)}"
TIMEOUT_SEC="${RENQUANT_SHADOW_AB_TIMEOUT_SEC:-3600}"

LOG_DIR="$OUTPUT_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/${SESSION_DATE}_session.log"
exec >>"$LOG" 2>&1
echo "=== shadow-ab session $SESSION_DATE start $(date -u +%FT%TZ) ==="

cd "$REPO_DIR" || { echo "SETUP: cannot cd $REPO_DIR"; exit 2; }
# Credentials (Alpaca readonly account snapshot) come from the umbrella .env.
[ -f "$REPO_DIR/.env" ] && { set -a; # shellcheck disable=SC1091
  source "$REPO_DIR/.env"; set +a; }
# Full pinned-subrepo PYTHONPATH — the exact recipe check_readonly_e2e.sh uses.
# shellcheck disable=SC1091
source "$REPO_DIR/scripts/subrepo_env.sh" || { echo "SETUP: subrepo_env"; exit 2; }
renquant_load_subrepo_env "$REPO_DIR"
SUBREPO_ROOT="$(renquant_subrepo_root "$REPO_DIR" "$(dirname "$REPO_DIR")")"
export RENQUANT_SUBREPO_ROOT="$SUBREPO_ROOT"
export PYTHONPATH="$(renquant_subrepo_pythonpath "$SUBREPO_ROOT" renquant-orchestrator renquant-common renquant-base-data renquant-artifacts renquant-model renquant-pipeline renquant-execution renquant-strategy-104 renquant-backtesting):${PYTHONPATH:-}"
export RENQUANT_REPO_ROOT="$REPO_DIR"
export RENQUANT_SUPPRESS_PREFLIGHT_NTFY=1

STRATEGY_CONFIGS="$SUBREPO_ROOT/renquant-strategy-104/configs"
CONFIG_A="$STRATEGY_CONFIGS/strategy_config.shadow_a.json"
CONFIG_B="$STRATEGY_CONFIGS/strategy_config.shadow_b.json"
DATA_MANIFEST="$STRATEGY_CONFIGS/xgb_prod_artifact_manifest.json"
STRATEGY_DIR="$REPO_DIR/backtesting/renquant_104"
for f in "$CONFIG_A" "$CONFIG_B" "$DATA_MANIFEST"; do
    [ -f "$f" ] || { echo "SETUP: missing $f"; exit 2; }
done

# Session market snapshot: the frozen identity input (as-of + universe from
# the PINNED shadow_a watchlist + corporate-action declaration). Both arms
# consume the SEALED copy the runner materializes from this file.
MARKET_SNAPSHOT="$OUTPUT_ROOT/market_snapshot_${SESSION_DATE}.json"
"$PYTHON" - "$CONFIG_A" "$MARKET_SNAPSHOT" "$SESSION_DATE" <<'PY' || { echo "SETUP: market snapshot build failed"; exit 2; }
import datetime as dt
import json
import sys

config_path, out_path, session_date = sys.argv[1], sys.argv[2], sys.argv[3]
config = json.load(open(config_path, encoding="utf-8"))
universe = sorted(str(t) for t in config.get("watchlist") or [])
if not universe:
    raise SystemExit("pinned shadow_a config has an empty watchlist")
payload = {
    "as_of": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "session_date": session_date,
    "universe": universe,
    "universe_count": len(universe),
    "corporate_actions": None,
    "source": "scripts/shadow_ab_daily.sh (pinned strategy-104 shadow_a watchlist)",
}
with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(payload, fh, indent=2, sort_keys=True)
    fh.write("\n")
print(f"market snapshot: {out_path} universe={len(universe)}")
PY

# One paired two-arm session. Frozen tags default inside the runner
# (alpaca_shadow_a / alpaca_shadow_b). Account snapshot is fetched once,
# readonly, then sealed together with the market snapshot before either arm.
set +e
timeout_cmd=()
command -v timeout >/dev/null 2>&1 && timeout_cmd=(timeout "$TIMEOUT_SEC")
"${timeout_cmd[@]}" "$PYTHON" -m renquant_orchestrator shadow-ab \
    --config-a "$CONFIG_A" \
    --config-b "$CONFIG_B" \
    --data-manifest "$DATA_MANIFEST" \
    --output-root "$OUTPUT_ROOT" \
    --market-snapshot-json "$MARKET_SNAPSHOT" \
    --session-date "$SESSION_DATE" \
    --repo-root "$REPO_DIR" \
    --strategy-dir "$STRATEGY_DIR" \
    --ntfy-topic "$NTFY_TOPIC" \
    > "$OUTPUT_ROOT/session_${SESSION_DATE}.json" \
    2> "$OUTPUT_ROOT/session_${SESSION_DATE}_stderr.log"
RC=$?
set -e
echo "shadow-ab exit=$RC (0=valid pair, 3=precheck abort, 4=pair invalidated, 5=VOID)"
if [ "$RC" -eq 5 ]; then
    echo "SHADOW-AB VOID — config drift against the frozen experiment; operator action required"
fi
echo "=== shadow-ab session $SESSION_DATE end $(date -u +%FT%TZ) ==="
exit "$RC"
