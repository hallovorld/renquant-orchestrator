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


def test_data_output_fresh_false_when_last_row_missing_required_field(tmp_path):
    """A row missing the required 'date' field must FAIL liveness outright —
    it must NEVER fall back to trusting the file's mtime alone (that was the
    #248 review's fail-open bug: a process could append a corrupt/incomplete
    row with a fresh mtime and be reported healthy)."""
    today = dt.date.today().isoformat()
    p = tmp_path / "no_date_field.jsonl"
    _write_jsonl(p, [{"ticker": "AAPL", "no_date_key_here": True}])
    ok, reason = liveness._data_output_fresh(str(p), today)
    assert ok is False, reason
    assert "corrupt" in reason or "truncated" in reason


def test_data_output_fresh_false_when_final_line_is_corrupt_with_fresh_mtime(tmp_path):
    """Codex review case: last physical line is truncated JSON (a writer mid-
    write, or a crash), mtime is fresh (file was just touched), and there is
    NO earlier complete row to fall back to — must fail, not report healthy
    off the fresh mtime alone."""
    today = dt.date.today().isoformat()
    p = tmp_path / "corrupt_tail_only.jsonl"
    p.write_text('{"date": "' + today + '", "ticker": "AAPL", "mid": 12.')  # truncated mid-write
    ok, reason = liveness._data_output_fresh(str(p), today)
    assert ok is False, reason


def test_data_output_fresh_false_when_last_row_missing_date_value(tmp_path):
    today = dt.date.today().isoformat()
    p = tmp_path / "empty_date.jsonl"
    _write_jsonl(p, [{"date": "", "ticker": "AAPL"}])
    ok, reason = liveness._data_output_fresh(str(p), today)
    assert ok is False, reason


def test_data_output_fresh_uses_prior_complete_row_when_tail_is_corrupt(tmp_path):
    """A legitimate mid-write case: the last physical line is a truncated
    write-in-progress, but a complete row immediately before it is FRESH
    (within the tight age bound) and correctly dated today — must be
    reported healthy via that prior row, with the corrupt tail as a
    non-fatal diagnostic, not silently discarded and not fatal on its own."""
    today = dt.date.today().isoformat()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    p = tmp_path / "mid_write.jsonl"
    good_row = json.dumps({"date": today, "ticker": "AAPL", "ts": now_iso})
    p.write_text(good_row + "\n" + '{"date": "' + today + '", "ticker": "MSFT", "ts": "')
    ok, reason = liveness._data_output_fresh(str(p), today)
    assert ok is True, reason


def test_data_output_fresh_false_when_prior_complete_row_is_stale_and_tail_corrupt(tmp_path):
    """Codex review case: a stale-but-valid row followed by a fresh-but-
    corrupt row. The corrupt fresh row must NOT be used to fake freshness
    (its mtime is fresh but it has no usable date/ticker); the fallback to
    the prior row must correctly report it as STALE via its own real date,
    not report healthy just because *some* row exists."""
    today = dt.date.today().isoformat()
    stale = (dt.date.today() - dt.timedelta(days=3)).isoformat()
    p = tmp_path / "stale_then_corrupt.jsonl"
    stale_row = json.dumps({"date": stale, "ticker": "AAPL", "ts": f"{stale}T10:00:00+00:00"})
    p.write_text(stale_row + "\n" + '{"date": "' + today + '", "ticker": "MSFT", "mid": tru')
    ok, reason = liveness._data_output_fresh(str(p), today)
    assert ok is False, reason
    assert "stale" in reason


def test_data_output_fresh_false_when_last_row_timestamp_exceeds_tight_age_bound(tmp_path):
    """A row correctly dated today but whose fine-grained timestamp is hours
    old must fail the TIGHT age bound, not merely the coarse date==today
    check (this is the actual fix beyond the corrupt-row case: 'today' alone
    is too permissive a freshness bar for a collector sampling every 60s)."""
    today = dt.date.today().isoformat()
    stale_ts = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=3)).isoformat()
    p = tmp_path / "stale_ts_fresh_date.jsonl"
    _write_jsonl(p, [{"date": today, "ticker": "AAPL", "ts": stale_ts}])
    ok, reason = liveness._data_output_fresh(str(p), today)
    assert ok is False, reason
    assert "exceeds" in reason


def test_data_output_fresh_handles_row_larger_than_fixed_tail_chunk(tmp_path, monkeypatch):
    """A final row longer than the fixed tail-read chunk gets its opening
    bytes cut off by the seek and correctly fails to parse as JSON on its
    own — the backward scan must still find an earlier complete row rather
    than crashing or silently reporting healthy off the mangled fragment."""
    monkeypatch.setattr(liveness, "_TAIL_CHUNK_BYTES", 256)
    today = dt.date.today().isoformat()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    p = tmp_path / "oversized_last_line.jsonl"
    good_row = json.dumps({"date": today, "ticker": "AAPL", "ts": now_iso})
    oversized = json.dumps({"date": today, "ticker": "MSFT", "ts": now_iso, "pad": "x" * 2000})
    p.write_text(good_row + "\n" + oversized)
    ok, reason = liveness._data_output_fresh(str(p), today)
    # The oversized final line's opening bytes are chopped by the 256-byte
    # tail seek, so it cannot parse; the scan must fall back to the earlier
    # complete, fresh row and report healthy through it.
    assert ok is True, reason


def test_last_complete_jsonl_row_reads_the_final_valid_line_of_a_multiline_file(tmp_path):
    p = tmp_path / "multi.jsonl"
    _write_jsonl(p, [{"date": "2026-07-02", "ticker": f"T{i}"} for i in range(50)])
    row, tail_was_corrupt = liveness._last_complete_jsonl_row(str(p))
    assert row == {"date": "2026-07-02", "ticker": "T49"}
    assert tail_was_corrupt is False


def test_last_complete_jsonl_row_none_for_missing_file():
    row, tail_was_corrupt = liveness._last_complete_jsonl_row("/nonexistent/path/x.jsonl")
    assert row is None
    assert tail_was_corrupt is False


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
