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
import json
import os
import plistlib
import stat
import subprocess
import sys
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


# ─────────────────────────── wrapper: mkdir concurrency lock ─────────────────


_WRAPPER = OPS_DIR / "run_estimate_snapshotter.sh"


def _stub_env(tmp_path: Path) -> dict:
    """A fake RQ_ROOT/BD_RUN_ROOT tree with a stub `.venv/bin/python` standing
    in for the real venv, so the wrapper can be exercised without any real
    project dependency or network access."""
    rq_root = tmp_path / "rq_root"
    (rq_root / ".venv" / "bin").mkdir(parents=True)
    marker = rq_root / "ran.marker"
    stub_python = rq_root / ".venv" / "bin" / "python"
    stub_python.write_text(
        "#!/bin/sh\n"
        f"touch '{marker}'\n"
        "exit 0\n"
    )
    stub_python.chmod(stub_python.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    (rq_root / ".env").write_text("")
    bd_root = tmp_path / "bd_root" / "src"
    bd_root.mkdir(parents=True)
    return {
        "RQ_ROOT": str(rq_root),
        "BD_RUN_ROOT": str(tmp_path / "bd_root"),
        "PIT_SNAPSHOT_LOCK_DIR": str(tmp_path / "lock.d"),
    }, marker


def test_wrapper_runs_when_lock_is_free(tmp_path):
    env_overrides, marker = _stub_env(tmp_path)
    env = {**os.environ, **env_overrides}
    result = subprocess.run(["/bin/bash", str(_WRAPPER)], env=env, capture_output=True, text=True)
    assert result.returncode == 0
    assert marker.exists(), "stub python was never invoked — wrapper did not run the collector"
    assert not Path(env_overrides["PIT_SNAPSHOT_LOCK_DIR"]).exists(), "lock dir must be removed on exit"


def test_wrapper_skips_without_invoking_collector_when_lock_held(tmp_path):
    env_overrides, marker = _stub_env(tmp_path)
    lock_dir = Path(env_overrides["PIT_SNAPSHOT_LOCK_DIR"])
    lock_dir.mkdir(parents=True)  # simulate a concurrent run already holding the lock
    env = {**os.environ, **env_overrides}
    result = subprocess.run(["/bin/bash", str(_WRAPPER)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, "a held lock must be a benign skip (exit 0), not a failure"
    assert not marker.exists(), "the collector must NOT have been invoked while the lock was held"
    assert lock_dir.exists(), "this process must not remove a lock it did not acquire"


def test_wrapper_concurrent_invocations_exactly_one_proceeds(tmp_path):
    """Two near-simultaneous invocations: exactly one acquires the lock and
    runs the collector; the loser skips cleanly."""
    env_overrides, marker = _stub_env(tmp_path)
    lock_dir = Path(env_overrides["PIT_SNAPSHOT_LOCK_DIR"])
    env = {**os.environ, **env_overrides}
    # Pre-hold the lock (deterministic stand-in for a genuine race — proves
    # the mechanism, since a real concurrent subprocess race is inherently
    # timing-dependent and would make this test flaky).
    lock_dir.mkdir(parents=True)
    loser = subprocess.run(["/bin/bash", str(_WRAPPER)], env=env, capture_output=True, text=True)
    assert loser.returncode == 0
    assert not marker.exists()
    lock_dir.rmdir()
    winner = subprocess.run(["/bin/bash", str(_WRAPPER)], env=env, capture_output=True, text=True)
    assert winner.returncode == 0
    assert marker.exists()
