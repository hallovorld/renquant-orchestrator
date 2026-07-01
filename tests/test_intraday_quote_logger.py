"""Tests for ``intraday_quote_logger`` — renquant105 Stage-1 OBSERVE-ONLY tick feed.

Fully hermetic and deterministic: a fake quote source (no network, no Alpaca), a
fake exchange calendar (session boundaries injected) and an injected clock (no
wall-clock, no real sleeps). Verifies the DATA-VALIDITY policy the reviewer
required — calendar-aware sessions (holidays, early closes, DST), quote causality
+ freshness + same-session membership, crossed/invalid NBBO censoring, the frozen
eligibility-policy stamp — plus the record schema ``intraday_pairing_logger``
consumes (incl. a REAL round-trip against the actual #215 consumer, pinned as a
fixture until #215 merges). Never touches live state.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

import pytest

from renquant_orchestrator.intraday_quote_logger import (
    DEFAULT_FUTURE_TOLERANCE_SEC,
    DEFAULT_MAX_QUOTE_AGE_SEC,
    ELIGIBILITY_POLICY_VERSION,
    ET,
    STATUS_CROSSED_NBBO,
    STATUS_FUTURE_QUOTE,
    STATUS_INVALID_NBBO,
    STATUS_NO_SOURCE_TS,
    STATUS_OK,
    STATUS_OUT_OF_SESSION,
    STATUS_STALE_PRIOR_SESSION,
    STATUS_STALE_QUOTE,
    STATUS_UNPRICEABLE,
    AlpacaQuoteSource,
    NyseSessionCalendar,
    Quote,
    QuoteLogger,
    SessionBounds,
    TickFeedWriter,
    alpaca_credentials_present,
    build_tick_record,
    default_censor_feed_path,
    default_tick_feed_path,
    evaluate_quote,
    is_market_hours,
    load_watchlist,
    main,
    market_phase,
    session_date,
    tick_key,
)

UTC = ZoneInfo("UTC")

DATE = "2026-06-30"  # a Tuesday (regular session, EDT)
OPEN_10AM = datetime(2026, 6, 30, 10, 0, tzinfo=ET)
BEFORE_OPEN = datetime(2026, 6, 30, 9, 0, tzinfo=ET)
AFTER_CLOSE = datetime(2026, 6, 30, 16, 5, tzinfo=ET)
SATURDAY = datetime(2026, 7, 4, 11, 0, tzinfo=ET)
QTS = "2026-06-30T10:00:00-04:00"  # exchange ts == sample instant

# A fake session for 2026-06-30 (regular EDT hours).
SESSION_0630 = SessionBounds(
    open=datetime(2026, 6, 30, 9, 30, tzinfo=ET),
    close=datetime(2026, 6, 30, 16, 0, tzinfo=ET),
)


class FakeCalendar:
    """Deterministic session calendar: a dict of ET date -> SessionBounds. A date
    absent from the map is a non-trading day (weekend/holiday)."""

    name = "FAKE"

    def __init__(self, sessions: Mapping[date, SessionBounds]) -> None:
        self._sessions = dict(sessions)

    def session_bounds(self, day: date) -> SessionBounds | None:
        return self._sessions.get(day)


CAL_0630 = FakeCalendar({date(2026, 6, 30): SESSION_0630})


class FakeQuoteSource:
    """Deterministic in-memory quote source. Absent tickers simulate a per-ticker
    miss; ``raise_all`` simulates a whole-batch fetch failure."""

    name = "fake"

    def __init__(self, quotes: Mapping[str, Quote], *, raise_all: bool = False) -> None:
        self._quotes = dict(quotes)
        self._raise_all = raise_all

    def get_quotes(self, tickers: Sequence[str]) -> Mapping[str, Quote]:
        if self._raise_all:
            raise RuntimeError("simulated batch failure")
        return {t: self._quotes[t] for t in tickers if t in self._quotes}


def _logger(tmp_path, source, tickers, *, calendar=CAL_0630, **kw):
    return QuoteLogger(
        source,
        TickFeedWriter(tmp_path / "ticks.jsonl"),
        tickers,
        calendar=calendar,
        censor_writer=TickFeedWriter(tmp_path / "ticks.censored.jsonl"),
        **kw,
    )


# ---------------------------------------------------------------------------
# Quote.mid
# ---------------------------------------------------------------------------
def test_mid_from_nbbo():
    assert Quote(bid=100.0, ask=100.2).mid() == pytest.approx(100.1)


def test_mid_falls_back_to_last_when_one_sided():
    assert Quote(bid=100.0, ask=None, last=99.5).mid() == pytest.approx(99.5)
    assert Quote(bid=None, ask=None, last=101.0).mid() == pytest.approx(101.0)


def test_mid_none_when_unpriceable():
    assert Quote(bid=None, ask=None, last=None).mid() is None


# ---------------------------------------------------------------------------
# Calendar-aware market-hours gating (fake calendar injected)
# ---------------------------------------------------------------------------
def test_market_phase_open_before_closed_weekend():
    assert market_phase(OPEN_10AM, CAL_0630) == "open"
    assert market_phase(BEFORE_OPEN, CAL_0630) == "before_open"
    assert market_phase(AFTER_CLOSE, CAL_0630) == "closed"
    assert market_phase(datetime(2026, 6, 30, 16, 0, tzinfo=ET), CAL_0630) == "closed"  # close exclusive
    assert market_phase(datetime(2026, 6, 30, 9, 30, tzinfo=ET), CAL_0630) == "open"  # open inclusive
    # a date absent from the calendar (holiday/weekend) is closed
    assert market_phase(SATURDAY, CAL_0630) == "closed"


def test_market_phase_holiday_is_closed_all_day():
    # New Year's Day 2026 is not a trading session -> closed even at "10am".
    cal = FakeCalendar({})  # no sessions at all
    assert market_phase(datetime(2026, 1, 1, 10, 0, tzinfo=ET), cal) == "closed"
    assert is_market_hours(datetime(2026, 1, 1, 10, 0, tzinfo=ET), cal) is False


def test_market_phase_early_close_half_day():
    # A 13:00 ET early close: 12:59 is open, 13:00 is closed.
    early = SessionBounds(
        open=datetime(2026, 11, 27, 9, 30, tzinfo=ET),
        close=datetime(2026, 11, 27, 13, 0, tzinfo=ET),
    )
    cal = FakeCalendar({date(2026, 11, 27): early})
    assert market_phase(datetime(2026, 11, 27, 12, 59, tzinfo=ET), cal) == "open"
    assert market_phase(datetime(2026, 11, 27, 13, 0, tzinfo=ET), cal) == "closed"
    # 14:00 would be "open" under a naive 09:30-16:00 rule — the calendar closes it.
    assert market_phase(datetime(2026, 11, 27, 14, 0, tzinfo=ET), cal) == "closed"


def test_is_market_hours():
    assert is_market_hours(OPEN_10AM, CAL_0630) is True
    assert is_market_hours(BEFORE_OPEN, CAL_0630) is False
    assert is_market_hours(AFTER_CLOSE, CAL_0630) is False


def test_session_date_is_et():
    assert session_date(OPEN_10AM) == DATE
    # a UTC instant (2026-07-01 02:00Z) is still the prior ET calendar day
    assert session_date(datetime(2026, 7, 1, 2, 0, tzinfo=UTC)) == DATE


# ---------------------------------------------------------------------------
# Real NYSE calendar (pandas_market_calendars) — holiday / early close / DST
# ---------------------------------------------------------------------------
def test_nyse_calendar_regular_session_edt():
    cal = NyseSessionCalendar()
    b = cal.session_bounds(date(2026, 6, 30))
    assert b is not None
    assert (b.open.hour, b.open.minute) == (9, 30)
    assert (b.close.hour, b.close.minute) == (16, 0)
    # EDT in summer -> UTC-4
    assert b.open.utcoffset().total_seconds() == -4 * 3600


def test_nyse_calendar_holidays_have_no_session():
    cal = NyseSessionCalendar()
    for holiday in (date(2026, 1, 1), date(2026, 7, 3), date(2026, 11, 26), date(2026, 12, 25)):
        assert cal.session_bounds(holiday) is None


def test_nyse_calendar_early_close_half_days():
    cal = NyseSessionCalendar()
    for half in (date(2026, 11, 27), date(2026, 12, 24)):
        b = cal.session_bounds(half)
        assert b is not None
        assert (b.close.hour, b.close.minute) == (13, 0)  # 1pm early close


def test_nyse_calendar_dst_boundary_open_is_0930_local_both_seasons():
    cal = NyseSessionCalendar()
    summer = cal.session_bounds(date(2026, 6, 30))  # EDT (UTC-4)
    winter = cal.session_bounds(date(2026, 12, 15))  # EST (UTC-5)
    assert summer is not None and winter is not None
    # Local open is 09:30 in BOTH seasons (DST resolved) ...
    assert (summer.open.hour, summer.open.minute) == (9, 30)
    assert (winter.open.hour, winter.open.minute) == (9, 30)
    # ... but the UTC instant differs by the DST hour (13:30Z vs 14:30Z).
    assert summer.open.astimezone(UTC).hour == 13
    assert winter.open.astimezone(UTC).hour == 14


def test_nyse_calendar_matches_execution_primitive(tmp_path):
    # Same source of truth as renquant_execution.preopen_cancel_gate: NYSE via
    # pandas_market_calendars. Cross-check open/close against a direct schedule().
    import pandas_market_calendars as mcal

    sched = mcal.get_calendar("NYSE").schedule("2026-11-27", "2026-11-27")
    exp_close = sched["market_close"].iloc[0].tz_convert(ET)
    got = NyseSessionCalendar().session_bounds(date(2026, 11, 27))
    assert got is not None
    assert got.close == exp_close.to_pydatetime()


# ---------------------------------------------------------------------------
# evaluate_quote — the frozen eligibility policy (causality/freshness/NBBO)
# ---------------------------------------------------------------------------
def test_evaluate_ok_within_session_and_fresh():
    q = Quote(bid=100.0, ask=100.2, ts="2026-06-30T09:59:30-04:00")
    ev = evaluate_quote(q, sampled_at=OPEN_10AM, session=SESSION_0630)
    assert ev.status == STATUS_OK
    assert ev.mid == pytest.approx(100.1)
    assert ev.quote_age == pytest.approx(30.0)


def test_evaluate_out_of_session_when_no_session():
    q = Quote(bid=100.0, ask=100.2, ts=QTS)
    ev = evaluate_quote(q, sampled_at=OPEN_10AM, session=None)
    assert ev.status == STATUS_OUT_OF_SESSION
    assert ev.mid is None


def test_evaluate_out_of_session_when_sample_after_close():
    q = Quote(bid=100.0, ask=100.2, ts="2026-06-30T16:05:00-04:00")
    ev = evaluate_quote(q, sampled_at=AFTER_CLOSE, session=SESSION_0630)
    assert ev.status == STATUS_OUT_OF_SESSION


def test_evaluate_crossed_nbbo_censored():
    q = Quote(bid=100.3, ask=100.0, ts=QTS)  # bid > ask
    ev = evaluate_quote(q, sampled_at=OPEN_10AM, session=SESSION_0630)
    assert ev.status == STATUS_CROSSED_NBBO
    assert ev.mid is None


def test_evaluate_invalid_nbbo_nonpositive():
    q = Quote(bid=0.0, ask=100.0, ts=QTS)  # non-positive bid
    ev = evaluate_quote(q, sampled_at=OPEN_10AM, session=SESSION_0630)
    assert ev.status == STATUS_INVALID_NBBO


def test_evaluate_unpriceable():
    q = Quote(bid=None, ask=None, last=None, ts=QTS)
    ev = evaluate_quote(q, sampled_at=OPEN_10AM, session=SESSION_0630)
    assert ev.status == STATUS_UNPRICEABLE


def test_evaluate_no_source_ts_censored():
    q = Quote(bid=100.0, ask=100.2, ts=None)  # cannot prove causality
    ev = evaluate_quote(q, sampled_at=OPEN_10AM, session=SESSION_0630)
    assert ev.status == STATUS_NO_SOURCE_TS


def test_evaluate_future_quote_censored():
    # Source timestamp minutes AHEAD of the sample instant -> skewed/future.
    q = Quote(bid=100.0, ask=100.2, ts="2026-06-30T10:05:00-04:00")
    ev = evaluate_quote(q, sampled_at=OPEN_10AM, session=SESSION_0630)
    assert ev.status == STATUS_FUTURE_QUOTE


def test_evaluate_future_quote_censored_even_by_one_second():
    # Codex r2: the contract is source_ts <= sampled_at with ZERO tolerance — a
    # quote just ONE SECOND ahead of the sample instant must fail closed, never be
    # admitted as OK (point-in-time evidence must never include future data; a
    # prior 2s "benign clock skew" tolerance let this slip through as STATUS_OK).
    q = Quote(bid=100.0, ask=100.2, ts="2026-06-30T10:00:01-04:00")
    ev = evaluate_quote(q, sampled_at=OPEN_10AM, session=SESSION_0630)
    assert ev.status == STATUS_FUTURE_QUOTE
    assert ev.mid is None
    # explicit default-tolerance sanity: the production default is really 0.0
    assert DEFAULT_FUTURE_TOLERANCE_SEC == 0.0


def test_evaluate_quote_at_exact_sample_instant_is_ok_not_future():
    # source_ts == sampled_at (quote_age == 0) is the boundary case: NOT future.
    q = Quote(bid=100.0, ask=100.2, ts="2026-06-30T10:00:00-04:00")
    ev = evaluate_quote(q, sampled_at=OPEN_10AM, session=SESSION_0630)
    assert ev.status == STATUS_OK
    assert ev.quote_age == pytest.approx(0.0)


def test_evaluate_stale_repeated_prior_session_quote_censored():
    # A repeated quote whose exchange ts is from YESTERDAY's session: same-session
    # membership fails -> stale_prior_session (not treated as today's evidence).
    q = Quote(bid=100.0, ask=100.2, ts="2026-06-29T15:59:00-04:00")
    ev = evaluate_quote(q, sampled_at=OPEN_10AM, session=SESSION_0630)
    assert ev.status == STATUS_STALE_PRIOR_SESSION


def test_evaluate_stale_by_age_within_session_censored():
    # Same-session but older than max age -> stale_quote.
    old_ts = "2026-06-30T09:56:00-04:00"  # 4 min before a 10:00 sample
    ev = evaluate_quote(
        Quote(bid=100.0, ask=100.2, ts=old_ts),
        sampled_at=OPEN_10AM,
        session=SESSION_0630,
        max_age_sec=120.0,
    )
    assert ev.status == STATUS_STALE_QUOTE
    assert ev.quote_age == pytest.approx(240.0)


# ---------------------------------------------------------------------------
# build_tick_record — always returns a record with a status + policy stamp
# ---------------------------------------------------------------------------
def test_build_tick_record_ok_schema_and_mid():
    rec = build_tick_record(
        ticker="NVDA",
        quote=Quote(bid=100.0, ask=100.2, last=100.1, ts=QTS),
        sample_ts=OPEN_10AM,
        session=SESSION_0630,
        date=DATE,
        source_name="fake",
    )
    assert rec["status"] == STATUS_OK
    # keys the CURRENT #215 consumer reads (schema v3):
    # date/ticker (join key) + source_ts (as-of ordering/selection) + bid/ask
    # (the consumer derives + validates its own arrival mid from these).
    assert rec["schema_version"] == "3"
    assert rec["date"] == DATE
    assert rec["ticker"] == "NVDA"
    assert rec["source_ts"] == QTS  # exact key select_first_eligible_tick reads
    assert rec["bid"] == 100.0 and rec["ask"] == 100.2 and rec["last"] == 100.1
    # this producer's own validated mid + as-of convenience field ride along too
    assert rec["mid"] == pytest.approx(100.1)
    assert rec["tick_time"] == QTS  # prefers the exchange quote timestamp
    # frozen eligibility policy stamp + provenance
    assert rec["eligibility_policy_version"] == ELIGIBILITY_POLICY_VERSION
    assert rec["max_quote_age_sec"] == DEFAULT_MAX_QUOTE_AGE_SEC
    assert rec["session_open"] == SESSION_0630.open.isoformat()
    assert rec["quote_age"] == pytest.approx(0.0)
    # observe-only provenance, no verdict / order / entry_price. The consumer no
    # longer defaults any arm's entry to a midpoint (v2 removed midpoint-as-fill).
    assert rec["observe_only"] is True
    assert "entry_price" not in rec
    assert "order" not in rec and "verdict" not in rec


def test_build_tick_record_source_ts_none_when_quote_ts_absent():
    # source_ts is the RAW quote.ts (None when absent), never fabricated from the
    # sample instant — that fallback belongs only to tick_time (an audit
    # convenience field for the censored sidecar, since a no-source-ts quote is
    # censored anyway and never reaches the eligible feed).
    rec = build_tick_record(
        ticker="NVDA",
        quote=Quote(bid=100.0, ask=100.2, ts=None),
        sample_ts=OPEN_10AM,
        session=SESSION_0630,
        date=DATE,
    )
    assert rec["status"] == STATUS_NO_SOURCE_TS
    assert rec["source_ts"] is None
    assert rec["tick_time"] is not None  # falls back to the sample instant


def test_build_tick_record_censored_has_no_consumable_mid():
    # A crossed NBBO is recorded WITH a status but mid=None, so even if it reached
    # the consumer it could not be used as evidence.
    rec = build_tick_record(
        ticker="MU",
        quote=Quote(bid=50.4, ask=50.0, ts=QTS),  # crossed
        sample_ts=OPEN_10AM,
        session=SESSION_0630,
        date=DATE,
    )
    assert rec["status"] == STATUS_CROSSED_NBBO
    assert rec["mid"] is None


def test_tick_key_shape():
    rec = build_tick_record(
        ticker="NVDA",
        quote=Quote(bid=100.0, ask=100.2, ts=QTS),
        sample_ts=OPEN_10AM,
        session=SESSION_0630,
        date=DATE,
    )
    assert tick_key(rec) == (DATE, "NVDA", QTS)


# ---------------------------------------------------------------------------
# TickFeedWriter — idempotent append
# ---------------------------------------------------------------------------
def _rec(ticker: str, ts: str, mid_bid: float = 100.0) -> dict:
    return build_tick_record(
        ticker=ticker,
        quote=Quote(bid=mid_bid, ask=mid_bid + 0.2, ts=ts),
        sample_ts=OPEN_10AM,
        session=SESSION_0630,
        date=DATE,
    )


def test_writer_idempotent_append(tmp_path):
    out = tmp_path / "renquant105_pilot" / "intraday_ticks.jsonl"
    writer = TickFeedWriter(out)
    recs = [_rec("NVDA", QTS), _rec("MU", QTS)]
    assert writer.append(recs) == 2
    assert out.exists()
    # same observations again -> nothing new
    assert writer.append(recs) == 0
    assert len(out.read_text().strip().splitlines()) == 2
    # a distinct quote timestamp for NVDA -> a new row
    assert writer.append([_rec("NVDA", "2026-06-30T10:01:00-04:00")]) == 1
    assert len(out.read_text().strip().splitlines()) == 3


def test_writer_dedup_survives_restart(tmp_path):
    out = tmp_path / "ticks.jsonl"
    TickFeedWriter(out).append([_rec("NVDA", QTS)])
    # a fresh writer reloads the existing keys from disk
    assert TickFeedWriter(out).append([_rec("NVDA", QTS)]) == 0


def test_default_censor_feed_path_is_sidecar():
    p = default_censor_feed_path("/x/y/intraday_ticks.jsonl")
    assert p == Path("/x/y/intraday_ticks.jsonl.censored.jsonl")


# ---------------------------------------------------------------------------
# QuoteLogger.sample_once
# ---------------------------------------------------------------------------
def test_sample_once_writes_ok_censors_bad_skips_missing(tmp_path):
    source = FakeQuoteSource(
        {
            "NVDA": Quote(bid=100.0, ask=100.2, ts=QTS),  # ok
            "MU": Quote(bid=None, ask=None, last=None, ts=QTS),  # unpriceable -> censor
            "AMD": Quote(bid=10.4, ask=10.0, ts=QTS),  # crossed -> censor
            # AAPL absent from the source -> a per-ticker source miss (skip)
        }
    )
    logger = _logger(tmp_path, source, ["NVDA", "MU", "AMD", "AAPL"])
    summary = logger.sample_once(now=OPEN_10AM)
    assert summary["sampled"] is True
    assert summary["n_ok"] == 1
    assert summary["n_censored"] == 2
    assert summary["n_missing"] == 1
    assert summary["rows_written"] == 1
    assert summary["censored_written"] == 2
    assert summary["censored_reasons"] == {STATUS_UNPRICEABLE: 1, STATUS_CROSSED_NBBO: 1}
    # eligible feed holds only the ok tick; sidecar holds the censored ones
    feed = [json.loads(line) for line in (tmp_path / "ticks.jsonl").read_text().splitlines()]
    assert [r["ticker"] for r in feed] == ["NVDA"]
    assert all(r["status"] == STATUS_OK for r in feed)
    sidecar = [json.loads(line) for line in (tmp_path / "ticks.censored.jsonl").read_text().splitlines()]
    assert {r["ticker"] for r in sidecar} == {"MU", "AMD"}
    assert all(r["mid"] is None for r in sidecar)


def test_sample_once_market_hours_gate(tmp_path):
    source = FakeQuoteSource({"NVDA": Quote(bid=100.0, ask=100.2, ts=QTS)})
    logger = _logger(tmp_path, source, ["NVDA"])
    closed = logger.sample_once(now=AFTER_CLOSE)
    assert closed["sampled"] is False
    assert closed["reason"] == "market_closed"
    assert closed["rows_written"] == 0
    # --force bypasses the sample gate, but an out-of-session quote is still CENSORED
    # (never eligible) — a forced off-hours run yields audit rows, not evidence.
    forced = logger.sample_once(now=AFTER_CLOSE, force=True)
    assert forced["sampled"] is True
    assert forced["rows_written"] == 0
    assert forced["n_censored"] == 1
    assert forced["censored_reasons"] == {STATUS_OUT_OF_SESSION: 1}


def test_sample_once_partial_source_failure_isolation(tmp_path):
    # AAPL absent from the source mapping simulates a per-ticker miss (transport
    # gap): counted as missing, never fatal; the good tickers still write.
    source = FakeQuoteSource(
        {
            "NVDA": Quote(bid=100.0, ask=100.2, ts=QTS),
            "MSFT": Quote(bid=400.0, ask=400.4, ts=QTS),
        }
    )
    logger = _logger(tmp_path, source, ["NVDA", "AAPL", "MSFT"])
    summary = logger.sample_once(now=OPEN_10AM)
    assert summary["n_ok"] == 2  # NVDA + MSFT
    assert summary["n_missing"] == 1  # AAPL missing, not fatal
    assert summary["rows_written"] == 2


def test_sample_once_whole_batch_failure_does_not_raise(tmp_path):
    source = FakeQuoteSource({}, raise_all=True)
    logger = _logger(tmp_path, source, ["NVDA", "MU"])
    summary = logger.sample_once(now=OPEN_10AM)  # must not raise
    assert summary["sampled"] is True
    assert summary["n_ok"] == 0
    assert summary["rows_written"] == 0
    assert summary["n_missing"] == 2


def test_sample_once_on_holiday_with_force_all_censored(tmp_path):
    # No session on the calendar for this date -> even forced, everything censors.
    holiday_cal = FakeCalendar({})
    now = datetime(2026, 1, 1, 10, 0, tzinfo=ET)
    source = FakeQuoteSource({"NVDA": Quote(bid=100.0, ask=100.2, ts="2026-01-01T10:00:00-05:00")})
    logger = _logger(tmp_path, source, ["NVDA"], calendar=holiday_cal)
    summary = logger.sample_once(now=now, force=True)
    assert summary["rows_written"] == 0
    assert summary["censored_reasons"] == {STATUS_OUT_OF_SESSION: 1}


# ---------------------------------------------------------------------------
# run_loop — injected clock + sleep, no wall-clock
# ---------------------------------------------------------------------------
def test_run_loop_samples_during_open_and_stops_at_close(tmp_path):
    source = FakeQuoteSource({"NVDA": Quote(bid=100.0, ask=100.2, ts=QTS)})
    logger = _logger(tmp_path, source, ["NVDA"])
    times = iter(
        [
            BEFORE_OPEN,  # wait, no sample
            datetime(2026, 6, 30, 9, 35, tzinfo=ET),  # sample
            datetime(2026, 6, 30, 9, 36, tzinfo=ET),  # sample (distinct tick via quote ts)
            AFTER_CLOSE,  # stop
        ]
    )
    # give each open tick a distinct, fresh, in-session quote timestamp
    qts = iter(["2026-06-30T09:35:00-04:00", "2026-06-30T09:36:00-04:00"])

    def source_get(tickers):
        return {"NVDA": Quote(bid=100.0, ask=100.2, ts=next(qts))}

    source.get_quotes = source_get  # type: ignore[assignment]

    slept: list[float] = []
    result = logger.run_loop(
        cadence_sec=30,
        now_fn=lambda: next(times),
        sleep_fn=slept.append,
        max_cycles=10,
    )
    assert result["samples"] == 2
    assert result["rows_written"] == 2
    assert slept == [30, 30, 30]  # before_open, open, open (then closed -> break)


def test_run_loop_force_respects_max_cycles(tmp_path):
    # Forced off-hours: it still SAMPLES max_cycles times, but every quote is
    # out-of-session so nothing lands in the eligible feed.
    source = FakeQuoteSource({"NVDA": Quote(bid=100.0, ask=100.2, ts=QTS)})
    logger = _logger(tmp_path, source, ["NVDA"])
    result = logger.run_loop(
        cadence_sec=1,
        now_fn=lambda: AFTER_CLOSE,  # closed, but force bypasses the gate
        sleep_fn=lambda _s: None,
        force=True,
        max_cycles=3,
    )
    assert result["cycles"] == 3
    assert result["samples"] == 3
    assert result["rows_written"] == 0  # all out-of-session -> censored
    assert result["censored_written"] >= 1


# ---------------------------------------------------------------------------
# Schema + round-trip against the real consumer
# ---------------------------------------------------------------------------
def test_feed_reads_back_required_keys(tmp_path):
    source = FakeQuoteSource(
        {
            "NVDA": Quote(bid=100.0, ask=100.2, ts=QTS),
            "MU": Quote(bid=50.0, ask=50.4, ts=QTS),
        }
    )
    logger = _logger(tmp_path, source, ["NVDA", "MU"])
    logger.sample_once(now=OPEN_10AM)
    lines = [json.loads(line) for line in (tmp_path / "ticks.jsonl").read_text().strip().splitlines()]
    assert {r["ticker"] for r in lines} == {"NVDA", "MU"}
    for r in lines:
        assert r["date"] == DATE
        assert isinstance(r["mid"], float)
        assert isinstance(r["source_ts"], str)  # the consumer's as-of ordering key
        assert "tick_time" in r


def _load_vendored_pr215_consumer():
    """Drop the ACTUAL #215 consumer in (pinned verbatim, re-vendored from its
    CURRENT head at ``tests/fixtures/intraday_pairing_logger_pr215.py`` — see that
    file's header for the exact pinned commit) and load it under the
    ``renquant_orchestrator`` package so its relative import
    (``from .runtime_paths import ...``) resolves against the installed package.
    Proves interop against the current producer/consumer schema+version contract
    NOW instead of leaving it skipped until #215 merges (Codex #216 r2). Loaded
    under a distinct module name so it never shadows the real module; cleaned up
    by the caller."""
    fixture = Path(__file__).parent / "fixtures" / "intraday_pairing_logger_pr215.py"
    modname = "renquant_orchestrator._vendored_intraday_pairing_logger_pr215"
    spec = importlib.util.spec_from_file_location(modname, fixture)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[modname] = mod
    spec.loader.exec_module(mod)
    return modname, mod


def _sample_two_names_into(tmp_path, calendar=CAL_0630, now=OPEN_10AM):
    """Shared setup for both round-trip tests: sample NVDA + MU through THIS
    producer into a real tick-feed file, returning its path."""
    source = FakeQuoteSource(
        {
            "NVDA": Quote(bid=100.0, ask=100.2, ts=QTS),
            "MU": Quote(bid=50.0, ask=50.4, ts=QTS),
        }
    )
    out = tmp_path / "ticks.jsonl"
    QuoteLogger(
        source,
        TickFeedWriter(out),
        ["NVDA", "MU"],
        calendar=calendar,
        censor_writer=TickFeedWriter(tmp_path / "ticks.censored.jsonl"),
    ).sample_once(now=now)
    return out


def _assert_round_trip_into_current_pairing_contract(pairing, out, tmp_path):
    """Shared assertions against the v2 (current-head) #215 contract: raw per-arm
    arrival observations, NO midpoint-as-fill, ``source_ts``-keyed tick selection.
    Shared by the vendored-fixture test and the (currently skipped)
    real-installed-module test so both exercise the identical current contract."""
    ticks = pairing.load_intraday_ticks(out, DATE)
    assert set(ticks) == {(DATE, "NVDA"), (DATE, "MU")}
    # each name maps to the RAW LIST of its ticks (v2 — selection happens in
    # pair_records via the frozen first-eligible-tick rule, not in the loader).
    nvda_ticks = ticks[(DATE, "NVDA")]
    assert len(nvda_ticks) == 1
    # the exact key select_first_eligible_tick / _quote_from_tick read for as-of
    # ordering + arrival-quote construction — this producer's schema v3 field.
    assert nvda_ticks[0]["source_ts"] == QTS
    assert nvda_ticks[0]["mid"] == pytest.approx(100.1)
    assert nvda_ticks[0]["bid"] == 100.0 and nvda_ticks[0]["ask"] == 100.2

    admitted = [pairing.AdmittedName(DATE, "NVDA", "buy", "sv1")]
    fills = {("sv1", "NVDA"): pairing.PriceRef(101.0)}
    # The intraday arm's arrival tick is chosen by the FROZEN first-eligible-tick
    # rule (as-of enforced): supply the conviction/eligibility instant explicitly —
    # this producer stamps market data, not decision eligibility, so the consumer
    # (or its caller) must always supply it.
    eligibility = {(DATE, "NVDA"): "2026-06-30T09:59:00-04:00"}
    rec = pairing.pair_records(admitted, fills, ticks, eligibility=eligibility)[0]

    # No arm's entry is ever defaulted to a midpoint (v2 removed midpoint-as-fill,
    # which had silently collapsed the intraday "shortfall" to ~zero) — the
    # intraday arm is recorded as a raw arrival OBSERVATION, flagged hypothetical.
    assert rec["intraday_entry_hypothetical"] is True
    assert "entry_price" not in rec["intraday_arm"]
    # this producer's tick DID supply a usable intraday arrival quote/mid
    assert rec["intraday_arm"]["arrival_quote"] is not None
    assert rec["intraday_arm"]["arrival_quote"]["mid"] == pytest.approx(100.1)
    assert rec["intraday_arm"]["fill"] is None  # Stage-1: no real intraday order
    # no batch arrival quote was supplied in this test -> that ONE input is
    # censored (recorded, not imputed) — never fabricated from the intraday mid.
    assert rec["censored_reason"] == "no_batch_arrival_quote"
    assert rec["filled"] is True  # the batch arm DID get a real historical fill
    assert rec["decomposition"]["is_execution_quality"] is False


def test_round_trip_into_vendored_pr215_consumer(tmp_path):
    # Local, hermetic interop against the pinned #215 consumer fixture, re-vendored
    # from its CURRENT head (not a stale earlier schema) so this proves the real
    # producer/consumer contract, not an outdated one.
    modname, pairing = _load_vendored_pr215_consumer()
    try:
        out = _sample_two_names_into(tmp_path)
        _assert_round_trip_into_current_pairing_contract(pairing, out, tmp_path)
    finally:
        sys.modules.pop(modname, None)


def test_round_trip_into_intraday_pairing_logger(tmp_path):
    # When #215 merges to main the real installed module exists — assert real
    # interop then against the identical assertions the vendored test already
    # proves now; skip cleanly until it lands (the vendored round-trip above is
    # the real, non-skipped assurance of the current contract today).
    pairing = pytest.importorskip("renquant_orchestrator.intraday_pairing_logger")
    out = _sample_two_names_into(tmp_path)
    _assert_round_trip_into_current_pairing_contract(pairing, out, tmp_path)


# ---------------------------------------------------------------------------
# Watchlist loader
# ---------------------------------------------------------------------------
def test_load_watchlist_reads_array(tmp_path):
    cfg = tmp_path / "strategy_config.json"
    cfg.write_text(json.dumps({"watchlist": ["NVDA", "MU", "AAPL"], "other": 1}))
    assert load_watchlist(cfg) == ["NVDA", "MU", "AAPL"]


def test_load_watchlist_rejects_empty(tmp_path):
    cfg = tmp_path / "strategy_config.json"
    cfg.write_text(json.dumps({"watchlist": []}))
    with pytest.raises(ValueError):
        load_watchlist(cfg)


# ---------------------------------------------------------------------------
# default path stays off the umbrella tree
# ---------------------------------------------------------------------------
def test_default_tick_feed_path_under_data_root(tmp_path):
    p = default_tick_feed_path(tmp_path)
    assert p == tmp_path / "logs" / "renquant105_pilot" / "intraday_ticks.jsonl"


# ---------------------------------------------------------------------------
# CLI main — with an injected source (no network)
# ---------------------------------------------------------------------------
def test_main_once_json_with_injected_source(tmp_path, capsys):
    source = FakeQuoteSource(
        {"NVDA": Quote(bid=100.0, ask=100.2, ts=QTS), "MSFT": Quote(bid=400.0, ask=400.4, ts=QTS)}
    )
    out = tmp_path / "ticks.jsonl"
    # --force + off-hours would censor; use an in-session sample by injecting the
    # real calendar isn't hermetic, so drive via the real NYSE calendar date/time.
    rc = main(
        ["--once", "--force", "--json", "--tickers", "NVDA,MSFT", "--out", str(out)],
        source=source,
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "once"
    assert payload["observe_only"] is True
    assert payload["eligibility_policy_version"] == ELIGIBILITY_POLICY_VERSION
    # Whether the rows are eligible depends on wall-clock vs the real NYSE session;
    # the CLI must run clean and stamp the policy either way.
    assert "rows_written" in payload
    assert payload["censored_out"].endswith(".censored.jsonl")


def test_main_missing_credentials_returns_2(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    # no injected source -> real path -> credential preflight fails closed
    rc = main(["--once", "--force", "--tickers", "NVDA"])  # source=None
    assert rc == 2
    assert "ALPACA_API_KEY" in capsys.readouterr().out


def test_alpaca_credentials_present(monkeypatch):
    monkeypatch.setenv("ALPACA_API_KEY", "k")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "s")
    assert alpaca_credentials_present() is True
    monkeypatch.delenv("ALPACA_SECRET_KEY")
    assert alpaca_credentials_present() is False


def test_alpaca_source_is_readonly_data_only():
    # Constructing the source imports/holds NO trading client — data only.
    src = AlpacaQuoteSource()
    assert src.name == "alpaca-iex"
    assert not hasattr(src, "submit_order")
    assert not hasattr(src, "place_order")
