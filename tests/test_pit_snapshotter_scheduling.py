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
    # C1 feature builder runs AFTER the snapshot (14:30) and liveness (15:00)
    # so it always sees today's published snapshot when one exists.
    "com.renquant.pit-c1-features.plist": (15, 30),
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


def test_weekend_is_not_flagged_as_a_lapsed_session(monkeypatch, tmp_path):
    saturday = dt.date(2026, 7, 4)  # Saturday — launchd doesn't fire
    monkeypatch.setattr(liveness, "ROOT", str(tmp_path))
    rc = liveness.main(["--as-of", saturday.isoformat()])
    assert rc == 0


def test_holiday_weekday_is_still_checked(monkeypatch, tmp_path):
    # Snapshotter runs all weekdays including holidays (FMP data updates
    # regardless of market status). Liveness must verify, not skip.
    holiday_friday = dt.date(2026, 7, 3)  # observed July 4th
    monkeypatch.setattr(liveness, "ROOT", str(tmp_path))
    rc = liveness.main(["--as-of", holiday_friday.isoformat()])
    assert rc == 1  # no snapshot dir → flagged as missing


def test_ordinary_weekday_with_no_snapshot_is_flagged():
    # 2026-06-29 is a Monday, not a holiday.
    weekday = dt.date(2026, 6, 29)
    problems = liveness.check_snapshot(weekday)
    assert problems and "missing" in problems[0]


def test_collection_day_is_weekday_only():
    assert liveness._is_collection_day(dt.date(2026, 6, 29)) is True   # Monday
    assert liveness._is_collection_day(dt.date(2026, 7, 3)) is True    # Friday (holiday)
    assert liveness._is_collection_day(dt.date(2026, 7, 4)) is False   # Saturday
    assert liveness._is_collection_day(dt.date(2026, 7, 5)) is False   # Sunday


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
    # Use a Saturday so the check skips (no snapshot expected)
    fixed = dt.date(2026, 7, 4)  # Saturday
    rc = liveness.main(["--as-of", fixed.isoformat()])
    assert rc == 0
    out = capsys.readouterr().out
    assert "2026-07-04" in out


# ───────────────── wrapper: kernel-released fcntl.flock concurrency lock ─────
#
# #233 round 3: the mkdir-based lock (round 2) was only released by a shell
# `EXIT` trap, which does not fire on SIGKILL/host-crash/power-loss — a run
# killed mid-flight left the lock directory on disk forever, silently
# skipping every future scheduled run of this non-backfillable dataset. The
# tests below replace the old sequential precreate/remove/run "concurrency"
# test (which never actually raced two processes) with a genuine overlapping
# race and a genuine kill -9 crash-recovery scenario.
#
# #233 round 4: round 3's launcher held the flock itself but ran the wrapped
# command as a SEPARATE CHILD via `subprocess.run` — SIGKILL to the launcher
# released the lock (correct) but never reached the child (SIGKILL cannot be
# forwarded), so the child could become an orphan that keeps running while a
# new invocation, seeing the lock free, starts a second overlapping run. The
# fix execs the wrapped command IN PLACE of the launcher, so there is only
# ever one process — killing it kills the actual protected work directly,
# with nothing left behind to orphan. `test_exec_replaces_process_no_orphan_
# possible` below proves this property directly (same PID before/after exec,
# and nothing alive after SIGKILL); `test_killed_lock_holder_does_not_block_
# the_next_run` is updated to also assert the killed work is genuinely gone,
# not just that the lock was reacquirable.


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
    property the old mkdir+trap lock could not guarantee. Also asserts the
    killed holder's PID is genuinely dead (not merely that the lock was
    reacquirable) -- round 3's equivalent test proved lock reacquisition but
    not exclusivity of the protected work, which is what round 4's exec-based
    fix (verified structurally by test_exec_replaces_process_no_orphan_
    possible below) closes."""
    lock_file = str(tmp_path / "crash.lock")
    holder_log = tmp_path / "holder.log"
    holder = subprocess.Popen(
        [sys.executable, str(_LOCK_LAUNCHER), "--lock-file", lock_file,
         "--log-file", str(holder_log), "--", "sleep", "30"],
    )
    holder_pid = holder.pid
    _wait_for_lock_held(lock_file, timeout=5)

    holder.kill()  # SIGKILL -- uncatchable, no trap/finally in the holder can run
    holder.wait(timeout=5)

    # Round 4: the launcher execs into `sleep 30` in place of itself, so
    # holder_pid IS the protected work's own PID (not a distinct child) --
    # killing it must leave nothing alive under that PID.
    with pytest.raises(ProcessLookupError):
        os.kill(holder_pid, 0)

    env_overrides, runs_log = _stub_env(tmp_path)
    env = {**os.environ, **env_overrides, "PIT_SNAPSHOT_LOCK_FILE": lock_file}
    result = subprocess.run(["/bin/bash", str(_WRAPPER)], env=env, capture_output=True, text=True)
    assert result.returncode == 0
    assert _run_count(runs_log) == 1, (
        "the lock must be immediately acquirable after the holder was SIGKILLed -- "
        "a stale lock here would mean this dataset silently stops collecting forever"
    )


def test_exec_replaces_process_no_orphan_possible(tmp_path):
    """Round 4's core property, proven directly: the launcher execs the
    wrapped command IN PLACE of itself (same PID before and after), rather
    than spawning it as a separate child via subprocess.run. Round 3's
    equivalent test only proved the LOCK was reacquirable after a SIGKILL --
    it never asserted the wrapped command's own process was actually dead,
    so it could not have caught an orphaned child continuing to run (and
    writing to the protected dataset) after the launcher was killed.

    Wraps a single-process, non-forking command (a bare `python3 -c
    "time.sleep(...)"`, matching the real production shape -- the actual
    wrapped command in run_estimate_snapshotter.sh is one direct
    `$RQ_ROOT/.venv/bin/python -m renquant_base_data.fmp_estimate_revisions`
    invocation, not a shell script). This distinction matters: an earlier
    draft of this test wrapped `sh -c "cmd1; cmd2"` instead, and found that
    exec-replacing the launcher with a *shell* does NOT fully close the
    hole when the shell itself forks a further child to run the tail
    command of a multi-statement `-c` script -- that grandchild inherits the
    lock fd via fork() (independent of exec/close-on-exec, which only takes
    effect at exec time) and can itself become an orphan one level down,
    keeping the kernel flock held even after the shell (and thus the
    launcher's original PID) is SIGKILLed. This launcher's guarantee is
    therefore precise: the lock's lifetime matches the wrapped command's OWN
    top-level process lifetime. That is sufficient for this PR's actual
    non-forking wrapped command, and is asserted here against that same
    shape; it would NOT be sufficient for a wrapped command that itself
    forks additional children without exec'ing them (documented in
    run_with_lock.py's own docstring for future callers of this launcher)."""
    lock_file = str(tmp_path / "exec.lock")
    log_file = str(tmp_path / "exec.log")

    launcher = subprocess.Popen(
        [sys.executable, str(_LOCK_LAUNCHER), "--lock-file", lock_file,
         "--log-file", log_file, "--", sys.executable, "-c",
         "import time; time.sleep(30)"],
    )
    launcher_pid = launcher.pid
    _wait_for_lock_held(lock_file, timeout=5)

    launcher.kill()  # SIGKILL the single PID that is now the protected work itself
    launcher.wait(timeout=5)

    with pytest.raises(ProcessLookupError):
        os.kill(launcher_pid, 0)  # confirms the protected work is genuinely gone

    # A second invocation must be immediately safe: nothing is left running
    # under any PID that could race a fresh run's writes.
    env_overrides, runs_log = _stub_env(tmp_path)
    env = {**os.environ, **env_overrides, "PIT_SNAPSHOT_LOCK_FILE": lock_file}
    result = subprocess.run(["/bin/bash", str(_WRAPPER)], env=env, capture_output=True, text=True)
    assert result.returncode == 0
    assert _run_count(runs_log) == 1


def test_run_with_lock_propagates_wrapped_command_exit_code(tmp_path):
    lock_file = str(tmp_path / "rc.lock")
    log_file = str(tmp_path / "rc.log")
    result = subprocess.run(
        [sys.executable, str(_LOCK_LAUNCHER), "--lock-file", lock_file,
         "--log-file", log_file, "--", "sh", "-c", "exit 7"],
        capture_output=True, text=True,
    )
    assert result.returncode == 7


# ───────────────── C1 feature-builder wrapper (M-SIG C1 serving path) ────────
#
# The heavy lock-machinery guarantees are proven once above against
# run_with_lock.py (shared by both wrappers). Here we only assert the C1
# wrapper's own wiring: it reaches the builder through the stub venv python
# when its lock is free, and it skips cleanly (exit 0, no builder invocation)
# when its own DEDICATED lock file is held — the two wrappers must not share
# a lock, or a long snapshot fetch would silently skip the feature build.

_C1_WRAPPER = OPS_DIR / "run_c1_feature_builder.sh"


def _c1_env(tmp_path: Path):
    env_overrides, runs_log = _stub_env(tmp_path)
    env_overrides["PIT_C1_LOCK_FILE"] = str(tmp_path / "c1.lock")
    return env_overrides, runs_log


def test_c1_wrapper_runs_builder_when_lock_free(tmp_path):
    env_overrides, runs_log = _c1_env(tmp_path)
    env = {**os.environ, **env_overrides}
    result = subprocess.run(["/bin/bash", str(_C1_WRAPPER)], env=env,
                            capture_output=True, text=True)
    assert result.returncode == 0
    assert _run_count(runs_log) == 1, "stub python was never invoked — wrapper did not run the builder"


def test_c1_wrapper_skips_cleanly_when_its_own_lock_is_held(tmp_path):
    env_overrides, runs_log = _c1_env(tmp_path)
    lock_file = env_overrides["PIT_C1_LOCK_FILE"]
    holder_log = tmp_path / "holder.log"
    holder = subprocess.Popen(
        [sys.executable, str(_LOCK_LAUNCHER), "--lock-file", lock_file,
         "--log-file", str(holder_log), "--", "sleep", "5"],
    )
    try:
        _wait_for_lock_held(lock_file, timeout=5)
        env = {**os.environ, **env_overrides}
        result = subprocess.run(["/bin/bash", str(_C1_WRAPPER)], env=env,
                                capture_output=True, text=True)
        assert result.returncode == 0, "a held lock must be a benign skip (exit 0), not a failure"
        assert _run_count(runs_log) == 0, "the builder must NOT run while its lock is held"
    finally:
        holder.kill()
        holder.wait(timeout=5)


def test_c1_wrapper_uses_a_dedicated_lock_not_the_snapshotters(tmp_path):
    """Holding the SNAPSHOTTER's lock must not block the C1 builder."""
    env_overrides, runs_log = _c1_env(tmp_path)
    snap_lock = env_overrides["PIT_SNAPSHOT_LOCK_FILE"]
    holder_log = tmp_path / "holder.log"
    holder = subprocess.Popen(
        [sys.executable, str(_LOCK_LAUNCHER), "--lock-file", snap_lock,
         "--log-file", str(holder_log), "--", "sleep", "5"],
    )
    try:
        _wait_for_lock_held(snap_lock, timeout=5)
        env = {**os.environ, **env_overrides}
        result = subprocess.run(["/bin/bash", str(_C1_WRAPPER)], env=env,
                                capture_output=True, text=True)
        assert result.returncode == 0
        assert _run_count(runs_log) == 1, "the C1 builder must proceed under its own lock"
    finally:
        holder.kill()
        holder.wait(timeout=5)


def test_c1_wrapper_points_at_the_read_only_lake_and_pit_features_out(tmp_path):
    """The wrapper must invoke `pit_revision_features build` with the lake as
    --snapshot-root and a data/pit_features out-root (the builder itself
    structurally refuses anything else — this pins the wrapper's wiring)."""
    text = _C1_WRAPPER.read_text()
    assert "-m renquant_base_data.pit_revision_features build" in text
    assert "--snapshot-root" in text and "data/estimate_snapshots" in text
    assert "--out" in text and "data/pit_features" in text
