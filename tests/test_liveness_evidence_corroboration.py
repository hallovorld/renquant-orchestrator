"""Liveness was judged on a file most of these jobs never write.

Measured 2026-08-01 across the 43 manifested jobs: 21 sat in NO_EVIDENCE_STALE and
**21 of 21** had newer material in their own log directory — the bucket was entirely
noise, which trains its reader to skip it. Two separable defects produced that:

  * the verdict reads the plist's `StandardOutPath`, while most jobs write a DATED log
    beside it, leaving the declared file empty and frozen forever;
  * `expected_firings` implemented `Weekday` but silently ignored `Day`, so a monthly
    job was counted as firing daily — `monthly-calibrator-refresh` was reported **60
    firings stale** over an interval containing **2** of its real firings.

After both: EVIDENCE_FRESH 17 -> 19, NO_EVIDENCE_STALE 21 -> 1.
"""

from __future__ import annotations

import datetime as dt
import os
import pathlib
import sys

import pytest

OPS = pathlib.Path(__file__).resolve().parent.parent / "ops"
sys.path.insert(0, str(OPS))

import launchd_liveness_scan as L  # noqa: E402

MONTHLY = [{"Day": 1, "Hour": 3, "Minute": 0}]
WEEKLY = [{"Weekday": 6, "Hour": 4, "Minute": 0}]
DAILY = [{"Hour": 3, "Minute": 0}]


# ------------------------------------------------------------- the schedule defect --
def test_DAY_of_month_is_honoured_so_a_monthly_job_is_not_judged_daily():
    """The measured case: 2026-06-01 -> 2026-08-01 contains TWO firings of a
    day-of-month-1 job. It was counted as 60."""
    n = L.expected_firings(MONTHLY, dt.datetime(2026, 6, 1, 3, 0, 5),
                           dt.datetime(2026, 8, 1, 1, 53))
    assert n == 1                      # 2026-07-01 fired; 2026-08-01 03:00 not yet


def test_the_same_interval_under_a_DAILY_schedule_is_the_old_wrong_answer():
    """Pins the size of the bug rather than asserting it in prose."""
    n = L.expected_firings(DAILY, dt.datetime(2026, 6, 1, 3, 0, 5),
                           dt.datetime(2026, 8, 1, 1, 53))
    assert n == 60


def test_WEEKDAY_still_works(the_regression_guard=None):
    n = L.expected_firings(WEEKLY, dt.datetime(2026, 5, 17, 4, 0),
                           dt.datetime(2026, 8, 1, 1, 53))
    assert n == 10


def test_MONTH_is_honoured():
    e = [{"Month": 1, "Day": 1, "Hour": 0, "Minute": 0}]
    assert L.expected_firings(e, dt.datetime(2026, 1, 1, 1),
                              dt.datetime(2026, 12, 31)) == 0
    assert L.expected_firings(e, dt.datetime(2025, 12, 31),
                              dt.datetime(2026, 12, 31)) == 1


def test_an_UNRECOGNISED_schedule_key_REFUSES_instead_of_being_ignored():
    """The default is inverted. Enumerating known keys and skipping the rest is what
    produced the `Day` bug: an ignored constraint inflates the count, and an inflated
    count reads as a dead job."""
    with pytest.raises(L.UnsupportedScheduleKey) as exc:
        L.expected_firings([{"Hour": 3, "Quarter": 2}], dt.datetime(2026, 1, 1),
                           dt.datetime(2026, 2, 1))
    assert "Quarter" in str(exc.value)


def test_every_key_this_repo_uses_is_supported():
    assert {"Minute", "Hour", "Day", "Weekday", "Month"} <= L.SUPPORTED_SCHEDULE_KEYS


# ------------------------------------------------------------------ corroboration --
def _row(tmp_path, label, logname="stdout.log", subdir="j", entries=None, mtime_days=40):
    d = tmp_path / subdir
    d.mkdir(exist_ok=True)
    p = d / logname
    p.write_text("")
    old = (dt.datetime.now() - dt.timedelta(days=mtime_days)).timestamp()
    os.utime(p, (old, old))
    return {"label": label, "log": str(p), "status": L.NO_EVIDENCE_STALE,
            "detail": "stale", "_schedule_entries_parsed": entries or DAILY}


def test_a_SHARED_log_directory_yields_AMBIGUOUS_not_a_liveness_claim(tmp_path):
    """The newest file may belong to a neighbour. Attributing it would be a check
    passing on evidence about a different object."""
    a = _row(tmp_path, "a", "a.log")
    b = _row(tmp_path, "b", "b.log")
    (tmp_path / "j" / "fresh.log").write_text("x")
    L.corroborate([a, b])
    assert a["status"] == L.STALE_AMBIGUOUS_SHARED_LOG_DIR
    assert a["shared_log_dir_owners"] == ["a", "b"]


def test_a_FRESH_sibling_in_an_UNSHARED_directory_is_recorded(tmp_path):
    r = _row(tmp_path, "solo", "stdout.log")
    (tmp_path / "j" / "2026-08-01.log").write_text("ran")
    L.corroborate([r])
    assert r["status"] == L.STALE_BUT_SIBLING_FILE_IS_NEWER
    assert r["sibling_evidence"] == "2026-08-01.log"


def test_a_corroborated_job_is_NOT_promoted_to_EVIDENCE_FRESH(tmp_path):
    """The declared surface still shows nothing; all that is established is that
    SOMETHING wrote there."""
    r = _row(tmp_path, "solo", "stdout.log")
    (tmp_path / "j" / "2026-08-01.log").write_text("ran")
    L.corroborate([r])
    assert r["status"] != L.EVIDENCE_FRESH
    assert "NOT a liveness claim" in r["detail"]


def test_a_STALE_sibling_does_NOT_rescue_a_dead_job(tmp_path):
    """The fail-open I introduced and caught before the PR: the first version moved every
    job with ANY newer sibling out of the stale bucket, which rescued `daily103` — whose
    newest file is 94 DAYS old. A corpse newer than the headstone is not liveness."""
    r = _row(tmp_path, "dead", "stdout.log", mtime_days=200)
    old = (dt.datetime.now() - dt.timedelta(days=94)).timestamp()
    sib = tmp_path / "j" / "2026-04-28.log"
    sib.write_text("last gasp")
    os.utime(sib, (old, old))
    L.corroborate([r])
    assert r["status"] == L.NO_EVIDENCE_STALE
    assert r["sibling_missed_firings"] >= L.MISSED_FIRINGS_TOLERANCE
    assert "is ITSELF" in r["detail"]


def test_an_EMPTY_sibling_is_not_evidence(tmp_path):
    r = _row(tmp_path, "solo", "stdout.log")
    (tmp_path / "j" / "empty.log").write_text("")
    L.corroborate([r])
    assert r["status"] == L.NO_EVIDENCE_STALE


def test_corroboration_never_touches_a_non_stale_row(tmp_path):
    r = _row(tmp_path, "ok", "stdout.log")
    r["status"] = L.EVIDENCE_FRESH
    (tmp_path / "j" / "2026-08-01.log").write_text("ran")
    L.corroborate([r])
    assert r["status"] == L.EVIDENCE_FRESH


def test_the_internal_schedule_field_is_never_published(tmp_path):
    """`_schedule_entries_parsed` is plumbing between two passes, not evidence."""
    rep = L.scan([], now=dt.datetime(2026, 8, 1))
    assert all("_schedule_entries_parsed" not in r for r in rep["results"])
