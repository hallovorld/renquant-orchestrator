#!/bin/zsh
# rq105 N1: session-long intraday quote logger (OBSERVE-ONLY; #208 Stage-1, #231 N1).
# Runs from a PINNED orchestrator checkout (RQ105_ORCH_ROOT), never the working tree.
# The logger self-loops on --cadence with an internal NYSE session gate; launchd
# starts it pre-open each weekday and it exits after the close.
#
# GOAL-5 FAIL-LOUD (2026-07-22): the collector stalled SILENTLY mid-session on
# 07-14/16/17/20/22 — intraday_ticks.jsonl froze ~08:37 while the session ran to
# 13:00 PT, with NO error logged (empty .err, 0-byte day log) and NO ntfy, so the
# stall was a black box discovered hours later at the 14:00 PT liveness check.
# Root cause of the SILENCE (NOT of the stall — that needs a live observation):
# the old wrapper ran the collector in the FOREGROUND and only checked $? AFTER
# it returned, so (a) a hang never returns -> the check is never reached, and
# (b) a process-group kill (launchd unload / system sleep / OOM) takes out the
# wrapper before the check. The day log is 0-byte because the module emits
# nothing to stdout/stderr during normal operation.
#
# This wrapper now makes the NEXT stall diagnosable + immediately alerting:
#   (1) CAPTURE ANY termination — non-zero exit / crash / caught signal / an
#       unexpected clean early exit — via traps + a background wait, writing the
#       exit code + day-log tail + timestamp to a dedicated NON-EMPTY crash log
#       (logs/rq105/quote_logger_crash_<date>.log) and firing an UN-MISSABLE ntfy.
#   (2) a lightweight background feed-staleness WATCHDOG that catches a SILENT
#       HANG (feed frozen while the collector process is still alive) the SAME
#       session, instead of hours later at 14:00 PT.
# It touches ONLY its own logs and READS the feed's mtime — it changes nothing in
# the observe-only collector module and can place no orders. It does NOT try to
# fix the unknown root cause of the stall; it makes that root cause observable.
set -u
RQ_ROOT="${RQ_ROOT:-/Users/renhao/git/github/RenQuant}"
RQ105_ORCH_ROOT="${RQ105_ORCH_ROOT:-/Users/renhao/git/github/renquant-orchestrator-run}"
LOG_DIR="$RQ_ROOT/logs/rq105"
mkdir -p "$LOG_DIR"
TS="$(date +%Y-%m-%d)"
DAY_LOG="$LOG_DIR/quote_logger_$TS.log"
CRASH_LOG="$LOG_DIR/quote_logger_crash_$TS.log"
# Campaign B5: the orchestrator session-calendar primitive now lives in
# renquant_common.market_calendar — put a sibling renquant-common checkout on
# PYTHONPATH (pinned -run checkout preferred; the venv install alone may
# predate market_calendar).
RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common-run/src"
[ -d "$RQ_COMMON_SRC" ] || RQ_COMMON_SRC="$(dirname "$RQ105_ORCH_ROOT")/renquant-common/src"
export PYTHONPATH="$RQ105_ORCH_ROOT/src:$RQ_COMMON_SRC"

# Collector binary. Env-overridable ONLY so a test can substitute a stub; the
# production path is the pinned RenQuant venv python, unchanged.
PY_BIN="${RQ105_PYTHON_BIN:-$RQ_ROOT/.venv/bin/python}"

# Un-missable-alert config (mirrors rq105_liveness_check._ALERT_*): a 105-DOWN
# alert shares the "renquant" topic with every other sentinel, so make it stand
# out — urgent priority + distinctive tags + an unmistakable title. Optional
# RQ105_NTFY_TOPIC routes 105-down to a dedicated topic; unset -> notify.sh's
# normal resolution ($RQ/.env NTFY_TOPIC -> fleet default "renquant").
ALERT_PRIORITY="${RQ105_ALERT_PRIORITY:-urgent}"
ALERT_TAGS="${RQ105_ALERT_TAGS:-rotating_light,rq105}"
if [ -n "${RQ105_NTFY_TOPIC:-}" ]; then export NTFY_TOPIC="$RQ105_NTFY_TOPIC"; fi

# Fail-loud thresholds (all env-overridable; defaults chosen to NOT false-alarm
# on a normal session or a half-day early close). Times are LOCAL (PT), matching
# the launchd schedule / the machine timezone.
FEED_PATH="${RQ105_FEED_PATH:-$RQ_ROOT/logs/renquant105_pilot/intraday_ticks.jsonl}"
# A clean (rc=0) exit sooner than this many seconds after start is an unexpected
# EARLY stop (e.g. the calendar/gate wrongly reported "closed" mid-session). A
# full session start(06:25 PT)->close(13:00 PT) is ~6.5h; a half-day early close
# is ~3.5h; 3h (10800s) clears half-days yet catches an 08:37-PT stop (~2.2h in).
MIN_SESSION_SECONDS="${RQ105_MIN_SESSION_SECONDS:-10800}"
WATCHDOG_INTERVAL="${RQ105_WATCHDOG_INTERVAL:-300}"           # poll every 5 min
WATCHDOG_STALE_SECONDS="${RQ105_WATCHDOG_STALE_SECONDS:-900}" # feed frozen >=15 min = stall (feed cadence is 60s)
WATCHDOG_START_HHMM="${RQ105_WATCHDOG_START_HHMM:-0645}"      # 15 min after 06:30 PT open (let first writes land)
WATCHDOG_END_HHMM="${RQ105_WATCHDOG_END_HHMM:-1300}"         # 13:00 PT close

# GOAL-5 AUTO-RESTART (2026-07-22): the plist now carries KeepAlive
# SuccessfulExit=false, so a mid-session CRASH (non-zero exit / signal death)
# auto-restarts the collector instead of leaving it dead-for-the-day (the old
# plist fired ONCE at 06:25 with no KeepAlive). launchd KeepAlive has NO
# time-of-day condition, so THIS wrapper is the session gate: outside the window
# we exit 0 (clean) BEFORE launching anything, so KeepAlive never respawns the
# job off-session (nights / pre-open / post-close). Weekend/holiday non-sessions
# are already covered — the plist is weekday-only and the collector's own NYSE
# calendar makes it exit 0 on a holiday (a clean exit -> no respawn).
SESSION_START_HHMM="${RQ105_SESSION_START_HHMM:-0625}"       # launchd fire time (PT)
SESSION_END_HHMM="${RQ105_SESSION_END_HHMM:-1300}"          # 13:00 PT close
# On a detected SILENT HANG the watchdog kills the (observe-only, order-less)
# collector so its non-zero exit lets KeepAlive auto-restart it — a hang is
# otherwise invisible to KeepAlive (the process never exits). Set 0 to alert-only.
WATCHDOG_KILL="${RQ105_WATCHDOG_KILL:-1}"
# ntfy cooldown: KeepAlive can respawn a PERSISTENTLY-crashing collector every
# ThrottleInterval, so rate-limit the un-missable alert (the crash LOG is still
# written EVERY time) to avoid an urgent-priority storm. First alert always fires.
ALERT_COOLDOWN_SECONDS="${RQ105_ALERT_COOLDOWN_SECONDS:-1800}"
ALERT_STAMP="$LOG_DIR/.rq105_alert_cooldown"

# Session-window guard (must run BEFORE any trap is installed, so this exit is a
# plain clean exit that KeepAlive treats as success).
_now_hm=$(( 10#$(date +%H%M) ))
if [ "$_now_hm" -lt "$(( 10#$SESSION_START_HHMM ))" ] || [ "$_now_hm" -ge "$(( 10#$SESSION_END_HHMM ))" ]; then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] rq105 quote logger: current time outside the session window ${SESSION_START_HHMM}-${SESSION_END_HHMM} PT — clean no-op exit 0 (KeepAlive must not respawn off-session)" >> "$DAY_LOG"
  exit 0
fi

START_EPOCH="$(date +%s)"
TERM_SIGNAL=""

# Un-missable notifier (canonical shell sender; priority+tags are positional
# args 3/4 of rq_notify — see RenQuant/scripts/notify.sh).
rq105_alert() {  # $1 title  $2 body
  # Cooldown: suppress a REPEAT ntfy within the window (the crash LOG is written
  # by the caller regardless) so a KeepAlive respawn loop can't storm the topic.
  _now="$(date +%s)"
  if [ -f "$ALERT_STAMP" ]; then
    _last="$(cat "$ALERT_STAMP" 2>/dev/null || echo 0)"
    [ -z "$_last" ] && _last=0
    if [ $(( _now - _last )) -lt "$ALERT_COOLDOWN_SECONDS" ]; then
      return 0
    fi
  fi
  echo "$_now" > "$ALERT_STAMP" 2>/dev/null || true
  . "$RQ_ROOT/scripts/notify.sh" 2>/dev/null || true
  if typeset -f rq_notify >/dev/null 2>&1; then
    rq_notify "$1" "$2" "$ALERT_PRIORITY" "$ALERT_TAGS" || true
  fi
}

# Crash record: exit code + timestamp + a tail of the (usually empty) day log,
# to a dedicated NON-EMPTY crash log, then one un-missable alert.
rq105_emit_crash() {  # $1 rc-label  $2 reason  $3 elapsed-seconds  $4 alert-title
  _stamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  {
    echo "[$_stamp] rq105 quote logger TERMINATED rc=$1 elapsed=${3}s — $2"
    echo "--- tail(40) of $DAY_LOG ---"
    if [ -s "$DAY_LOG" ]; then
      tail -n 40 "$DAY_LOG"
    else
      echo "(day log EMPTY — collector emitted no stdout/stderr; this is the silent-stall black box)"
    fi
    echo "--- end tail ---"
    echo
  } >> "$CRASH_LOG" 2>&1
  rq105_alert "$4" "rc=$1 ($TS) — $2; crash log: logs/rq105/quote_logger_crash_$TS.log"
}

_RAN_CAPTURE=""
_finish() {
  [ -n "${_RAN_CAPTURE:-}" ] && return
  _RAN_CAPTURE=1
  if [ -n "${WATCHDOG_PID:-}" ]; then
    # Reap the watchdog subshell AND its in-flight `sleep` child so nothing
    # lingers holding an inherited descriptor (child first, while the parent
    # still owns it).
    pkill -P "$WATCHDOG_PID" 2>/dev/null || true
    kill "$WATCHDOG_PID" 2>/dev/null || true
  fi
  _elapsed=$(( $(date +%s) - START_EPOCH ))
  if [ -n "${TERM_SIGNAL:-}" ]; then
    rq105_emit_crash "sig:$TERM_SIGNAL" \
      "wrapper caught SIG$TERM_SIGNAL (launchd unload / system sleep / manual kill) mid-run" \
      "$_elapsed" "🚨 rq105 DOWN — quote collector killed (SIG$TERM_SIGNAL)"
  elif [ "${COLLECTOR_RC:-0}" -ne 0 ]; then
    rq105_emit_crash "${COLLECTOR_RC:-?}" \
      "collector exited NON-ZERO (crash / unhandled error)" \
      "$_elapsed" "🚨 rq105 DOWN — quote collector crashed"
  elif [ "$_elapsed" -lt "$MIN_SESSION_SECONDS" ]; then
    rq105_emit_crash "0" \
      "collector exited CLEANLY but only ${_elapsed}s in (< ${MIN_SESSION_SECONDS}s) — unexpected early stop" \
      "$_elapsed" "🚨 rq105 DOWN — quote collector stopped early"
  fi
  # else: normal full-session completion (rc=0 after running the whole session) — no alert.
}

# Background feed-staleness watchdog: catch a SILENT HANG (process alive but feed
# frozen) the same session. Reads only the feed's mtime; alerts ONCE per run.
rq105_watchdog() {  # expects COLLECTOR_PID in the environment
  _wd_alerted=""
  _wstart=$(( 10#$WATCHDOG_START_HHMM ))
  _wend=$(( 10#$WATCHDOG_END_HHMM ))
  while :; do
    sleep "$WATCHDOG_INTERVAL"
    [ -n "$_wd_alerted" ] && continue
    _hm=$(( 10#$(date +%H%M) ))
    { [ "$_hm" -lt "$_wstart" ] || [ "$_hm" -ge "$_wend" ]; } && continue
    kill -0 "$COLLECTOR_PID" 2>/dev/null || continue   # collector gone -> _finish handles it
    [ -f "$FEED_PATH" ] || continue
    _mtime="$(stat -f %m "$FEED_PATH" 2>/dev/null || echo 0)"
    _age=$(( $(date +%s) - _mtime ))
    if [ "$_age" -ge "$WATCHDOG_STALE_SECONDS" ]; then
      _wd_alerted=1
      _stamp="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
      echo "[$_stamp] rq105 SILENT STALL — $FEED_PATH frozen ${_age}s (>= ${WATCHDOG_STALE_SECONDS}s) while collector PID $COLLECTOR_PID is STILL ALIVE (hang)" >> "$CRASH_LOG"
      rq105_alert "🚨 rq105 DOWN — tick feed frozen (collector hung)" \
        "intraday_ticks.jsonl not written for ${_age}s during the session ($TS) while the collector process is still alive — likely hung. crash log: logs/rq105/quote_logger_crash_$TS.log"
      if [ "$WATCHDOG_KILL" != "0" ]; then
        # Kill the hung (observe-only) collector so its non-zero exit lets
        # KeepAlive auto-restart it — a hang is otherwise invisible to KeepAlive.
        echo "[$_stamp] watchdog KILLING hung collector PID $COLLECTOR_PID so KeepAlive can auto-restart it" >> "$CRASH_LOG"
        kill -TERM "$COLLECTOR_PID" 2>/dev/null || true
        sleep 5
        kill -KILL "$COLLECTOR_PID" 2>/dev/null || true
      fi
    fi
  done
}

# Run the collector in the BACKGROUND so the wrapper survives to capture its
# termination, then start the watchdog once the collector PID is known.
"$PY_BIN" -m renquant_orchestrator.intraday_quote_logger \
  --env-file "$RQ_ROOT/.env" \
  --data-root "$RQ_ROOT" \
  --log-level INFO \
  >> "$DAY_LOG" 2>&1 &
COLLECTOR_PID=$!

# The watchdog writes only to the crash log + ntfy; keep it off the wrapper's
# own stdout/stderr so an in-flight `sleep` can never hold a captured pipe open
# after the wrapper exits (also keeps watchdog chatter out of the launchd .out).
rq105_watchdog >/dev/null 2>&1 &
WATCHDOG_PID=$!

trap 'TERM_SIGNAL=TERM; kill "$COLLECTOR_PID" 2>/dev/null || true' TERM
trap 'TERM_SIGNAL=INT;  kill "$COLLECTOR_PID" 2>/dev/null || true' INT
trap 'TERM_SIGNAL=HUP;  kill "$COLLECTOR_PID" 2>/dev/null || true' HUP
trap '_finish' EXIT

wait "$COLLECTOR_PID"
COLLECTOR_RC=$?
_finish
exit "$COLLECTOR_RC"
