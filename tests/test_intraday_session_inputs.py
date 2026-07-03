"""Tests for the Stage-1 intraday input assembly (RFC #208 §6, §8 row 3):
the class-A leak guard over runs.alpaca.db, the class-B capture/verify
fingerprint, and the §7 reservations parsed from a slice-1
``OrderStateBook.to_snapshot()`` state file."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from renquant_orchestrator.intraday_quote_logger import SessionBounds
from renquant_orchestrator.intraday_session_inputs import (
    FrozenSignalError,
    OrderStateFileError,
    SignalLeakError,
    assert_signal_predates_session,
    capture_session_start,
    load_frozen_daily_signal,
    load_order_state_reservations,
    previous_session,
    verify_session_start,
)

ET = ZoneInfo("America/New_York")


class FakeCalendar:
    """Deterministic session calendar: only the listed ISO dates are sessions."""

    name = "FAKE-NYSE"

    def __init__(self, sessions: dict[str, tuple[str, str]]):
        self._sessions = sessions

    def session_bounds(self, day) -> SessionBounds | None:
        key = day.isoformat()
        if key not in self._sessions:
            return None
        open_hm, close_hm = self._sessions[key]
        oh, om = (int(x) for x in open_hm.split(":"))
        ch, cm = (int(x) for x in close_hm.split(":"))
        return SessionBounds(
            open=datetime(day.year, day.month, day.day, oh, om, tzinfo=ET),
            close=datetime(day.year, day.month, day.day, ch, cm, tzinfo=ET),
        )


# 2026-07-06 is a Monday; 2026-07-03 the prior session (Friday); the weekend
# in between has no sessions.
MONDAY = "2026-07-06"
FRIDAY = "2026-07-03"
CAL = FakeCalendar({FRIDAY: ("09:30", "16:00"), MONDAY: ("09:30", "16:00")})


# ─────────────────────────── previous_session ───────────────────────────
def test_previous_session_skips_weekend():
    assert previous_session(CAL, MONDAY) == FRIDAY


def test_previous_session_skips_holiday():
    # Friday removed (holiday) -> falls back to Thursday.
    cal = FakeCalendar({"2026-07-02": ("09:30", "16:00"), MONDAY: ("09:30", "16:00")})
    assert previous_session(cal, MONDAY) == "2026-07-02"


def test_previous_session_fails_loudly_when_no_session_in_window():
    with pytest.raises(FrozenSignalError):
        previous_session(FakeCalendar({}), MONDAY)


# ─────────────────────────── class-A loader + leak guard ───────────────────────────
GOOD_BUNDLE = json.dumps(
    {
        "config_hash": "cfg",
        "artifact_hashes": {"panel": "abc"},
        "watchlist_hash": "wl",
    }
)


def _make_db(tmp_path: Path, runs, scores) -> Path:
    db = tmp_path / "runs.alpaca.db"
    con = sqlite3.connect(db)
    con.execute(
        "create table pipeline_runs (run_id text, run_date text, run_type text,"
        " strategy text, run_bundle_json text, created_at text)"
    )
    con.execute(
        "create table candidate_scores (run_id text, ticker text, role text,"
        " panel_score real)"
    )
    con.executemany("insert into pipeline_runs values (?,?,?,?,?,?)", runs)
    con.executemany("insert into candidate_scores values (?,?,?,?)", scores)
    con.commit()
    con.close()
    return db


def _score_rows(run_id: str, n: int = 3, null_from: int | None = None):
    rows = []
    for i in range(n):
        score = None if (null_from is not None and i >= null_from) else float(i) / 10
        rows.append((run_id, f"T{i:02d}", "candidate", score))
    return rows


def test_loads_prior_session_run_and_refuses_todays(tmp_path):
    """The as-of leak guard: only the PRIOR session's committed run is
    eligible as class A — a fresher same-day run exists and must be ignored."""
    db = _make_db(
        tmp_path,
        runs=[
            ("run-fri", FRIDAY, "live", "s104", GOOD_BUNDLE, "2026-07-03T21:00:00"),
            ("run-mon", MONDAY, "live", "s104", GOOD_BUNDLE, "2026-07-06T10:00:00"),
        ],
        scores=_score_rows("run-fri") + _score_rows("run-mon"),
    )
    signal = load_frozen_daily_signal(
        db_path=db, session_date=MONDAY, calendar=CAL, min_rows=3
    )
    assert signal["source_run_id"] == "run-fri"
    assert signal["as_of"] == FRIDAY
    assert signal["as_of"] < MONDAY  # §6: strictly predates the session
    assert signal["scores"] == {"T00": 0.0, "T01": 0.1, "T02": 0.2}
    assert signal["signal_version"].startswith("run-fri:")
    # And the scheduler-side re-assert accepts it.
    assert_signal_predates_session(signal, MONDAY)


def test_only_todays_run_exists_is_refused(tmp_path):
    """Today's run can NEVER serve as class A, even when it is the only one."""
    db = _make_db(
        tmp_path,
        runs=[("run-mon", MONDAY, "live", "s104", GOOD_BUNDLE, "2026-07-06T10:00:00")],
        scores=_score_rows("run-mon"),
    )
    with pytest.raises(FrozenSignalError):
        load_frozen_daily_signal(
            db_path=db, session_date=MONDAY, calendar=CAL, min_rows=3
        )


def test_no_fallback_to_older_than_prior_session(tmp_path):
    """A run older than the prior session is refused (outage fails loudly)."""
    db = _make_db(
        tmp_path,
        runs=[
            ("run-old", "2026-07-01", "live", "s104", GOOD_BUNDLE, "2026-07-01T21:00:00")
        ],
        scores=_score_rows("run-old"),
    )
    with pytest.raises(FrozenSignalError):
        load_frozen_daily_signal(
            db_path=db, session_date=MONDAY, calendar=CAL, min_rows=3
        )


def test_unfingerprinted_run_refused(tmp_path):
    bundle = json.dumps({"config_hash": "", "artifact_hashes": {}, "watchlist_hash": ""})
    db = _make_db(
        tmp_path,
        runs=[("run-fri", FRIDAY, "live", "s104", bundle, "2026-07-03T21:00:00")],
        scores=_score_rows("run-fri"),
    )
    with pytest.raises(FrozenSignalError, match="fingerprint"):
        load_frozen_daily_signal(
            db_path=db, session_date=MONDAY, calendar=CAL, min_rows=3
        )


def test_coverage_floor_refused(tmp_path):
    db = _make_db(
        tmp_path,
        runs=[("run-fri", FRIDAY, "live", "s104", GOOD_BUNDLE, "2026-07-03T21:00:00")],
        scores=_score_rows("run-fri", n=10, null_from=5),  # 50% coverage
    )
    with pytest.raises(FrozenSignalError, match="coverage|floor"):
        load_frozen_daily_signal(
            db_path=db, session_date=MONDAY, calendar=CAL, min_rows=3
        )


def test_non_live_run_refused(tmp_path):
    db = _make_db(
        tmp_path,
        runs=[("run-fri", FRIDAY, "sim", "s104", GOOD_BUNDLE, "2026-07-03T21:00:00")],
        scores=_score_rows("run-fri"),
    )
    with pytest.raises(FrozenSignalError):
        load_frozen_daily_signal(
            db_path=db, session_date=MONDAY, calendar=CAL, min_rows=3
        )


def test_assert_signal_predates_session_rejects_same_day_and_future():
    with pytest.raises(SignalLeakError):
        assert_signal_predates_session({"as_of": MONDAY}, MONDAY)
    with pytest.raises(SignalLeakError):
        assert_signal_predates_session({"as_of": "2026-07-07"}, MONDAY)
    with pytest.raises(SignalLeakError):
        assert_signal_predates_session({}, MONDAY)


# ─────────────────────────── class-B capture / verify ───────────────────────────
def test_session_start_capture_and_mutation_detection():
    snapshot = capture_session_start({"watchlist": ["A", "B"]}, captured_at="t0")
    verify_session_start(snapshot)  # intact -> passes
    mutated = dict(snapshot)
    mutated["gate_inputs"] = {"watchlist": ["A", "B", "C"]}
    with pytest.raises(SignalLeakError, match="mutated"):
        verify_session_start(mutated)


# ─────────────────────────── §7 reservations (slice-1 state file) ───────────────────────────
def _book(tmp_path: Path, payload) -> Path:
    p = tmp_path / "order_state.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _slice1_book(trading_day: str = MONDAY):
    """Shape produced by renquant-execution #20 OrderStateBook.to_snapshot()."""
    return {
        "schema_version": "order-state-machine-v1",
        "account": "acct",
        "trading_day": trading_day,
        "entries_halted": False,
        "halt_reason": None,
        "parents": [
            {
                "parent_intent_id": "pi-buy-open",
                "account": "acct",
                "symbol": "AAA",
                "trading_day": trading_day,
                "side": "BUY",
                "signal_version": "v1",
                "target_qty": 10.0,
                "children": [
                    {
                        "child_order_id": "pi-buy-open:1",
                        "attempt_n": 1,
                        "requested_qty": 10.0,
                        "price": 5.0,
                        "submitted_at": "2026-07-06T14:00:00+00:00",
                        "state": "PARTIALLY_FILLED",
                        "filled_qty": 4.0,
                    }
                ],
                "cum_canceled": 0.0,
                "cum_rejected": 0.0,
                "cum_expired": 0.0,
            },
            {
                "parent_intent_id": "pi-buy-done",
                "account": "acct",
                "symbol": "BBB",
                "trading_day": trading_day,
                "side": "BUY",
                "signal_version": "v1",
                "target_qty": 2.0,
                "children": [
                    {
                        "child_order_id": "pi-buy-done:1",
                        "attempt_n": 1,
                        "requested_qty": 2.0,
                        "price": 3.0,
                        "submitted_at": "2026-07-06T14:00:00+00:00",
                        "state": "FILLED",
                        "filled_qty": 2.0,
                    }
                ],
                "cum_canceled": 0.0,
                "cum_rejected": 0.0,
                "cum_expired": 0.0,
            },
            {
                "parent_intent_id": "pi-sell-open",
                "account": "acct",
                "symbol": "CCC",
                "trading_day": trading_day,
                "side": "SELL",
                "signal_version": "v1",
                "target_qty": 1.0,
                "children": [
                    {
                        "child_order_id": "pi-sell-open:1",
                        "attempt_n": 1,
                        "requested_qty": 1.0,
                        "price": 7.0,
                        "submitted_at": "2026-07-06T14:00:00+00:00",
                        "state": "SUBMITTED",
                        "filled_qty": 0.0,
                    }
                ],
                "cum_canceled": 0.0,
                "cum_rejected": 0.0,
                "cum_expired": 0.0,
            },
        ],
    }


def test_reservations_from_slice1_snapshot(tmp_path):
    path = _book(tmp_path, _slice1_book())
    parsed = load_order_state_reservations(path, trading_day=MONDAY)
    # Only the OPEN buy child reserves: unfilled 6 × price 5 = 30. The FILLED
    # buy reserves nothing; the open SELL never reserves cash (§7).
    assert parsed["open_buy_reservations"] == {"pi-buy-open": 30.0}
    # ALL parents are in-flight decisions (dedup keys), both sides.
    assert parsed["in_flight_parent_intents"] == [
        "pi-buy-done",
        "pi-buy-open",
        "pi-sell-open",
    ]
    assert parsed["pending_broker_tickers"] == ["AAA", "CCC"]
    assert parsed["entries_halted"] is False


def test_reservations_missing_file_is_empty_defaults(tmp_path):
    parsed = load_order_state_reservations(tmp_path / "absent.json")
    assert parsed["open_buy_reservations"] == {}
    assert parsed["in_flight_parent_intents"] == []


def test_reservations_wrong_schema_version_refused(tmp_path):
    book = _slice1_book()
    book["schema_version"] = "order-state-machine-v99"
    with pytest.raises(OrderStateFileError, match="schema_version"):
        load_order_state_reservations(_book(tmp_path, book), trading_day=MONDAY)


def test_reservations_stale_trading_day_refused(tmp_path):
    path = _book(tmp_path, _slice1_book(trading_day=FRIDAY))
    with pytest.raises(OrderStateFileError, match="stale|trading_day"):
        load_order_state_reservations(path, trading_day=MONDAY)


def test_reservations_corrupt_file_refused(tmp_path):
    p = tmp_path / "order_state.json"
    p.write_text("{not json", encoding="utf-8")
    with pytest.raises(OrderStateFileError, match="unreadable"):
        load_order_state_reservations(p, trading_day=MONDAY)
