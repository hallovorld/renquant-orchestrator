#!/bin/sh
# catchup_guard.sh — boot catch-up guard for calendar-only launchd jobs.
# Born as ops/renquant105/rq105_catchup_guard.sh (orch#1085/#1087); moved here
# and generalised when the same boot (2026-08-28 10:38) turned out to have
# dropped the 06:05 dawn preflight and the 07:00 run-surface drift scan too.
# Sourced by run_batch_scores_export.sh / run_session_scheduler.sh /
# renquant104/dawn_funnel_preflight.sh / run_surface_drift_scan.sh.
#
# PORTABILITY (regression fixed after orch#1098). This file is SOURCED by
# wrappers whose shebang and plist ProgramArguments are /bin/zsh (the two
# rq105 jobs) and by wrappers that run bash (dawn preflight, drift scan); the
# CI runner executes it under bash and dash (/bin/sh). It must therefore be
# the common subset of zsh, bash and POSIX sh, under `set -u`:
#   - no `eval` of variable NAMES, no `${!name}`, no `local -n`, no arrays,
#     no `[[ ]]`, no `$'..'`, no `read -a`;
#   - no reliance on word-splitting an unquoted `$var` (zsh does NOT split by
#     default: `for x in $list` iterates ONCE over the whole string — that
#     is exactly how #1098's `eval "val=\${$req:-}"` became
#     `${RQ_ROOT CATCHUP_CUTOFF_HELPER PYTHONPATH:-}` → zsh "bad substitution"
#     → `val: parameter not set` → both rq105 wrappers exit 1);
#   - every read of a possibly-unset variable spelled `${var:-}`.
# tests/test_catchup_guard_shell_portability.py runs the decision matrix under
# each of /bin/zsh, /bin/bash, /bin/sh and asserts identical rc/stdout/stderr/
# log, and sources the guard exactly the way run_batch_scores_export.sh does.
#
# WHY. launchd fires a StartCalendarInterval slot only while the machine is
# up. A slot missed during SLEEP is coalesced on wake; a slot missed across a
# BOOT is dropped. On 2026-08-28 the host booted 10:38 local: the 06:15
# batch-score export and the 06:25 session scheduler never ran, run_shadow_
# serving.sh exited "SKIP upstream" and the liveness check said OK — and the
# 06:05 dawn preflight and the 07:00 drift scan were dropped by the same boot
# (no dawn_pin_identity_2026-08-28.json, zero 2026-08-28 lines in the drift
# scan's log). The fix is RunAtLoad=true in those plists (launchd then also
# invokes the job once at every bootstrap: boot, login, manual bootstrap) —
# and THIS guard, which makes every invocation idempotent and bounded so
# RunAtLoad can neither double-run a job nor run it at an hour where its
# output is meaningless.
#
# RULE — one decision, applied to EVERY invocation (calendar fire or load):
#   RUN   iff  slot <= local HHMM < cutoff
#         AND  at least one named output for <date> is missing
#   SKIP  otherwise (caller exits 0), after exactly ONE stamped line.
#
# <cutoff> names the job's calendar:
#   session  — the job is bound to an NYSE SESSION (its plist is Mon–Fri):
#              the cutoff is that date's ACTUAL local session close from
#              catchup_cutoff.py (early-close aware), and a non-session date
#              (weekend / holiday) REFUSES. r2 of orch#1085 (codex): a fixed
#              1300 would have exported a "pre-session" vector after a 10:00 PT
#              early close, and a weekday test would have run on Labor Day.
#   HHMM     — the job runs on EVERY calendar day (its plist has no Weekday
#              key, e.g. the 07:00 drift scan): a literal local cutoff, 2400 =
#              end of day. No calendar is consulted, so a calendar-day job
#              keeps its calendar-day behaviour and only gains the
#              missed-slot-after-boot catch-up.
#
# The session cutoff comes from catchup_cutoff.py run under the WRAPPER'S OWN
# PYTHONPATH (the pinned orchestrator src + the pin-verified renquant-common),
# so the calendar the cutoff comes from is the calendar the job imports. The
# helper's exit code is the day verdict: 0 = session (stdout HHMM), 1 =
# non-session, 2 = error. Anything but "0 and a 4-digit HHMM" is a REFUSAL
# (return 1, one stamped line, the wrapper exits 0): the job is never run
# after its session, and a broken calendar never becomes a run — the job's own
# liveness check then reports the missing output, which is the designed alarm.
#
# The guard writes to its OWN dated file (catchup_guard_<job>_<date>.log),
# never to the wrapper's evidence log: ops/launchd_manifest.json's
# evidence_glob for these jobs must witness REAL runs only, so a load-time
# skip can never read as "the job fired today" to the drift/liveness scans.
# The helper's stderr (a traceback, if any) is appended to that same guard log.
#
# No clock overrides: the caller passes the date and HHMM explicitly ($TS /
# $(date +%H%M) in the wrappers), which is what makes the function testable
# without any process-environment switch. The environment it DOES require is
# the wrapper's already-established one: RQ_ROOT (whose .venv runs the helper)
# always; CATCHUP_CUTOFF_HELPER (the helper's path) and PYTHONPATH (what it
# imports) in `session` mode — absent any of these the guard returns 2, never
# a silent skip.
#
# Returns 0 = run, 1 = skip, 2 = usage error (the caller treats 2 as FATAL,
# never as a silent skip).
launchd_catchup_guard() {
  if [ "$#" -lt 7 ]; then
    echo "usage: launchd_catchup_guard <job> <date YYYY-MM-DD> <now HHMM> <slot HHMM> <cutoff session|HHMM> <guard_log> <output>..." >&2
    return 2
  fi
  job="$1"; day="$2"; now_hhmm="$3"; slot="$4"; cutoff_spec="$5"; guard_log="$6"
  shift 6
  case "$day" in
    [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;;
    *) echo "launchd_catchup_guard: date must be YYYY-MM-DD (got '$day')" >&2; return 2 ;;
  esac
  # Decimal, not octal: strip leading zeros before arithmetic comparison so
  # "0830" can never be read as an (invalid) octal literal by any sh.
  now_n=$(printf '%s' "$now_hhmm" | sed 's/^0*//'); now_n="${now_n:-0}"
  slot_n=$(printf '%s' "$slot" | sed 's/^0*//'); slot_n="${slot_n:-0}"
  case "$now_n$slot_n" in
    *[!0-9]*) echo "launchd_catchup_guard: non-numeric HHMM ($now_hhmm / $slot)" >&2; return 2 ;;
  esac
  case "$cutoff_spec" in
    session) ;;
    [0-9][0-9][0-9][0-9]) ;;
    *) echo "launchd_catchup_guard: cutoff must be 'session' or a literal HHMM (got '$cutoff_spec')" >&2; return 2 ;;
  esac
  # Required environment, checked by NAME + VALUE pairs: no eval, no indirect
  # expansion, no word-splitting of a name list (zsh does not split; see the
  # PORTABILITY note above). Every read is `${VAR:-}` so `set -u` never fires.
  _require_env() {
    if [ -z "$2" ]; then
      echo "launchd_catchup_guard: $1 must be set by the sourcing wrapper before the guard (the cutoff comes from the pinned calendar)" >&2
      return 2
    fi
    return 0
  }
  _require_env RQ_ROOT "${RQ_ROOT:-}" || return 2
  if [ "$cutoff_spec" = "session" ]; then
    _require_env CATCHUP_CUTOFF_HELPER "${CATCHUP_CUTOFF_HELPER:-}" || return 2
    _require_env PYTHONPATH "${PYTHONPATH:-}" || return 2
  fi
  _stamp() {
    printf '%s [catch-up guard %s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$job" "$*" >> "$guard_log"
  }
  if [ "$cutoff_spec" = "session" ]; then
    py="$RQ_ROOT/.venv/bin/python"
    [ -x "$py" ] || py="python3"
    cutoff=$("$py" "$CATCHUP_CUTOFF_HELPER" --date "$day" 2>> "$guard_log")
    cutoff_rc=$?
    case "$cutoff_rc:$cutoff" in
      0:[0-9][0-9][0-9][0-9]) ;;
      *)
        _stamp "SKIP calendar refused catch-up for $day (helper rc=$cutoff_rc: ${cutoff:-no output}): $job runs only inside an NYSE session"
        echo "launchd_catchup_guard: $job refused for $day (helper rc=$cutoff_rc: ${cutoff:-no output})" >&2
        return 1 ;;
    esac
    cutoff_why="$day session close $cutoff local"
  else
    cutoff="$cutoff_spec"
    cutoff_why="literal cutoff $cutoff local, calendar-day job"
  fi
  cutoff_n=$(printf '%s' "$cutoff" | sed 's/^0*//'); cutoff_n="${cutoff_n:-0}"
  if [ "$now_n" -lt "$slot_n" ]; then
    _stamp "SKIP local $now_hhmm is before the $slot slot: the calendar fire owns it"; return 1
  fi
  if [ "$now_n" -ge "$cutoff_n" ]; then
    _stamp "SKIP local $now_hhmm is at/after the $cutoff cutoff ($cutoff_why): too late for a catch-up run (outputs: $*)"; return 1
  fi
  for f in "$@"; do
    if [ ! -f "$f" ]; then
      _stamp "RUN local $now_hhmm in [$slot,$cutoff) ($cutoff_why), missing output: $f"
      return 0
    fi
  done
  _stamp "SKIP today's output already present (idempotent): $*"
  return 1
}
