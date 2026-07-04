"""Tests for the entry-timing policy module (sprint D2): the pure decision
matrix on synthetic tick fixtures (gap-up reverting / gap-up running /
gap-down / no-gap), hard-deadline degradation, counterfactual cost
correctness (hand-computed), schema round-trip + idempotency, flag-absent ⇒
baseline, the comparison-report CLI, and the scheduler tick-observer seam
(shadow-only, observer errors never halt the session)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from renquant_orchestrator.entry_timing_policy import (
    ACTION_SUBMIT_NOW,
    ACTION_WAIT,
    EVALUATED_POLICIES,
    POLICY_BASELINE,
    POLICY_DELAY_FIXED,
    POLICY_REVERSION,
    POLICY_VWAP_CHASE,
    REASON_BASELINE,
    REASON_DEADLINE,
    REASON_DELAY_ELAPSED,
    REASON_GAP_DOWN,
    REASON_MISSING_REF,
    REASON_NO_GAP,
    REASON_NON_BUY,
    REASON_RETRACE_HIT,
    REASON_WAITING_DELAY,
    REASON_WAITING_RETRACE,
    REASON_WINDOW_NOT_OPEN,
    SCHEMA_VERSION,
    EntryIntent,
    EntryTimingPolicyConfig,
    QuoteContext,
    SessionClock,
    ShadowEntryTimingEvaluator,
    decide,
    load_entry_timing_config,
    load_policy_rows,
    main as policy_main,
    summarize_policy_rows,
)

ET = ZoneInfo("America/New_York")
DAY = "2026-07-06"  # a Monday


def at(hh: int, mm: int, ss: int = 0) -> datetime:
    return datetime(2026, 7, 6, hh, mm, ss, tzinfo=ET)


def make_clock(tick_seconds: float = 720.0) -> SessionClock:
    return SessionClock(
        open=at(9, 30),
        first_eligible=at(9, 35),
        entry_cutoff=at(15, 30),
        close=at(16, 0),
        tick_seconds=tick_seconds,
    )


def windows_record() -> dict:
    return {
        "open": at(9, 30).isoformat(),
        "first_eligible_tick": at(9, 35).isoformat(),
        "entry_cutoff": at(15, 30).isoformat(),
        "close": at(16, 0).isoformat(),
    }


def buy_intent(arrival: datetime, *, prior_close: float | None = 100.0) -> EntryIntent:
    return EntryIntent(
        ticker="AAA",
        trading_day=DAY,
        arrival_time=arrival,
        side="buy",
        parent_intent_id=f"pi-AAA-BUY-{DAY}",
        signal_version="sv1",
        prior_close=prior_close,
    )


CONFIG = EntryTimingPolicyConfig()  # defaults: delay 30, retrace 0.5, min gap 10bps


# ─────────────────────── pure decision matrix ───────────────────────
def test_baseline_submits_at_first_eligible_tick():
    d = decide(
        POLICY_BASELINE,
        intent=buy_intent(at(9, 42)),
        clock=make_clock(),
        quote=QuoteContext(now=at(9, 42), mid=102.0, open_print=102.0),
        config=CONFIG,
    )
    assert d.action == ACTION_SUBMIT_NOW
    assert d.reason == REASON_BASELINE
    assert d.degraded is False


def test_all_policies_wait_before_window():
    for policy in EVALUATED_POLICIES:
        d = decide(
            policy,
            intent=buy_intent(at(9, 42)),
            clock=make_clock(),
            quote=QuoteContext(now=at(9, 33), mid=102.0, open_print=102.0),
            config=CONFIG,
        )
        assert d.action == ACTION_WAIT
        assert d.reason == REASON_WINDOW_NOT_OPEN


def test_delay_fixed_waits_then_submits():
    clock = make_clock()
    intent = buy_intent(at(9, 42))
    early = decide(
        POLICY_DELAY_FIXED,
        intent=intent,
        clock=clock,
        quote=QuoteContext(now=at(9, 42), mid=102.0, open_print=102.0),
        config=CONFIG,
    )
    assert early.action == ACTION_WAIT
    assert early.reason == REASON_WAITING_DELAY
    late = decide(
        POLICY_DELAY_FIXED,
        intent=intent,
        clock=clock,
        quote=QuoteContext(now=at(10, 6), mid=101.0, open_print=102.0),
        config=CONFIG,
    )
    assert late.action == ACTION_SUBMIT_NOW
    assert late.reason == REASON_DELAY_ELAPSED


def test_reversion_gap_up_triggers_on_retrace():
    """prior 100, open print 102 (gap +200bps), retrace_frac 0.5 => trigger 101."""
    clock = make_clock()
    intent = buy_intent(at(9, 42), prior_close=100.0)
    waiting = decide(
        POLICY_REVERSION,
        intent=intent,
        clock=clock,
        quote=QuoteContext(now=at(9, 54), mid=101.5, open_print=102.0),
        config=CONFIG,
    )
    assert waiting.action == ACTION_WAIT
    assert waiting.reason == REASON_WAITING_RETRACE
    assert waiting.trigger_price == pytest.approx(101.0)
    assert waiting.gap_bps == pytest.approx(200.0)
    hit = decide(
        POLICY_REVERSION,
        intent=intent,
        clock=clock,
        quote=QuoteContext(now=at(10, 6), mid=100.9, open_print=102.0),
        config=CONFIG,
    )
    assert hit.action == ACTION_SUBMIT_NOW
    assert hit.reason == REASON_RETRACE_HIT
    assert hit.trigger_price == pytest.approx(101.0)


def test_reversion_gap_down_submits_now():
    d = decide(
        POLICY_REVERSION,
        intent=buy_intent(at(9, 42), prior_close=100.0),
        clock=make_clock(),
        quote=QuoteContext(now=at(9, 42), mid=98.0, open_print=98.0),
        config=CONFIG,
    )
    assert d.action == ACTION_SUBMIT_NOW
    assert d.reason == REASON_GAP_DOWN
    assert d.degraded is False
    assert d.gap_bps == pytest.approx(-200.0)


def test_reversion_no_gap_submits_now():
    d = decide(
        POLICY_REVERSION,
        intent=buy_intent(at(9, 42), prior_close=100.0),
        clock=make_clock(),
        quote=QuoteContext(now=at(9, 42), mid=100.05, open_print=100.05),
        config=CONFIG,
    )
    assert d.action == ACTION_SUBMIT_NOW
    assert d.reason == REASON_NO_GAP  # |5bps| < min_gap_bps=10


def test_reversion_missing_reference_degrades_to_submit():
    d = decide(
        POLICY_REVERSION,
        intent=buy_intent(at(9, 42), prior_close=None),
        clock=make_clock(),
        quote=QuoteContext(now=at(9, 42), mid=102.0, open_print=102.0),
        config=CONFIG,
    )
    assert d.action == ACTION_SUBMIT_NOW
    assert d.reason == REASON_MISSING_REF
    assert d.degraded is True  # never guesses a gap; fails toward participation


def test_hard_deadline_degrades_to_submit_now():
    """Gap-up never retraces: the policy degrades on the LAST tick that can
    still act before the deadline (now + tick_seconds > deadline)."""
    clock = make_clock(tick_seconds=720.0)  # deadline = cutoff = 15:30
    intent = buy_intent(at(9, 42), prior_close=100.0)
    running = QuoteContext(now=at(15, 0), mid=103.0, open_print=102.0)
    d = decide(POLICY_REVERSION, intent=intent, clock=clock, quote=running, config=CONFIG)
    assert d.action == ACTION_WAIT  # 15:00 + 12min = 15:12 <= 15:30

    last_chance = QuoteContext(now=at(15, 20), mid=103.5, open_print=102.0)
    d = decide(POLICY_REVERSION, intent=intent, clock=clock, quote=last_chance, config=CONFIG)
    assert d.action == ACTION_SUBMIT_NOW  # 15:20 + 12min = 15:32 > 15:30
    assert d.degraded is True
    assert d.reason == REASON_DEADLINE
    assert d.deadline == at(15, 30)


def test_deadline_applies_to_delay_fixed_too():
    config = EntryTimingPolicyConfig(delay_minutes=600.0)  # target past the cutoff
    d = decide(
        POLICY_DELAY_FIXED,
        intent=buy_intent(at(9, 42)),
        clock=make_clock(),
        quote=QuoteContext(now=at(15, 25), mid=102.0, open_print=102.0),
        config=config,
    )
    assert d.action == ACTION_SUBMIT_NOW
    assert d.degraded is True
    assert d.reason == REASON_DEADLINE


def test_non_buy_never_delayed():
    intent = EntryIntent(
        ticker="AAA", trading_day=DAY, arrival_time=at(9, 42), side="sell"
    )
    for policy in EVALUATED_POLICIES:
        d = decide(
            policy,
            intent=intent,
            clock=make_clock(),
            quote=QuoteContext(now=at(9, 42), mid=102.0),
            config=CONFIG,
        )
        assert d.action == ACTION_SUBMIT_NOW
        assert d.reason == REASON_NON_BUY


def test_vwap_chase_is_out_of_scope():
    with pytest.raises(ValueError, match="out of scope"):
        decide(
            POLICY_VWAP_CHASE,
            intent=buy_intent(at(9, 42)),
            clock=make_clock(),
            quote=QuoteContext(now=at(9, 42), mid=102.0, open_print=102.0),
            config=CONFIG,
        )


# ─────────────────────── config: absent ⇒ baseline ───────────────────────
def test_config_absent_is_baseline():
    for cfg in ({}, {"intraday_decisioning": {}}, {"intraday_decisioning": {"enabled": True}}):
        loaded = load_entry_timing_config(cfg)
        assert loaded.policy == POLICY_BASELINE
        assert loaded.config_errors == ()
        assert loaded.delay_minutes == 30.0
        assert loaded.retrace_frac == 0.5


def test_config_reads_entry_timing_keys():
    loaded = load_entry_timing_config(
        {
            "intraday_decisioning": {
                "entry_timing": {
                    "policy": "gap_reversion_trigger",
                    "delay_minutes": 45,
                    "retrace_frac": 0.35,
                    "min_gap_bps": 20,
                }
            }
        }
    )
    assert loaded.policy == POLICY_REVERSION
    assert loaded.delay_minutes == 45.0
    assert loaded.retrace_frac == 0.35
    assert loaded.min_gap_bps == 20.0
    assert loaded.config_errors == ()


def test_config_malformed_falls_back_to_baseline():
    loaded = load_entry_timing_config(
        {
            "intraday_decisioning": {
                "entry_timing": {"policy": "delay_fixed", "delay_minutes": "abc"}
            }
        }
    )
    assert loaded.config_errors  # collected, not silently defaulted
    assert loaded.policy == POLICY_BASELINE  # any error => fail-safe to control
    assert loaded.delay_minutes == 30.0


def test_config_selecting_vwap_chase_is_an_error():
    loaded = load_entry_timing_config(
        {"intraday_decisioning": {"entry_timing": {"policy": "vwap_chase"}}}
    )
    assert loaded.policy == POLICY_BASELINE
    assert any("OUT OF SCOPE" in e for e in loaded.config_errors)


def test_config_retrace_frac_out_of_range_rejected():
    loaded = load_entry_timing_config(
        {"intraday_decisioning": {"entry_timing": {"retrace_frac": 1.5}}}
    )
    assert loaded.retrace_frac == 0.5
    assert loaded.config_errors


# ─────────────────────── shadow evaluation fixtures ───────────────────────
def tick_record(
    idx: int,
    when: datetime,
    prices: dict[str, float],
    intents: list[dict] | None = None,
    *,
    windows: dict | None = None,
    day: str = DAY,
) -> dict:
    return {
        "schema_version": "rq105-intraday-shadow-v1",
        "kind": "intraday_decision_shadow_tick",
        "session_date": day,
        "tick_index": idx,
        "tick_at": when.isoformat(),
        "mode": "shadow",
        "window_phase": "entries_open",
        "windows": windows_record() if windows is None else windows,
        "inputs": {"live_state": {"prices": dict(prices)}},
        "decisions": {
            "intents": list(intents or ()),
            "skipped": [],
            "blocked_by": {},
            "counters": {},
        },
    }


def entry_intent_payload(symbol: str = "AAA") -> dict:
    return {
        "parent_intent_id": f"pi-{symbol}-BUY-{DAY}",
        "symbol": symbol,
        "side": "BUY",
        "kind": "entry",
        "signal_version": "sv1",
    }


def gap_up_reverting_ticks() -> list[dict]:
    """Arrival at 102.0 (gap-up vs prior close 100), retraces through the
    101.0 trigger at 10:06."""
    return [
        tick_record(0, at(9, 42), {"AAA": 102.0}, [entry_intent_payload()]),
        tick_record(1, at(9, 54), {"AAA": 101.5}),
        tick_record(2, at(10, 6), {"AAA": 100.9}),
        tick_record(3, at(10, 18), {"AAA": 101.2}),
    ]


def test_evaluator_gap_up_reverting(tmp_path: Path):
    log = tmp_path / "policy.jsonl"
    ev = ShadowEntryTimingEvaluator(
        config=CONFIG, log_path=log, prior_close_refs={"AAA": 100.0}
    )
    for rec in gap_up_reverting_ticks():
        ev.on_tick(rec)
    ev.flush()
    rows = {r["policy"]: r for r in load_policy_rows(log)}
    assert set(rows) == set(EVALUATED_POLICIES)

    base = rows[POLICY_BASELINE]
    assert base["participated"] is True
    assert base["virtual_entry_mid"] == pytest.approx(102.0)
    assert base["saved_vs_baseline_bps"] == pytest.approx(0.0)
    assert base["degraded"] is False

    rev = rows[POLICY_REVERSION]
    assert rev["reason"] == REASON_RETRACE_HIT
    assert rev["virtual_entry_mid"] == pytest.approx(100.9)
    assert rev["trigger_price"] == pytest.approx(101.0)
    # Counterfactual: (102.0 - 100.9) / 102.0 * 1e4
    assert rev["saved_vs_baseline_bps"] == pytest.approx((102.0 - 100.9) / 102.0 * 1e4)
    assert rev["degraded"] is False

    # delay_fixed (30 min): first tick at/after 10:00 is 10:06 @ 100.9.
    dly = rows[POLICY_DELAY_FIXED]
    assert dly["reason"] == REASON_DELAY_ELAPSED
    assert dly["virtual_entry_mid"] == pytest.approx(100.9)


def test_evaluator_gap_up_running_degrades_at_deadline(tmp_path: Path):
    """Never retraces: reversion must degrade to submit-now at the deadline
    (participation never sacrificed), with the degradation logged."""
    log = tmp_path / "policy.jsonl"
    ev = ShadowEntryTimingEvaluator(
        config=CONFIG, log_path=log, prior_close_refs={"AAA": 100.0}
    )
    ticks = [tick_record(0, at(9, 42), {"AAA": 102.0}, [entry_intent_payload()])]
    when, idx, px = at(9, 54), 1, 102.2
    while when < at(15, 30):
        ticks.append(tick_record(idx, when, {"AAA": px}))
        when, idx, px = when + timedelta(minutes=12), idx + 1, px + 0.1
    for rec in ticks:
        ev.on_tick(rec)
    ev.flush()
    rows = {r["policy"]: r for r in load_policy_rows(log)}
    rev = rows[POLICY_REVERSION]
    assert rev["participated"] is True
    assert rev["degraded"] is True
    assert rev["reason"] == REASON_DEADLINE
    # Degradation fires on the last tick where now + 720s > 15:30.
    assert rev["decided_tick_time"] == at(15, 18).isoformat()
    assert rev["saved_vs_baseline_bps"] < 0  # chased the running gap — recorded honestly


def test_evaluator_gap_down_and_no_gap_match_baseline(tmp_path: Path):
    log = tmp_path / "policy.jsonl"
    ev = ShadowEntryTimingEvaluator(
        config=CONFIG,
        log_path=log,
        prior_close_refs={"DDD": 100.0, "FFF": 100.0},
    )
    intents = [
        {**entry_intent_payload("DDD"), "parent_intent_id": f"pi-DDD-BUY-{DAY}"},
        {**entry_intent_payload("FFF"), "parent_intent_id": f"pi-FFF-BUY-{DAY}"},
    ]
    # DDD gaps down (98.0); FFF opens flat (100.05, 5bps < min_gap_bps).
    ev.on_tick(tick_record(0, at(9, 42), {"DDD": 98.0, "FFF": 100.05}, intents))
    ev.flush()
    rows = {(r["ticker"], r["policy"]): r for r in load_policy_rows(log)}
    assert rows[("DDD", POLICY_REVERSION)]["reason"] == REASON_GAP_DOWN
    assert rows[("DDD", POLICY_REVERSION)]["saved_vs_baseline_bps"] == pytest.approx(0.0)
    assert rows[("FFF", POLICY_REVERSION)]["reason"] == REASON_NO_GAP
    assert rows[("FFF", POLICY_REVERSION)]["saved_vs_baseline_bps"] == pytest.approx(0.0)


def test_counterfactual_cost_hand_computed(tmp_path: Path):
    """Hand-computed: baseline enters at 105.0, reversion at 102.5 =>
    saved = (105 - 102.5) / 105 * 1e4 = 238.095238... bps."""
    log = tmp_path / "policy.jsonl"
    ev = ShadowEntryTimingEvaluator(
        config=CONFIG, log_path=log, prior_close_refs={"AAA": 100.0}
    )
    ev.on_tick(tick_record(0, at(9, 42), {"AAA": 105.0}, [entry_intent_payload()]))
    ev.on_tick(tick_record(1, at(9, 54), {"AAA": 102.5}))  # trigger = 102.5
    ev.flush()
    rows = {r["policy"]: r for r in load_policy_rows(log)}
    saved = rows[POLICY_REVERSION]["saved_vs_baseline_bps"]
    assert saved == pytest.approx(238.0952380952381)


def test_schema_round_trip_and_idempotency(tmp_path: Path):
    log = tmp_path / "policy.jsonl"
    ticks = gap_up_reverting_ticks()
    ev = ShadowEntryTimingEvaluator(
        config=CONFIG, log_path=log, prior_close_refs={"AAA": 100.0}
    )
    for rec in ticks:
        ev.on_tick(rec)
    ev.flush()
    rows = load_policy_rows(log)
    assert len(rows) == len(EVALUATED_POLICIES)
    required = {
        "schema_version",
        "kind",
        "stage",
        "mode",
        "observe_only",
        "places_orders",
        "session_date",
        "ticker",
        "side",
        "parent_intent_id",
        "signal_version",
        "policy",
        "selected_policy",
        "policy_params",
        "config_fingerprint",
        "arrival_tick_time",
        "prior_close_ref",
        "open_print",
        "participated",
        "action",
        "decided_tick_time",
        "virtual_entry_mid",
        "degraded",
        "reason",
        "trigger_price",
        "gap_bps",
        "deadline",
        "baseline_entry_mid",
        "baseline_tick_time",
        "saved_vs_baseline_bps",
        "censored_reason",
    }
    for row in rows:
        assert required <= set(row)
        assert row["schema_version"] == SCHEMA_VERSION
        assert row["mode"] == "shadow"
        assert row["observe_only"] is True
        assert row["places_orders"] is False
        assert row["config_fingerprint"] == CONFIG.fingerprint()
    # Idempotent: a fresh evaluator over the same session appends nothing.
    ev2 = ShadowEntryTimingEvaluator(
        config=CONFIG, log_path=log, prior_close_refs={"AAA": 100.0}
    )
    for rec in ticks:
        ev2.on_tick(rec)
    ev2.flush()
    assert ev2.rows_written == 0
    assert len(load_policy_rows(log)) == len(rows)


def test_flush_censors_unresolved_by_cause(tmp_path: Path):
    """Session halted after the arrival tick: baseline resolved, the waiting
    policies are recorded censored by cause — never imputed, never dropped."""
    log = tmp_path / "policy.jsonl"
    ev = ShadowEntryTimingEvaluator(
        config=CONFIG, log_path=log, prior_close_refs={"AAA": 100.0}
    )
    ev.on_tick(tick_record(0, at(9, 42), {"AAA": 102.0}, [entry_intent_payload()]))
    ev.flush()
    rows = {r["policy"]: r for r in load_policy_rows(log)}
    assert rows[POLICY_BASELINE]["participated"] is True
    for policy in (POLICY_DELAY_FIXED, POLICY_REVERSION):
        assert rows[policy]["participated"] is False
        assert rows[policy]["censored_reason"] == "unresolved_at_flush"
        assert rows[policy]["saved_vs_baseline_bps"] is None


def test_ticks_without_windows_are_counted_not_crashed(tmp_path: Path):
    ev = ShadowEntryTimingEvaluator(config=CONFIG, log_path=tmp_path / "p.jsonl")
    ev.on_tick(
        tick_record(0, at(9, 42), {"AAA": 102.0}, [entry_intent_payload()], windows={})
    )
    assert ev.ticks_without_windows == 1
    assert ev.rows_written == 0


# ─────────────────────── comparison report ───────────────────────
def test_report_summarizes_per_policy(tmp_path: Path):
    log = tmp_path / "policy.jsonl"
    ev = ShadowEntryTimingEvaluator(
        config=CONFIG, log_path=log, prior_close_refs={"AAA": 100.0}
    )
    for rec in gap_up_reverting_ticks():
        ev.on_tick(rec)
    ev.flush()
    summary = summarize_policy_rows(load_policy_rows(log))
    assert summary["n_sessions"] == 1
    assert summary["n_names"] == 1
    rev = summary["per_policy"][POLICY_REVERSION]
    assert rev["participation_rate"] == pytest.approx(1.0)
    assert rev["degradation_count"] == 0
    expected = (102.0 - 100.9) / 102.0 * 1e4
    assert rev["saved_vs_baseline_bps"]["mean"] == pytest.approx(expected)
    assert rev["saved_vs_baseline_bps"]["median"] == pytest.approx(expected)
    base = summary["per_policy"][POLICY_BASELINE]
    assert base["saved_vs_baseline_bps"]["mean"] == pytest.approx(0.0)
    # The report names the pre-registered selection protocol, renders no verdict.
    assert "selection_protocol" in summary


def test_report_cli_json(tmp_path: Path, capsys):
    log = tmp_path / "policy.jsonl"
    ev = ShadowEntryTimingEvaluator(
        config=CONFIG, log_path=log, prior_close_refs={"AAA": 100.0}
    )
    for rec in gap_up_reverting_ticks():
        ev.on_tick(rec)
    ev.flush()
    assert policy_main(["report", "--log", str(log), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["n_rows"] == len(EVALUATED_POLICIES)
    assert POLICY_REVERSION in payload["per_policy"]


def test_report_cli_handles_missing_log(tmp_path: Path, capsys):
    assert policy_main(["report", "--log", str(tmp_path / "absent.jsonl"), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["n_rows"] == 0


def test_replay_cli_backfills_from_shadow_log(tmp_path: Path, capsys):
    shadow_log = tmp_path / "intraday_decisions_shadow.jsonl"
    with shadow_log.open("w", encoding="utf-8") as fh:
        for rec in gap_up_reverting_ticks():
            fh.write(json.dumps(rec) + "\n")
    refs = tmp_path / "prior_close.json"
    refs.write_text(json.dumps({"AAA": 100.0}), encoding="utf-8")
    out = tmp_path / "policy.jsonl"
    assert (
        policy_main(
            [
                "replay",
                "--shadow-log",
                str(shadow_log),
                "--date",
                DAY,
                "--prior-close-refs-json",
                str(refs),
                "--out",
                str(out),
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "shadow-replay"
    assert payload["observe_only"] is True
    assert payload["rows_written"] == len(EVALUATED_POLICIES)
    rows = {r["policy"]: r for r in load_policy_rows(out)}
    assert rows[POLICY_REVERSION]["saved_vs_baseline_bps"] == pytest.approx(
        (102.0 - 100.9) / 102.0 * 1e4
    )


# ─────────────────────── the scheduler tick-observer seam ───────────────────────
from renquant_orchestrator.intraday_quote_logger import SessionBounds  # noqa: E402
from renquant_orchestrator.intraday_session_scheduler import (  # noqa: E402
    ENV_FLAG,
    IntradayDecisioningConfig,
    KillSwitch,
    SessionScheduler,
    ShadowTickWriter,
)


class FakeCalendar:
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


class ManualClock:
    def __init__(self, start: datetime):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now = self.now + timedelta(seconds=seconds)


def one_entry_tick_runner(
    *,
    signal,
    session_start,
    live_state,
    session_counters,
    in_flight_parent_intents,
    exit_orders,
):
    """Emits ONE BUY entry intent for AAA (deduped via in-flight parents)."""
    intents = []
    pid = f"pi-AAA-BUY-{live_state['trading_day']}"
    price = float(live_state.get("prices", {}).get("AAA", 0.0))
    if pid not in set(in_flight_parent_intents) and price > 0:
        intents.append(
            {
                "parent_intent_id": pid,
                "symbol": "AAA",
                "side": "BUY",
                "kind": "entry",
                "quantity": 1.0,
                "price": price,
                "notional": price,
                "trading_day": live_state["trading_day"],
                "signal_version": signal["signal_version"],
            }
        )
    return {
        "enabled": True,
        "reason": "ok",
        "intents": intents,
        "skipped": [],
        "blocked_by": {},
        "counters": dict(session_counters),
    }


def build_scheduler(tmp_path: Path, evaluator_or_observer, price_fn) -> tuple[SessionScheduler, ManualClock]:
    def live_state(*, now: datetime, trading_day: str):
        return {
            "as_of": now.astimezone(ET).isoformat(),
            "trading_day": trading_day,
            "account": "TEST-ACCT",
            "cash": 1000.0,
            "equity": 2000.0,
            "positions": {},
            "prices": {"AAA": price_fn(now)},
            "open_buy_reservations": {},
            "unsettled_buys": 0.0,
            "pending_broker_tickers": [],
        }

    def signal_loader(day: str):
        return {"signal_version": "run:cafe", "as_of": "2026-07-03", "scores": {"AAA": 0.9}}

    scheduler = SessionScheduler(
        config=IntradayDecisioningConfig(enabled=True),
        tick_runner=one_entry_tick_runner,
        signal_loader=signal_loader,
        session_start_provider=lambda day, now: {"session_date": day},
        live_state_provider=live_state,
        writer=ShadowTickWriter(tmp_path / "shadow.jsonl"),
        manifest_path=tmp_path / "manifest.json",
        kill_switch=KillSwitch(tmp_path / "KILL"),
        calendar=FakeCalendar({DAY: ("09:30", "16:00")}),
        environ={ENV_FLAG: "1"},
        tick_observer=evaluator_or_observer,
    )
    clock = ManualClock(at(9, 30))
    return scheduler, clock


def gap_price(now: datetime) -> float:
    """Gap-up at 102 vs prior close 100; retraces below the 101 trigger at 10:05+."""
    if now < at(9, 55):
        return 102.0
    if now < at(10, 5):
        return 101.6
    return 100.8


def test_evaluator_runs_inside_scheduler_tick_loop(tmp_path: Path):
    log = tmp_path / "policy.jsonl"
    evaluator = ShadowEntryTimingEvaluator(
        config=CONFIG, log_path=log, prior_close_refs={"AAA": 100.0}
    )
    scheduler, clock = build_scheduler(tmp_path, evaluator.on_tick, gap_price)
    manifest = scheduler.run_session(now_fn=clock, sleep_fn=clock.sleep, max_cycles=60)
    evaluator.flush()
    assert manifest["status"] == "completed"
    assert "tick_observer_errors" not in manifest  # evaluator never raised
    # Tick records carry the §11b windows stamp the evaluator consumed.
    ticks = [
        json.loads(line)
        for line in (tmp_path / "shadow.jsonl").read_text().splitlines()
        if line.strip()
    ]
    assert all(t.get("windows") for t in ticks)
    rows = {r["policy"]: r for r in load_policy_rows(log)}
    assert set(rows) == set(EVALUATED_POLICIES)
    base = rows[POLICY_BASELINE]
    assert base["virtual_entry_mid"] == pytest.approx(102.0)
    rev = rows[POLICY_REVERSION]
    assert rev["reason"] == REASON_RETRACE_HIT
    assert rev["virtual_entry_mid"] == pytest.approx(100.8)
    assert rev["saved_vs_baseline_bps"] == pytest.approx((102.0 - 100.8) / 102.0 * 1e4)
    # Shadow-only: nothing in the policy log looks like an order.
    for row in rows.values():
        assert row["places_orders"] is False
        assert row["observe_only"] is True


def test_observer_errors_never_halt_the_session(tmp_path: Path):
    def exploding_observer(record):
        raise RuntimeError("diagnostic surface blew up")

    scheduler, clock = build_scheduler(tmp_path, exploding_observer, gap_price)
    manifest = scheduler.run_session(now_fn=clock, sleep_fn=clock.sleep, max_cycles=60)
    assert manifest["status"] == "completed"  # the decision loop survived
    assert manifest["tick_observer_errors"] > 0  # ...and the failure is counted
