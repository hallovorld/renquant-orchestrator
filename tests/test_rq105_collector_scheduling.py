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
sys.path.insert(0, str(REPO / "src"))

import rq105_liveness_check as liveness  # noqa: E402
import check_activation_prereqs as prereqs  # noqa: E402
from renquant_orchestrator.intraday_pairing_logger import (  # noqa: E402
    ArmObservation, QuoteRef, build_paired_record,
)
from renquant_orchestrator.entry_timing_shadow import (  # noqa: E402
    AdmittedName, PolicyOutcome, Tick, build_record, DEFAULT_CONFIG,
)


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
    today = dt.date.today().isoformat()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    p = tmp_path / "intraday_ticks.jsonl"
    _write_jsonl(p, [{"date": "2026-07-01", "ticker": "AAPL", "ts": now_iso},
                      {"date": today, "ticker": "AAPL", "ts": now_iso}])
    ok, reason = liveness._data_output_fresh(str(p), today, liveness._row_timestamp_quote, liveness._ROW_EVENT_TIME)
    assert ok is True, reason


def test_data_output_fresh_false_when_last_row_is_stale(tmp_path):
    today = dt.date.today().isoformat()
    stale_ts = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=2)).isoformat()
    p = tmp_path / "paired_is.jsonl"
    _write_jsonl(p, [{"date": "2026-06-30", "ticker": "MSFT", "ts": stale_ts}])
    ok, reason = liveness._data_output_fresh(str(p), today, liveness._row_timestamp_quote, liveness._ROW_EVENT_TIME)
    assert ok is False
    assert "stale" in reason


def test_data_output_fresh_false_when_last_row_has_no_timestamp_field(tmp_path):
    """All three collectors write ts/source_ts/tick_time unconditionally — a
    row missing all three does NOT count as 'complete' even with a valid
    date+ticker, and must not pass on a date-only match (that was the
    weaker fallback this review closed: 'today' alone could be hours old)."""
    today = dt.date.today().isoformat()
    p = tmp_path / "no_timestamp.jsonl"
    _write_jsonl(p, [{"date": today, "ticker": "AAPL"}])
    ok, reason = liveness._data_output_fresh(str(p), today, liveness._row_timestamp_quote, liveness._ROW_EVENT_TIME)
    assert ok is False, reason
    assert "timestamp" in reason


def test_data_output_fresh_false_when_row_timestamp_is_in_the_future(tmp_path):
    """A timestamp materially ahead of wall-clock now is clock skew or
    source corruption, not extra freshness — negative age must not read as
    'very fresh'."""
    today = dt.date.today().isoformat()
    future_ts = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)).isoformat()
    p = tmp_path / "future_ts.jsonl"
    _write_jsonl(p, [{"date": today, "ticker": "AAPL", "ts": future_ts}])
    ok, reason = liveness._data_output_fresh(str(p), today, liveness._row_timestamp_quote, liveness._ROW_EVENT_TIME)
    assert ok is False, reason
    assert "FUTURE" in reason


def test_data_output_fresh_true_within_small_clock_skew_tolerance(tmp_path):
    """A few seconds ahead is genuine inter-machine clock drift, not
    corruption — the tolerance must not be zero."""
    today = dt.date.today().isoformat()
    slightly_ahead = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=2)).isoformat()
    p = tmp_path / "small_skew.jsonl"
    _write_jsonl(p, [{"date": today, "ticker": "AAPL", "ts": slightly_ahead}])
    ok, reason = liveness._data_output_fresh(str(p), today, liveness._row_timestamp_quote, liveness._ROW_EVENT_TIME)
    assert ok is True, reason


def test_data_output_fresh_false_when_file_missing(tmp_path):
    p = tmp_path / "does_not_exist.jsonl"
    ok, reason = liveness._data_output_fresh(str(p), "2026-07-02", liveness._row_timestamp_quote, liveness._ROW_EVENT_TIME)
    assert ok is False
    assert "missing" in reason


def test_data_output_fresh_false_when_file_empty(tmp_path):
    p = tmp_path / "entry_timing_shadow.jsonl"
    p.write_text("")
    ok, reason = liveness._data_output_fresh(str(p), "2026-07-02", liveness._row_timestamp_quote, liveness._ROW_EVENT_TIME)
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
    ok, reason = liveness._data_output_fresh(str(p), today, liveness._row_timestamp_quote, liveness._ROW_EVENT_TIME)
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
    ok, reason = liveness._data_output_fresh(str(p), today, liveness._row_timestamp_quote, liveness._ROW_EVENT_TIME)
    assert ok is False, reason


def test_data_output_fresh_false_when_last_row_missing_date_value(tmp_path):
    today = dt.date.today().isoformat()
    p = tmp_path / "empty_date.jsonl"
    _write_jsonl(p, [{"date": "", "ticker": "AAPL"}])
    ok, reason = liveness._data_output_fresh(str(p), today, liveness._row_timestamp_quote, liveness._ROW_EVENT_TIME)
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
    ok, reason = liveness._data_output_fresh(str(p), today, liveness._row_timestamp_quote, liveness._ROW_EVENT_TIME)
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
    ok, reason = liveness._data_output_fresh(str(p), today, liveness._row_timestamp_quote, liveness._ROW_EVENT_TIME)
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
    ok, reason = liveness._data_output_fresh(str(p), today, liveness._row_timestamp_quote, liveness._ROW_EVENT_TIME)
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
    ok, reason = liveness._data_output_fresh(str(p), today, liveness._row_timestamp_quote, liveness._ROW_EVENT_TIME)
    # The oversized final line's opening bytes are chopped by the 256-byte
    # tail seek, so it cannot parse; the scan must fall back to the earlier
    # complete, fresh row and report healthy through it.
    assert ok is True, reason


# ─────────── per-collector schema mismatch (#248 review r4) ───────────
# The three rq105 collectors do NOT share one row schema. A prior round wrongly
# assumed all three unconditionally write a top-level ts/source_ts/tick_time
# field; these tests build rows via the REAL record constructors
# (build_paired_record / build_record) to prove the per-collector extractors
# actually match production, not a guessed field name.


def _fresh_arm(eligible_ts: str, mid: float = 100.0) -> ArmObservation:
    return ArmObservation(
        arm="intraday",
        eligible_ts=eligible_ts,
        arrival_quote=QuoteRef(bid=mid - 0.01, ask=mid + 0.01, source_ts=eligible_ts,
                                source="first_eligible_tick"),
        fill=None,
    )


def test_row_timestamp_pairing_reads_real_build_paired_record(tmp_path):
    """intraday_pairing_logger.build_paired_record() has NO top-level
    timestamp field at all — verified against the real dataclass structure,
    not assumed. The OLD uniform rule (require top-level ts/source_ts/
    tick_time) would reject every real pairing row unconditionally."""
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    intraday_arm = _fresh_arm(now_iso)
    batch_arm = ArmObservation(arm="batch", eligible_ts="2026-07-02T13:30:00+00:00",
                                arrival_quote=QuoteRef(bid=99.9, ask=100.1,
                                                        source_ts="2026-07-02T13:30:00+00:00"),
                                fill=None)
    record = build_paired_record(
        date="2026-07-02", ticker="AAPL", side="buy",
        batch_arm=batch_arm, intraday_arm=intraday_arm)

    # The OLD (buggy) uniform rule: no top-level ts/source_ts/tick_time.
    assert liveness._row_timestamp_quote(record) is None, (
        "a real pairing record has no top-level timestamp — the old uniform "
        "rule would have wrongly rejected this healthy row")

    # The corrected per-collector extractor finds it in the nested arm.
    extracted = liveness._row_timestamp_pairing(record)
    assert extracted is not None
    assert extracted.isoformat().startswith(now_iso[:19])

    p = tmp_path / "paired_is.jsonl"
    p.write_text(json.dumps(record) + "\n")
    # freshness_basis=_FILE_MTIME (pairing is a POST-CLOSE ONE-SHOT batch
    # collector, per the round-4 fix): the row's nested event timestamp is
    # NOT the freshness signal — the just-written file's own mtime is.
    ok, reason = liveness._data_output_fresh(
        str(p), "2026-07-02", liveness._row_timestamp_pairing, liveness._FILE_MTIME)
    assert ok is True, reason


def test_postclose_healthy_run_with_morning_event_timestamps_reports_fresh(tmp_path):
    """The exact scenario codex named: a HEALTHY post-close run, freshly
    written (mtime ~now, e.g. right after the 13:15 PT fire), containing a
    real pairing row whose event timestamps are from THIS MORNING (hours
    before a 14:00 PT liveness check, near session open) — must report
    fresh. Applying the quote feed's 10-minute event-time bound to this row
    would incorrectly fail a perfectly healthy job; only the file's own
    mtime (recorded moments ago by this write) may gate freshness here."""
    morning_iso = "2026-07-02T06:35:00+00:00"  # ~09:35 ET, near session open
    intraday_arm = _fresh_arm(morning_iso)
    batch_arm = ArmObservation(arm="batch", eligible_ts=morning_iso,
                                arrival_quote=QuoteRef(bid=99.9, ask=100.1, source_ts=morning_iso),
                                fill=None)
    record = build_paired_record(
        date="2026-07-02", ticker="AAPL", side="buy",
        batch_arm=batch_arm, intraday_arm=intraday_arm)
    extracted = liveness._row_timestamp_pairing(record)
    assert extracted is not None and extracted.isoformat().startswith(morning_iso[:19])
    # Confirm this row genuinely WOULD fail a row_event_time/tight-bound
    # check — proving the fix isn't accidentally passing for the wrong
    # reason (e.g. because the row happens to also look fresh by event time).
    hours_stale = dt.datetime.now(dt.timezone.utc) - extracted
    assert hours_stale > liveness._TIGHT_AGE_BOUND, (
        "test fixture's morning timestamp must actually be older than the "
        "quote feed's 10min bound, or this test proves nothing")

    p = tmp_path / "paired_is.jsonl"
    p.write_text(json.dumps(record) + "\n")  # mtime is "now" — file just written
    ok, reason = liveness._data_output_fresh(
        str(p), "2026-07-02", liveness._row_timestamp_pairing, liveness._FILE_MTIME)
    assert ok is True, reason


def test_postclose_stale_run_with_todays_morning_rows_still_reports_stale(tmp_path):
    """The inverse scenario codex named: an OLD file (yesterday's leftover,
    or a job that silently stopped running) whose content HAPPENS to carry
    today's morning event timestamps (a contrived-but-illustrative case,
    e.g. a stale test fixture or copied file) must still report stale — the
    check must genuinely be reading file mtime as the completion signal,
    not accidentally passing because the row's date/event-time look
    plausible."""
    morning_iso = "2026-07-02T06:35:00+00:00"
    intraday_arm = _fresh_arm(morning_iso)
    batch_arm = ArmObservation(arm="batch", eligible_ts=morning_iso,
                                arrival_quote=QuoteRef(bid=99.9, ask=100.1, source_ts=morning_iso),
                                fill=None)
    record = build_paired_record(
        date="2026-07-02", ticker="AAPL", side="buy",
        batch_arm=batch_arm, intraday_arm=intraday_arm)
    p = tmp_path / "paired_is.jsonl"
    p.write_text(json.dumps(record) + "\n")
    old = dt.datetime.now().timestamp() - 3 * 3600  # file itself is 3h old, exceeds 90min bound
    import os
    os.utime(str(p), (old, old))
    ok, reason = liveness._data_output_fresh(
        str(p), "2026-07-02", liveness._row_timestamp_pairing, liveness._FILE_MTIME)
    assert ok is False, reason


def test_row_timestamp_entry_timing_reads_real_normal_entry_record(tmp_path):
    """entry_timing_shadow.build_record() writes top-level entry_tick_time
    (verified against the real record constructor), not 'tick_time'."""
    now = dt.datetime.now(dt.timezone.utc)
    tick = Tick(date="2026-07-02", ticker="AAPL", tick_time=now.isoformat(),
                when=now, mid=100.0, bid=99.9, ask=100.1)
    outcome = PolicyOutcome(policy="immediate", eligible=True, entry_tick=tick)
    name = AdmittedName(date="2026-07-02", ticker="AAPL")
    record = build_record(name=name, outcome=outcome, config=DEFAULT_CONFIG)

    assert record["entry_tick_time"] == now.isoformat()
    extracted = liveness._row_timestamp_entry_timing(record)
    assert extracted is not None

    p = tmp_path / "entry_timing_shadow.jsonl"
    p.write_text(json.dumps(record) + "\n")
    # freshness_basis=_FILE_MTIME applies UNCONDITIONALLY to entry-timing
    # (round-4 fix), even for a NORMAL row that has a real entry_tick_time —
    # that field is a market-event instant (often near session open), not a
    # collector-completion signal, so it must not gate freshness here either.
    ok, reason = liveness._data_output_fresh(
        str(p), "2026-07-02", liveness._row_timestamp_entry_timing, liveness._FILE_MTIME)
    assert ok is True, reason


def test_row_timestamp_entry_timing_censored_row_falls_back_to_file_mtime(tmp_path):
    """A censored/no-entry row legitimately has entry_tick_time=None and NO
    other timestamp field (verified against the real record constructor).
    The old uniform rule would have rejected this as 'no parseable
    timestamp' even though it's a genuinely healthy censored outcome for a
    post-close one-shot collector — freshness_basis=_FILE_MTIME must accept
    it and use the file's own mtime as the collector-completion signal."""
    outcome = PolicyOutcome(policy="immediate", eligible=False, entry_tick=None,
                             censored_reason="no_eligible_tick")
    name = AdmittedName(date="2026-07-02", ticker="AAPL")
    record = build_record(name=name, outcome=outcome, config=DEFAULT_CONFIG)

    assert record["entry_tick_time"] is None
    assert liveness._row_timestamp_entry_timing(record) is None

    p = tmp_path / "entry_timing_shadow.jsonl"
    p.write_text(json.dumps(record) + "\n")
    ok, reason = liveness._data_output_fresh(
        str(p), "2026-07-02", liveness._row_timestamp_entry_timing, liveness._FILE_MTIME)
    assert ok is True, reason  # fresh file mtime (just written) carries it


def test_row_timestamp_entry_timing_censored_row_fails_when_file_stale(tmp_path):
    """A censored row's file-mtime basis must still enforce the postclose
    completion age bound (90min, round-4 — wider than the quote feed's
    10min since it's the completion signal for a once-daily batch job) —
    an old file is stale even though the row content is valid."""
    outcome = PolicyOutcome(policy="immediate", eligible=False, entry_tick=None,
                             censored_reason="no_eligible_tick")
    name = AdmittedName(date="2026-07-02", ticker="AAPL")
    record = build_record(name=name, outcome=outcome, config=DEFAULT_CONFIG)

    p = tmp_path / "entry_timing_shadow.jsonl"
    p.write_text(json.dumps(record) + "\n")
    old = dt.datetime.now().timestamp() - 3 * 3600  # 3h ago, exceeds the 90-min postclose bound
    import os
    os.utime(str(p), (old, old))
    ok, reason = liveness._data_output_fresh(
        str(p), "2026-07-02", liveness._row_timestamp_entry_timing, liveness._FILE_MTIME)
    assert ok is False, reason


def test_row_timestamp_pairing_missing_timestamp_falls_back_to_file_mtime(tmp_path):
    """Round-4 correction: pairing is a POST-CLOSE ONE-SHOT batch collector
    (freshness_basis=_FILE_MTIME), not continuously-appended — a pairing
    row with genuinely no extractable timestamp anywhere (e.g. both arms
    null/malformed) is STILL treated as complete via the file's own mtime,
    the same as a censored entry-timing row. This is the OPPOSITE of the
    prior round's behavior for this collector, corrected once codex traced
    the real 13:15-PT-run / 14:00-PT-check schedule showing pairing's row
    timestamps are market-event instants, not completion signals."""
    record = {"date": "2026-07-02", "ticker": "AAPL", "batch_arm": None, "intraday_arm": None}
    assert liveness._row_timestamp_pairing(record) is None
    p = tmp_path / "paired_is.jsonl"
    p.write_text(json.dumps(record) + "\n")
    ok, reason = liveness._data_output_fresh(
        str(p), "2026-07-02", liveness._row_timestamp_pairing, liveness._FILE_MTIME)
    assert ok is True, reason  # fresh file mtime (just written) carries it, like censored entry-timing


def test_row_timestamp_pairing_missing_timestamp_fails_when_file_stale(tmp_path):
    """The file-mtime fallback for a timestamp-less pairing row must still
    enforce the postclose completion bound — an old file is stale even
    though the row's date/ticker schema is otherwise valid."""
    record = {"date": "2026-07-02", "ticker": "AAPL", "batch_arm": None, "intraday_arm": None}
    p = tmp_path / "paired_is.jsonl"
    p.write_text(json.dumps(record) + "\n")
    old = dt.datetime.now().timestamp() - 3 * 3600  # 3h ago, exceeds the 90-min postclose bound
    import os
    os.utime(str(p), (old, old))
    ok, reason = liveness._data_output_fresh(
        str(p), "2026-07-02", liveness._row_timestamp_pairing, liveness._FILE_MTIME)
    assert ok is False, reason


def test_last_complete_jsonl_row_reads_the_final_valid_line_of_a_multiline_file(tmp_path):
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    p = tmp_path / "multi.jsonl"
    _write_jsonl(p, [{"date": "2026-07-02", "ticker": f"T{i}", "ts": now_iso} for i in range(50)])
    row, tail_was_corrupt, has_ts = liveness._last_complete_jsonl_row(
        str(p), liveness._row_timestamp_quote, freshness_basis=liveness._ROW_EVENT_TIME)
    assert row == {"date": "2026-07-02", "ticker": "T49", "ts": now_iso}
    assert tail_was_corrupt is False
    assert has_ts is True


def test_last_complete_jsonl_row_skips_rows_missing_timestamp_field(tmp_path):
    """A row missing its timestamp is not 'complete' for a continuously-
    appended collector (freshness_basis=liveness._ROW_EVENT_TIME) — the true last line
    fails the completeness check, so falling back to an earlier row counts
    as tail_was_corrupt=True (we did not use the file's actual last line)."""
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    p = tmp_path / "mixed.jsonl"
    _write_jsonl(p, [
        {"date": "2026-07-02", "ticker": "AAPL", "ts": now_iso},
        {"date": "2026-07-02", "ticker": "MSFT"},  # no timestamp — must be skipped
    ])
    row, tail_was_corrupt, has_ts = liveness._last_complete_jsonl_row(
        str(p), liveness._row_timestamp_quote, freshness_basis=liveness._ROW_EVENT_TIME)
    assert row == {"date": "2026-07-02", "ticker": "AAPL", "ts": now_iso}
    assert tail_was_corrupt is True
    assert has_ts is True


def test_last_complete_jsonl_row_none_for_missing_file():
    row, tail_was_corrupt, has_ts = liveness._last_complete_jsonl_row(
        "/nonexistent/path/x.jsonl", liveness._row_timestamp_quote, freshness_basis=liveness._ROW_EVENT_TIME)
    assert row is None
    assert tail_was_corrupt is False
    assert has_ts is False


def test_last_complete_jsonl_row_oversized_true_last_line_is_not_corrupt(tmp_path, monkeypatch):
    """Codex review: if the file's true last physical line simply needed a
    bigger read (legitimately long, not corrupt) and the expanded read
    parses it successfully, tail_was_corrupt must be False — the returned
    row IS the actual last line, just recovered with more bytes, not a
    fallback to an earlier one."""
    monkeypatch.setattr(liveness, "_TAIL_CHUNK_BYTES", 256)
    today = dt.date.today().isoformat()
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()
    p = tmp_path / "oversized_true_last.jsonl"
    oversized = json.dumps({"date": today, "ticker": "MSFT", "ts": now_iso, "pad": "x" * 2000})
    p.write_text(oversized)  # the ONLY line — no earlier row to fall back to
    row, tail_was_corrupt, has_ts = liveness._last_complete_jsonl_row(
        str(p), liveness._row_timestamp_quote, freshness_basis=liveness._ROW_EVENT_TIME)
    assert row is not None and row["ticker"] == "MSFT"
    assert tail_was_corrupt is False, (
        "the true last line parsed fine once expanded — it was never corrupt")
    assert has_ts is True


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
