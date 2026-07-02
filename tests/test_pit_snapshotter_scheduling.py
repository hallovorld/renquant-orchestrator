"""Tests for ops/pit/*: launchd plist schedules, the NYSE-holiday-aware
liveness gate against the collector's real 4-endpoint publication contract,
and the wrapper's mkdir-based non-blocking concurrency lock (#233 review —
the plists needed schedule verification, the liveness check accepted "any
parquet + any manifest-named file" instead of validating all four named
endpoint manifests, there was no concurrency guard despite the collector's
own docstring requiring one, and the log directory was never created before
launchd would try to redirect stdout/stderr into it)."""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import plistlib
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
OPS_DIR = REPO / "ops" / "pit"
sys.path.insert(0, str(OPS_DIR))

import pit_liveness_check as liveness  # noqa: E402


# ─────────────────────────── plist schedule checks ───────────────────────────

_EXPECTED_TIMES = {
    "com.renquant.pit-estimate-snapshot.plist": (14, 30),
    "com.renquant.pit-liveness.plist": (15, 0),
}


@pytest.mark.parametrize("filename,expected", _EXPECTED_TIMES.items())
def test_plist_schedule_matches_documented_pt_time(filename, expected):
    exp_hour, exp_minute = expected
    with open(OPS_DIR / filename, "rb") as fh:
        plist = plistlib.load(fh)
    intervals = plist["StartCalendarInterval"]
    assert len(intervals) == 5, f"{filename}: expected one entry per weekday (Mon-Fri)"
    weekdays = {entry["Weekday"] for entry in intervals}
    assert weekdays == {1, 2, 3, 4, 5}, f"{filename}: expected Mon(1)-Fri(5) only"
    for entry in intervals:
        assert 0 <= entry["Hour"] <= 23, f"{filename}: invalid Hour {entry['Hour']}"
        assert 0 <= entry["Minute"] <= 59, f"{filename}: invalid Minute {entry['Minute']}"
        assert (entry["Hour"], entry["Minute"]) == expected, (
            f"{filename}: {entry} does not match documented {exp_hour}:{exp_minute:02d}"
        )


@pytest.mark.parametrize("filename", _EXPECTED_TIMES.keys())
def test_plist_log_paths_are_under_documented_log_dir(filename):
    with open(OPS_DIR / filename, "rb") as fh:
        plist = plistlib.load(fh)
    for key in ("StandardOutPath", "StandardErrorPath"):
        assert "logs/pit_snapshots/" in plist[key], f"{filename}: {key} not under logs/pit_snapshots/"


# ─────────────────────────── liveness: session-day gating ────────────────────


def test_holiday_is_not_flagged_as_a_lapsed_session(monkeypatch, tmp_path):
    # Mock the calendar check directly rather than depending on
    # pandas_market_calendars (and its historical data) being installed in
    # whatever environment runs this suite — test_calendar_failure_fails_
    # closed_to_session_day already covers the "library unavailable" case;
    # this test is purely about main()'s own control flow when a day IS
    # correctly identified as non-session.
    holiday = dt.date(2026, 1, 1)  # New Year's Day, for readability only
    monkeypatch.setattr(liveness, "_is_session_day", lambda day: False)
    monkeypatch.setattr(liveness, "ROOT", str(tmp_path))  # no snapshot dir exists at all
    rc = liveness.main(["--as-of", holiday.isoformat()])
    assert rc == 0  # must not alert/fail just because nothing was published on a holiday


def test_ordinary_weekday_with_no_snapshot_is_flagged():
    # 2026-06-29 is a Monday, not a holiday.
    weekday = dt.date(2026, 6, 29)
    problems = liveness.check_snapshot(weekday)
    assert problems and "missing" in problems[0]


def test_calendar_failure_fails_closed_to_session_day(monkeypatch):
    def _boom():
        raise RuntimeError("pandas_market_calendars unavailable")

    monkeypatch.setattr(liveness, "_session_calendar", _boom)
    # A calendar failure must NOT silently skip the check — it must still be
    # treated as a session day so a real lapse can't hide behind a broken import.
    assert liveness._is_session_day(dt.date(2026, 6, 29)) is True


# ─────────────────────────── liveness: publication contract ──────────────────


def _write_manifest(day_dir: Path, endpoint: str, *, status="ok", as_of=None,
                     parquet_bytes=b"x", write_parquet=True):
    day_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "endpoint": endpoint,
        "as_of": as_of,
        "status": status,
        "output": f"{endpoint}.parquet",
        "rows": 100,
        "sha256": "deadbeef",
    }
    (day_dir / f"{endpoint}.manifest.json").write_text(json.dumps(manifest))
    if write_parquet:
        (day_dir / f"{endpoint}.parquet").write_bytes(parquet_bytes)


def test_all_four_endpoints_published_is_healthy(tmp_path, monkeypatch):
    monkeypatch.setattr(liveness, "ROOT", str(tmp_path))
    today = dt.date(2026, 6, 29)
    day_dir = tmp_path / today.isoformat()
    for ep in liveness.ENDPOINTS:
        _write_manifest(day_dir, ep, as_of=today.isoformat())
    assert liveness.check_snapshot(today) == []


def test_missing_one_endpoint_manifest_is_unhealthy(tmp_path, monkeypatch):
    monkeypatch.setattr(liveness, "ROOT", str(tmp_path))
    today = dt.date(2026, 6, 29)
    day_dir = tmp_path / today.isoformat()
    for ep in liveness.ENDPOINTS[:-1]:
        _write_manifest(day_dir, ep, as_of=today.isoformat())
    problems = liveness.check_snapshot(today)
    assert len(problems) == 1
    assert liveness.ENDPOINTS[-1] in problems[0]
    assert "missing" in problems[0]


def test_zero_byte_manifest_is_unhealthy(tmp_path, monkeypatch):
    monkeypatch.setattr(liveness, "ROOT", str(tmp_path))
    today = dt.date(2026, 6, 29)
    day_dir = tmp_path / today.isoformat()
    for ep in liveness.ENDPOINTS:
        _write_manifest(day_dir, ep, as_of=today.isoformat())
    (day_dir / f"{liveness.ENDPOINTS[0]}.manifest.json").write_text("")
    problems = liveness.check_snapshot(today)
    assert any("zero-byte" in p for p in problems)


def test_zero_byte_parquet_is_unhealthy(tmp_path, monkeypatch):
    monkeypatch.setattr(liveness, "ROOT", str(tmp_path))
    today = dt.date(2026, 6, 29)
    day_dir = tmp_path / today.isoformat()
    for ep in liveness.ENDPOINTS:
        _write_manifest(day_dir, ep, as_of=today.isoformat())
    (day_dir / f"{liveness.ENDPOINTS[0]}.parquet").write_bytes(b"")
    problems = liveness.check_snapshot(today)
    assert any("zero-byte" in p and "parquet" in p for p in problems)


def test_partial_status_manifest_is_unhealthy(tmp_path, monkeypatch):
    monkeypatch.setattr(liveness, "ROOT", str(tmp_path))
    today = dt.date(2026, 6, 29)
    day_dir = tmp_path / today.isoformat()
    for ep in liveness.ENDPOINTS:
        status = "partial" if ep == liveness.ENDPOINTS[0] else "ok"
        _write_manifest(day_dir, ep, as_of=today.isoformat(), status=status)
    problems = liveness.check_snapshot(today)
    assert any("partial" in p for p in problems)


def test_stale_as_of_manifest_from_a_prior_day_is_rejected(tmp_path, monkeypatch):
    """A leftover manifest published under a WRONG as_of (e.g. a bug, or a
    manually-copied file) must not be silently accepted just because a file
    with the right name exists — the collector's own as_of field must match."""
    monkeypatch.setattr(liveness, "ROOT", str(tmp_path))
    today = dt.date(2026, 6, 29)
    stale_date = dt.date(2026, 6, 20)
    day_dir = tmp_path / today.isoformat()
    for ep in liveness.ENDPOINTS:
        _write_manifest(day_dir, ep, as_of=stale_date.isoformat())
    problems = liveness.check_snapshot(today)
    assert len(problems) == len(liveness.ENDPOINTS)
    assert all("as_of" in p for p in problems)


def test_missing_referenced_parquet_is_unhealthy(tmp_path, monkeypatch):
    monkeypatch.setattr(liveness, "ROOT", str(tmp_path))
    today = dt.date(2026, 6, 29)
    day_dir = tmp_path / today.isoformat()
    for ep in liveness.ENDPOINTS:
        _write_manifest(day_dir, ep, as_of=today.isoformat(), write_parquet=(ep != liveness.ENDPOINTS[0]))
    problems = liveness.check_snapshot(today)
    assert any("missing" in p and liveness.ENDPOINTS[0] in p for p in problems)


# ─────────────────────────── date injection ───────────────────────────────


def test_as_of_flag_overrides_today(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(liveness, "ROOT", str(tmp_path))
    monkeypatch.setattr(liveness, "_is_session_day", lambda day: False)
    fixed = dt.date(2026, 1, 1)  # arbitrary fixed date, deterministic regardless of run date
    rc = liveness.main(["--as-of", fixed.isoformat()])
    assert rc == 0
    out = capsys.readouterr().out
    assert "2026-01-01" in out


# ───────────────── wrapper: kernel-released fcntl.flock concurrency lock ─────
#
# #233 round 3: the mkdir-based lock (round 2) was only released by a shell
# `EXIT` trap, which does not fire on SIGKILL/host-crash/power-loss — a run
# killed mid-flight left the lock directory on disk forever, silently
# skipping every future scheduled run of this non-backfillable dataset. The
# tests below replace the old sequential precreate/remove/run "concurrency"
# test (which never actually raced two processes) with a genuine overlapping
# race and a genuine kill -9 crash-recovery scenario.


_WRAPPER = OPS_DIR / "run_estimate_snapshotter.sh"
_LOCK_LAUNCHER = OPS_DIR / "run_with_lock.py"


def _stub_env(tmp_path: Path, *, sleep_seconds: float = 0) -> dict:
    """A fake RQ_ROOT/BD_RUN_ROOT tree with a stub `.venv/bin/python` standing
    in for the real venv, so the wrapper can be exercised without any real
    project dependency or network access. The stub APPENDS one line per
    invocation to `runs.log` (rather than just touching a marker) so tests
    can assert the collector ran exactly N times, not merely "at least
    once" -- important for the overlap test, where only one of two
    concurrent wrapper invocations must reach the collector. `sleep_seconds`
    lets a test hold the lock open long enough for a genuine race to land
    inside that window instead of depending on process-startup jitter."""
    rq_root = tmp_path / "rq_root"
    (rq_root / ".venv" / "bin").mkdir(parents=True)
    runs_log = rq_root / "runs.log"
    stub_python = rq_root / ".venv" / "bin" / "python"
    stub_python.write_text(
        "#!/bin/sh\n"
        f"sleep {sleep_seconds}\n"
        f"echo ran >> '{runs_log}'\n"
        "exit 0\n"
    )
    stub_python.chmod(stub_python.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    (rq_root / ".env").write_text("")
    bd_root = tmp_path / "bd_root" / "src"
    bd_root.mkdir(parents=True)
    return {
        "RQ_ROOT": str(rq_root),
        "BD_RUN_ROOT": str(tmp_path / "bd_root"),
        "PIT_SNAPSHOT_LOCK_FILE": str(tmp_path / "snapshot.lock"),
    }, runs_log


def _run_count(runs_log: Path) -> int:
    if not runs_log.exists():
        return 0
    return len([ln for ln in runs_log.read_text().splitlines() if ln.strip()])


def _wrapper_log_path(env_overrides: dict) -> Path:
    """The wrapper computes its own log path internally as
    $RQ_ROOT/logs/pit_snapshots/estimate_snapshot_<today>.log -- reproduce
    that here so tests can inspect what the wrapper itself wrote (its own
    SKIP lines), as distinct from a test-controlled lock-holder's log."""
    ts = dt.date.today().isoformat()
    return Path(env_overrides["RQ_ROOT"]) / "logs" / "pit_snapshots" / f"estimate_snapshot_{ts}.log"


def test_wrapper_runs_when_lock_is_free(tmp_path):
    env_overrides, runs_log = _stub_env(tmp_path)
    env = {**os.environ, **env_overrides}
    result = subprocess.run(["/bin/bash", str(_WRAPPER)], env=env, capture_output=True, text=True)
    assert result.returncode == 0
    assert _run_count(runs_log) == 1, "stub python was never invoked — wrapper did not run the collector"
    # Unlike the old mkdir lock, the flock lock FILE is expected to persist on
    # disk after use (the file itself is inert; only an active flock on it
    # means anything) -- so there is no "lock removed on exit" assertion here.
    assert Path(env_overrides["PIT_SNAPSHOT_LOCK_FILE"]).exists()


def test_wrapper_skips_without_invoking_collector_when_lock_held(tmp_path):
    """A genuinely-held flock (not a precreated directory) blocks a second
    wrapper invocation until the holder releases it."""
    env_overrides, runs_log = _stub_env(tmp_path)
    lock_file = env_overrides["PIT_SNAPSHOT_LOCK_FILE"]
    holder_log = tmp_path / "holder.log"
    # Hold the lock for real via the launcher itself, wrapping a long sleep.
    holder = subprocess.Popen(
        [sys.executable, str(_LOCK_LAUNCHER), "--lock-file", lock_file,
         "--log-file", str(holder_log), "--", "sleep", "5"],
    )
    try:
        _wait_for_lock_held(lock_file, timeout=5)
        env = {**os.environ, **env_overrides}
        result = subprocess.run(["/bin/bash", str(_WRAPPER)], env=env, capture_output=True, text=True)
        assert result.returncode == 0, "a held lock must be a benign skip (exit 0), not a failure"
        assert _run_count(runs_log) == 0, "the collector must NOT have been invoked while the lock was held"
        assert "SKIP" in _wrapper_log_path(env_overrides).read_text()
    finally:
        holder.kill()
        holder.wait(timeout=5)


def _wait_for_lock_held(lock_file: str, timeout: float) -> None:
    """Poll until some OTHER process holds an exclusive flock on lock_file,
    by repeatedly attempting (and immediately releasing) our own
    non-blocking lock -- once our attempt starts failing, the holder has it."""
    deadline = time.monotonic() + timeout
    fd = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        while time.monotonic() < deadline:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                return  # someone else holds it now
            time.sleep(0.02)
        raise TimeoutError(f"lock at {lock_file} was never acquired by the holder within {timeout}s")
    finally:
        os.close(fd)


def test_wrapper_concurrent_invocations_exactly_one_proceeds(tmp_path):
    """Two REAL near-simultaneous wrapper invocations (both started before
    either finishes, via subprocess.Popen with no wait in between): exactly
    one acquires the lock and runs the collector; the loser skips cleanly.
    The stub collector sleeps briefly so the race window is wide enough to
    be non-flaky without depending on precise OS scheduling timing."""
    env_overrides, runs_log = _stub_env(tmp_path, sleep_seconds=1)
    env = {**os.environ, **env_overrides}
    proc_a = subprocess.Popen(["/bin/bash", str(_WRAPPER)], env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    proc_b = subprocess.Popen(["/bin/bash", str(_WRAPPER)], env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    rc_a = proc_a.wait(timeout=15)
    rc_b = proc_b.wait(timeout=15)
    assert rc_a == 0 and rc_b == 0, "both must exit 0 -- the loser's skip is not a failure"
    assert _run_count(runs_log) == 1, "exactly one of the two overlapping invocations must reach the collector"


def test_killed_lock_holder_does_not_block_the_next_run(tmp_path):
    """Crash-recovery: a process holding the flock lock is killed with
    SIGKILL (uncatchable -- exactly what a host crash or `kill -9` looks
    like; no EXIT trap of any kind can run). A fresh invocation started
    immediately after must acquire the lock right away, proving the kernel
    released it automatically and no stale-lock state persists -- the
    property the old mkdir+trap lock could not guarantee."""
    lock_file = str(tmp_path / "crash.lock")
    holder_log = tmp_path / "holder.log"
    holder = subprocess.Popen(
        [sys.executable, str(_LOCK_LAUNCHER), "--lock-file", lock_file,
         "--log-file", str(holder_log), "--", "sleep", "30"],
    )
    _wait_for_lock_held(lock_file, timeout=5)

    holder.kill()  # SIGKILL -- uncatchable, no trap/finally in the holder can run
    holder.wait(timeout=5)

    env_overrides, runs_log = _stub_env(tmp_path)
    env = {**os.environ, **env_overrides, "PIT_SNAPSHOT_LOCK_FILE": lock_file}
    result = subprocess.run(["/bin/bash", str(_WRAPPER)], env=env, capture_output=True, text=True)
    assert result.returncode == 0
    assert _run_count(runs_log) == 1, (
        "the lock must be immediately acquirable after the holder was SIGKILLed -- "
        "a stale lock here would mean this dataset silently stops collecting forever"
    )


def test_run_with_lock_propagates_wrapped_command_exit_code(tmp_path):
    lock_file = str(tmp_path / "rc.lock")
    log_file = str(tmp_path / "rc.log")
    result = subprocess.run(
        [sys.executable, str(_LOCK_LAUNCHER), "--lock-file", lock_file,
         "--log-file", log_file, "--", "sh", "-c", "exit 7"],
        capture_output=True, text=True,
    )
    assert result.returncode == 7
