#!/usr/bin/env bash
# shadow_ab_daily.sh — D6-§2a two-arm shadow experiment, one paired session.
#
# Invoked by launchd (deploy/com.renquant.shadow-ab-daily.plist, 14:35 PT —
# post-close, after the daily prod cycle) — NOT installed by merging this PR;
# arming/installation is a separately-granted operator landing step.
#
# RUNTIME CONTRACT (Codex r2 on #460): every runtime, data-root, and
# pin-manifest input is an EXPLICIT externally-supplied value — this script
# has NO default that points at the deprecated RenQuant umbrella (or at any
# sibling directory). The launchd plist supplies the values as configuration;
# the script fails closed when one is missing. Repo code paths come from the
# IMMUTABLE run manifest (verified commit + clean tree by the runner BEFORE
# either arm) — never from name/sibling directory lookup.
#
# Required environment (supplied by the plist):
#   RENQUANT_SHADOW_AB_PYTHON        interpreter to run the orchestrator with
#   RENQUANT_SHADOW_AB_RUN_MANIFEST  immutable run manifest json
#                                    ({repos:{name:{path,commit}}, data_revision})
#   RENQUANT_SHADOW_AB_REPO_ROOT     runtime data/artifact root (exported as
#                                    RENQUANT_REPO_ROOT, passed as --repo-root)
#   RENQUANT_SHADOW_AB_STRATEGY_DIR  artifact-resolution anchor (--strategy-dir)
# Optional:
#   RENQUANT_SHADOW_AB_DATA_ROOT     OHLCV parquet root (--ohlcv-dir); defaults
#                                    to $RENQUANT_SHADOW_AB_REPO_ROOT/data/ohlcv
#   RENQUANT_SHADOW_AB_DATA_MANIFEST frozen data manifest (defaults to the
#                                    pinned strategy repo's copy)
#   RENQUANT_SHADOW_AB_ENV_FILE      credentials env file (Alpaca readonly reads)
#   RENQUANT_SHADOW_AB_ROOT          experiment output root (default ~/renquant-shadow-ab)
#   RENQUANT_SHADOW_AB_NTFY_TOPIC    dedicated shadow topic (never the live one)
#   RENQUANT_SHADOW_AB_SESSION_DATE  ISO session date (default: today)
#   RENQUANT_SHADOW_AB_TIMEOUT_SEC   whole-session budget (default 3600)
#
# SAFE BY CONSTRUCTION: the shadow-ab runner is readonly (readonly account
# snapshot fetch; native chain builds a readonly execution payload; per-arm
# state isolated under the experiment root). Prod state/db are never written.
# A failure here must never affect the prod cycle — the exit code only marks
# the session-pair invalid.
set -uo pipefail

PYTHON="${RENQUANT_SHADOW_AB_PYTHON:?RENQUANT_SHADOW_AB_PYTHON must be supplied (no default runtime)}"
RUN_MANIFEST="${RENQUANT_SHADOW_AB_RUN_MANIFEST:?RENQUANT_SHADOW_AB_RUN_MANIFEST must be supplied (immutable pin manifest)}"
REPO_ROOT="${RENQUANT_SHADOW_AB_REPO_ROOT:?RENQUANT_SHADOW_AB_REPO_ROOT must be supplied (runtime data/artifact root)}"
STRATEGY_DIR="${RENQUANT_SHADOW_AB_STRATEGY_DIR:?RENQUANT_SHADOW_AB_STRATEGY_DIR must be supplied (artifact anchor)}"
DATA_ROOT="${RENQUANT_SHADOW_AB_DATA_ROOT:-$REPO_ROOT/data/ohlcv}"
OUTPUT_ROOT="${RENQUANT_SHADOW_AB_ROOT:-$HOME/renquant-shadow-ab}"
NTFY_TOPIC="${RENQUANT_SHADOW_AB_NTFY_TOPIC:-renquant-shadow-ab}"   # DEDICATED topic (never the live one)
SESSION_DATE="${RENQUANT_SHADOW_AB_SESSION_DATE:-$(date +%F)}"
TIMEOUT_SEC="${RENQUANT_SHADOW_AB_TIMEOUT_SEC:-3600}"

LOG_DIR="$OUTPUT_ROOT/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/${SESSION_DATE}_session.log"
exec >>"$LOG" 2>&1
echo "=== shadow-ab session $SESSION_DATE start $(date -u +%FT%TZ) ==="

[ -f "$RUN_MANIFEST" ] || { echo "SETUP: run manifest missing: $RUN_MANIFEST"; exit 2; }
# Optional credentials (Alpaca readonly account snapshot) — explicit path only.
if [ -n "${RENQUANT_SHADOW_AB_ENV_FILE:-}" ]; then
    [ -f "$RENQUANT_SHADOW_AB_ENV_FILE" ] || { echo "SETUP: env file missing: $RENQUANT_SHADOW_AB_ENV_FILE"; exit 2; }
    set -a; # shellcheck disable=SC1090
    source "$RENQUANT_SHADOW_AB_ENV_FILE"; set +a
fi

# PYTHONPATH is built from the MANIFEST's repo paths (the same checkouts the
# runner verifies against the pinned commits before either arm) plus this
# orchestrator checkout — no sibling lookup, no umbrella subrepo_env.sh.
ORCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST_PYTHONPATH="$("$PYTHON" - "$RUN_MANIFEST" <<'PY'
import json
import pathlib
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
parts = []
for entry in manifest.get("repos", {}).values():
    src = pathlib.Path(entry["path"]) / "src"
    if src.is_dir():
        parts.append(str(src))
print(":".join(parts))
PY
)" || { echo "SETUP: manifest unreadable"; exit 2; }
export PYTHONPATH="$ORCH_DIR/src:$MANIFEST_PYTHONPATH:${PYTHONPATH:-}"
export RENQUANT_REPO_ROOT="$REPO_ROOT"
export RENQUANT_SUPPRESS_PREFLIGHT_NTFY=1

# Arm configs + frozen data manifest resolve from the MANIFEST's pinned
# strategy-104 checkout (verified by the runner), never a sibling path.
STRATEGY_CONFIGS="$("$PYTHON" - "$RUN_MANIFEST" <<'PY'
import json
import pathlib
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
entry = manifest["repos"]["renquant-strategy-104"]
print(pathlib.Path(entry["path"]) / "configs")
PY
)" || { echo "SETUP: strategy repo missing from manifest"; exit 2; }
CONFIG_A="$STRATEGY_CONFIGS/strategy_config.shadow_a.json"
CONFIG_B="$STRATEGY_CONFIGS/strategy_config.shadow_b.json"
DATA_MANIFEST="${RENQUANT_SHADOW_AB_DATA_MANIFEST:-$STRATEGY_CONFIGS/xgb_prod_artifact_manifest.json}"
for f in "$CONFIG_A" "$CONFIG_B" "$DATA_MANIFEST"; do
    [ -f "$f" ] || { echo "SETUP: missing $f"; exit 2; }
done

# Session market snapshot: the frozen identity input (as-of + universe from
# the PINNED shadow_a watchlist + corporate-action declaration). Both arms
# consume the SEALED copy the runner materializes from this file; per-symbol
# BAR validity (stale/future vs the session-close watermark) is enforced at
# hydration inside each arm.
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
# (alpaca_shadow_a / alpaca_shadow_b). The runner verifies the run manifest
# (commit + clean tree per repo) BEFORE either arm, seals both snapshots, and
# records resolved commits + data revision in the sealed bundle.
set +e
timeout_cmd=()
command -v timeout >/dev/null 2>&1 && timeout_cmd=(timeout "$TIMEOUT_SEC")
"${timeout_cmd[@]}" "$PYTHON" -m renquant_orchestrator shadow-ab \
    --config-a "$CONFIG_A" \
    --config-b "$CONFIG_B" \
    --data-manifest "$DATA_MANIFEST" \
    --run-manifest "$RUN_MANIFEST" \
    --output-root "$OUTPUT_ROOT" \
    --market-snapshot-json "$MARKET_SNAPSHOT" \
    --session-date "$SESSION_DATE" \
    --repo-root "$REPO_ROOT" \
    --strategy-dir "$STRATEGY_DIR" \
    --ohlcv-dir "$DATA_ROOT" \
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
