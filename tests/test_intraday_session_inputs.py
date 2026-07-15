"""Tests for the Stage-1 intraday input assembly (RFC #208 §6, §8 row 3):
the class-A leak guard over runs.alpaca.db, the class-B capture/verify
fingerprint, and the §7 reservations parsed from a slice-1
``OrderStateBook.to_snapshot()`` state file."""
from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from renquant_orchestrator.intraday_quote_logger import SessionBounds
from renquant_orchestrator.intraday_session_inputs import (
    FrozenSignalError,
    OrderStateFileError,
    SignalLeakError,
    UnboundedBrokerCallError,
    _broker_call_with_retry,
    _call_timeout_var,
    _call_with_deadline,
    _extract_retry_after,
    _extract_status_code,
    _fingerprint_gaps,
    _is_transient,
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
        "artifact_hashes": {
            "panel": "abc",
            "global_calibration": "cal",
            "ranking.panel_scoring.artifact_path": "scorer",
        },
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


def test_fingerprint_gaps_accepts_missing_optional_artifact_hashes():
    """Codex #399 review: a config-declared but non-semantic artifact
    (shadow lane, aux ngboost head, quality-floor threshold, etc.) missing
    its hash must NOT block class-A — only panel + global_calibration
    (the two artifacts that actually feed the panel score) are required."""
    bundle = {
        "config_hash": "cfg",
        "artifact_hashes": {
            "panel": "abc",
            "global_calibration": "cal",
            "ranking.panel_scoring.shadow_models[0].artifact_path": None,
            "panel_ltr.ngboost.artifact_path": None,
            "ranking.panel_scoring.quality_floor.gate_b_artifact_path": None,
            "ranking.panel_scoring.global_calibration.regime_conditional.artifact_pattern": None,
        },
        "watchlist_hash": "wl",
    }
    assert _fingerprint_gaps(bundle) == []


def test_fingerprint_gaps_requires_panel_and_global_calibration():
    """Missing either of the two primary runtime artifacts IS a gap,
    regardless of what else is present."""
    missing_panel = {
        "config_hash": "cfg",
        "artifact_hashes": {"global_calibration": "cal"},
        "watchlist_hash": "wl",
    }
    gaps = _fingerprint_gaps(missing_panel)
    assert len(gaps) == 1
    assert "artifact_hashes(panel)" in gaps[0]

    missing_calibration = {
        "config_hash": "cfg",
        "artifact_hashes": {"panel": "abc"},
        "watchlist_hash": "wl",
    }
    gaps = _fingerprint_gaps(missing_calibration)
    assert len(gaps) == 1
    assert "artifact_hashes(global_calibration)" in gaps[0]


def test_fingerprint_gaps_ignores_raw_panel_scoring_key_when_panel_alias_present():
    """A config using the panel_ltr.artifact_path fallback (so the raw
    ranking.panel_scoring.artifact_path key is never even present) must not
    be spuriously blocked — the panel alias is sufficient proof either way."""
    bundle = {
        "config_hash": "cfg",
        "artifact_hashes": {
            "panel": "abc",  # resolved via the panel_ltr.artifact_path fallback
            "global_calibration": "cal",
            # note: no "ranking.panel_scoring.artifact_path" key at all
        },
        "watchlist_hash": "wl",
    }
    assert _fingerprint_gaps(bundle) == []


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


# ---------------------------------------------------------------------------
# Broker retry tests
# ---------------------------------------------------------------------------
class _TransientError(Exception):
    pass


class _HTTPError(Exception):
    def __init__(self, status_code, headers=None):
        self.status_code = status_code

        class _Resp:
            pass

        self.response = _Resp()
        self.response.status_code = status_code
        self.response.headers = headers or {}
        super().__init__(f"HTTP {status_code}")


class _NullSession:
    """Placeholder exposing `.request` so `_call_with_deadline`'s
    session-reflection check recognizes the wrapping fake client as
    patchable. Never actually invoked by the plain-function test doubles
    below -- it only exists to satisfy the reflectable-`_session`
    precondition `_call_with_deadline` now REQUIRES of every callable
    (Codex r3: the previous thread-based fallback for unreflectable
    callables was removed as not cancellation-safe)."""

    def request(self, *args, **kwargs):  # pragma: no cover - unused by these fakes
        raise AssertionError("these test doubles do not call session.request directly")


def _as_reflectable_call(fn):
    """Wrap a bare zero-arg callable as a bound method of an object with a
    reflectable ``_session`` -- the shape `_call_with_deadline` now
    requires, matching the real `client.get_account` /
    `client.get_all_positions` call sites (bound methods of
    `alpaca.trading.client.TradingClient`, which has a private `_session`).
    Retry/backoff/classification tests exercise `_broker_call_with_retry`
    through this same gate rather than an unreflectable bare function."""

    class _Client:
        def __init__(self):
            self._session = _NullSession()

        def call(self):
            return fn()

    return _Client().call


class TestTransientClassification:
    def test_status_based_transient(self):
        for code in (429, 500, 502, 503, 504):
            assert _is_transient(_HTTPError(code)) is True

    def test_status_based_permanent(self):
        for code in (400, 401, 403, 404, 422):
            assert _is_transient(_HTTPError(code)) is False

    def test_timeout_string_transient(self):
        assert _is_transient(_TransientError("request timed out")) is True

    def test_non_transient_string(self):
        assert _is_transient(ValueError("invalid symbol")) is False

    def test_connection_error_class(self):
        class ConnectionError(Exception):
            pass
        assert _is_transient(ConnectionError("reset")) is True


class TestExtractHelpers:
    def test_extract_status_code_from_attribute(self):
        assert _extract_status_code(_HTTPError(429)) == 429

    def test_extract_status_code_none_for_plain(self):
        assert _extract_status_code(ValueError("x")) is None

    def test_extract_retry_after_present(self):
        exc = _HTTPError(429, headers={"Retry-After": "5"})
        assert _extract_retry_after(exc) == 5.0

    def test_extract_retry_after_absent(self):
        exc = _HTTPError(429, headers={})
        assert _extract_retry_after(exc) is None

    def test_extract_retry_after_invalid(self):
        exc = _HTTPError(429, headers={"Retry-After": "not-a-number"})
        assert _extract_retry_after(exc) is None

    def test_extract_retry_after_no_response(self):
        assert _extract_retry_after(ValueError("x")) is None

    def test_extract_retry_after_http_date_future(self):
        from email.utils import format_datetime
        from datetime import datetime as _dt, timezone, timedelta
        future = _dt.now(tz=timezone.utc) + timedelta(seconds=30)
        exc = _HTTPError(429, headers={"Retry-After": format_datetime(future)})
        val = _extract_retry_after(exc)
        assert val is not None
        assert 25.0 <= val <= 35.0

    def test_extract_retry_after_http_date_past(self):
        from email.utils import format_datetime
        from datetime import datetime as _dt, timezone, timedelta
        past = _dt.now(tz=timezone.utc) - timedelta(seconds=10)
        exc = _HTTPError(429, headers={"Retry-After": format_datetime(past)})
        val = _extract_retry_after(exc)
        assert val == 0.0

    def test_extract_retry_after_zero(self):
        exc = _HTTPError(429, headers={"Retry-After": "0"})
        assert _extract_retry_after(exc) == 0.0


def test_broker_retry_succeeds_after_transient(monkeypatch):
    import renquant_orchestrator.intraday_session_inputs as mod

    monkeypatch.setattr(mod, "_BROKER_BACKOFF_BASE", 0.01)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise _TransientError("504 Gateway Timeout")
        return "ok"

    assert _broker_call_with_retry(_as_reflectable_call(flaky), label="test") == "ok"
    assert len(calls) == 3


def test_broker_retry_raises_on_non_transient():
    def fatal():
        raise ValueError("invalid symbol")

    with pytest.raises(ValueError, match="invalid symbol"):
        _broker_call_with_retry(_as_reflectable_call(fatal), label="test")


def test_broker_retry_exhausted_raises(monkeypatch):
    import renquant_orchestrator.intraday_session_inputs as mod

    monkeypatch.setattr(mod, "_BROKER_BACKOFF_BASE", 0.01)

    def always_timeout():
        raise _TransientError("request timed out")

    with pytest.raises(_TransientError, match="timed out"):
        _broker_call_with_retry(_as_reflectable_call(always_timeout), label="test")


def test_broker_retry_429_with_retry_after(monkeypatch):
    import renquant_orchestrator.intraday_session_inputs as mod

    monkeypatch.setattr(mod, "_BROKER_BACKOFF_BASE", 0.01)
    calls = []

    def rate_limited():
        calls.append(1)
        if len(calls) < 2:
            raise _HTTPError(429, headers={"Retry-After": "0.01"})
        return "ok"

    assert _broker_call_with_retry(_as_reflectable_call(rate_limited), label="test") == "ok"
    assert len(calls) == 2


def test_broker_retry_skips_auth_errors():
    def auth_fail():
        raise _HTTPError(401)

    with pytest.raises(_HTTPError):
        _broker_call_with_retry(_as_reflectable_call(auth_fail), label="test")


def test_broker_retry_skips_validation_errors():
    def bad_request():
        raise _HTTPError(422)

    with pytest.raises(_HTTPError):
        _broker_call_with_retry(_as_reflectable_call(bad_request), label="test")


def test_broker_retry_deadline_exceeded(monkeypatch):
    import renquant_orchestrator.intraday_session_inputs as mod

    monkeypatch.setattr(mod, "_BROKER_BACKOFF_BASE", 0.01)
    monkeypatch.setattr(mod, "_BROKER_DEADLINE_SECONDS", 0.0)

    def always_502():
        raise _HTTPError(502)

    with pytest.raises(RuntimeError, match="deadline exceeded"):
        _broker_call_with_retry(_as_reflectable_call(always_502), label="test")


def test_broker_retry_deadline_prevents_further_attempts(monkeypatch):
    """After fn() returns (possibly slowly), no retry if deadline passed."""
    import renquant_orchestrator.intraday_session_inputs as mod

    monkeypatch.setattr(mod, "_BROKER_BACKOFF_BASE", 0.01)
    monkeypatch.setattr(mod, "_BROKER_DEADLINE_SECONDS", 0.05)
    calls = []

    def slow_then_fail():
        calls.append(1)
        import time
        time.sleep(0.06)
        raise _HTTPError(502)

    with pytest.raises((RuntimeError, _HTTPError)):
        _broker_call_with_retry(_as_reflectable_call(slow_then_fail), label="test")
    assert len(calls) <= 2


def test_broker_retry_429_zero_retry_after(monkeypatch):
    """Retry-After: 0 should retry immediately, not fall back to backoff."""
    import renquant_orchestrator.intraday_session_inputs as mod

    monkeypatch.setattr(mod, "_BROKER_BACKOFF_BASE", 100.0)
    monkeypatch.setattr(mod, "_BROKER_DEADLINE_SECONDS", 5.0)
    calls = []

    def rate_limited():
        calls.append(1)
        if len(calls) < 2:
            raise _HTTPError(429, headers={"Retry-After": "0"})
        return "ok"

    result = _broker_call_with_retry(_as_reflectable_call(rate_limited), label="test")
    assert result == "ok"
    assert len(calls) == 2


def test_broker_retry_429_http_date_retry_after(monkeypatch):
    """Retry-After as HTTP-date is honored (capped by deadline)."""
    import renquant_orchestrator.intraday_session_inputs as mod
    from email.utils import format_datetime
    from datetime import datetime as _dt, timezone, timedelta

    monkeypatch.setattr(mod, "_BROKER_BACKOFF_BASE", 0.01)
    monkeypatch.setattr(mod, "_BROKER_DEADLINE_SECONDS", 5.0)
    calls = []
    future = _dt.now(tz=timezone.utc) + timedelta(seconds=0.01)

    def rate_limited():
        calls.append(1)
        if len(calls) < 2:
            raise _HTTPError(429, headers={
                "Retry-After": format_datetime(future)
            })
        return "ok"

    result = _broker_call_with_retry(_as_reflectable_call(rate_limited), label="test")
    assert result == "ok"
    assert len(calls) == 2


class _TransportTimeoutSession:
    """A stub ``requests.Session`` that enforces its ``timeout=`` kwarg the
    way the real ``requests``/``urllib3`` socket layer does: the call
    raises a timeout error *from inside itself*, synchronously in the
    calling thread, once it has waited ``timeout`` seconds against a
    simulated remote that would hang for ``hang_seconds`` -- no external
    canceller (thread, future, etc.) is needed or involved. This is what
    ``_call_with_deadline``'s session-patch mechanism actually relies on
    for cancellation-safety.
    """

    def __init__(self, hang_seconds: float):
        self.hang_seconds = hang_seconds
        self.timeouts_seen: list[float | None] = []

    def request(self, method, url, **kwargs):
        timeout = kwargs.get("timeout")
        self.timeouts_seen.append(timeout)
        waited = min(timeout, self.hang_seconds) if timeout is not None else self.hang_seconds
        time.sleep(waited)
        if timeout is not None and self.hang_seconds > timeout:
            raise TimeoutError(
                f"simulated transport-level read timeout after {timeout:.3f}s"
            )
        return "ok-within-budget"


class _TransportTimeoutClient:
    """Bound-method shape matching ``AlpacaLiveStateSource``'s real call
    sites: a private, reflectable ``_session``."""

    def __init__(self, session):
        self._session = session

    def call(self):
        return self._session.request("GET", "https://paper-api.alpaca.markets/v2/account")


def test_call_with_deadline_propagates_transport_level_timeout_not_thread():
    """The abort must come from the transport call raising synchronously
    (mirroring a real `requests.exceptions.Timeout`), not from a
    Future/thread race: a would-be-forever hang (`hang_seconds=999`) is cut
    off at ~the given timeout and the exception propagates directly out of
    `_call_with_deadline` -- there is no thread left behind because none
    was ever created."""
    session = _TransportTimeoutSession(hang_seconds=999.0)
    client = _TransportTimeoutClient(session)

    start = time.monotonic()
    with pytest.raises(TimeoutError, match="simulated transport-level read timeout"):
        _call_with_deadline(client.call, timeout=0.05, label="test")
    elapsed = time.monotonic() - start

    assert session.timeouts_seen == [0.05]
    assert elapsed < 0.5, (
        f"transport-level timeout should abort near its {0.05}s bound, not "
        f"the 999s simulated hang; took {elapsed:.2f}s"
    )


def test_call_with_deadline_rejects_callable_without_reflectable_session():
    """r4 (Codex): a callable with no reflectable bound `_session` must be
    refused loudly -- NOT run unbounded, and NOT raced against via a
    detached thread (the removed fallback)."""

    def plain():
        return "unbounded"

    with pytest.raises(UnboundedBrokerCallError, match="no supported timeout-cancellation"):
        _call_with_deadline(plain, timeout=1.0, label="test")


def test_broker_retry_call_bounded_by_remaining_deadline(monkeypatch):
    """r3 (issue 2) + r4 (Codex): a hanging call must not be allowed to keep
    the helper (or its caller) blocked past the overall deadline. r4
    rewrites this to abort via the REAL cancellation-safe mechanism (a
    transport-level timeout raised synchronously inside the call, per
    `_TransportTimeoutSession`) instead of the removed detached-thread
    fallback -- proving the retry loop's remaining-budget plumbing still
    produces a prompt, bounded failure with the new mechanism.
    """
    import renquant_orchestrator.intraday_session_inputs as mod

    monkeypatch.setattr(mod, "_BROKER_DEADLINE_SECONDS", 0.15)
    monkeypatch.setattr(mod, "_BROKER_BACKOFF_BASE", 0.01)

    session = _TransportTimeoutSession(hang_seconds=999.0)
    client = _TransportTimeoutClient(session)

    start = time.monotonic()
    with pytest.raises(Exception, match="exceeded|deadline|timeout"):
        mod._broker_call_with_retry(client.call, label="test")
    elapsed = time.monotonic() - start
    assert elapsed < 0.5, (
        f"helper should give up near the {mod._BROKER_DEADLINE_SECONDS}s "
        f"deadline, not wait out the 999s hang; took {elapsed:.2f}s"
    )
    # Every attempt received a shrinking, sub-second budget derived from the
    # remaining deadline -- never the full simulated hang.
    assert all(t is not None and t < 1.0 for t in session.timeouts_seen)


def test_no_thread_pool_fallback_in_module():
    """Structural regression guard for the r4 fix: the detached-thread
    fallback must not exist anywhere in this module as executable code --
    Codex asked for its removal, not a workaround alongside it. Checks for
    an actual import/construction, not mere prose mentions in docstrings
    explaining *why* it was removed."""
    import inspect

    import renquant_orchestrator.intraday_session_inputs as mod

    assert "concurrent" not in mod.__dict__
    source = inspect.getsource(mod)
    assert "import concurrent" not in source
    assert "ThreadPoolExecutor(" not in source


class _FakeAlpacaSession:
    """Mimics the surface of alpaca-py's ``requests.Session`` for the parts
    ``RESTClient._one_request`` touches: a bare ``.request(method, url,
    **opts)`` with no timeout of its own."""

    def __init__(self):
        self.captured_timeouts = []

    def request(self, method, url, **kwargs):
        self.captured_timeouts.append(kwargs.get("timeout"))
        return "response"


class _FakeAlpacaClient:
    """Mimics ``alpaca.trading.client.TradingClient``: a bound
    ``get_account``-shaped method whose ``__self__`` exposes a private
    ``_session`` exactly like the real ``RESTClient``."""

    def __init__(self, session):
        self._session = session

    def get_account(self):
        self._session.request("GET", "https://paper-api.alpaca.markets/v2/account")
        return "account"


def test_call_with_deadline_threads_real_timeout_into_alpaca_session():
    """Prove the fix reaches the actual call site: _call_with_deadline must
    bound the real requests.Session call (not just a thread-level race) when
    fn is a bound method of an object exposing a private `_session`, as
    AlpacaLiveStateSource's `client.get_account` / `client.get_all_positions`
    are.
    """
    import renquant_orchestrator.intraday_session_inputs as mod

    session = _FakeAlpacaSession()
    client = _FakeAlpacaClient(session)

    result = mod._call_with_deadline(
        client.get_account, timeout=12.5, label="get_account"
    )

    assert result == "account"
    assert session.captured_timeouts == [12.5]


def test_call_with_deadline_updates_timeout_per_attempt_idempotently():
    """The session patch must be idempotent (wrapped once) while still
    honoring a fresh timeout value on each subsequent call -- matching how
    AlpacaLiveStateSource reuses the same memoized client/session across
    get_account() and get_all_positions() on every attempt."""
    import renquant_orchestrator.intraday_session_inputs as mod

    session = _FakeAlpacaSession()
    client = _FakeAlpacaClient(session)

    mod._call_with_deadline(client.get_account, timeout=30.0, label="get_account")
    wrapped_request = session.request
    mod._call_with_deadline(client.get_account, timeout=5.0, label="get_account")

    assert session.captured_timeouts == [30.0, 5.0]
    # Patched exactly once -- no repeated re-wrapping across calls.
    assert session.request is wrapped_request


def test_call_with_deadline_concurrent_callers_see_own_timeout():
    """Two threads sharing the SAME memoized client/session must each see
    their own timeout value, not the other caller's. Before the ContextVar
    fix, this would interleave because both wrote to
    `session._renquant_call_timeout` on the shared session object."""
    import threading
    import renquant_orchestrator.intraday_session_inputs as mod

    barrier = threading.Barrier(2, timeout=5)
    results: dict[str, float | None] = {}

    class _BarrierSession:
        def __init__(self):
            self._renquant_timeout_patched = False

        def request(self, method, url, **kwargs):
            timeout = kwargs.get("timeout")
            caller = threading.current_thread().name
            barrier.wait()
            results[caller] = timeout
            return "response"

    class _BarrierClient:
        def __init__(self, session):
            self._session = session

        def call(self):
            return self._session.request("GET", "/test")

    session = _BarrierSession()
    client = _BarrierClient(session)

    def worker(name: str, budget: float):
        threading.current_thread().name = name
        mod._call_with_deadline(client.call, timeout=budget, label=name)

    t1 = threading.Thread(target=worker, args=("A", 10.0))
    t2 = threading.Thread(target=worker, args=("B", 99.0))
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert results["A"] == 10.0, f"Thread A saw {results['A']}, expected 10.0"
    assert results["B"] == 99.0, f"Thread B saw {results['B']}, expected 99.0"
