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
export RENQUANT_OHLCV_DIR="$DATA_ROOT"
export RENQUANT_SUPPRESS_PREFLIGHT_NTFY=1

# STRATEGY_DIR (the artifact-fingerprint-resolution anchor) + arm configs +
# frozen data manifest ALL resolve from the SAME MANIFEST-pinned strategy-104
# checkout (verified by the runner) — there is deliberately no second,
# independent strategy-dir input. Codex re-review of #460 r2: a separate
# RENQUANT_SHADOW_AB_STRATEGY_DIR let a caller pair manifest-verified configs
# with artifacts resolved from an arbitrary, UNVERIFIED checkout — exactly the
# pin-integrity hole the manifest exists to close. One resolved path, used
# for both.
STRATEGY_DIR="$("$PYTHON" - "$RUN_MANIFEST" <<'PY'
import json
import pathlib
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
entry = manifest["repos"]["renquant-strategy-104"]
print(pathlib.Path(entry["path"]))
PY
)" || { echo "SETUP: strategy repo missing from manifest"; exit 2; }
STRATEGY_CONFIGS="$STRATEGY_DIR/configs"
CONFIG_A="$STRATEGY_CONFIGS/strategy_config.shadow_a.json"
CONFIG_B="$STRATEGY_CONFIGS/strategy_config.shadow_b.json"
DATA_MANIFEST="${RENQUANT_SHADOW_AB_DATA_MANIFEST:-$STRATEGY_CONFIGS/xgb_prod_artifact_manifest.json}"
for f in "$CONFIG_A" "$CONFIG_B" "$DATA_MANIFEST"; do
    [ -f "$f" ] || { echo "SETUP: missing $f"; exit 2; }
done

# Session market snapshot: the canonical native_live_market_snapshot artifact
# (real prices + as-of), never a hand-rolled JSON — a snapshot with a
# "universe" field but no "prices" hashes an EMPTY universe (the decision-
# digest identity derives universe from market_snapshot.prices), which is not
# a valid sealed market input regardless of what it claims (Codex r1). Prices
# are the pinned watchlist's last LOCAL close via LocalStore (RENQUANT_OHLCV_DIR
# above), the same readonly source hydrate_pipeline_context reads; no live
# quote fetch, no network. Per-symbol BAR validity (stale/future vs the
# session-close watermark) is separately enforced at hydration inside each
# arm (validate_market_bars, r2) — this snapshot's own freshness is not that
# check, only that the DIGEST faithfully covers the real universe it claims.
MARKET_SNAPSHOT="$OUTPUT_ROOT/market_snapshot_${SESSION_DATE}.json"
PRICES_JSON="$OUTPUT_ROOT/prices_${SESSION_DATE}.json"
AS_OF="$(date -u +%FT%TZ)"
"$PYTHON" - "$CONFIG_A" "$PRICES_JSON" <<'PY' || { echo "SETUP: price snapshot build failed"; exit 2; }
import json
import sys

from renquant_pipeline.kernel.data import LocalStore

config_path, out_path = sys.argv[1], sys.argv[2]
config = json.load(open(config_path, encoding="utf-8"))
universe = sorted(str(t) for t in config.get("watchlist") or [])
if not universe:
    raise SystemExit("pinned shadow_a config has an empty watchlist")

store = LocalStore()
prices: dict[str, float] = {}
missing: list[str] = []
for symbol in universe:
    frame = store.load(symbol, "1d")
    close = float(frame["close"].iloc[-1]) if frame is not None and not frame.empty else 0.0
    if close > 0:
        prices[symbol] = close
    else:
        missing.append(symbol)
if missing:
    raise SystemExit(
        f"no local close price for {len(missing)} pinned watchlist symbol(s) "
        f"(fail-closed, cannot seal a market snapshot missing prices): {missing}"
    )
with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(prices, fh, indent=2, sort_keys=True)
print(f"prices: {out_path} symbols={len(prices)}")
PY

"$PYTHON" -m renquant_orchestrator native-live-market-snapshot \
    --as-of "$AS_OF" \
    --prices-json "$PRICES_JSON" \
    --output-json "$MARKET_SNAPSHOT" \
    || { echo "SETUP: native-live-market-snapshot build failed"; exit 2; }

# End-to-end assertion (Codex r1): the sealed snapshot's OWN decision-identity
# universe (as the runner will derive it) must equal the pinned watchlist
# exactly — never trust that the artifact says what this script intended.
"$PYTHON" - "$MARKET_SNAPSHOT" "$CONFIG_A" <<'PY' || { echo "SETUP: market snapshot universe assertion failed"; exit 2; }
import json
import sys

from renquant_orchestrator.native_live_context import market_snapshot_identity

snapshot_path, config_path = sys.argv[1], sys.argv[2]
snapshot = json.load(open(snapshot_path, encoding="utf-8"))
config = json.load(open(config_path, encoding="utf-8"))
pinned = sorted(str(t) for t in config.get("watchlist") or [])
identity = market_snapshot_identity(snapshot)
if identity["universe"] != pinned:
    raise SystemExit(
        "market snapshot digest universe does not match the pinned watchlist "
        f"(fail-closed): digest={identity['universe']} pinned={pinned}"
    )
print(f"universe assertion OK: {len(pinned)} symbols")
PY

# One paired two-arm session. Frozen tags default inside the runner
# (alpaca_shadow_a / alpaca_shadow_b). The runner verifies the run manifest
# (commit + clean tree per repo) BEFORE either arm, seals both snapshots, and
# records resolved commits + data revision in the sealed bundle.
#
# Portable timeout enforcement (Codex r1): macOS ships no ``timeout`` by
# default (BSD userland) — an unconditionally-empty timeout_cmd silently ran
# the session UNBOUNDED. Prefer GNU ``timeout``/Homebrew ``gtimeout`` when
# present; otherwise a bash watchdog enforces the SAME bound and marks the
# session paired-invalidated (exit 4) rather than letting it hang forever.
SHADOW_AB_ARGS=(
    -m renquant_orchestrator shadow-ab
    --config-a "$CONFIG_A"
    --config-b "$CONFIG_B"
    --data-manifest "$DATA_MANIFEST"
    --run-manifest "$RUN_MANIFEST"
    --output-root "$OUTPUT_ROOT"
    --market-snapshot-json "$MARKET_SNAPSHOT"
    --session-date "$SESSION_DATE"
    --repo-root "$REPO_ROOT"
    --strategy-dir "$STRATEGY_DIR"
    --ohlcv-dir "$DATA_ROOT"
    --ntfy-topic "$NTFY_TOPIC"
)
SESSION_OUT="$OUTPUT_ROOT/session_${SESSION_DATE}.json"
SESSION_ERR="$OUTPUT_ROOT/session_${SESSION_DATE}_stderr.log"
EXIT_PAIR_INVALIDATED=4

_TIMEOUT_BIN=""
if command -v timeout >/dev/null 2>&1; then
    _TIMEOUT_BIN="timeout"
elif command -v gtimeout >/dev/null 2>&1; then
    _TIMEOUT_BIN="gtimeout"
fi

set +e
if [ -n "$_TIMEOUT_BIN" ]; then
    "$_TIMEOUT_BIN" "$TIMEOUT_SEC" "$PYTHON" "${SHADOW_AB_ARGS[@]}" \
        > "$SESSION_OUT" 2> "$SESSION_ERR"
    RC=$?
    # GNU timeout/gtimeout's own "command timed out" convention is exit 124
    # (128+SIGTERM) — remap to the SAME paired-invalidated code the bash
    # watchdog fallback below uses, so a caller never has to know which
    # enforcement path actually fired.
    if [ "$RC" -eq 124 ]; then
        echo "SHADOW-AB TIMEOUT — $_TIMEOUT_BIN killed the session after ${TIMEOUT_SEC}s"
        RC=$EXIT_PAIR_INVALIDATED
    fi
else
    echo "SETUP: no timeout/gtimeout on PATH — enforcing ${TIMEOUT_SEC}s via bash watchdog"
    "$PYTHON" "${SHADOW_AB_ARGS[@]}" > "$SESSION_OUT" 2> "$SESSION_ERR" &
    child_pid=$!
    waited=0
    killed=0
    while kill -0 "$child_pid" 2>/dev/null; do
        if [ "$waited" -ge "$TIMEOUT_SEC" ]; then
            echo "SHADOW-AB TIMEOUT — exceeded ${TIMEOUT_SEC}s (watchdog fallback); killing pid $child_pid"
            kill -TERM "$child_pid" 2>/dev/null
            sleep 2
            kill -KILL "$child_pid" 2>/dev/null
            killed=1
            break
        fi
        sleep 1
        waited=$((waited + 1))
    done
    wait "$child_pid" 2>/dev/null
    RC=$?
    [ "$killed" -eq 1 ] && RC=$EXIT_PAIR_INVALIDATED
fi
set -e
echo "shadow-ab exit=$RC (0=valid pair, 3=precheck abort, 4=pair invalidated, 5=VOID)"
if [ "$RC" -eq 5 ]; then
    echo "SHADOW-AB VOID — config drift against the frozen experiment; operator action required"
fi
echo "=== shadow-ab session $SESSION_DATE end $(date -u +%FT%TZ) ==="
exit "$RC"
