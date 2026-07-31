#!/usr/bin/env bash
# RQ104 silent-refusal sentinel (GOAL-5 AC5) — wrapper that produces DATED evidence.
#
# WHY THIS WRAPPER EXISTS. The sentinel itself has been merged and unscheduled;
# running it by hand on 2026-07-31 for the first time it immediately reported
# `weekly-retrain-patchtst` dead for four weeks (4 non-acting runs, 3 of them
# CRASHED, one reproducible cause). The first version of this job's plist sent
# stdout to `logs/rq104/launchd_silent_refusal.out` — an APPEND-ONLY file with no
# date in its name. That is the exact anti-pattern measured on the drift scan the
# same night (orch#663): 0 of 18 lines there began with a date, so no line belonged
# to any run, and a RESOLVED containment alarm was indistinguishable from a live
# one. Shipping a new job with that shape would have been building the defect in.
#
# So this wrapper writes `logs/rq104/silent_refusal_<YYYY-MM-DD>.log`, which is what
# the manifest's `evidence_glob` reads and what the liveness scan can score. The
# launchd .out/.err remain, but only for output from a run that never got far
# enough to produce its own evidence.
#
# EVIDENCE ORDERING — lifted deliberately from run_model_freshness_monitor.sh,
# where it was a codex BLOCKER on orch#638. Prerequisites and the import probe run
# BEFORE the dated file is created, so the file's EXISTENCE is proof the sentinel
# actually ran. Creating it first would leave a freshly-mtimed evidence file after a
# setup failure, and any scan reading that glob would report the job alive.
#
# EXIT CODES pass through the sentinel's own mapping; the code alone cannot separate
# "found something" from "crashed", which is the #622 lesson — hence the dated log.
set -uo pipefail

REPO_DIR="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
ORCH_DIR="${RQ_ORCH_ROOT:-/Users/renhao/git/github/renquant-orchestrator-run}"
PYTHON="$REPO_DIR/.venv/bin/python"
LOG_DIR="$REPO_DIR/logs/rq104"
LOG="$LOG_DIR/silent_refusal_$(date +%F).log"
SENTINEL="$ORCH_DIR/ops/renquant104/rq104_silent_refusal_sentinel.py"

# --- 1. prerequisites. Every failure exits non-zero WITHOUT creating $LOG. -------
fail() { echo "PREREQ FAILED: $*" >&2; exit 4; }

[ -d "$REPO_DIR" ]  || fail "umbrella root absent: $REPO_DIR"
[ -d "$ORCH_DIR" ]  || fail "orchestrator run checkout absent: $ORCH_DIR"
[ -x "$PYTHON" ]    || fail "interpreter not executable: $PYTHON"
[ -r "$SENTINEL" ]  || fail "sentinel unreadable: $SENTINEL"

set -a; source "$REPO_DIR/.env" 2>/dev/null; set +a   # optional by design
export PYTHONPATH="$ORCH_DIR/src:$ORCH_DIR/ops:$ORCH_DIR/ops/renquant104:${PYTHONPATH:-}"

# The sentinel must IMPORT before we commit to producing evidence: a PYTHONPATH that
# resolves to the wrong checkout would otherwise still land a dated log.
"$PYTHON" - "$SENTINEL" <<'PROBE' 2>/dev/null || fail "sentinel not importable under the resolved PYTHONPATH"
import importlib.util, sys
spec = importlib.util.spec_from_file_location("_probe", sys.argv[1])
mod = importlib.util.module_from_spec(spec)
sys.modules["_probe"] = mod
spec.loader.exec_module(mod)
PROBE

mkdir -p "$LOG_DIR" || fail "cannot create $LOG_DIR"

# --- 2. run into a TEMP file; the evidence path stays untouched until step 3. ----
TMP="$(mktemp "${LOG}.XXXXXX")" || fail "cannot create temp log beside $LOG"
trap 'rm -f "$TMP"' EXIT

{
  echo "=== rq104 silent-refusal sentinel start $(date '+%F %T %Z') ==="
  echo "--- observe-only: reads job history + notifies; changes no job and no state"
} >>"$TMP" 2>&1

# tee is LAST in the pipe, so PIPESTATUS[0] is the only faithful read of the
# sentinel's own status. The exit code is the payload; it must not be swallowed.
"$PYTHON" "$SENTINEL" 2>&1 | tee -a "$TMP"
RC="${PIPESTATUS[0]}"

echo "=== rq104 silent-refusal sentinel finished rc=$RC $(date '+%F %T %Z') ===" >>"$TMP"

# --- 3. commit the evidence atomically, only now that the run happened. ---------
mv -f "$TMP" "$LOG" || { echo "could not commit evidence to $LOG" >&2; exit 5; }
trap - EXIT
exit "$RC"
