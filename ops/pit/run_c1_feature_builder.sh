#!/bin/bash
# C1 PIT revision-drift feature builder (M-SIG C1 serving path, sprint D2).
# Turns the accrued data/estimate_snapshots/<date>/ lake into the C1 feature
# table at data/pit_features/ (a RESEARCH lake, not a prod input — flag-off
# pre-build; the confirmatory C1 test unlocks ~2027-01). The builder is
# renquant_base_data.pit_revision_features (base-data repo — feature
# derivation is base-data's; scheduling is orchestrator's per the #210 split).
#
# Ordering: runs at 15:30 PT, AFTER the 14:30 snapshotter and the 15:00
# liveness check, so it always sees today's published snapshot when one exists.
# Unlike a snapshot lapse, a builder failure is RECOVERABLE (the build is an
# incremental, deterministic function of the lake — the next run catches up),
# so the ntfy alert is informational, not a data-loss alarm.
#
# Concurrency: same kernel-released fcntl.flock launcher as the snapshotter
# (run_with_lock.py), own lock file. The wrapped command is a single
# non-forking python invocation, per that launcher's documented caveat.
# Reads the snapshot lake READ-ONLY (the builder refuses any out-root that
# overlaps the lake or a canonical path, structurally).
set -u
RQ_ROOT="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
BD_RUN_ROOT="${BD_RUN_ROOT:-/Users/renhao/git/github/renquant-base-data-run}"
LOG_DIR="$RQ_ROOT/logs/pit_snapshots"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d)"
LOCK_FILE="${PIT_C1_LOCK_FILE:-/tmp/pit_c1_feature_builder.lock}"
LOG_FILE="$LOG_DIR/c1_features_$TS.log"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Stdlib-only lock launcher on a plain interpreter (see run_with_lock.py).
LOCK_PYTHON="${PIT_LOCK_PYTHON:-python3}"

export PYTHONPATH="$BD_RUN_ROOT/src"
"$LOCK_PYTHON" "$SCRIPT_DIR/run_with_lock.py" \
  --lock-file "$LOCK_FILE" --log-file "$LOG_FILE" -- \
  "$RQ_ROOT/.venv/bin/python" -m renquant_base_data.pit_revision_features build \
  --snapshot-root "$RQ_ROOT/data/estimate_snapshots" \
  --out "$RQ_ROOT/data/pit_features"
RC=$?
if [ $RC -ne 0 ]; then
  source "$RQ_ROOT/.env" 2>/dev/null || true
  [ -n "${NTFY_TOPIC:-}" ] && curl -s -H "Title: C1 PIT feature build FAILED rc=$RC ($TS)" \
    -d "see logs/pit_snapshots/c1_features_$TS.log — recoverable (incremental rebuild next run), but investigate" \
    "ntfy.sh/$NTFY_TOPIC" >/dev/null
fi
exit $RC
