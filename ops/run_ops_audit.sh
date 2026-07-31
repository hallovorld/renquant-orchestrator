#!/usr/bin/env bash
# ops-audit — one scheduled surface for the read-only detectors (issue #649).
#
# EVIDENCE ORDERING follows the #638 review: prerequisites first, run into a temp
# file, publish by atomic rename only after the aggregator returned. The dated log's
# EXISTENCE is therefore proof the audit ran — never a fresh mtime from a setup that
# failed before it started.
set -uo pipefail

REPO_DIR="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
PYTHON="$REPO_DIR/.venv/bin/python"
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$REPO_DIR/logs/ops_audit"
LOG="$LOG_DIR/ops_audit_$(date +%F).log"

fail() { echo "PREREQ FAILED: $*" >&2; exit 4; }
[ -d "$REPO_DIR" ]  || fail "umbrella root absent: $REPO_DIR"
[ -x "$PYTHON" ]    || fail "interpreter not executable: $PYTHON"
[ -r "$SELF_DIR/ops_audit.py" ] || fail "ops_audit.py not beside this wrapper"
"$PYTHON" -c "import ast,sys; ast.parse(open('$SELF_DIR/ops_audit.py').read())" \
    || fail "ops_audit.py does not parse"
mkdir -p "$LOG_DIR" || fail "cannot create $LOG_DIR"

TMP="$(mktemp "${LOG}.XXXXXX")" || fail "cannot create temp log beside $LOG"
trap 'rm -f "$TMP"' EXIT

{
  echo "=== ops-audit start $(date '+%F %T %Z') ==="
  echo "--- read-only: every member is checked for write calls by test_no_member_writes"
} >>"$TMP" 2>&1

"$PYTHON" "$SELF_DIR/ops_audit.py" 2>&1 | tee -a "$TMP"
RC="${PIPESTATUS[0]}"

{
  echo "--- ops-audit exit=$RC (0 clean | 1 a detector found something | 3 a detector could not run)"
  echo "=== ops-audit end $(date '+%F %T %Z') ==="
} >>"$TMP" 2>&1

mv -f "$TMP" "$LOG" || { echo "could not publish evidence to $LOG" >&2; exit 5; }
trap - EXIT
exit "$RC"
