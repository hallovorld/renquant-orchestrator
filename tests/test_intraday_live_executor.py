"""Tests for the Stage-2 live executor (RFC #208 §7/§9.3a/§10, sprint D2).

Covers the pre-registered safety surface, with NO live broker call anywhere
(fake ports only; the real ``AlpacaBrokerPort`` — owned by
renquant-execution — is tested THERE, against an injected fake client; this
suite only pins the lazy fail-closed import seam):

- the §9.3a arming matrix — the original 16 quadruple-gate combinations
  EXTENDED (campaign A4, audit #296 OR-3) with the allowlist-consistency,
  loss-budget and session-counter dimensions (128 combinations); only
  all-gates-true arms live;
- authorization-file schema rejection cases, including the campaign-A4
  fields: ``canary_allowlist`` (absent / null / empty / malformed all fail
  closed — §9.3a has no unrestricted-canary mode), the REQUIRED
  ``max_cumulative_loss_usd``, and ``max_live_sessions`` (hard cap 20);
- canary-allowlist ENFORCEMENT: non-allowlisted BUY intents skipped with a
  counted, journaled reason and never shown to the broker; exits NEVER
  blocked; the hard assert around every BUY submit;
- the §9.3a cumulative loss budget: realized and MTM trip paths, sticky
  across sessions (persisted), halts entries while exits continue, fires
  the CRITICAL notification, refuses re-arming;
- the §9.3a session counter: idempotent per date, journal-stamped,
  ceiling refuses arming and hard-fails a defense-in-depth begin_session;
- envelope persistence round-trips, the new-authorization reset (old
  envelope archived), and corrupt-state fail-closed;
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
    CANARY_STATE_SCHEMA_VERSION,
    ENV_LIVE_FLAG,
    GATE_AUTHORIZATION_FILE,
    GATE_CANARY_ENVELOPE,
    GATE_CONFIG_MODE_LIVE,
    GATE_ENV_LIVE_FLAG,
    GATE_KILL_SWITCH_ABSENT,
    HALT_REASON_LOSS_BUDGET,
    MAX_CANARY_LIVE_SESSIONS,
    MIN_SHADOW_SESSIONS_CLEAN,
    REASON_ENTRIES_HALTED,
    REASON_ENTRY_CAP,
    REASON_NOT_ALLOWLISTED,
    RECORD_KIND_ACTION,
    RECORD_KIND_ENVELOPE,
    RECORD_KIND_LIVE_TICK,
    CanaryEnvelopeTracker,
    DeadManSwitch,
    EntryCapExceededError,
    LiveActionLog,
    LiveTickExecutor,
    LiveTickWriter,
    Stage2Authorization,
    Stage2AuthorizationError,
    Stage2ContractError,
    assert_canary_allowlist,
    assert_entry_cap,
    entry_notional_submitted,
    load_stage2_authorization,
    read_canary_envelope,
    resolve_stage2_arming,
)

ET = ZoneInfo("America/New_York")
DAY = "2026-07-06"  # a Monday
ACCOUNT = "TEST-ACCT"
SIGNAL_VERSION = "run-fri:deadbeef"
NOW = datetime(2026, 7, 6, 10, 0, tzinfo=ET)


# ─────────────────────────── fixtures ───────────────────────────
#: BUY symbols the suite exercises — all pre-declared, so the §9.3a
#: allowlist enforcement is active in EVERY executor test below. SELL-only
#: symbols (EEE, HUGE, YYY) are deliberately NOT allowlisted: any exit that
#: flows in these tests also pins allowlist-never-blocks-exits.
ALLOWLIST = ["AAA", "BBB", "BIG", "CCC", "DDD"]


def valid_authorization_payload(**overrides) -> dict:
    payload = {
        "authorized_by": "renhao",
        "date": "2026-07-03",
        "expiry": "2026-07-31",
        "daily_entry_notional_cap": 500.0,
        "canary_allowlist": list(ALLOWLIST),
        "max_cumulative_loss_usd": 150.0,
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

    def fill(self, client_order_id: str, qty: float, price: float | None = None) -> None:
        order = self.orders[client_order_id]
        order["filled_qty"] += qty
        if price is not None:
            order["filled_avg_price"] = price
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
        row = {"status": order["status"], "filled_qty": order["filled_qty"]}
        if "filled_avg_price" in order:
            row["filled_avg_price"] = order["filled_avg_price"]
        return row


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
    trading_day: str = DAY,
    max_loss: float = 10_000.0,
    notifications: list | None = None,
    auth_overrides: dict | None = None,
) -> LiveTickExecutor:
    overrides = dict(auth_overrides or {})
    overrides.setdefault("daily_entry_notional_cap", cap)
    overrides.setdefault("max_cumulative_loss_usd", max_loss)
    sink = notifications if notifications is not None else []
    executor = LiveTickExecutor(
        account=ACCOUNT,
        trading_day=trading_day,
        port=port if port is not None else FakeBrokerPort(),
        action_log=LiveActionLog(tmp_path / "actions.jsonl"),
        book_path=tmp_path / "order_state_book.json",
        authorization=make_authorization(**overrides),
        canary_state_path=tmp_path / "stage2_canary_state.json",
        # NEVER the real ntfy poster in tests.
        notify=lambda title, body: sink.append((title, body)),
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


def read_broker_actions(tmp_path: Path) -> list[dict]:
    return [r for r in read_actions(tmp_path) if r["kind"] == RECORD_KIND_ACTION]


def read_envelope_stamps(tmp_path: Path) -> list[dict]:
    return [r for r in read_actions(tmp_path) if r["kind"] == RECORD_KIND_ENVELOPE]


def write_canary_state(
    tmp_path: Path,
    authorization_sha256: str,
    *,
    sessions: list[str] | None = None,
    tripped: bool = False,
) -> Path:
    path = tmp_path / "stage2_canary_state.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": CANARY_STATE_SCHEMA_VERSION,
                "authorization_sha256": authorization_sha256,
                "sessions": list(sessions or []),
                "positions": {},
                "realized_pnl_usd": 0.0,
                "last_marks": {},
                "loss_budget_tripped": tripped,
                "trip_reason": "seeded trip" if tripped else None,
                "previous_envelopes": [],
            }
        ),
        encoding="utf-8",
    )
    return path


# ──────────── the §9.3a arming matrix (16 quadruple-gate combos ────────────
# ──────────── × allowlist/budget/counter dimensions = 128 combos) ───────────
@pytest.mark.parametrize(
    "config_live,auth_file,env_flag,kill_absent,allowlist_ok,budget_ok,sessions_ok",
    list(itertools.product([True, False], repeat=7)),
)
def test_arming_matrix_all_128_combinations(
    tmp_path,
    config_live,
    auth_file,
    env_flag,
    kill_absent,
    allowlist_ok,
    budget_ok,
    sessions_ok,
):
    """ONLY all-gates-true arms live; ANY missing gate ⇒ shadow (counted).

    The original 16-combination quadruple-gate matrix, extended (campaign
    A4, audit #296 OR-3) with three envelope dimensions: allowlist
    consistency with the pinned config (part of gate 2 — authorization
    validity), the persisted §9.3a loss-budget trip, and the persisted
    session-counter ceiling (gate 5 — envelope availability).
    """
    config = IntradayDecisioningConfig(
        enabled=True,
        mode=MODE_LIVE if config_live else MODE_SHADOW,
        # allowlist_ok=False: the pinned config declares an allowlist the
        # authorization's is NOT a subset of — ambiguity fails closed.
        canary_allowlist=() if allowlist_ok else ("ZZZ",),
    )
    auth_path = (
        write_authorization(tmp_path) if auth_file else tmp_path / "absent.json"
    )
    auth_sha = hash_jsonable(valid_authorization_payload())
    if not budget_ok or not sessions_ok:
        write_canary_state(
            tmp_path,
            auth_sha,
            sessions=(
                [f"2026-06-{d:02d}" for d in range(1, MAX_CANARY_LIVE_SESSIONS + 1)]
                if not sessions_ok
                else []
            ),
            tripped=not budget_ok,
        )
    environ = {ENV_LIVE_FLAG: "1"} if env_flag else {}
    kill_path = tmp_path / "KILL"
    if not kill_absent:
        kill_path.touch()

    decision = resolve_stage2_arming(
        config=config,
        authorization_path=auth_path,
        canary_state_path=tmp_path / "stage2_canary_state.json",
        kill_switch=KillSwitch(kill_path),
        environ=environ,
        today=DAY,
    )
    # Gate 2 folds in allowlist consistency; gate 5 (envelope) requires a
    # schema-valid authorization to even be evaluable, so it fails closed
    # whenever the file is absent.
    expected_gates = {
        GATE_CONFIG_MODE_LIVE: config_live,
        GATE_AUTHORIZATION_FILE: auth_file and allowlist_ok,
        GATE_ENV_LIVE_FLAG: env_flag,
        GATE_KILL_SWITCH_ABSENT: kill_absent,
        GATE_CANARY_ENVELOPE: auth_file and budget_ok and sessions_ok,
    }
    should_arm = all(expected_gates.values())
    assert decision.armed is should_arm
    assert decision.mode_effective == (MODE_LIVE if should_arm else MODE_SHADOW)
    assert decision.gates == expected_gates
    # A refused live request is DOWNGRADED (counted); shadow-mode configs are
    # not "downgraded", they simply never asked.
    assert decision.downgraded is (config_live and not should_arm)
    if not should_arm:
        assert decision.reasons  # every failed gate is explained
    if should_arm:
        assert decision.envelope is not None
        assert decision.envelope["sessions_used"] == 0
        assert decision.envelope["loss_budget_tripped"] is False


# ─────────────────── authorization-file schema rejections ───────────────────
def test_valid_authorization_loads(tmp_path):
    path = write_authorization(tmp_path)
    auth = load_stage2_authorization(path, today=DAY)
    assert auth.authorized_by == "renhao"
    assert auth.daily_entry_notional_cap == 500.0
    assert auth.shadow_sessions_clean == MIN_SHADOW_SESSIONS_CLEAN
    assert auth.entry_order_type == "limit"  # A5.2 default: marketable-limit
    assert auth.exit_order_type == "market"
    assert auth.canary_allowlist == tuple(sorted(ALLOWLIST))
    assert auth.max_cumulative_loss_usd == 150.0
    assert auth.max_live_sessions == MAX_CANARY_LIVE_SESSIONS  # §9.3a default
    assert auth.content_sha256 == hash_jsonable(valid_authorization_payload())
    record = auth.to_manifest_record()
    assert record["canary_allowlist"] == sorted(ALLOWLIST)


def test_authorization_allowlist_is_normalized(tmp_path):
    path = write_authorization(
        tmp_path,
        valid_authorization_payload(
            canary_allowlist=["nvda", "NVDA", " msft "], max_live_sessions=3
        ),
    )
    auth = load_stage2_authorization(path, today=DAY)
    assert auth.canary_allowlist == ("MSFT", "NVDA")  # upper, dedup, sorted
    assert auth.max_live_sessions == 3


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
        # ── campaign A4 (audit #296 OR-3): the §9.3a envelope fields. ──
        # null is NOT an unrestricted-canary acknowledgment — no such mode
        # exists in §9.3a/§10, so it fails closed like absence does.
        ({"canary_allowlist": None}, "null is not accepted"),
        ({"canary_allowlist": []}, "must not be empty"),
        ({"canary_allowlist": "AAPL"}, "must be a non-empty list"),
        ({"canary_allowlist": ["not a symbol!"]}, "not a plausible symbol"),
        ({"canary_allowlist": [""]}, "not a plausible symbol"),
        ({"max_cumulative_loss_usd": 0}, "positive finite USD"),
        ({"max_cumulative_loss_usd": -150}, "positive finite USD"),
        ({"max_cumulative_loss_usd": "large"}, "must be a number"),
        ({"max_live_sessions": 0}, "outside"),
        ({"max_live_sessions": MAX_CANARY_LIVE_SESSIONS + 1}, "outside"),
        ({"max_live_sessions": 2.5}, "must be an integer"),
        ({"max_live_sessions": True}, "must be an integer"),
    ],
)
def test_authorization_schema_rejections(tmp_path, mutation, match):
    path = write_authorization(tmp_path, valid_authorization_payload(**mutation))
    with pytest.raises(Stage2AuthorizationError, match=match):
        load_stage2_authorization(path, today=DAY)


@pytest.mark.parametrize(
    "missing_key,match",
    [
        # ABSENT fails closed too: §10 "canary allowlist required" — there is
        # no no-restriction default to fall back to (audit #296 OR-3).
        ("canary_allowlist", "canary_allowlist is required"),
        ("max_cumulative_loss_usd", "max_cumulative_loss_usd is required"),
    ],
)
def test_authorization_envelope_fields_are_required(tmp_path, missing_key, match):
    payload = valid_authorization_payload()
    del payload[missing_key]
    path = write_authorization(tmp_path, payload)
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
    rows = read_broker_actions(tmp_path)
    assert [r["phase"] for r in rows] == ["write_ahead", "outcome"]
    assert rows[0]["order_type"] == "limit"
    assert rows[0]["time_in_force"] == "day"
    assert rows[1]["status"] == "accepted"
    # The §9.3a envelope (session counter) is stamped in the same journal.
    stamps = read_envelope_stamps(tmp_path)
    assert [s["phase"] for s in stamps] == ["session_begin"]
    assert stamps[0]["envelope"]["sessions_used"] == 1


def test_broker_error_outcome_is_journaled_and_child_rejected(tmp_path):
    port = FakeBrokerPort()
    port.fail_next_submits = 1
    executor = make_executor(tmp_path, port)
    result = executor.process_tick(
        {"intents": [make_intent("AAA", "BUY", 2, 100.0)]}, now=NOW
    )
    assert result["submitted"][0]["status"] == "error"
    rows = read_broker_actions(tmp_path)
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
        authorization=make_authorization(max_cumulative_loss_usd=10_000.0),
        canary_state_path=tmp_path / "stage2_canary_state.json",
        notify=lambda title, body: None,
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
        authorization=make_authorization(max_cumulative_loss_usd=10_000.0),
        canary_state_path=tmp_path / "stage2_canary_state.json",
        notify=lambda title, body: None,
    )
    report = restored.begin_session()
    assert report["reconcile_clean"] is False
    assert report["entries_halted"] is True


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


# ───────────── §9.3a canary allowlist enforcement (campaign A4) ─────────────
def test_allowlist_blocks_non_allowlisted_entries_never_exits(tmp_path):
    port = FakeBrokerPort()
    executor = make_executor(tmp_path, port)
    result = executor.process_tick(
        {
            "intents": [
                make_intent("AAA", "BUY", 1, 100.0),  # allowlisted → submits
                make_intent("ZZZ", "BUY", 1, 100.0),  # NOT allowlisted → skip
                make_intent("YYY", "SELL", 2, 50.0),  # exit: NEVER allowlisted-gated
            ]
        },
        now=NOW,
    )
    submitted = {(s["symbol"], s["side"]) for s in result["submitted"]}
    assert submitted == {("AAA", "BUY"), ("YYY", "SELL")}
    (skip,) = result["skipped"]
    assert skip["symbol"] == "ZZZ"
    assert skip["reasons"] == [REASON_NOT_ALLOWLISTED]
    assert "canary allowlist" in skip["detail"]
    # Counted + journaled; the broker NEVER saw the non-allowlisted intent.
    assert result["canary"]["allowlist_skips"] == 1
    assert result["canary"]["allowlist"] == sorted(ALLOWLIST)
    assert {(c["symbol"], c["side"]) for c in port.submit_calls} == submitted


def test_allowlist_hard_assert_binds_buys_only():
    with pytest.raises(Stage2ContractError, match="allowlist breach"):
        assert_canary_allowlist("ZZZ", side="BUY", allowlist=("AAA", "BBB"))
    assert_canary_allowlist("AAA", side="BUY", allowlist=("AAA", "BBB"))
    # Exits are exempt (§10 exits-always-allowed).
    assert_canary_allowlist("ZZZ", side="SELL", allowlist=("AAA", "BBB"))


def test_config_allowlist_consistency_is_gate_2(tmp_path):
    """When the pinned config ALSO declares an allowlist, the authorization's
    must be a subset — a superset config passes, a disagreement fails gate 2."""
    auth_path = write_authorization(
        tmp_path, valid_authorization_payload(canary_allowlist=["AAA", "BBB"])
    )

    def arm(config_allowlist):
        return resolve_stage2_arming(
            config=IntradayDecisioningConfig(
                enabled=True, mode=MODE_LIVE, canary_allowlist=config_allowlist
            ),
            authorization_path=auth_path,
            canary_state_path=tmp_path / "stage2_canary_state.json",
            kill_switch=KillSwitch(tmp_path / "KILL"),
            environ={ENV_LIVE_FLAG: "1"},
            today=DAY,
        )

    assert arm(()).armed is True  # config silent → the authorization binds
    assert arm(("AAA", "BBB")).armed is True  # equal
    assert arm(("AAA", "BBB", "CCC")).armed is True  # config superset
    for bad in (("ZZZ",), ("AAA",)):  # disjoint / authorization wider
        decision = arm(bad)
        assert decision.armed is False
        assert decision.gates[GATE_AUTHORIZATION_FILE] is False
        assert any("allowlist disagrees" in r for r in decision.reasons)


# ───────────── §9.3a cumulative loss budget (campaign A4) ─────────────
def test_loss_budget_trips_on_realized_loss_halts_entries_exits_flow(tmp_path):
    port = FakeBrokerPort()
    notifications: list = []
    executor = make_executor(
        tmp_path, port, cap=500.0, max_loss=100.0, notifications=notifications
    )
    # Tick 1: enter AAA 4 × $100; broker fills at $100.
    executor.process_tick({"intents": [make_intent("AAA", "BUY", 4, 100.0)]}, now=NOW)
    port.fill(pid("AAA", "BUY") + ":1", 4.0)
    # Tick 2: the fill lands (position 4 @ 100); exit intent at $60 marks the
    # position down → MTM -160 breaches the $100 budget AFTER the exit was
    # submitted (exits are never gated on the budget).
    r2 = executor.process_tick(
        {"intents": [make_intent("AAA", "SELL", 4, 60.0)]},
        now=NOW + timedelta(minutes=5),
    )
    assert [s["side"] for s in r2["submitted"]] == ["SELL"]
    assert r2["canary"]["loss_budget"]["tripped"] is True
    assert r2["canary"]["loss_budget"]["newly_tripped"] is True
    assert r2["entries_halted"] is True
    assert r2["halt_reason"] == HALT_REASON_LOSS_BUDGET
    # CRITICAL notification fired exactly once, and the trip is journaled.
    assert len(notifications) == 1
    assert "loss budget tripped" in notifications[0][0]
    assert [s["phase"] for s in read_envelope_stamps(tmp_path)] == [
        "session_begin",
        "loss_budget_trip",
    ]
    # Tick 3: the sell filled at $60 → realized -160; entries stay halted,
    # exits still flow (§10), and no SECOND notification fires (sticky).
    port.fill(pid("AAA", "SELL") + ":1", 4.0)
    r3 = executor.process_tick(
        {
            "intents": [
                make_intent("BBB", "BUY", 1, 50.0),
                make_intent("CCC", "SELL", 1, 30.0),
            ]
        },
        now=NOW + timedelta(minutes=10),
    )
    assert [s["reasons"] for s in r3["skipped"]] == [[REASON_ENTRIES_HALTED]]
    assert [s["side"] for s in r3["submitted"]] == ["SELL"]
    assert r3["canary"]["loss_budget"]["realized_pnl_usd"] == pytest.approx(-160.0)
    assert r3["canary"]["loss_budget"]["newly_tripped"] is False
    assert len(notifications) == 1
    # Persisted state carries the trip.
    state = json.loads(
        (tmp_path / "stage2_canary_state.json").read_text(encoding="utf-8")
    )
    assert state["loss_budget_tripped"] is True
    assert state["realized_pnl_usd"] == pytest.approx(-160.0)


def test_loss_budget_trips_on_mark_to_market_alone(tmp_path):
    port = FakeBrokerPort()
    executor = make_executor(tmp_path, port, max_loss=100.0)
    executor.process_tick({"intents": [make_intent("AAA", "BUY", 2, 100.0)]}, now=NOW)
    port.fill(pid("AAA", "BUY") + ":1", 2.0)
    # No exit, no realized loss — a marks-only tick breaches on MTM.
    result = executor.process_tick(
        {"intents": [], "marks": {"AAA": 30.0}}, now=NOW + timedelta(minutes=5)
    )
    budget = result["canary"]["loss_budget"]
    assert budget["unrealized_pnl_usd"] == pytest.approx(-140.0)
    assert budget["tripped"] is True
    assert result["halt_reason"] == HALT_REASON_LOSS_BUDGET


def test_exits_of_pre_canary_positions_are_not_attributed(tmp_path):
    port = FakeBrokerPort()
    executor = make_executor(tmp_path, port, max_loss=100.0)
    # A SELL of a position Stage 2 never originated: flows, but its fill is
    # NOT canary P&L (it belongs to the batch book).
    executor.process_tick({"intents": [make_intent("EEE", "SELL", 2, 50.0)]}, now=NOW)
    port.fill(pid("EEE", "SELL") + ":1", 2.0)
    result = executor.process_tick({"intents": []}, now=NOW + timedelta(minutes=5))
    budget = result["canary"]["loss_budget"]
    assert budget["realized_pnl_usd"] == pytest.approx(0.0)
    assert budget["tripped"] is False


def test_broker_fill_price_preferred_over_limit_price(tmp_path):
    port = FakeBrokerPort()
    executor = make_executor(tmp_path, port)
    executor.process_tick({"intents": [make_intent("AAA", "BUY", 2, 100.0)]}, now=NOW)
    port.fill(pid("AAA", "BUY") + ":1", 2.0, price=99.5)  # broker-reported avg
    executor.process_tick({"intents": []}, now=NOW + timedelta(minutes=5))
    assert executor.canary.positions["AAA"]["cost_basis"] == pytest.approx(99.5)


def test_budget_trip_is_sticky_across_sessions_and_refuses_arming(tmp_path):
    port = FakeBrokerPort()
    executor = make_executor(tmp_path, port, max_loss=100.0)
    executor.process_tick({"intents": [make_intent("AAA", "BUY", 2, 100.0)]}, now=NOW)
    port.fill(pid("AAA", "BUY") + ":1", 2.0)
    executor.process_tick(
        {"intents": [], "marks": {"AAA": 10.0}}, now=NOW + timedelta(minutes=5)
    )
    assert executor.canary.loss_budget_tripped is True

    # A NEW session (new executor, fresh book path) under the SAME
    # authorization: the trip is restored from the persisted envelope and
    # entries halt from begin_session on; exits still flow.
    port2 = FakeBrokerPort()
    next_day = "2026-07-07"
    executor2 = LiveTickExecutor(
        account=ACCOUNT,
        trading_day=next_day,
        port=port2,
        action_log=LiveActionLog(tmp_path / "actions.jsonl"),
        book_path=tmp_path / "order_state_book_2.json",
        authorization=make_authorization(max_cumulative_loss_usd=100.0),
        canary_state_path=tmp_path / "stage2_canary_state.json",
        notify=lambda title, body: None,
    )
    report = executor2.begin_session()
    assert report["entries_halted"] is True
    assert report["halt_reason"] == HALT_REASON_LOSS_BUDGET
    assert report["canary_envelope"]["loss_budget_tripped"] is True
    assert report["canary_envelope"]["sessions_used"] == 2  # both days counted
    def next_day_intent(symbol, side, qty, price):
        # A different trading day ⇒ a different lockstep id; leave it blank
        # and let the book derive it (the lockstep guard has its own test).
        return {
            **make_intent(symbol, side, qty, price),
            "trading_day": next_day,
            "parent_intent_id": "",
        }

    result = executor2.process_tick(
        {
            "intents": [
                next_day_intent("BBB", "BUY", 1, 50.0),
                next_day_intent("CCC", "SELL", 1, 30.0),
            ]
        },
        now=NOW + timedelta(days=1),
    )
    assert [s["reasons"] for s in result["skipped"]] == [[REASON_ENTRIES_HALTED]]
    assert [s["side"] for s in result["submitted"]] == ["SELL"]

    # And the arming gate refuses the envelope until re-authorization.
    auth_path = write_authorization(
        tmp_path, valid_authorization_payload(max_cumulative_loss_usd=100.0)
    )
    decision = resolve_stage2_arming(
        config=IntradayDecisioningConfig(enabled=True, mode=MODE_LIVE),
        authorization_path=auth_path,
        canary_state_path=tmp_path / "stage2_canary_state.json",
        kill_switch=KillSwitch(tmp_path / "KILL"),
        environ={ENV_LIVE_FLAG: "1"},
        today=DAY,
    )
    assert decision.armed is False
    assert decision.gates[GATE_CANARY_ENVELOPE] is False
    assert any("loss budget" in r for r in decision.reasons)


# ───────────── §9.3a session counter + ceiling (campaign A4) ─────────────
def test_session_counter_is_idempotent_per_date(tmp_path):
    executor = make_executor(tmp_path)
    assert executor.canary.sessions_used == 1
    # A same-day restart does NOT consume a second envelope slot.
    restart = make_executor(tmp_path)
    assert restart.canary.sessions_used == 1
    assert restart.begin_session()["canary_envelope"]["sessions_used"] == 1


def test_session_ceiling_refuses_arming_and_begin_session(tmp_path):
    auth_payload = valid_authorization_payload(max_live_sessions=2)
    auth_path = write_authorization(tmp_path, auth_payload)
    auth_sha = hash_jsonable(auth_payload)
    write_canary_state(
        tmp_path, auth_sha, sessions=["2026-07-01", "2026-07-02"]
    )
    decision = resolve_stage2_arming(
        config=IntradayDecisioningConfig(enabled=True, mode=MODE_LIVE),
        authorization_path=auth_path,
        canary_state_path=tmp_path / "stage2_canary_state.json",
        kill_switch=KillSwitch(tmp_path / "KILL"),
        environ={ENV_LIVE_FLAG: "1"},
        today=DAY,
    )
    assert decision.armed is False
    assert decision.gates[GATE_CANARY_ENVELOPE] is False
    assert any("re-authorization required" in r for r in decision.reasons)
    # Defense in depth: even a directly-constructed executor refuses a NEW
    # session beyond the ceiling… (the envelope is keyed to the authorization
    # CONTENT hash, so the executor must carry the exact same payload).
    same_auth = {"max_live_sessions": 2, "max_cumulative_loss_usd": 150.0}
    with pytest.raises(Stage2ContractError, match="session ceiling"):
        make_executor(tmp_path, auth_overrides=same_auth)
    # …but a RESTART of an already-counted session is not a new session.
    write_canary_state(tmp_path, auth_sha, sessions=["2026-07-01", DAY])
    restart = make_executor(tmp_path, auth_overrides=same_auth)
    assert restart.canary.sessions_used == 2


def test_one_below_ceiling_still_arms(tmp_path):
    auth_payload = valid_authorization_payload()
    auth_path = write_authorization(tmp_path, auth_payload)
    write_canary_state(
        tmp_path,
        hash_jsonable(auth_payload),
        sessions=[f"2026-06-{d:02d}" for d in range(1, MAX_CANARY_LIVE_SESSIONS)],
    )
    decision = resolve_stage2_arming(
        config=IntradayDecisioningConfig(enabled=True, mode=MODE_LIVE),
        authorization_path=auth_path,
        canary_state_path=tmp_path / "stage2_canary_state.json",
        kill_switch=KillSwitch(tmp_path / "KILL"),
        environ={ENV_LIVE_FLAG: "1"},
        today=DAY,
    )
    assert decision.armed is True
    assert decision.envelope["sessions_used"] == MAX_CANARY_LIVE_SESSIONS - 1
    assert decision.envelope["sessions_remaining"] == 1


# ───────────── envelope persistence + identity (campaign A4) ─────────────
def test_new_authorization_starts_fresh_envelope_and_archives_old(tmp_path):
    port = FakeBrokerPort()
    executor = make_executor(tmp_path, port, max_loss=100.0)
    executor.process_tick({"intents": [make_intent("AAA", "BUY", 2, 100.0)]}, now=NOW)
    port.fill(pid("AAA", "BUY") + ":1", 2.0)
    executor.process_tick(
        {"intents": [], "marks": {"AAA": 10.0}}, now=NOW + timedelta(minutes=5)
    )
    old_sha = executor.authorization.content_sha256
    assert executor.canary.loss_budget_tripped is True

    # A NEW recorded §9.3a decision (different content) ⇒ fresh envelope;
    # the exhausted one is archived, not clobbered.
    new_auth = make_authorization(max_cumulative_loss_usd=200.0)
    assert new_auth.content_sha256 != old_sha
    tracker = CanaryEnvelopeTracker(
        tmp_path / "stage2_canary_state.json", authorization=new_auth
    )
    assert tracker.loss_budget_tripped is False
    assert tracker.sessions_used == 0
    assert len(tracker.previous_envelopes) == 1
    archived = tracker.previous_envelopes[0]
    assert archived["authorization_sha256"] == old_sha
    assert archived["loss_budget_tripped"] is True
    # read_canary_envelope agrees (the arming view).
    envelope = read_canary_envelope(
        tmp_path / "stage2_canary_state.json", authorization=new_auth
    )
    assert envelope["loss_budget_tripped"] is False
    assert envelope["sessions_used"] == 0


def test_corrupt_canary_state_fails_closed(tmp_path):
    state_path = tmp_path / "stage2_canary_state.json"
    state_path.write_text("{not json", encoding="utf-8")
    # The executor refuses to construct (never silently reset a loss ledger)…
    with pytest.raises(Stage2ContractError, match="refusing to silently reset"):
        make_executor(tmp_path, begin=False)
    # …and the arming gate fails the envelope gate rather than raising.
    auth_path = write_authorization(tmp_path)
    decision = resolve_stage2_arming(
        config=IntradayDecisioningConfig(enabled=True, mode=MODE_LIVE),
        authorization_path=auth_path,
        canary_state_path=state_path,
        kill_switch=KillSwitch(tmp_path / "KILL"),
        environ={ENV_LIVE_FLAG: "1"},
        today=DAY,
    )
    assert decision.armed is False
    assert decision.gates[GATE_CANARY_ENVELOPE] is False
    assert any("refusing to silently reset" in r for r in decision.reasons)


def test_arm_decision_manifest_record_carries_envelope_and_allowlist(tmp_path):
    auth_path = write_authorization(tmp_path)
    decision = resolve_stage2_arming(
        config=IntradayDecisioningConfig(enabled=True, mode=MODE_LIVE),
        authorization_path=auth_path,
        canary_state_path=tmp_path / "stage2_canary_state.json",
        kill_switch=KillSwitch(tmp_path / "KILL"),
        environ={ENV_LIVE_FLAG: "1"},
        today=DAY,
    )
    record = decision.to_manifest_record()
    assert record["armed"] is True
    assert record["gates"][GATE_CANARY_ENVELOPE] is True
    assert record["authorization"]["canary_allowlist"] == sorted(ALLOWLIST)
    assert record["authorization"]["max_cumulative_loss_usd"] == 150.0
    assert record["authorization"]["max_live_sessions"] == MAX_CANARY_LIVE_SESSIONS
    assert record["envelope"]["sessions_used"] == 0
    assert record["envelope"]["max_live_sessions"] == MAX_CANARY_LIVE_SESSIONS
    assert record["envelope"]["loss_budget_tripped"] is False
