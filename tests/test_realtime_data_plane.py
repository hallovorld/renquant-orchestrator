"""Tests for the renquant105 OBSERVE-ONLY real-time data plane.

Fixtures + a fake tick feed (schema-aligned to #216 intraday_ticks.jsonl) with an
explicit ``as_of`` (no wall-clock, no network). Covers snapshot assembly,
staleness + causality + same-session censoring, and no-order/no-mutation
invariants.
"""
from __future__ import annotations

import json
from pathlib import Path

from renquant_orchestrator.realtime_data_plane import (
    QUOTE_MISSING,
    QUOTE_OK,
    QUOTE_STALE,
    IntradaySnapshotRow,
    JsonlTickFeedSource,
    build_realtime_snapshot,
    default_tick_feed_path,
    main as data_plane_main,
    session_date,
)

# July 2026 → ET is UTC-04:00 (DST). as_of at 13:00 ET, session 2026-07-01.
AS_OF = "2026-07-01T13:00:00-04:00"
SESSION = "2026-07-01"


def _tick(ticker: str, mid: float, tick_time: str, *, date: str = SESSION, source: str = "fake"):
    """A tick row carrying exactly the #216 schema keys the data plane reads."""
    return {
        "schema_version": "1",
        "record_kind": "intraday_quote_tick",
        "observe_only": True,
        "date": date,
        "ticker": ticker,
        "mid": mid,
        "tick_time": tick_time,
        "source": source,
    }


class FakeTickFeed:
    """Deterministic in-memory tick source. Records reads; forbids any mutation
    method being called (there are none — a data source must never place orders)."""

    name = "fake-tick-feed"

    def __init__(self, ticks: list[dict]) -> None:
        self._ticks = ticks
        self.read_calls = 0

    def read_ticks(self):
        self.read_calls += 1
        return list(self._ticks)

    def place_order(self, *_a, **_k):  # pragma: no cover - must never be called
        raise AssertionError("data plane must not place orders")


def test_snapshot_assembly_picks_latest_causal_tick() -> None:
    feed = FakeTickFeed(
        [
            _tick("AAPL", 100.0, "2026-07-01T12:59:00-04:00"),
            _tick("AAPL", 101.0, "2026-07-01T12:59:55-04:00"),  # latest, 5s old → fresh
            _tick("MSFT", 200.0, "2026-07-01T12:59:58-04:00"),
        ]
    )
    snap = build_realtime_snapshot(
        as_of=AS_OF,
        daily_features={"AAPL": "sig-v1", "MSFT": {"signal_version": "sig-v1"}},
        feed_source=feed,
    )

    assert snap.as_of == "2026-07-01T13:00:00-04:00"
    assert snap.session_date == SESSION
    by = snap.by_ticker()
    assert by["AAPL"].quote_status == QUOTE_OK
    assert by["AAPL"].intraday_mid == 101.0  # latest, not the earlier 100.0
    assert by["AAPL"].daily_feature_ref == "sig-v1"
    assert by["AAPL"].age_sec == 5.0
    assert by["MSFT"].intraday_mid == 200.0
    assert by["MSFT"].daily_feature_ref == {"signal_version": "sig-v1"}
    assert feed.read_calls == 1
    assert snap.metadata["n_ok"] == 2
    assert snap.metadata["schema_ref"] == "intraday_ticks.jsonl (#216)"


def test_causality_future_tick_is_censored() -> None:
    feed = FakeTickFeed(
        [
            _tick("AAPL", 100.0, "2026-07-01T12:59:50-04:00"),  # 10s before as_of → causal
            _tick("AAPL", 111.0, "2026-07-01T13:00:30-04:00"),  # AFTER as_of → must be ignored
        ]
    )
    snap = build_realtime_snapshot(
        as_of=AS_OF, daily_features={"AAPL": "sig"}, feed_source=feed
    )
    row = snap.by_ticker()["AAPL"]
    # The future 111.0 tick can never enter the earlier decision.
    assert row.intraday_mid == 100.0
    assert row.quote_status == QUOTE_OK


def test_only_future_ticks_yield_missing() -> None:
    feed = FakeTickFeed([_tick("AAPL", 111.0, "2026-07-01T13:00:30-04:00")])
    snap = build_realtime_snapshot(
        as_of=AS_OF, daily_features={"AAPL": "sig"}, feed_source=feed
    )
    row = snap.by_ticker()["AAPL"]
    assert row.quote_status == QUOTE_MISSING
    assert row.intraday_mid is None
    assert row.source_ts is None


def test_stale_quote_is_censored_but_provenance_kept() -> None:
    feed = FakeTickFeed([_tick("AAPL", 100.0, "2026-07-01T12:59:00-04:00")])  # 60s old
    snap = build_realtime_snapshot(
        as_of=AS_OF, daily_features={"AAPL": "sig"}, feed_source=feed, staleness_sec=15.0
    )
    row = snap.by_ticker()["AAPL"]
    assert row.quote_status == QUOTE_STALE
    assert row.intraday_mid is None  # censored — never surfaced as fresh
    assert row.age_sec == 60.0  # provenance retained for the ledger
    assert row.source_ts == "2026-07-01T12:59:00-04:00"
    assert snap.metadata["n_stale"] == 1


def test_cross_session_tick_ignored() -> None:
    feed = FakeTickFeed(
        [
            _tick("AAPL", 99.0, "2026-06-30T12:59:55-04:00", date="2026-06-30"),  # prior session
            _tick("AAPL", 100.0, "2026-07-01T12:59:55-04:00"),  # this session
        ]
    )
    snap = build_realtime_snapshot(
        as_of=AS_OF, daily_features={"AAPL": "sig"}, feed_source=feed
    )
    row = snap.by_ticker()["AAPL"]
    assert row.intraday_mid == 100.0  # cross-session 99.0 never carried
    assert row.session_date == SESSION


def test_missing_ticker_has_no_quote() -> None:
    feed = FakeTickFeed([_tick("AAPL", 100.0, "2026-07-01T12:59:55-04:00")])
    snap = build_realtime_snapshot(
        as_of=AS_OF, daily_features={"AAPL": "sig", "TSLA": "sig"}, feed_source=feed
    )
    by = snap.by_ticker()
    assert by["TSLA"].quote_status == QUOTE_MISSING
    assert by["TSLA"].intraday_mid is None
    assert by["TSLA"].daily_feature_ref == "sig"  # still tracked in the watchlist


def test_unpriceable_tick_skipped() -> None:
    feed = FakeTickFeed(
        [
            {**_tick("AAPL", 0.0, "2026-07-01T12:59:59-04:00"), "mid": None},  # unpriceable
            _tick("AAPL", 100.0, "2026-07-01T12:59:50-04:00"),
        ]
    )
    snap = build_realtime_snapshot(
        as_of=AS_OF, daily_features={"AAPL": "sig"}, feed_source=feed
    )
    row = snap.by_ticker()["AAPL"]
    assert row.intraday_mid == 100.0  # falls back to the priceable earlier tick


def test_observe_only_and_no_mutation_invariants() -> None:
    feed = FakeTickFeed([_tick("AAPL", 100.0, "2026-07-01T12:59:55-04:00")])
    snap = build_realtime_snapshot(
        as_of=AS_OF, daily_features={"AAPL": "sig"}, feed_source=feed
    )
    payload = snap.to_payload()
    assert payload["observe_only"] is True
    assert payload["record_kind"] == "intraday_market_snapshot"
    # No decision/order surface anywhere in the payload.
    text = json.dumps(payload)
    for forbidden in ("order", "side", "qty", "place", "pin", "gate"):
        assert forbidden not in text.lower()


def test_row_dataclass_is_frozen_record() -> None:
    row = IntradaySnapshotRow(
        as_of=AS_OF,
        ticker="AAPL",
        intraday_mid=100.0,
        quote_status=QUOTE_OK,
        daily_feature_ref="sig",
        source_ts=AS_OF,
        age_sec=0.0,
        source="fake",
        session_date=SESSION,
    )
    rec = row.to_record()
    assert rec["ticker"] == "AAPL"
    assert rec["quote_status"] == QUOTE_OK
    assert set(rec) == {
        "as_of", "ticker", "intraday_mid", "quote_status", "daily_feature_ref",
        "source_ts", "age_sec", "source", "session_date",
    }


def test_session_date_and_default_path(tmp_path: Path) -> None:
    assert session_date(AS_OF) == SESSION
    p = default_tick_feed_path(tmp_path)
    assert p == tmp_path / "logs" / "renquant105_pilot" / "intraday_ticks.jsonl"


def test_jsonl_feed_reads_and_skips_bad_lines(tmp_path: Path) -> None:
    feed_path = tmp_path / "intraday_ticks.jsonl"
    feed_path.write_text(
        json.dumps(_tick("AAPL", 100.0, "2026-07-01T12:59:55-04:00")) + "\n"
        + "\n"  # blank line
        + "{not json}\n"  # malformed
        + json.dumps(_tick("MSFT", 200.0, "2026-07-01T12:59:55-04:00")) + "\n",
        encoding="utf-8",
    )
    rows = list(JsonlTickFeedSource(feed_path).read_ticks())
    assert {r["ticker"] for r in rows} == {"AAPL", "MSFT"}


def test_cli_writes_snapshot(tmp_path: Path, capsys) -> None:
    feed_path = tmp_path / "intraday_ticks.jsonl"
    feed_path.write_text(
        json.dumps(_tick("AAPL", 101.0, "2026-07-01T12:59:55-04:00")) + "\n", encoding="utf-8"
    )
    features = tmp_path / "features.json"
    features.write_text(json.dumps({"AAPL": "sig-v1"}), encoding="utf-8")
    out = tmp_path / "snapshot.json"

    rc = data_plane_main(
        [
            "--as-of", AS_OF,
            "--tick-feed", str(feed_path),
            "--daily-features-json", str(features),
            "--output-json", str(out),
            "--json",
        ]
    )
    assert rc == 0
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["observe_only"] is True
    assert written["rows"][0]["ticker"] == "AAPL"
    assert written["rows"][0]["intraday_mid"] == 101.0
    printed = json.loads(capsys.readouterr().out)
    assert printed == written
