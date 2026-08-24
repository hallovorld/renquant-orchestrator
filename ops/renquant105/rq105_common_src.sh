#!/bin/zsh
# Single reviewed answer to "which renquant-common does an rq105 job import?"
#
# WHY THIS FILE EXISTS (orch#1016). Every rq105 wrapper used to carry its own
# copy of a two-line fallback:
#
#     RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common-run/src"
#     [ -d "$RQ_COMMON_SRC" ] || RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common/src"
#
# The drift scanner's phrasing is the finding: *which copy executes is decided
# by filesystem state, not by review*. Three consequences, all live:
#   1. invisible in the normal case — the jobs work either way;
#   2. it flips SILENTLY — the day anyone creates renquant-common-run/, five
#      scheduled jobs change which code they run, with no commit and no review;
#   3. today the `else` branch wins on every job, so scheduled production work
#      imports a DEV working tree governed by no pin.
#
# WHAT THIS RECORDS, AND WHAT IT DOES NOT. `RQ105_COMMON_CHECKOUT` below is a
# RECORD of which checkout actually runs today — not an endorsement of it.
# Pointing scheduled jobs at a dev tree is its own problem and is NOT fixed
# here. What is fixed is that the answer now lives in a reviewed file: changing
# it takes a commit, and creating a sibling directory no longer changes
# anything. Migrating to a pinned `-run` checkout is a one-line change to this
# constant, made deliberately, with the checkout created first.
#
# There is deliberately NO fallback. If the named checkout is absent this exits
# non-zero rather than importing a different copy of the code: a job that cannot
# resolve its own dependency must stop, not guess.

RQ105_COMMON_CHECKOUT="${RQ105_COMMON_CHECKOUT:-renquant-common}"

rq105_resolve_common_src() {
  local repos_root="$(dirname "${RQ105_ORCH_ROOT:?RQ105_ORCH_ROOT must be set}")"
  local candidate="$repos_root/$RQ105_COMMON_CHECKOUT/src"
  if [ ! -d "$candidate" ]; then
    echo "FATAL: renquant-common checkout '$RQ105_COMMON_CHECKOUT' not found at $candidate." >&2
    echo "       Refusing to fall back to another copy — which code runs is a reviewed" >&2
    echo "       decision (orch#1016). Fix the checkout, or change RQ105_COMMON_CHECKOUT" >&2
    echo "       in ops/renquant105/rq105_common_src.sh via review." >&2
    return 1
  fi
  RQ_COMMON_SRC="$candidate"
  export RQ_COMMON_SRC
}
