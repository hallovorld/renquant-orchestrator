"""Tests for ops/renquant105/*: launchd plist schedules, the NYSE-holiday-aware
liveness gate, and the per-collector output-freshness check (#232 review — the
plists previously had an invalid Hour=25 and two wrong times, the liveness
check treated every weekday as a session day, and its output check was an
unverified best-effort glob)."""
from __future__ import annotations

import datetime as dt
import json
import plistlib
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
OPS_DIR = REPO / "ops" / "renquant105"
sys.path.insert(0, str(OPS_DIR))

import rq105_liveness_check as liveness  # noqa: E402
import check_activation_prereqs as prereqs  # noqa: E402


# ─────────────────────────── plist schedule checks ───────────────────────────

_EXPECTED_TIMES = {
    "com.renquant.rq105-quote-logger.plist": (6, 25),
    "com.renquant.rq105-postclose.plist": (13, 15),
    "com.renquant.rq105-liveness.plist": (14, 0),
}


@pytest.mark.parametrize("filename,expected", _EXPECTED_TIMES.items())
def test_plist_schedule_matches_documented_pt_time(filename, expected):
    exp_hour, exp_minute = expected
    with open(OPS_DIR / filename, "rb") as fh:
        plist = plistlib.load(fh)
    intervals = plist["StartCalendarInterval"]
    assert len(intervals) == 5, f"{filename}: expected one entry per weekday (Mon-Fri)"
    weekdays = {entry["Weekday"] for entry in intervals}
    assert weekdays == {1, 2, 3, 4, 5}, f"{filename}: must cover Mon(1)-Fri(5) only"
    for entry in intervals:
        assert 0 <= entry["Hour"] <= 23, f"{filename}: Hour={entry['Hour']} out of range"
        assert entry["Hour"] == exp_hour, (
            f"{filename}: Hour={entry['Hour']}, expected {exp_hour} (PT)"
        )
        assert entry["Minute"] == exp_minute, (
            f"{filename}: Minute={entry['Minute']}, expected {exp_minute}"
        )


def test_all_plists_write_under_an_existing_log_directory_convention():
    """StandardOutPath/StandardErrorPath must land under logs/rq105 — the
    README's install step is responsible for creating this directory before
    any plist is loaded (launchd will not create it itself)."""
    for filename in _EXPECTED_TIMES:
        with open(OPS_DIR / filename, "rb") as fh:
            plist = plistlib.load(fh)
        assert "/logs/rq105/" in plist["StandardOutPath"]
        assert "/logs/rq105/" in plist["StandardErrorPath"]


def test_readme_documents_mkdir_before_load_and_current_launchctl_verbs():
    readme = (OPS_DIR / "README.md").read_text()
    assert "mkdir -p" in readme
    assert "logs/rq105" in readme
    assert "launchctl bootstrap" in readme
    assert "launchctl load" not in readme, "deprecated launchctl verb should not remain"
    assert "launchctl unload" not in readme, "deprecated launchctl verb should not remain"
    assert "bootout" in readme
    assert "kickstart" in readme


# ─────────────────────────── holiday-aware session gate ───────────────────────────


class _FakeCalendar:
    """Deterministic stand-in for the real pandas_market_calendars-backed
    NyseSessionCalendar, so this test never depends on that package or a live
    schedule lookup."""

    def __init__(self, holidays: set[dt.date]):
        self._holidays = holidays

    def session_bounds(self, day: dt.date):
        if day.weekday() >= 5 or day in self._holidays:
            return None
        return object()  # any non-None sentinel; liveness only checks is-None


def test_is_session_day_treats_known_2026_holiday_as_non_session(monkeypatch):
    # 2026-01-01 (New Year's Day, a Thursday) is a real NYSE holiday.
    holiday = dt.date(2026, 1, 1)
    monkeypatch.setattr(liveness, "_session_calendar", lambda: _FakeCalendar({holiday}))
    assert liveness._is_session_day(holiday) is False


def test_is_session_day_treats_ordinary_weekday_as_session(monkeypatch):
    ordinary = dt.date(2026, 7, 2)  # a Thursday, not a holiday in the fixture
    monkeypatch.setattr(liveness, "_session_calendar", lambda: _FakeCalendar(set()))
    assert liveness._is_session_day(ordinary) is True


def test_is_session_day_treats_weekend_as_non_session(monkeypatch):
    saturday = dt.date(2026, 7, 4)
    monkeypatch.setattr(liveness, "_session_calendar", lambda: _FakeCalendar(set()))
    assert liveness._is_session_day(saturday) is False


def test_is_session_day_fails_closed_to_true_when_calendar_check_raises(monkeypatch):
    """If the real NYSE calendar dependency is broken/unavailable, treat the
    day as a session day (never silently skip a possible real lapse)."""
    class _Boom:
        def session_bounds(self, day):
            raise RuntimeError("pandas_market_calendars unavailable")

    monkeypatch.setattr(liveness, "_session_calendar", lambda: _Boom())
    assert liveness._is_session_day(dt.date(2026, 7, 2)) is True


# ─────────────────────────── per-collector output freshness ───────────────────────────


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def test_data_output_fresh_true_when_last_row_dated_today(tmp_path):
    today = "2026-07-02"
    p = tmp_path / "intraday_ticks.jsonl"
    _write_jsonl(p, [{"date": "2026-07-01", "ticker": "AAPL"},
                      {"date": today, "ticker": "AAPL"}])
    ok, reason = liveness._data_output_fresh(str(p), today)
    assert ok is True, reason


def test_data_output_fresh_false_when_last_row_is_stale(tmp_path):
    today = "2026-07-02"
    p = tmp_path / "paired_is.jsonl"
    _write_jsonl(p, [{"date": "2026-06-30", "ticker": "MSFT"}])
    ok, reason = liveness._data_output_fresh(str(p), today)
    assert ok is False
    assert "stale" in reason


def test_data_output_fresh_false_when_file_missing(tmp_path):
    p = tmp_path / "does_not_exist.jsonl"
    ok, reason = liveness._data_output_fresh(str(p), "2026-07-02")
    assert ok is False
    assert "missing" in reason


def test_data_output_fresh_false_when_file_empty(tmp_path):
    p = tmp_path / "entry_timing_shadow.jsonl"
    p.write_text("")
    ok, reason = liveness._data_output_fresh(str(p), "2026-07-02")
    assert ok is False
    assert "EMPTY" in reason


def test_data_output_fresh_falls_back_to_mtime_when_last_row_unparseable(tmp_path):
    today = dt.date.today().isoformat()
    p = tmp_path / "no_date_field.jsonl"
    _write_jsonl(p, [{"ticker": "AAPL", "no_date_key_here": True}])
    ok, reason = liveness._data_output_fresh(str(p), today)
    # mtime is "today" since the file was just written by this test.
    assert ok is True, reason


def test_last_jsonl_row_reads_the_final_line_of_a_multiline_file(tmp_path):
    p = tmp_path / "multi.jsonl"
    _write_jsonl(p, [{"n": i} for i in range(50)])
    row = liveness._last_jsonl_row(str(p))
    assert row == {"n": 49}


def test_last_jsonl_row_none_for_missing_file():
    assert liveness._last_jsonl_row("/nonexistent/path/x.jsonl") is None


# ─────────────────────── N1b activation guard (#232 review r2) ───────────────


def _write_rfc(tmp_path: Path, body: str) -> Path:
    doc_dir = tmp_path / "doc" / "design"
    doc_dir.mkdir(parents=True)
    rfc = doc_dir / "2026-06-30-renquant105-intraday-decisioning-architecture.md"
    rfc.write_text(body)
    return tmp_path


def test_activation_guard_refuses_when_both_prereqs_missing(tmp_path):
    repo_root = _write_rfc(tmp_path, "REVISION: r12 (2026-06-30) — rollout-boundary fix.")
    ok, missing = prereqs.check_prereqs(repo_root)
    assert ok is False
    assert len(missing) == 2


def test_activation_guard_refuses_when_only_224_landed(tmp_path):
    repo_root = _write_rfc(
        tmp_path,
        "REVISION: r13 (2026-07-02) — folds in amendment A2 from the independent design review.",
    )
    ok, missing = prereqs.check_prereqs(repo_root)
    assert ok is False
    assert any("#227" in m for m in missing)
    assert not any("#224" in m for m in missing)


def test_activation_guard_refuses_when_only_227_landed(tmp_path):
    repo_root = _write_rfc(
        tmp_path,
        "REVISION: r14 (2026-07-02) — measurement-integrity pins (amendment A5.1-A5.3).",
    )
    ok, missing = prereqs.check_prereqs(repo_root)
    assert ok is False
    assert any("#224" in m for m in missing)
    assert not any("#227" in m for m in missing)


def test_activation_guard_passes_when_both_landed(tmp_path):
    repo_root = _write_rfc(
        tmp_path,
        "REVISION: r14 (2026-07-02) — measurement-integrity pins (amendment A5.1-A5.3). "
        "Prior: r13 (2026-07-02) — folds in amendment A2 from the independent design review.",
    )
    ok, missing = prereqs.check_prereqs(repo_root)
    assert ok is True
    assert missing == []


def test_activation_guard_refuses_when_rfc_file_missing(tmp_path):
    ok, missing = prereqs.check_prereqs(tmp_path)
    assert ok is False
    assert "not found" in missing[0]


def test_activation_guard_main_refuses_and_prints_missing_items(tmp_path, monkeypatch, capsys):
    repo_root = _write_rfc(tmp_path, "REVISION: r12 (2026-06-30) — rollout-boundary fix.")
    original_check_prereqs = prereqs.check_prereqs
    monkeypatch.setattr(
        prereqs, "check_prereqs", lambda root: original_check_prereqs(repo_root)
    )
    rc = prereqs.main([])
    assert rc == 1
    err = capsys.readouterr().err
    assert "REFUSED" in err
    assert "#224" in err and "#227" in err


def test_activation_guard_main_passes_when_both_landed(tmp_path, monkeypatch, capsys):
    repo_root = _write_rfc(
        tmp_path,
        "REVISION: r14 (2026-07-02) — measurement-integrity pins (amendment A5.1-A5.3). "
        "Prior: r13 (2026-07-02) — folds in amendment A2 from the independent design review.",
    )
    original_check_prereqs = prereqs.check_prereqs
    monkeypatch.setattr(
        prereqs, "check_prereqs", lambda root: original_check_prereqs(repo_root)
    )
    rc = prereqs.main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "OK" in out
