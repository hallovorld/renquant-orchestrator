"""Tests for ``intraday_quote_logger`` — renquant105 Stage-1 OBSERVE-ONLY tick feed.

Fully hermetic and deterministic: a fake quote source (no network, no Alpaca) and
an injected clock (no wall-clock, no real sleeps). Verifies the record schema that
``intraday_pairing_logger`` consumes (incl. a real round-trip when that consumer is
available), market-hours gating, per-ticker and whole-batch failure isolation,
idempotent append, ``--once`` and the loop. Never touches live state.
"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Mapping, Sequence
from zoneinfo import ZoneInfo

import pytest

UTC = ZoneInfo("UTC")

from renquant_orchestrator.intraday_quote_logger import (
    ET,
    AlpacaQuoteSource,
    Quote,
    QuoteLogger,
    TickFeedWriter,
    alpaca_credentials_present,
    build_tick_record,
    default_tick_feed_path,
    is_market_hours,
    load_watchlist,
    main,
    market_phase,
    session_date,
    tick_key,
)

DATE = "2026-06-30"  # a Tuesday
OPEN_10AM = datetime(2026, 6, 30, 10, 0, tzinfo=ET)
BEFORE_OPEN = datetime(2026, 6, 30, 9, 0, tzinfo=ET)
AFTER_CLOSE = datetime(2026, 6, 30, 16, 5, tzinfo=ET)
SATURDAY = datetime(2026, 7, 4, 11, 0, tzinfo=ET)
QTS = "2026-06-30T10:00:00-04:00"


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
# Market-hours gating (pure)
# ---------------------------------------------------------------------------
def test_market_phase_open_before_closed_weekend():
    assert market_phase(OPEN_10AM) == "open"
    assert market_phase(BEFORE_OPEN) == "before_open"
    assert market_phase(AFTER_CLOSE) == "closed"
    assert market_phase(datetime(2026, 6, 30, 16, 0, tzinfo=ET)) == "closed"  # 16:00 exclusive
    assert market_phase(datetime(2026, 6, 30, 9, 30, tzinfo=ET)) == "open"  # 09:30 inclusive
    assert market_phase(SATURDAY) == "closed"


def test_is_market_hours():
    assert is_market_hours(OPEN_10AM) is True
    assert is_market_hours(BEFORE_OPEN) is False
    assert is_market_hours(AFTER_CLOSE) is False


def test_session_date_is_et():
    assert session_date(OPEN_10AM) == DATE
    # a UTC instant (2026-07-01 02:00Z) is still the prior ET calendar day
    assert session_date(datetime(2026, 7, 1, 2, 0, tzinfo=UTC)) == DATE


# ---------------------------------------------------------------------------
# build_tick_record + tick_key
# ---------------------------------------------------------------------------
def test_build_tick_record_schema_and_mid():
    rec = build_tick_record(
        ticker="NVDA",
        quote=Quote(bid=100.0, ask=100.2, last=100.1, ts=QTS),
        sample_ts=OPEN_10AM,
        date=DATE,
        source_name="fake",
    )
    assert rec is not None
    # keys the consumer reads
    assert rec["date"] == DATE
    assert rec["ticker"] == "NVDA"
    assert rec["mid"] == pytest.approx(100.1)
    assert rec["tick_time"] == QTS  # prefers the exchange quote timestamp
    # observe-only provenance + raw fields, no verdict / order / entry_price
    assert rec["observe_only"] is True
    assert rec["bid"] == 100.0 and rec["ask"] == 100.2 and rec["last"] == 100.1
    assert "entry_price" not in rec  # not asserted here (consumer defaults to mid)
    assert "order" not in rec and "verdict" not in rec


def test_build_tick_record_tick_time_falls_back_to_sample_ts():
    rec = build_tick_record(
        ticker="MU", quote=Quote(bid=1.0, ask=1.2), sample_ts=OPEN_10AM, date=DATE
    )
    assert rec["tick_time"] == OPEN_10AM.isoformat()


def test_build_tick_record_none_when_unpriceable():
    assert (
        build_tick_record(
            ticker="X", quote=Quote(None, None, None), sample_ts=OPEN_10AM, date=DATE
        )
        is None
    )


def test_tick_key_shape():
    rec = build_tick_record(
        ticker="NVDA", quote=Quote(bid=100.0, ask=100.2, ts=QTS), sample_ts=OPEN_10AM, date=DATE
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


# ---------------------------------------------------------------------------
# QuoteLogger.sample_once
# ---------------------------------------------------------------------------
def _logger(tmp_path, source, tickers):
    return QuoteLogger(source, TickFeedWriter(tmp_path / "ticks.jsonl"), tickers)


def test_sample_once_writes_priceable_skips_unpriceable(tmp_path):
    source = FakeQuoteSource(
        {
            "NVDA": Quote(bid=100.0, ask=100.2, ts=QTS),
            "MU": Quote(bid=None, ask=None, last=None, ts=QTS),  # unpriceable -> skip
        }
    )
    logger = _logger(tmp_path, source, ["NVDA", "MU"])
    summary = logger.sample_once(now=OPEN_10AM)
    assert summary["sampled"] is True
    assert summary["n_quoted"] == 1
    assert summary["n_skipped"] == 1
    assert summary["rows_written"] == 1


def test_sample_once_market_hours_gate(tmp_path):
    source = FakeQuoteSource({"NVDA": Quote(bid=100.0, ask=100.2, ts=QTS)})
    logger = _logger(tmp_path, source, ["NVDA"])
    closed = logger.sample_once(now=AFTER_CLOSE)
    assert closed["sampled"] is False
    assert closed["reason"] == "market_closed"
    assert closed["rows_written"] == 0
    # --force bypasses the gate
    forced = logger.sample_once(now=AFTER_CLOSE, force=True)
    assert forced["sampled"] is True
    assert forced["rows_written"] == 1


def test_sample_once_per_ticker_failure_isolation(tmp_path):
    # AAPL absent from the source mapping simulates a per-ticker miss.
    source = FakeQuoteSource(
        {
            "NVDA": Quote(bid=100.0, ask=100.2, ts=QTS),
            "MSFT": Quote(bid=400.0, ask=400.4, ts=QTS),
        }
    )
    logger = _logger(tmp_path, source, ["NVDA", "AAPL", "MSFT"])
    summary = logger.sample_once(now=OPEN_10AM)
    assert summary["n_quoted"] == 2  # NVDA + MSFT
    assert summary["n_skipped"] == 1  # AAPL missing, not fatal
    assert summary["rows_written"] == 2


def test_sample_once_whole_batch_failure_does_not_raise(tmp_path):
    source = FakeQuoteSource({}, raise_all=True)
    logger = _logger(tmp_path, source, ["NVDA", "MU"])
    summary = logger.sample_once(now=OPEN_10AM)  # must not raise
    assert summary["sampled"] is True
    assert summary["n_quoted"] == 0
    assert summary["rows_written"] == 0


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
    # give each open tick a distinct quote timestamp so both rows persist
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
    source = FakeQuoteSource({"NVDA": Quote(bid=100.0, ask=100.2, ts=QTS)})
    logger = _logger(tmp_path, source, ["NVDA"])
    result = logger.run_loop(
        cadence_sec=1,
        now_fn=lambda: AFTER_CLOSE,  # closed, but force bypasses
        sleep_fn=lambda _s: None,
        force=True,
        max_cycles=3,
    )
    assert result["cycles"] == 3
    assert result["samples"] == 3


# ---------------------------------------------------------------------------
# Schema + round-trip against the real consumer (when available)
# ---------------------------------------------------------------------------
def test_feed_reads_back_required_keys(tmp_path):
    source = FakeQuoteSource(
        {
            "NVDA": Quote(bid=100.0, ask=100.2, ts=QTS),
            "MU": Quote(bid=50.0, ask=50.4, ts=QTS),
        }
    )
    out = tmp_path / "ticks.jsonl"
    QuoteLogger(source, TickFeedWriter(out), ["NVDA", "MU"]).sample_once(now=OPEN_10AM)
    lines = [json.loads(l) for l in out.read_text().strip().splitlines()]
    assert {r["ticker"] for r in lines} == {"NVDA", "MU"}
    for r in lines:
        assert r["date"] == DATE
        assert isinstance(r["mid"], float)
        assert "tick_time" in r


def test_round_trip_into_intraday_pairing_logger(tmp_path):
    # Real composition: our feed must load through the consumer's own reader.
    # Guarded because intraday_pairing_logger ships in PR #215 (not yet on main);
    # this runs (and asserts real interop) once #215 merges, skips cleanly until.
    pairing = pytest.importorskip("renquant_orchestrator.intraday_pairing_logger")
    source = FakeQuoteSource(
        {
            "NVDA": Quote(bid=100.0, ask=100.2, ts=QTS),
            "MU": Quote(bid=50.0, ask=50.4, ts=QTS),
        }
    )
    out = tmp_path / "ticks.jsonl"
    QuoteLogger(source, TickFeedWriter(out), ["NVDA", "MU"]).sample_once(now=OPEN_10AM)

    ticks = pairing.load_intraday_ticks(out, DATE)
    assert set(ticks) == {(DATE, "NVDA"), (DATE, "MU")}
    assert ticks[(DATE, "NVDA")]["mid"] == pytest.approx(100.1)
    # and it feeds a non-censored intraday arm through the consumer's pairing
    admitted = [pairing.AdmittedName(DATE, "NVDA", "buy", "sv1")]
    fills = {("sv1", "NVDA"): pairing.PriceRef(101.0)}
    rec = pairing.pair_records(admitted, fills, ticks)[0]
    assert rec["censored_reason"] is None
    assert rec["intraday_entry_ref"] is not None


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
    rc = main(
        ["--once", "--force", "--json", "--tickers", "NVDA,MSFT", "--out", str(out)],
        source=source,
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "once"
    assert payload["observe_only"] is True
    assert payload["rows_written"] == 2
    assert out.exists()


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
