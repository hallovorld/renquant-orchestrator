"""Tests for the Stage-2 live executor (RFC #208 §7/§9.3a/§10, sprint D2).

Covers the pre-registered safety surface, with NO live broker call anywhere
(fake ports only; the real ``AlpacaBrokerPort`` — owned by
renquant-execution — is tested THERE, against an injected fake client; this
suite only pins the lazy fail-closed import seam):

- the §9.3a QUADRUPLE gate — all 16 combinations, only all-four arms live;
- authorization-file schema rejection cases;
- ``mode: "live"`` WITHOUT the authorization file still runs shadow
  (counted), and the fake port factory is never invoked;
- daily entry-notional cap enforcement including the exit exemption;
- write-ahead ordering (the journal line exists BEFORE the broker call);
- the dead-man switch (3 consecutive broker errors halt entries, exits
  continue);
- the fake-broker round trip: submit → partial fill → fill → snapshot →
  restore → reconcile, with the snapshot readable by the Stage-1
  ``load_order_state_reservations`` reader (slice-1 shape parity).
"""
from __future__ import annotations

import itertools
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from renquant_artifacts import hash_jsonable
from renquant_execution.order_state_machine import (
    OrderStateBook,
    compute_parent_intent_id,
)

from renquant_orchestrator.intraday_session_inputs import (
    load_order_state_reservations,
)
from renquant_orchestrator.intraday_session_scheduler import (
    ENV_FLAG as SHADOW_ENV_FLAG,
    IntradayDecisioningConfig,
    KillSwitch,
    MODE_LIVE,
    MODE_SHADOW,
)
from renquant_orchestrator.intraday_live_executor import (
    ENV_LIVE_FLAG,
    GATE_AUTHORIZATION_FILE,
    GATE_CONFIG_MODE_LIVE,
    GATE_ENV_LIVE_FLAG,
    GATE_KILL_SWITCH_ABSENT,
    MIN_SHADOW_SESSIONS_CLEAN,
    REASON_ENTRIES_HALTED,
    REASON_ENTRY_CAP,
    RECORD_KIND_ACTION,
    RECORD_KIND_LIVE_TICK,
    DeadManSwitch,
    EntryCapExceededError,
    LiveActionLog,
    LiveSessionRunner,
    LiveTickExecutor,
    LiveTickWriter,
    Stage2Authorization,
    Stage2AuthorizationError,
    Stage2ContractError,
    assert_entry_cap,
    entry_notional_submitted,
    load_stage2_authorization,
    resolve_stage2_arming,
)

ET = ZoneInfo("America/New_York")
DAY = "2026-07-06"  # a Monday
ACCOUNT = "TEST-ACCT"
SIGNAL_VERSION = "run-fri:deadbeef"
NOW = datetime(2026, 7, 6, 10, 0, tzinfo=ET)


# ─────────────────────────── fixtures ───────────────────────────
def valid_authorization_payload(**overrides) -> dict:
    payload = {
        "authorized_by": "renhao",
        "date": "2026-07-03",
        "expiry": "2026-07-31",
        "daily_entry_notional_cap": 500.0,
        "evidence": {
            "shadow_sessions_clean": 5,
            "replay_audits_green": True,
            "entry_timing_report": "doc/research/entry-timing-readout.md",
        },
    }
    payload.update(overrides)
    return payload


def write_authorization(tmp_path: Path, payload: dict | None = None) -> Path:
    path = tmp_path / "stage2_authorization.json"
    path.write_text(
        json.dumps(payload if payload is not None else valid_authorization_payload()),
        encoding="utf-8",
    )
    return path


def make_authorization(**overrides) -> Stage2Authorization:
    return Stage2Authorization.from_payload(
        valid_authorization_payload(**overrides), today=DAY
    )


class FakeBrokerPort:
    """In-memory broker: accepts submissions, scriptable fills/failures."""

    def __init__(self):
        self.orders: dict[str, dict] = {}
        self.submit_calls: list[dict] = []
        self.cancel_calls: list[str] = []
        self.fail_next_submits = 0
        self.on_submit = None  # hook(client_order_id) before accepting

    def submit_order(self, *, client_order_id, symbol, side, qty, limit_price=None):
        self.submit_calls.append(
            {
                "client_order_id": client_order_id,
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "limit_price": limit_price,
            }
        )
        if self.on_submit is not None:
            self.on_submit(client_order_id)
        if self.fail_next_submits > 0:
            self.fail_next_submits -= 1
            raise RuntimeError("broker down")
        assert client_order_id not in self.orders, "duplicate client_order_id"
        self.orders[client_order_id] = {
            "symbol": symbol,
            "side": side,
            "qty": float(qty),
            "filled_qty": 0.0,
            "status": "accepted",
            "limit_price": limit_price,
        }
        return {"status": "accepted", "filled_qty": 0.0, "broker_order_id": "b-1"}

    def fill(self, client_order_id: str, qty: float) -> None:
        order = self.orders[client_order_id]
        order["filled_qty"] += qty
        order["status"] = (
            "filled" if order["filled_qty"] >= order["qty"] - 1e-9 else "partially_filled"
        )

    def cancel_order(self, client_order_id):
        self.cancel_calls.append(client_order_id)
        order = self.orders[client_order_id]
        if order["status"] not in ("filled", "canceled", "rejected", "expired"):
            order["status"] = "canceled"
        return {"status": order["status"], "filled_qty": order["filled_qty"]}

    def open_orders(self):
        return {
            cid: o["qty"] - o["filled_qty"]
            for cid, o in self.orders.items()
            if o["status"] in ("accepted", "new", "partially_filled")
        }

    def order_status(self, client_order_id):
        order = self.orders[client_order_id]
        return {"status": order["status"], "filled_qty": order["filled_qty"]}


def pid(symbol: str, side: str) -> str:
    return compute_parent_intent_id(
        account=ACCOUNT,
        symbol=symbol,
        trading_day=DAY,
        side=side,
        signal_version=SIGNAL_VERSION,
    )


def make_intent(symbol: str, side: str, qty: float, price: float | None) -> dict:
    return {
        "parent_intent_id": pid(symbol, side),
        "account": ACCOUNT,
        "symbol": symbol,
        "side": side,
        "kind": "entry" if side == "BUY" else "exit",
        "quantity": qty,
        "price": price,
        "notional": (qty * price) if price else 0.0,
        "trading_day": DAY,
        "signal_version": SIGNAL_VERSION,
        "order": {"ticker": symbol},
    }


def make_executor(
    tmp_path: Path,
    port: FakeBrokerPort | None = None,
    *,
    cap: float = 500.0,
    begin: bool = True,
) -> LiveTickExecutor:
    executor = LiveTickExecutor(
        account=ACCOUNT,
        trading_day=DAY,
        port=port if port is not None else FakeBrokerPort(),
        action_log=LiveActionLog(tmp_path / "actions.jsonl"),
        book_path=tmp_path / "order_state_book.json",
        authorization=make_authorization(daily_entry_notional_cap=cap),
    )
    if begin:
        executor.begin_session()
    return executor


def read_actions(tmp_path: Path) -> list[dict]:
    path = tmp_path / "actions.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ─────────────────── the §9.3a quadruple gate (16 combos) ───────────────────
@pytest.mark.parametrize(
    "config_live,auth_file,env_flag,kill_absent",
    list(itertools.product([True, False], repeat=4)),
)
def test_quadruple_gate_all_16_combinations(
    tmp_path, config_live, auth_file, env_flag, kill_absent
):
    """ONLY all-four-gates-true arms live; ANY missing gate ⇒ shadow."""
    config = IntradayDecisioningConfig(
        enabled=True, mode=MODE_LIVE if config_live else MODE_SHADOW
    )
    auth_path = (
        write_authorization(tmp_path) if auth_file else tmp_path / "absent.json"
    )
    environ = {ENV_LIVE_FLAG: "1"} if env_flag else {}
    kill_path = tmp_path / "KILL"
    if not kill_absent:
        kill_path.touch()

    decision = resolve_stage2_arming(
        config=config,
        authorization_path=auth_path,
        kill_switch=KillSwitch(kill_path),
        environ=environ,
        today=DAY,
    )
    should_arm = config_live and auth_file and env_flag and kill_absent
    assert decision.armed is should_arm
    assert decision.mode_effective == (MODE_LIVE if should_arm else MODE_SHADOW)
    assert decision.gates == {
        GATE_CONFIG_MODE_LIVE: config_live,
        GATE_AUTHORIZATION_FILE: auth_file,
        GATE_ENV_LIVE_FLAG: env_flag,
        GATE_KILL_SWITCH_ABSENT: kill_absent,
    }
    # A refused live request is DOWNGRADED (counted); shadow-mode configs are
    # not "downgraded", they simply never asked.
    assert decision.downgraded is (config_live and not should_arm)
    if not should_arm:
        assert decision.reasons  # every failed gate is explained


# ─────────────────── authorization-file schema rejections ───────────────────
def test_valid_authorization_loads(tmp_path):
    path = write_authorization(tmp_path)
    auth = load_stage2_authorization(path, today=DAY)
    assert auth.authorized_by == "renhao"
    assert auth.daily_entry_notional_cap == 500.0
    assert auth.shadow_sessions_clean == MIN_SHADOW_SESSIONS_CLEAN
    assert auth.entry_order_type == "limit"  # A5.2 default: marketable-limit
    assert auth.exit_order_type == "market"
    assert auth.content_sha256 == hash_jsonable(valid_authorization_payload())


@pytest.mark.parametrize(
    "mutation,match",
    [
        ({"authorized_by": ""}, "authorized_by"),
        ({"authorized_by": None}, "authorized_by"),
        ({"date": "not-a-date"}, "date"),
        ({"date": "2026-08-01"}, "post-dated"),
        ({"expiry": "2026-07-01"}, "expired"),
        ({"expiry": "2026-12-31"}, "duration cap"),
        ({"daily_entry_notional_cap": 0}, "positive finite"),
        ({"daily_entry_notional_cap": -500}, "positive finite"),
        ({"daily_entry_notional_cap": "lots"}, "must be a number"),
        ({"evidence": None}, "evidence is required"),
        (
            {
                "evidence": {
                    "shadow_sessions_clean": MIN_SHADOW_SESSIONS_CLEAN - 1,
                    "replay_audits_green": True,
                    "entry_timing_report": "x.md",
                }
            },
            "below the",
        ),
        (
            {
                "evidence": {
                    "shadow_sessions_clean": 5,
                    "replay_audits_green": False,
                    "entry_timing_report": "x.md",
                }
            },
            "replay_audits_green",
        ),
        (
            {
                "evidence": {
                    "shadow_sessions_clean": 5,
                    "replay_audits_green": True,
                }
            },
            "entry_timing_report",
        ),
        ({"order": {"entry_order_type": "stop"}}, "entry_order_type"),
        ({"order": {"limit_price_offset_bps": 500}}, "limit_price_offset_bps"),
    ],
)
def test_authorization_schema_rejections(tmp_path, mutation, match):
    path = write_authorization(tmp_path, valid_authorization_payload(**mutation))
    with pytest.raises(Stage2AuthorizationError, match=match):
        load_stage2_authorization(path, today=DAY)


def test_authorization_missing_and_malformed_files(tmp_path):
    with pytest.raises(Stage2AuthorizationError, match="absent"):
        load_stage2_authorization(tmp_path / "nope.json", today=DAY)
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(Stage2AuthorizationError, match="unreadable"):
        load_stage2_authorization(bad, today=DAY)
    array = tmp_path / "array.json"
    array.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(Stage2AuthorizationError, match="not a JSON object"):
        load_stage2_authorization(array, today=DAY)


# ─────────────────── reconcile-before-emit on session start ───────────────────
def test_tick_before_begin_session_is_refused(tmp_path):
    executor = make_executor(tmp_path, begin=False)
    with pytest.raises(Stage2ContractError, match="reconcile-before-emit"):
        executor.process_tick({"intents": []}, now=NOW)


def test_begin_session_reconciles_fresh_book_against_broker(tmp_path):
    port = FakeBrokerPort()
    # An unknown broker open order that a FRESH book cannot explain.
    port.orders["ghost-1"] = {
        "symbol": "AAA",
        "side": "BUY",
        "qty": 5.0,
        "filled_qty": 0.0,
        "status": "accepted",
        "limit_price": 10.0,
    }
    executor = make_executor(tmp_path, port, begin=False)
    report = executor.begin_session()
    assert report["reconcile_clean"] is False
    assert report["entries_halted"] is True
    assert report["mismatches"][0]["kind"] == "unknown_broker_order"
    # Entries halted, exits still flow.
    result = executor.process_tick(
        {
            "intents": [
                make_intent("BBB", "BUY", 2, 50.0),
                make_intent("CCC", "SELL", 1, 30.0),
            ]
        },
        now=NOW,
    )
    assert [s["reasons"] for s in result["skipped"]] == [[REASON_ENTRIES_HALTED]]
    assert [s["side"] for s in result["submitted"]] == ["SELL"]


# ─────────────────────── cap enforcement + exit exemption ───────────────────────
def test_entry_cap_blocks_entries_but_never_exits(tmp_path):
    port = FakeBrokerPort()
    executor = make_executor(tmp_path, port, cap=500.0)
    result = executor.process_tick(
        {
            "intents": [
                make_intent("BIG", "BUY", 3, 200.0),  # 600 > 500 → blocked
                make_intent("AAA", "BUY", 4, 100.0),  # 400 ≤ 500 → submitted
                make_intent("BBB", "BUY", 2, 60.0),  # 400+120 > 500 → blocked
                make_intent("HUGE", "SELL", 100, 300.0),  # exits NEVER capped
            ]
        },
        now=NOW,
    )
    submitted = {(s["symbol"], s["side"]) for s in result["submitted"]}
    assert submitted == {("AAA", "BUY"), ("HUGE", "SELL")}
    reasons = {s["symbol"]: s["reasons"] for s in result["skipped"]}
    assert reasons == {"BIG": [REASON_ENTRY_CAP], "BBB": [REASON_ENTRY_CAP]}
    assert result["cap"]["entry_notional_submitted"] == pytest.approx(400.0)
    # The broker saw exactly the allowed orders.
    broker_sides = {(c["symbol"], c["side"]) for c in port.submit_calls}
    assert broker_sides == {("AAA", "BUY"), ("HUGE", "SELL")}


def test_entry_cap_hard_assertion(tmp_path):
    executor = make_executor(tmp_path, cap=500.0)
    book = executor.book
    book.register_intent(
        symbol="AAA", side="BUY", signal_version=SIGNAL_VERSION, target_qty=4
    )
    with pytest.raises(EntryCapExceededError, match="cap breach"):
        assert_entry_cap(book, additional_notional=600.0, cap=500.0)
    assert_entry_cap(book, additional_notional=500.0, cap=500.0)  # boundary ok
    assert entry_notional_submitted(book) == 0.0


def test_cap_counts_gross_submitted_across_ticks(tmp_path):
    port = FakeBrokerPort()
    executor = make_executor(tmp_path, port, cap=500.0)
    executor.process_tick(
        {"intents": [make_intent("AAA", "BUY", 4, 100.0)]}, now=NOW
    )
    # Second tick: 400 already submitted, another 150 would breach.
    result = executor.process_tick(
        {"intents": [make_intent("BBB", "BUY", 3, 50.0)]},
        now=NOW + timedelta(minutes=12),
    )
    assert result["skipped"][0]["reasons"] == [REASON_ENTRY_CAP]
    assert entry_notional_submitted(executor.book) == pytest.approx(400.0)


# ─────────────────────────── write-ahead ordering ───────────────────────────
def test_write_ahead_line_lands_before_the_broker_call(tmp_path):
    port = FakeBrokerPort()
    observed: list[dict] = []

    def on_submit(client_order_id: str) -> None:
        rows = read_actions(tmp_path)
        ahead = [
            r
            for r in rows
            if r.get("phase") == "write_ahead"
            and r.get("client_order_id") == client_order_id
        ]
        outcomes = [
            r
            for r in rows
            if r.get("phase") == "outcome"
            and any(
                a.get("action_id") == r.get("action_id")
                for a in ahead
            )
        ]
        observed.append(
            {"cid": client_order_id, "ahead": len(ahead), "outcomes": len(outcomes)}
        )

    port.on_submit = on_submit
    executor = make_executor(tmp_path, port)
    executor.process_tick(
        {"intents": [make_intent("AAA", "BUY", 2, 100.0)]}, now=NOW
    )
    # At the moment the broker was called, the write-ahead line existed and
    # its outcome did not.
    assert observed == [{"cid": pid("AAA", "BUY") + ":1", "ahead": 1, "outcomes": 0}]
    rows = read_actions(tmp_path)
    assert [r["phase"] for r in rows if r["kind"] == RECORD_KIND_ACTION] == [
        "write_ahead",
        "outcome",
    ]
    assert rows[0]["order_type"] == "limit"
    assert rows[0]["time_in_force"] == "day"
    assert rows[1]["status"] == "accepted"


def test_broker_error_outcome_is_journaled_and_child_rejected(tmp_path):
    port = FakeBrokerPort()
    port.fail_next_submits = 1
    executor = make_executor(tmp_path, port)
    result = executor.process_tick(
        {"intents": [make_intent("AAA", "BUY", 2, 100.0)]}, now=NOW
    )
    assert result["submitted"][0]["status"] == "error"
    rows = read_actions(tmp_path)
    assert rows[0]["phase"] == "write_ahead"
    assert rows[1]["phase"] == "outcome"
    assert rows[1]["status"] == "error"
    assert "broker down" in rows[1]["error"]
    parent = executor.book.parent(pid("AAA", "BUY"))
    assert parent.cum_rejected == pytest.approx(2.0)
    assert parent.open_child is None


# ─────────────────────────────── dead-man ───────────────────────────────
def test_dead_man_three_consecutive_errors_halt_entries_exits_continue(tmp_path):
    port = FakeBrokerPort()
    port.fail_next_submits = 3
    executor = make_executor(tmp_path, port, cap=5000.0)
    result = executor.process_tick(
        {
            "intents": [
                make_intent("AAA", "BUY", 1, 100.0),
                make_intent("BBB", "BUY", 1, 100.0),
                make_intent("CCC", "BUY", 1, 100.0),
            ]
        },
        now=NOW,
    )
    assert result["dead_man"]["tripped"] is True
    assert result["entries_halted"] is True
    assert result["halt_reason"] == "dead_man_consecutive_broker_errors"

    # Next tick: entries refused WITHOUT touching the broker; exits flow.
    calls_before = len(port.submit_calls)
    result2 = executor.process_tick(
        {
            "intents": [
                make_intent("DDD", "BUY", 1, 100.0),
                make_intent("EEE", "SELL", 2, 50.0),
            ]
        },
        now=NOW + timedelta(minutes=12),
    )
    assert [s["reasons"] for s in result2["skipped"]] == [[REASON_ENTRIES_HALTED]]
    assert [s["side"] for s in result2["submitted"]] == ["SELL"]
    assert len(port.submit_calls) == calls_before + 1  # only the exit


def test_dead_man_success_resets_the_consecutive_counter(tmp_path):
    dead_man = DeadManSwitch()
    assert dead_man.record_failure() is False
    assert dead_man.record_failure() is False
    dead_man.record_success()
    assert dead_man.consecutive_failures == 0
    assert dead_man.record_failure() is False  # 1 of 3 again — not tripped
    assert dead_man.tripped is False


# ───────────────────────── fake-broker round trip ─────────────────────────
def test_round_trip_submit_partial_fill_snapshot_restore_reconcile(tmp_path):
    port = FakeBrokerPort()
    executor = make_executor(tmp_path, port)
    book_path = tmp_path / "order_state_book.json"

    # Tick 1: submit an entry (4 × $100).
    executor.process_tick(
        {"intents": [make_intent("AAA", "BUY", 4, 100.0)]}, now=NOW
    )
    cid = pid("AAA", "BUY") + ":1"
    assert port.orders[cid]["qty"] == 4.0

    # Broker partially fills 2; tick 2 reconciles the fill into the book.
    # (+5 min: under the 10-min stale-pending age, so the child stays OPEN.)
    port.fill(cid, 2.0)
    executor.process_tick({"intents": []}, now=NOW + timedelta(minutes=5))
    parent = executor.book.parent(pid("AAA", "BUY"))
    assert parent.cum_filled == pytest.approx(2.0)
    assert parent.open_qty == pytest.approx(2.0)

    # The persisted snapshot is slice-1 shape: Stage-1's reservations reader
    # parses it and sees the open-buy reservation (2 unfilled × $100).
    snapshot = json.loads(book_path.read_text(encoding="utf-8"))
    assert snapshot["schema_version"] == "order-state-machine-v1"
    reservations = load_order_state_reservations(book_path, trading_day=DAY)
    assert reservations["open_buy_reservations"] == {
        pid("AAA", "BUY"): pytest.approx(200.0)
    }
    assert reservations["in_flight_parent_intents"] == [pid("AAA", "BUY")]

    # RESTORE into a brand-new executor: refuses ticks until begin_session
    # reconciles against broker open-orders (restore ⇒ needs_reconcile).
    restored = LiveTickExecutor(
        account=ACCOUNT,
        trading_day=DAY,
        port=port,
        action_log=LiveActionLog(tmp_path / "actions.jsonl"),
        book_path=book_path,
        authorization=make_authorization(),
    )
    with pytest.raises(Stage2ContractError, match="reconcile-before-emit"):
        restored.process_tick({"intents": []}, now=NOW + timedelta(minutes=7))
    report = restored.begin_session()
    assert report["restored"] is True
    assert report["reconcile_clean"] is True
    assert report["entries_halted"] is False

    # Broker completes the fill; the restored book converges to FILLED.
    port.fill(cid, 2.0)
    restored.process_tick({"intents": []}, now=NOW + timedelta(minutes=9))
    parent = restored.book.parent(pid("AAA", "BUY"))
    assert parent.state.value == "FILLED"
    assert parent.cum_filled == pytest.approx(4.0)
    final = json.loads(book_path.read_text(encoding="utf-8"))
    assert final["parents"][0]["children"][0]["filled_qty"] == pytest.approx(4.0)


def test_restore_with_book_broker_mismatch_halts_entries(tmp_path):
    port = FakeBrokerPort()
    executor = make_executor(tmp_path, port)
    executor.process_tick(
        {"intents": [make_intent("AAA", "BUY", 4, 100.0)]}, now=NOW
    )
    cid = pid("AAA", "BUY") + ":1"
    # The broker loses the order without a terminal status (still "accepted"
    # per order_status but absent from open_orders is the reconcilable case;
    # here we make order_status contradict by deleting it entirely).
    del port.orders[cid]
    port.orders[cid] = {
        "symbol": "AAA",
        "side": "BUY",
        "qty": 4.0,
        "filled_qty": 0.0,
        "status": "pending_new",  # not open per open_orders(), not terminal
        "limit_price": 100.0,
    }
    restored = LiveTickExecutor(
        account=ACCOUNT,
        trading_day=DAY,
        port=port,
        action_log=LiveActionLog(tmp_path / "actions.jsonl"),
        book_path=tmp_path / "order_state_book.json",
        authorization=make_authorization(),
    )
    report = restored.begin_session()
    assert report["reconcile_clean"] is False
    assert report["entries_halted"] is True


# ───────────────── mode:"live" without the file still shadows ─────────────────
class FakeCalendar:
    name = "FAKE-NYSE"

    def __init__(self, sessions: dict[str, tuple[str, str]]):
        self._sessions = sessions

    def session_bounds(self, day):
        from renquant_orchestrator.intraday_quote_logger import SessionBounds

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


class ManualClock:
    def __init__(self, start: datetime):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)


def fake_signal() -> dict:
    scores = {"AAA": 0.9, "BBB": 0.5}
    return {
        "signal_version": SIGNAL_VERSION,
        "as_of": "2026-07-03",
        "scores": scores,
        "source_run_id": "run-fri",
        "score_content_sha256": hash_jsonable(scores),
    }


def fake_live_state(*, now: datetime, trading_day: str):
    return {
        "as_of": now.astimezone(ET).isoformat(),
        "trading_day": trading_day,
        "account": ACCOUNT,
        "cash": 1000.0,
        "equity": 2000.0,
        "positions": {},
        "prices": {"AAA": 100.0, "BBB": 20.0},
        "open_buy_reservations": {},
        "unsettled_buys": 0.0,
        "pending_broker_tickers": [],
    }


def fake_tick_runner(
    *,
    signal,
    session_start,
    live_state,
    session_counters,
    in_flight_parent_intents,
    exit_orders,
):
    """One BUY intent per tick (lockstep parent ids), dedup on in-flight."""
    intents = []
    in_flight = set(in_flight_parent_intents)
    for symbol in sorted(signal["scores"], key=signal["scores"].get, reverse=True):
        parent = compute_parent_intent_id(
            account=live_state["account"],
            symbol=symbol,
            trading_day=live_state["trading_day"],
            side="BUY",
            signal_version=signal["signal_version"],
        )
        if parent in in_flight:
            continue
        price = float(live_state["prices"][symbol])
        intents.append(
            {
                "parent_intent_id": parent,
                "account": live_state["account"],
                "symbol": symbol,
                "side": "BUY",
                "kind": "entry",
                "quantity": 1.0,
                "price": price,
                "notional": price,
                "trading_day": live_state["trading_day"],
                "signal_version": signal["signal_version"],
                "order": {"ticker": symbol, "action": "buy", "quantity": 1.0},
            }
        )
        break
    return {
        "enabled": True,
        "reason": "ok",
        "intents": intents,
        "skipped": [],
        "blocked_by": {},
        "counters": dict(session_counters),
    }


def make_runner(
    tmp_path: Path,
    *,
    config: IntradayDecisioningConfig,
    environ: dict,
    with_authorization: bool,
    port: FakeBrokerPort | None = None,
) -> tuple[LiveSessionRunner, dict]:
    auth_path = (
        write_authorization(tmp_path)
        if with_authorization
        else tmp_path / "stage2_authorization.json"
    )
    state = {"port": port or FakeBrokerPort(), "factory_calls": 0}

    def port_factory(authorization):
        state["factory_calls"] += 1
        return state["port"]

    runner = LiveSessionRunner(
        config=config,
        tick_runner=fake_tick_runner,
        signal_loader=lambda day: fake_signal(),
        session_start_provider=lambda day, now: {"watchlist": ["AAA", "BBB"]},
        live_state_provider=fake_live_state,
        port_factory=port_factory,
        writer=LiveTickWriter(tmp_path / "live.jsonl"),
        shadow_log_path=tmp_path / "shadow.jsonl",
        manifest_path=tmp_path / "manifest.json",
        kill_switch=KillSwitch(tmp_path / "KILL"),
        authorization_path=auth_path,
        actions_log_path=tmp_path / "actions.jsonl",
        book_path=tmp_path / "order_state_book.json",
        calendar=FakeCalendar({DAY: ("10:00", "11:00")}),
        environ=environ,
        strategy_config_fingerprint="cfg-fp",
    )
    return runner, state


def run_full_session(runner: LiveSessionRunner):
    clock = ManualClock(datetime(2026, 7, 6, 10, 0, tzinfo=ET))
    return runner.run_session(now_fn=clock, sleep_fn=clock.sleep)


def test_mode_live_without_authorization_file_still_shadows(tmp_path):
    """The st104 config flip ALONE must not go live: no file ⇒ shadow, counted."""
    config = IntradayDecisioningConfig(
        enabled=True, mode=MODE_LIVE, tick_seconds=600.0
    )
    runner, state = make_runner(
        tmp_path,
        config=config,
        environ={SHADOW_ENV_FLAG: "1", ENV_LIVE_FLAG: "1"},
        with_authorization=False,
    )
    manifest = run_full_session(runner)
    assert manifest["status"] == "completed"
    assert manifest["mode_effective"] == MODE_SHADOW
    assert manifest["live_mode_downgraded_count"] == 1
    assert manifest["stage2_arming"]["armed"] is False
    assert manifest["stage2_arming"]["gates"][GATE_AUTHORIZATION_FILE] is False
    # The submitting client was never even constructed, and no broker call,
    # no actions journal, no order-state book came into existence.
    assert state["factory_calls"] == 0
    assert state["port"].submit_calls == []
    assert not (tmp_path / "actions.jsonl").exists()
    assert not (tmp_path / "order_state_book.json").exists()
    # The session ran as a normal Stage-1 shadow session.
    shadow_lines = (tmp_path / "shadow.jsonl").read_text(encoding="utf-8")
    assert "intraday_decision_shadow_tick" in shadow_lines
    assert not (tmp_path / "live.jsonl").exists()


def test_armed_live_session_submits_through_the_fake_port(tmp_path):
    config = IntradayDecisioningConfig(
        enabled=True, mode=MODE_LIVE, tick_seconds=600.0
    )
    runner, state = make_runner(
        tmp_path,
        config=config,
        environ={SHADOW_ENV_FLAG: "1", ENV_LIVE_FLAG: "1"},
        with_authorization=True,
    )
    manifest = run_full_session(runner)
    assert manifest["status"] == "completed"
    assert manifest["mode_effective"] == MODE_LIVE
    assert manifest["stage2_arming"]["armed"] is True
    assert manifest["live_mode_downgraded_count"] == 0
    assert state["factory_calls"] == 1
    # The fake tick runner buys 1 × AAA @ $100 on the first eligible tick.
    assert state["port"].submit_calls
    first = state["port"].submit_calls[0]
    assert (first["symbol"], first["side"], first["qty"]) == ("AAA", "BUY", 1.0)
    assert first["client_order_id"].endswith(":1")
    # Live tick log + WAL journal + persisted book all exist.
    live_rows = [
        json.loads(line)
        for line in (tmp_path / "live.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert all(r["kind"] == RECORD_KIND_LIVE_TICK for r in live_rows)
    assert live_rows[0]["mode"] == MODE_LIVE
    assert live_rows[0]["execution"]["cap"]["daily_entry_notional_cap"] == 500.0
    assert (tmp_path / "actions.jsonl").exists()
    book = json.loads((tmp_path / "order_state_book.json").read_text(encoding="utf-8"))
    assert book["schema_version"] == "order-state-machine-v1"
    assert manifest["session_start_reconcile"]["reconcile_clean"] is True
    # §11b close-cancel swept the unfilled DAY child at the bell.
    assert manifest["session_close"]["open_children"] == 0


def test_armed_session_with_kill_switch_present_stays_shadow(tmp_path):
    config = IntradayDecisioningConfig(
        enabled=True, mode=MODE_LIVE, tick_seconds=600.0
    )
    runner, state = make_runner(
        tmp_path,
        config=config,
        environ={SHADOW_ENV_FLAG: "1", ENV_LIVE_FLAG: "1"},
        with_authorization=True,
    )
    runner.kill_switch.path.touch()
    manifest = run_full_session(runner)
    # Gate 4 fails ⇒ shadow fallback; the shadow scheduler then also halts
    # on the same kill switch before any tick (defense in depth).
    assert manifest["stage2_arming"]["gates"][GATE_KILL_SWITCH_ABSENT] is False
    assert manifest["mode_effective"] == MODE_SHADOW
    assert manifest["status"] == "halted_kill_switch"
    assert state["factory_calls"] == 0


# AlpacaBrokerPort's own request-shaping test moved to
# renquant-execution/tests/test_alpaca_broker_port.py (renquant-execution#21)
# — broker adapters are owned there, not here. This repo only pins the seam:
# the adapter import is LAZY (inside the default port_factory, invoked only
# after arming) so merge order with renquant-execution#21 stays free.
def test_default_port_factory_import_is_lazy_and_fails_closed(monkeypatch):
    """An execution repo without the adapter breaks ARMING, not import."""
    import sys

    from renquant_orchestrator import intraday_live_executor as live

    monkeypatch.setitem(
        sys.modules, "renquant_execution.alpaca_broker_port", None
    )
    with pytest.raises(Stage2ContractError, match="renquant-execution#21"):
        live._load_alpaca_broker_port_cls()


def test_default_port_factory_uses_the_execution_owned_adapter():
    """When available, the loader returns renquant-execution's class —
    never a local reimplementation (CLAUDE.md: no broker adapters here)."""
    pytest.importorskip("renquant_execution.alpaca_broker_port")
    from renquant_orchestrator import intraday_live_executor as live

    cls = live._load_alpaca_broker_port_cls()
    assert cls.__module__ == "renquant_execution.alpaca_broker_port"
    assert cls.__name__ == "AlpacaBrokerPort"


# ───────────────────────── id lockstep guard ─────────────────────────
def test_parent_intent_id_lockstep_violation_halts_loudly(tmp_path):
    executor = make_executor(tmp_path)
    intent = make_intent("AAA", "BUY", 1, 100.0)
    intent["parent_intent_id"] = "pi-not-the-lockstep-recipe"
    with pytest.raises(Stage2ContractError, match="lockstep violation"):
        executor.process_tick({"intents": [intent]}, now=NOW)


def test_one_open_child_per_parent_is_consumed_from_slice_1(tmp_path):
    """The slice-1 rule holds through this driver: a second submit for the
    same parent while a child is OPEN is impossible (no_emittable_remainder)."""
    port = FakeBrokerPort()
    executor = make_executor(tmp_path, port, cap=5000.0)  # cap out of the way
    executor.process_tick(
        {"intents": [make_intent("AAA", "BUY", 4, 100.0)]}, now=NOW
    )
    result = executor.process_tick(
        {"intents": [make_intent("AAA", "BUY", 4, 100.0)]},
        now=NOW + timedelta(minutes=5),  # child still OPEN (< stale age)
    )
    assert result["skipped"][0]["reasons"] == ["no_emittable_remainder"]
    assert len(port.submit_calls) == 1
    book = OrderStateBook.from_snapshot(
        json.loads((tmp_path / "order_state_book.json").read_text(encoding="utf-8"))
    )
    assert len(book.parents()) == 1
    assert len(book.parents()[0].children) == 1
