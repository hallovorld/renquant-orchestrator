#!/bin/sh
# rq105_catchup_guard.sh — boot catch-up guard for calendar-only launchd jobs
# (orch#1085). Sourced by run_batch_scores_export.sh / run_session_scheduler.sh;
# POSIX sh so the CI runner (ubuntu, bash, no zsh) can execute it in tests.
#
# WHY. launchd fires a StartCalendarInterval slot only while the machine is
# up. A slot missed during SLEEP is coalesced on wake; a slot missed across a
# BOOT is dropped. On 2026-08-28 the host booted 10:38 local: the 06:15
# batch-score export and the 06:25 session scheduler never ran, run_shadow_
# serving.sh exited "SKIP upstream" and the liveness check said OK. The fix
# is RunAtLoad=true in those plists (launchd then also invokes the job once
# at every bootstrap: boot, login, manual bootstrap) — and THIS guard, which
# makes every invocation idempotent and bounded so RunAtLoad can neither
# double-run a job nor run it at an hour where its output is meaningless.
#
# RULE — one decision, applied to EVERY invocation (calendar fire or load):
#   RUN   iff  weekday (Mon-Fri)
#         AND  slot <= local HHMM < cutoff
#         AND  at least one named output for today is missing
#   SKIP  otherwise (caller exits 0), after exactly ONE stamped line.
#
# The guard writes to its OWN dated file (catchup_guard_<job>_<date>.log),
# never to the wrapper's evidence log: ops/launchd_manifest.json's
# evidence_glob for these jobs must witness REAL runs only, so a load-time
# skip can never read as "the job fired today" to the drift/liveness scans.
#
# No clock/env overrides: the caller passes weekday and HHMM explicitly
# ($(date +%u) / $(date +%H%M) in the wrappers), which is what makes the
# function testable without any process-environment switch.
#
# Returns 0 = run, 1 = skip, 2 = usage error (the caller treats 2 as FATAL,
# never as a silent skip).
rq105_catchup_guard() {
  if [ "$#" -lt 7 ]; then
    echo "usage: rq105_catchup_guard <job> <dow 1-7> <now HHMM> <slot HHMM> <cutoff HHMM> <guard_log> <output>..." >&2
    return 2
  fi
  job="$1"; dow="$2"; now_hhmm="$3"; slot="$4"; cutoff="$5"; guard_log="$6"
  shift 6
  # Decimal, not octal: strip leading zeros before arithmetic comparison so
  # "0830" can never be read as an (invalid) octal literal by any sh.
  now_n=$(printf '%s' "$now_hhmm" | sed 's/^0*//'); now_n="${now_n:-0}"
  slot_n=$(printf '%s' "$slot" | sed 's/^0*//'); slot_n="${slot_n:-0}"
  cutoff_n=$(printf '%s' "$cutoff" | sed 's/^0*//'); cutoff_n="${cutoff_n:-0}"
  case "$dow$now_n$slot_n$cutoff_n" in
    *[!0-9]*) echo "rq105_catchup_guard: non-numeric dow/HHMM ($dow / $now_hhmm / $slot / $cutoff)" >&2; return 2 ;;
  esac
  _stamp() {
    printf '%s [catch-up guard %s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$job" "$*" >> "$guard_log"
  }
  case "$dow" in
    6|7) _stamp "SKIP weekend (weekday=$dow): $job is Mon-Fri only"; return 1 ;;
  esac
  if [ "$now_n" -lt "$slot_n" ]; then
    _stamp "SKIP local $now_hhmm is before the $slot slot: the calendar fire owns it"; return 1
  fi
  if [ "$now_n" -ge "$cutoff_n" ]; then
    _stamp "SKIP local $now_hhmm is at/after the $cutoff cutoff: too late for a pre-session run (outputs: $*)"; return 1
  fi
  for f in "$@"; do
    if [ ! -f "$f" ]; then
      _stamp "RUN local $now_hhmm in [$slot,$cutoff), weekday=$dow, missing output: $f"
      return 0
    fi
  done
  _stamp "SKIP today's output already present (idempotent): $*"
  return 1
}
