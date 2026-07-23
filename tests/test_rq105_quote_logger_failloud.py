"""GOAL-5 fail-loud tests for ops/renquant105/run_quote_logger.sh.

The collector stalled SILENTLY mid-session on 07-14..07-22 (intraday_ticks.jsonl
froze ~08:37 while the session ran to 13:00 PT) with NO error and NO ntfy — the
wrapper only checked $? AFTER a FOREGROUND collector returned, so a hang (never
returns) or a process-group kill (wrapper dies first) produced nothing. These
tests drive the rewritten wrapper end-to-end with a STUB collector + a STUB ntfy
sender (no venv, no network) and assert it now (1) captures a termination reason
to a dedicated NON-EMPTY crash log + fires an UN-MISSABLE alert on a non-zero
exit, and (2) catches a SILENT HANG (feed frozen while the collector process is
alive) via its background watchdog.

macOS-only: the wrapper is a zsh launchd job using BSD `stat -f`/`date`, so the
suite skips off darwin / without zsh (matching where the job actually runs)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

import pytest

WRAPPER = (
    Path(__file__).resolve().parent.parent
    / "ops" / "renquant105" / "run_quote_logger.sh"
)

pytestmark = pytest.mark.skipif(
    sys.platform != "darwin" or shutil.which("zsh") is None,
    reason="run_quote_logger.sh is a macOS/zsh launchd job (BSD stat/date)",
)

# Fake canonical sender: the wrapper sources "$RQ_ROOT/scripts/notify.sh" and
# calls rq_notify "$title" "$body" "$priority" "$tags"; record every call so a
# test can assert the priority/tags/title without hitting the network.
_FAKE_NOTIFY = (
    "rq_notify() { "
    "printf 'TITLE=%s\\nBODY=%s\\nPRIO=%s\\nTAGS=%s\\n---\\n' "
    '"$1" "$2" "${3:-}" "${4:-}" >> "$RQ_ROOT/notify_record.txt"; }\n'
)


def _scratch_rq_root(tmp_path: Path) -> Path:
    rq = tmp_path / "rq"
    (rq / "scripts").mkdir(parents=True)
    (rq / "logs" / "rq105").mkdir(parents=True)
    (rq / "logs" / "renquant105_pilot").mkdir(parents=True)
    (rq / "scripts" / "notify.sh").write_text(_FAKE_NOTIFY, encoding="utf-8")
    return rq


def _fake_collector(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "fake_collector.sh"
    p.write_text("#!/bin/sh\n" + body, encoding="utf-8")
    p.chmod(0o755)
    return p


def _run_wrapper(rq: Path, env_overrides: dict, *, timeout: float = 30.0):
    env = os.environ.copy()
    env.update(
        {
            "RQ_ROOT": str(rq),
            # Keep PYTHONPATH probes harmless; the stub collector ignores them.
            "RQ105_ORCH_ROOT": str(rq / "orch-run"),
            "RENQUANT_NO_NOTIFY": "",  # the stub sender records regardless
            # Run "in window" regardless of the real wall clock, so neither the
            # KeepAlive session-window guard nor the watchdog's own active window
            # short-circuits the test. The outside-window test overrides the
            # session bounds explicitly.
            "RQ105_SESSION_START_HHMM": "0000",
            "RQ105_SESSION_END_HHMM": "2359",
            "RQ105_WATCHDOG_START_HHMM": "0000",
            "RQ105_WATCHDOG_END_HHMM": "2359",
        }
    )
    env.pop("NTFY_TOPIC", None)
    env.pop("RQ105_NTFY_TOPIC", None)
    env.update({k: str(v) for k, v in env_overrides.items()})
    return subprocess.run(
        ["/bin/zsh", str(WRAPPER)],
        env=env,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _crash_log(rq: Path) -> Path:
    return rq / "logs" / "rq105" / f"quote_logger_crash_{date.today().isoformat()}.log"


def _notify_record(rq: Path) -> str:
    f = rq / "notify_record.txt"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def _day_log(rq: Path) -> Path:
    return rq / "logs" / "rq105" / f"quote_logger_{date.today().isoformat()}.log"


def test_nonzero_exit_writes_crash_record_and_unmissable_alert(tmp_path):
    """Collector exits non-zero -> wrapper preserves the rc, writes a NON-EMPTY
    crash record (exit code + timestamp + day-log tail), and fires ONE urgent,
    distinctively-tagged, unmistakable-titled ntfy."""
    rq = _scratch_rq_root(tmp_path)
    collector = _fake_collector(tmp_path, "exit 7\n")

    proc = _run_wrapper(
        rq,
        {"RQ105_PYTHON_BIN": collector, "RQ105_WATCHDOG_INTERVAL": 999},
    )

    assert proc.returncode == 7, f"wrapper must preserve collector rc; got {proc.returncode}"

    crash = _crash_log(rq)
    assert crash.exists(), "crash log must be written on a non-zero collector exit"
    text = crash.read_text(encoding="utf-8")
    assert text.strip(), "crash log must be NON-EMPTY (the whole point vs the 0-byte black box)"
    assert "rc=7" in text
    assert "TERMINATED" in text

    record = _notify_record(rq)
    assert "TITLE=" in record, "an ntfy must be sent on a non-zero exit"
    assert "rq105 DOWN" in record, "title must be unmistakable, not buried in shared-topic noise"
    assert "PRIO=urgent" in record, "105-DOWN alert must be elevated priority"
    assert "TAGS=rotating_light,rq105" in record, "105-DOWN alert must carry distinctive tags"


def _stale_feed(rq: Path) -> None:
    feed = rq / "logs" / "renquant105_pilot" / "intraday_ticks.jsonl"
    feed.write_text('{"date":"x","ticker":"AAPL"}\n', encoding="utf-8")
    stale = time.time() - 300  # feed last written 5 min ago
    os.utime(feed, (stale, stale))


def test_silent_hang_watchdog_kills_collector_for_keepalive_restart(tmp_path):
    """Collector process ALIVE but the tick feed is frozen (the observed 08:37
    stall) -> the background watchdog fires an urgent 'feed frozen / collector
    hung' alert AND kills the hung (observe-only) collector, so its non-zero
    exit lets launchd KeepAlive auto-restart it (a hang is otherwise invisible
    to KeepAlive). The whole point of GOAL-5 Fix 3: recoverable, not fatal."""
    rq = _scratch_rq_root(tmp_path)
    _stale_feed(rq)
    # Would run for 30s (a hang) if the watchdog did not intervene.
    collector = _fake_collector(tmp_path, "sleep 30\nexit 0\n")

    proc = _run_wrapper(
        rq,
        {
            "RQ105_PYTHON_BIN": collector,
            "RQ105_WATCHDOG_INTERVAL": 1,
            "RQ105_WATCHDOG_STALE_SECONDS": 2,
            "RQ105_MIN_SESSION_SECONDS": 0,
            # WATCHDOG_KILL defaults to 1
        },
        timeout=20.0,
    )

    assert proc.returncode != 0, "a killed hung collector must exit non-zero so KeepAlive restarts it"
    record = _notify_record(rq)
    assert "hung" in record or "frozen" in record
    assert "PRIO=urgent" in record
    assert "TAGS=rotating_light,rq105" in record
    crash = _crash_log(rq).read_text(encoding="utf-8")
    assert "SILENT STALL" in crash and "KILLING" in crash


def test_silent_hang_alert_only_when_kill_disabled(tmp_path):
    """RQ105_WATCHDOG_KILL=0 -> alert on the frozen feed but leave the collector
    alone (it finishes and exits 0). Isolates the detection/alert from the kill,
    and proves the kill is opt-outable."""
    rq = _scratch_rq_root(tmp_path)
    _stale_feed(rq)
    collector = _fake_collector(tmp_path, "sleep 4\nexit 0\n")

    proc = _run_wrapper(
        rq,
        {
            "RQ105_PYTHON_BIN": collector,
            "RQ105_WATCHDOG_INTERVAL": 1,
            "RQ105_WATCHDOG_STALE_SECONDS": 2,
            "RQ105_WATCHDOG_KILL": 0,
            "RQ105_MIN_SESSION_SECONDS": 0,
        },
    )

    assert proc.returncode == 0
    record = _notify_record(rq)
    assert "hung" in record or "frozen" in record
    crash = _crash_log(rq).read_text(encoding="utf-8")
    assert "SILENT STALL" in crash
    assert "KILLING" not in crash


def test_outside_session_window_is_clean_noop(tmp_path):
    """KeepAlive session-window guard: outside the window the wrapper exits 0
    cleanly BEFORE launching the collector, so KeepAlive (SuccessfulExit=false)
    never respawns the job off-session. Even a crash-stub collector is never
    reached."""
    rq = _scratch_rq_root(tmp_path)
    collector = _fake_collector(tmp_path, "exit 7\n")  # would crash if launched

    proc = _run_wrapper(
        rq,
        {
            "RQ105_PYTHON_BIN": collector,
            # Empty window (start == end) -> current time is always "outside".
            "RQ105_SESSION_START_HHMM": "1200",
            "RQ105_SESSION_END_HHMM": "1200",
        },
    )

    assert proc.returncode == 0, "off-window run must exit 0 so KeepAlive does not respawn"
    assert not _crash_log(rq).exists(), "guard must short-circuit before the collector can crash"
    assert _notify_record(rq) == ""
    assert "outside the session window" in _day_log(rq).read_text(encoding="utf-8")


def test_holiday_noop_is_clean_no_crash_no_alert(tmp_path):
    """Exchange-calendar guard: a weekday NYSE holiday must be a clean no-op
    BEFORE the collector is ever launched — the window guard alone lets an
    in-window run through, and without this guard the collector's own quick
    clean exit gets misread by _finish() as an unexpected 'stopped early'
    crash (codex review, PR #567). Stubs RQ105_CAL_PYTHON_BIN to a script that
    deterministically reports 'not a session day' (rc=1), independent of the
    real NYSE calendar / any .venv, so the collector stub (which would crash
    if launched) is never reached."""
    rq = _scratch_rq_root(tmp_path)
    collector = _fake_collector(tmp_path, "exit 7\n")  # would crash if launched
    not_a_session_day = _fake_collector(tmp_path, "exit 1\n")

    proc = _run_wrapper(
        rq,
        {
            "RQ105_PYTHON_BIN": collector,
            "RQ105_CAL_PYTHON_BIN": not_a_session_day,
        },
    )

    assert proc.returncode == 0, "holiday no-op must exit 0 so KeepAlive does not respawn"
    assert not _crash_log(rq).exists(), "guard must short-circuit before the collector can crash"
    assert _notify_record(rq) == "", "a genuine holiday no-op must not page anyone"
    assert "not an NYSE session day" in _day_log(rq).read_text(encoding="utf-8")


def test_calendar_check_unavailable_fails_closed_and_still_runs(tmp_path):
    """If the calendar check itself cannot be evaluated (no CAL_PYTHON_BIN
    resolvable — the default `.venv` does not exist in this scratch root),
    the guard must fail CLOSED: proceed to launch the collector rather than
    silently skip a real session (never trade a false alarm's noise for a
    missed live stall, matching liveness_common.is_session_day's own
    fail-closed contract)."""
    rq = _scratch_rq_root(tmp_path)
    collector = _fake_collector(tmp_path, "exit 0\n")

    proc = _run_wrapper(
        rq,
        {
            "RQ105_PYTHON_BIN": collector,
            "RQ105_WATCHDOG_INTERVAL": 999,
            "RQ105_MIN_SESSION_SECONDS": 0,
            # RQ105_CAL_PYTHON_BIN left unset -> defaults to "$RQ_ROOT/.venv/bin/python",
            # which does not exist under the scratch tmp_path root.
        },
    )

    assert proc.returncode == 0
    assert not _crash_log(rq).exists()
    assert _notify_record(rq) == ""


def test_clean_full_session_completion_is_silent(tmp_path):
    """A collector that runs the whole session and exits 0 must NOT alert —
    fail-loud must add zero noise to the shared topic on a healthy day."""
    rq = _scratch_rq_root(tmp_path)
    collector = _fake_collector(tmp_path, "exit 0\n")

    proc = _run_wrapper(
        rq,
        {
            "RQ105_PYTHON_BIN": collector,
            "RQ105_WATCHDOG_INTERVAL": 999,
            "RQ105_MIN_SESSION_SECONDS": 0,  # treat the instant exit as a full session
        },
    )

    assert proc.returncode == 0
    assert not _crash_log(rq).exists(), "no crash record on a clean full-session completion"
    assert _notify_record(rq) == "", "no alert on a clean full-session completion"


def test_wrapper_text_has_fail_loud_machinery():
    """Cheap guardrails (matching the repo's wrapper-as-text convention) that the
    load-bearing fail-loud pieces stay present in future edits."""
    text = WRAPPER.read_text(encoding="utf-8")
    assert "quote_logger_crash_" in text, "dedicated crash log path must exist"
    assert "trap " in text and "EXIT" in text, "termination must be trapped"
    assert "rq105_watchdog" in text, "silent-hang watchdog must exist"
    assert "rotating_light,rq105" in text and "urgent" in text.lower(), (
        "alerts must default to distinctive tags + elevated priority"
    )
    assert "outside the session window" in text, "KeepAlive session-window guard must exist"
    assert "is_session_day" in text, "exchange-calendar guard must exist (holiday false-alarm fix)"
    assert "ALERT_COOLDOWN_SECONDS" in text, "alert cooldown (KeepAlive storm guard) must exist"
    assert "WATCHDOG_KILL" in text, "watchdog hang-kill (for KeepAlive restart) must exist"
