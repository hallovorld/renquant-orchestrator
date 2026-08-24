#!/bin/zsh
# Single reviewed answer to "which renquant-common does an rq105 job import?"
#
# It is the copy the umbrella PINS, verified against the pin before import:
#
#     <RQ_ROOT>/.subrepo_runtime/repos/renquant-common/src
#     <RQ_ROOT>/subrepos.lock.json -> subrepos[renquant-common].commit
#
# WHY (orch#1016). Every rq105 wrapper used to carry its own copy of
#
#     RQ_COMMON_SRC=".../renquant-common-run/src"
#     [ -d "$RQ_COMMON_SRC" ] || RQ_COMMON_SRC=".../renquant-common/src"
#
# so which copy executed was decided by filesystem state, not by review — and
# `renquant-common-run` is absent here, so every job imported the mutable dev
# working tree. run_session_scheduler.sh made it worse by placing that sibling
# BEFORE $SUBREPO/renquant-common/src on PYTHONPATH: the pinned copy was already
# there, and was being shadowed by the unpinned one.
#
# A directory NAME is not a revision, so this does not merely pick a path. The
# resolution and the pin check live in rq105_pinned_common.py — ONE
# implementation for shell and python, because two implementations of a pin
# check are two chances to disagree about what is pinned.
#
# There is deliberately NO fallback and NO env override of which checkout: an
# unreviewed process environment must not be able to choose the code while the
# drift scan reports the choice as reviewed. RQ_ROOT remains configurable — it
# is the deployment root every wrapper already parameterises — and the pin is
# verified inside whichever root is given.

# The sourcing wrapper passes its own directory in RQ105_OPS_DIR. Deliberately
# NOT `${0:A:h}`: that is zsh-only and expands to empty under bash/sh, so the CI
# runner (ubuntu, no zsh) could not execute this function at all — the tests
# would have to skip, and a check that skips is a check that covers nothing.
# Explicit beats clever here; the caller always knows its own directory.
rq105_resolve_common_src() {
  rq_root="${RQ_ROOT:?RQ_ROOT must be set}"
  ops_dir="${RQ105_OPS_DIR:?RQ105_OPS_DIR must be set by the sourcing wrapper}"
  py="$rq_root/.venv/bin/python"
  [ -x "$py" ] || py="python3"
  resolved="$("$py" "$ops_dir/rq105_pinned_common.py" --rq-root "$rq_root" --print-src)" || return 1
  [ -n "$resolved" ] || { echo "FATAL: pinned-common resolver printed nothing" >&2; return 1; }
  RQ_COMMON_SRC="$resolved"
  export RQ_COMMON_SRC
}
