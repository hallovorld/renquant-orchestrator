"""Tests for the Stage-1 shadow session scheduler (RFC #208 §8 row 3):
calendar gating (holiday/half-day), the §11b window semantics (entries stop
at close−30min, exits continue to the bell), the default-OFF triple gate
(config + env flag + kill-switch file honored mid-session), the class-A leak
abort, the never-submit runtime assertion, and the launchd package files."""
from __future__ import annotations

import json
import plistlib
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from renquant_artifacts import hash_jsonable

from renquant_orchestrator.intraday_quote_logger import SessionBounds
from renquant_orchestrator.intraday_session_scheduler import (
    DEFAULT_ENTRY_CLOSE_CUTOFF_SECONDS,
    DEFAULT_ENTRY_OPEN_DELAY_SECONDS,
    DEFAULT_TICK_SECONDS,
    ENV_FLAG,
    MODE_SHADOW,
    PHASE_ENTRIES_OPEN,
    PHASE_EXITS_ONLY,
    REASON_ENTRY_WINDOW_CUTOFF,
    IntradayDecisioningConfig,
    KillSwitch,
    PipelineContractUnavailable,
    SessionScheduler,
    SessionWindows,
    ShadowModeViolation,
    ShadowTickWriter,
    apply_entry_window_policy,
    assert_shadow_never_submits,
    bind_pipeline_tick_runner,
    env_flag_enabled,
    load_intraday_config,
    main as scheduler_main,
    resolve_mode,
)

ET = ZoneInfo("America/New_York")
DAY = "2026-07-06"  # a Monday


# ─────────────────────────── fixtures ───────────────────────────
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


def fake_signal(as_of: str = "2026-07-03") -> dict:
    scores = {"AAA": 0.9, "BBB": 0.5, "CCC": -0.2}
    return {
        "signal_version": "run-fri:deadbeef",
        "as_of": as_of,
        "scores": scores,
        "source_run_id": "run-fri",
        "score_content_sha256": hash_jsonable(scores),
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
    """Deterministic, pure stand-in for the slice-2 tick: enters the
    top-scored name not already in flight; passes every exit order through."""
    intents = []
    skipped = []
    counters = {
        "entries_count": int(session_counters.get("entries_count", 0)),
        "deployed_notional": float(session_counters.get("deployed_notional", 0.0)),
        "turnover_notional": float(session_counters.get("turnover_notional", 0.0)),
    }
    in_flight = set(in_flight_parent_intents)
    for order in exit_orders:
        symbol = str(order.get("ticker", "")).upper()
        pid = f"pi-{symbol}-SELL-{live_state['trading_day']}"
        if pid in in_flight:
            skipped.append(
                {
                    "symbol": symbol,
                    "side": "SELL",
                    "parent_intent_id": pid,
                    "reasons": ["duplicate_parent_intent_in_flight"],
                }
            )
            continue
        in_flight.add(pid)
        price = float(live_state.get("prices", {}).get(symbol, 0.0))
        qty = float(order.get("quantity", 1.0))
        notional = qty * price
        counters["turnover_notional"] += notional
        intents.append(
            {
                "parent_intent_id": pid,
                "account": live_state["account"],
                "symbol": symbol,
                "side": "SELL",
                "kind": "exit",
                "quantity": qty,
                "price": price,
                "notional": notional,
                "trading_day": live_state["trading_day"],
                "signal_version": signal["signal_version"],
                "order": dict(order),
            }
        )
    for symbol, _score in sorted(
        signal["scores"].items(), key=lambda kv: -kv[1]
    ):
        pid = f"pi-{symbol}-BUY-{live_state['trading_day']}"
        if pid in in_flight:
            continue
        price = float(live_state.get("prices", {}).get(symbol, 0.0))
        if price <= 0:
            continue
        notional = 1.0 * price
        counters["entries_count"] += 1
        counters["deployed_notional"] += notional
        counters["turnover_notional"] += notional
        intents.append(
            {
                "parent_intent_id": pid,
                "account": live_state["account"],
                "symbol": symbol,
                "side": "BUY",
                "kind": "entry",
                "quantity": 1.0,
                "price": price,
                "notional": notional,
                "trading_day": live_state["trading_day"],
                "signal_version": signal["signal_version"],
                "order": {"ticker": symbol, "action": "buy", "quantity": 1.0},
            }
        )
        break  # one entry per tick
    return {
        "enabled": True,
        "reason": "ok",
        "intents": intents,
        "skipped": skipped,
        "blocked_by": {},
        "counters": counters,
    }


def fake_live_state(*, now: datetime, trading_day: str):
    return {
        "as_of": now.astimezone(ET).isoformat(),
        "trading_day": trading_day,
        "account": "TEST-ACCT",
        "cash": 1000.0,
        "equity": 2000.0,
        "positions": {},
        "prices": {"AAA": 10.0, "BBB": 20.0, "CCC": 30.0, "ZZZ": 5.0},
        "open_buy_reservations": {},
        "unsettled_buys": 0.0,
        "pending_broker_tickers": [],
    }


def make_scheduler(
    tmp_path: Path,
    *,
    config: IntradayDecisioningConfig | None = None,
    calendar=None,
    tick_runner=fake_tick_runner,
    signal=None,
    environ=None,
    exit_orders_provider=None,
    kill_path: Path | None = None,
) -> SessionScheduler:
    config = config or IntradayDecisioningConfig(
        enabled=True,
        tick_seconds=600.0,  # 10-min ticks keep the simulated session short
    )
    calendar = calendar or FakeCalendar({DAY: ("10:00", "11:00")})
    signal = signal if signal is not None else fake_signal()
    return SessionScheduler(
        config=config,
        tick_runner=tick_runner,
        signal_loader=lambda day: signal,
        session_start_provider=lambda day, now: {"watchlist": ["AAA", "BBB", "CCC"]},
        live_state_provider=fake_live_state,
        writer=ShadowTickWriter(tmp_path / "shadow.jsonl"),
        manifest_path=tmp_path / "manifest.json",
        kill_switch=KillSwitch(kill_path or tmp_path / "KILL"),
        calendar=calendar,
        exit_orders_provider=exit_orders_provider,
        environ=environ if environ is not None else {ENV_FLAG: "1"},
        strategy_config_fingerprint="cfg-fp",
    )


def run_full_session(scheduler: SessionScheduler, start_hm: str = "10:00"):
    h, m = (int(x) for x in start_hm.split(":"))
    day = datetime.fromisoformat(DAY)
    clock = ManualClock(datetime(day.year, day.month, day.day, h, m, tzinfo=ET))
    return scheduler.run_session(now_fn=clock, sleep_fn=clock.sleep)


def read_ticks(tmp_path: Path) -> list[dict]:
    path = tmp_path / "shadow.jsonl"
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ─────────────────────────── config plumbing ───────────────────────────
def test_absent_section_means_disabled():
    config = load_intraday_config({"watchlist": ["AAA"]})
    assert config.enabled is False
    assert config.mode == MODE_SHADOW
    assert config.tick_seconds == DEFAULT_TICK_SECONDS
    assert config.entry_open_delay_seconds == DEFAULT_ENTRY_OPEN_DELAY_SECONDS
    assert config.entry_close_cutoff_seconds == DEFAULT_ENTRY_CLOSE_CUTOFF_SECONDS


def test_malformed_values_fail_closed():
    config = load_intraday_config(
        {"intraday_decisioning": {"enabled": True, "tick_seconds": "soon"}}
    )
    assert config.enabled is False  # errors force disabled
    assert config.config_errors
    config = load_intraday_config({"intraday_decisioning": {"enabled": "yes"}})
    assert config.enabled is False
    assert config.config_errors


def test_valid_section_parses():
    config = load_intraday_config(
        {
            "intraday_decisioning": {
                "enabled": True,
                "mode": "shadow",
                "tick_seconds": 720,
                "canary_allowlist": ["nvda", "MU"],
            }
        }
    )
    assert config.enabled is True
    assert config.canary_allowlist == ("NVDA", "MU")
    assert not config.config_errors


def test_env_flag_default_off():
    assert env_flag_enabled({}) is False
    assert env_flag_enabled({ENV_FLAG: "0"}) is False
    assert env_flag_enabled({ENV_FLAG: "1"}) is True
    assert env_flag_enabled({ENV_FLAG: "TRUE"}) is True


def test_live_mode_downgrades_to_shadow():
    config = load_intraday_config(
        {"intraday_decisioning": {"enabled": True, "mode": "live"}}
    )
    assert config.enabled is True  # live is a valid REQUEST...
    mode, downgraded = resolve_mode(config)
    assert mode == MODE_SHADOW  # ...but the effective mode is always shadow
    assert downgraded is True


# ─────────────────────────── calendar gating ───────────────────────────
def test_holiday_produces_no_ticks(tmp_path):
    scheduler = make_scheduler(tmp_path, calendar=FakeCalendar({}))
    manifest = run_full_session(scheduler)
    assert manifest["status"] == "non_session_day"
    assert manifest["tick_count"] == 0
    assert read_ticks(tmp_path) == []


def test_half_day_windows_scale_to_actual_close(tmp_path):
    """Early close: cutoffs derive from the calendar bounds, not clock times."""
    bounds = FakeCalendar({DAY: ("09:30", "13:00")}).session_bounds(
        datetime.fromisoformat(DAY).date()
    )
    windows = SessionWindows.from_bounds(bounds, IntradayDecisioningConfig())
    assert windows.first_eligible_tick == bounds.open + timedelta(minutes=5)
    assert windows.entry_cutoff == bounds.close - timedelta(minutes=30)
    assert windows.entry_cutoff.hour == 12 and windows.entry_cutoff.minute == 30


def test_tiny_session_entry_window_never_inverts():
    bounds = FakeCalendar({DAY: ("10:00", "10:20")}).session_bounds(
        datetime.fromisoformat(DAY).date()
    )
    windows = SessionWindows.from_bounds(bounds, IntradayDecisioningConfig())
    assert windows.entry_cutoff == windows.first_eligible_tick  # empty, not inverted


def test_disabled_config_runs_nothing(tmp_path):
    scheduler = make_scheduler(tmp_path, config=IntradayDecisioningConfig(enabled=False))
    manifest = run_full_session(scheduler)
    assert manifest["status"] == "disabled_config"
    assert read_ticks(tmp_path) == []


def test_env_flag_off_runs_nothing(tmp_path):
    scheduler = make_scheduler(tmp_path, environ={})
    manifest = run_full_session(scheduler)
    assert manifest["status"] == "disabled_env_flag"
    assert read_ticks(tmp_path) == []


# ─────────────────────────── the session loop ───────────────────────────
def test_session_ticks_windows_and_manifest(tmp_path):
    """A full simulated 10:00–11:00 session with 10-min ticks: first eligible
    tick 10:05 (so 10:00 is settling), entry cutoff 10:30, close 11:00."""
    exits = lambda now: [{"ticker": "ZZZ", "quantity": 2.0}]  # noqa: E731
    scheduler = make_scheduler(tmp_path, exit_orders_provider=exits)
    manifest = run_full_session(scheduler)

    assert manifest["status"] == "completed"
    ticks = read_ticks(tmp_path)
    # Clock: 10:00 settling → ticks at 10:10, 10:20 (entries_open),
    # 10:30, 10:40, 10:50 (exits_only) → closed at 11:00.
    assert [t["window_phase"] for t in ticks] == [
        PHASE_ENTRIES_OPEN,
        PHASE_ENTRIES_OPEN,
        PHASE_EXITS_ONLY,
        PHASE_EXITS_ONLY,
        PHASE_EXITS_ONLY,
    ]
    assert manifest["tick_count"] == 5
    assert manifest["calendar_id"] == "FAKE-NYSE"
    assert manifest["mode_effective"] == MODE_SHADOW
    assert manifest["class_a"]["signal_version"] == "run-fri:deadbeef"
    assert manifest["class_b"]["gate_input_fingerprint"]
    assert manifest["kill_switch_engaged"] is False

    # Every tick carries the frozen fingerprints (§6 replay obligation).
    for t in ticks:
        assert t["fingerprints"]["signal_version"] == "run-fri:deadbeef"
        assert (
            t["fingerprints"]["gate_input_fingerprint"]
            == manifest["class_b"]["gate_input_fingerprint"]
        )
        assert t["mode"] == MODE_SHADOW
        assert t["schema_version"] == "rq105-intraday-shadow-v1"

    # Entries only in the entry window: tick 0 enters AAA, tick 1 enters BBB
    # (AAA now in flight via seen_parents dedup).
    entry_syms = [
        [i["symbol"] for i in t["decisions"]["intents"] if i["kind"] == "entry"]
        for t in ticks
    ]
    assert entry_syms[0] == ["AAA"]
    assert entry_syms[1] == ["BBB"]
    assert entry_syms[2:] == [[], [], []]  # §11b: entries stop at the cutoff


def test_entries_stop_exits_continue_past_cutoff(tmp_path):
    """§11b envelope-cutoff semantics on the recorded decisions.

    The protective exit first arises AFTER the cutoff (a fresh risk exit at
    10:30) — an exit emitted earlier would correctly be §7-deduped on later
    ticks and prove nothing about the window.
    """
    exits = lambda now: (  # noqa: E731
        [{"ticker": "ZZZ", "quantity": 2.0}]
        if (now.hour, now.minute) >= (10, 30)
        else []
    )
    scheduler = make_scheduler(tmp_path, exit_orders_provider=exits)
    run_full_session(scheduler)
    ticks = read_ticks(tmp_path)
    exits_only = [t for t in ticks if t["window_phase"] == PHASE_EXITS_ONLY]
    assert exits_only
    first = exits_only[0]
    # The exit intent passed through untouched...
    exit_intents = [
        i for i in first["decisions"]["intents"] if i["kind"] == "exit"
    ]
    assert [i["symbol"] for i in exit_intents] == ["ZZZ"]
    # ...while the entry the runner still proposed was moved to skipped with
    # the window-cutoff audit reason, and no entry intent survived.
    assert all(i["kind"] == "exit" for i in first["decisions"]["intents"])
    cutoff_skips = [
        s
        for s in first["decisions"]["skipped"]
        if REASON_ENTRY_WINDOW_CUTOFF in s["reasons"]
    ]
    assert cutoff_skips and cutoff_skips[0]["symbol"] == "CCC"


def test_apply_entry_window_policy_backs_out_counters():
    decisions = {
        "intents": [
            {
                "symbol": "AAA",
                "side": "BUY",
                "kind": "entry",
                "parent_intent_id": "p1",
                "notional": 100.0,
            },
            {
                "symbol": "ZZZ",
                "side": "SELL",
                "kind": "exit",
                "parent_intent_id": "p2",
                "notional": 50.0,
            },
        ],
        "skipped": [],
        "counters": {
            "entries_count": 1,
            "deployed_notional": 100.0,
            "turnover_notional": 150.0,
        },
    }
    out = apply_entry_window_policy(
        decisions,
        phase=PHASE_EXITS_ONLY,
        counters_before={
            "entries_count": 0,
            "deployed_notional": 0.0,
            "turnover_notional": 0.0,
        },
    )
    assert [i["symbol"] for i in out["intents"]] == ["ZZZ"]
    assert out["counters"] == {
        "entries_count": 0,
        "deployed_notional": 0.0,
        "turnover_notional": 50.0,  # the exit's turnover survives
    }
    # In the entry window the same payload passes through untouched.
    untouched = apply_entry_window_policy(
        decisions, phase=PHASE_ENTRIES_OPEN, counters_before={}
    )
    assert len(untouched["intents"]) == 2


def test_rerun_is_idempotent_append_only(tmp_path):
    scheduler = make_scheduler(tmp_path)
    run_full_session(scheduler)
    n_first = len(read_ticks(tmp_path))
    # Re-run the same session (fresh writer over the same file): dedup on
    # (session_date, tick_index) means no duplicate lines.
    scheduler2 = make_scheduler(tmp_path)
    run_full_session(scheduler2)
    assert len(read_ticks(tmp_path)) == n_first


# ─────────────────────────── class-A leak abort ───────────────────────────
def test_todays_signal_aborts_session(tmp_path):
    """The leak guard holds even with an injected (test-double) tick runner:
    a class-A signal dated the session itself refuses the whole session."""
    scheduler = make_scheduler(tmp_path, signal=fake_signal(as_of=DAY))
    manifest = run_full_session(scheduler)
    assert manifest["status"] == "aborted_class_a_leak"
    assert manifest["tick_count"] == 0
    assert read_ticks(tmp_path) == []


def test_missing_signal_aborts_session(tmp_path):
    def loader(day):
        from renquant_orchestrator.intraday_session_inputs import FrozenSignalError

        raise FrozenSignalError("no qualifying run")

    scheduler = make_scheduler(tmp_path)
    scheduler.signal_loader = loader
    manifest = run_full_session(scheduler)
    assert manifest["status"] == "aborted_class_a_unavailable"
    assert read_ticks(tmp_path) == []


# ─────────────────────────── never-submit assertion ───────────────────────────
def test_assert_shadow_never_submits_rejects_non_shadow_mode():
    with pytest.raises(ShadowModeViolation, match="shadow"):
        assert_shadow_never_submits(mode="live", decisions={"intents": []})


def test_assert_shadow_never_submits_rejects_submission_evidence():
    decisions = {
        "intents": [
            {
                "symbol": "AAA",
                "side": "BUY",
                "kind": "entry",
                "broker_order_id": "ord-123",  # order-lifecycle evidence
            }
        ]
    }
    with pytest.raises(ShadowModeViolation, match="broker_order_id"):
        assert_shadow_never_submits(mode=MODE_SHADOW, decisions=decisions)


def test_submission_evidence_halts_session_and_writes_nothing(tmp_path):
    def submitting_runner(**kwargs):
        result = fake_tick_runner(**kwargs)
        result["intents"][0]["client_order_id"] = "pi-x:1"  # slice-1 child id
        return result

    scheduler = make_scheduler(tmp_path, tick_runner=submitting_runner)
    with pytest.raises(ShadowModeViolation):
        run_full_session(scheduler)
    assert read_ticks(tmp_path) == []  # asserted BEFORE persisting
    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "halted_shadow_violation"


def test_live_mode_config_downgrades_and_counts(tmp_path):
    config = load_intraday_config(
        {"intraday_decisioning": {"enabled": True, "mode": "live", "tick_seconds": 600}}
    )
    scheduler = make_scheduler(tmp_path, config=config)
    manifest = run_full_session(scheduler)
    assert manifest["status"] == "completed"
    assert manifest["mode_requested"] == "live"
    assert manifest["mode_effective"] == MODE_SHADOW
    assert manifest["live_mode_downgraded_count"] == 1
    assert all(t["mode"] == MODE_SHADOW for t in read_ticks(tmp_path))


# ─────────────────────────── kill switch ───────────────────────────
def test_kill_switch_pre_session(tmp_path):
    kill = tmp_path / "KILL"
    kill.write_text("stop", encoding="utf-8")
    scheduler = make_scheduler(tmp_path, kill_path=kill)
    manifest = run_full_session(scheduler)
    assert manifest["status"] == "halted_kill_switch"
    assert read_ticks(tmp_path) == []


def test_kill_switch_honored_mid_session(tmp_path):
    kill = tmp_path / "KILL"
    scheduler = make_scheduler(tmp_path, kill_path=kill)
    day = datetime.fromisoformat(DAY)
    clock = ManualClock(datetime(day.year, day.month, day.day, 10, 0, tzinfo=ET))
    sleeps = {"n": 0}

    def sleep_and_maybe_kill(seconds: float) -> None:
        clock.sleep(seconds)
        sleeps["n"] += 1
        if sleeps["n"] == 3:  # engage after the 2nd tick has run
            kill.write_text("halt", encoding="utf-8")

    manifest = scheduler.run_session(now_fn=clock, sleep_fn=sleep_and_maybe_kill)
    assert manifest["status"] == "halted_kill_switch"
    assert manifest["kill_switch_engaged"] is True
    # Ticks ran at 10:10 and 10:20; the switch engaged before the 10:30 tick.
    assert manifest["tick_count"] == 2
    assert len(read_ticks(tmp_path)) == 2


# ─────────────────────────── fail-closed pipeline binding + CLI ───────────────────────────
def test_bind_pipeline_tick_runner_fails_closed_until_pinned():
    """Until renquant-pipeline #163 is merged AND pinned, the default binding
    must refuse loudly; once it imports, it must bind (adaptive so the test
    stays correct across the pin bump)."""
    try:
        import renquant_pipeline.intraday_decisioning  # noqa: F401, PLC0415

        available = True
    except ImportError:
        available = False
    if available:
        runner = bind_pipeline_tick_runner(
            strategy_config={}, data_manifest={}, artifact_manifest={}
        )
        assert callable(runner)
    else:
        with pytest.raises(PipelineContractUnavailable, match="#163|not importable"):
            bind_pipeline_tick_runner(
                strategy_config={}, data_manifest={}, artifact_manifest={}
            )


def test_cli_fails_closed_without_pipeline_manifests(tmp_path):
    cfg = tmp_path / "strategy_config.json"
    cfg.write_text(json.dumps({"watchlist": ["AAA"]}), encoding="utf-8")
    rc = scheduler_main(
        ["--strategy-config", str(cfg), "--data-root", str(tmp_path)]
    )
    assert rc == 2  # no injected runner + no manifests => refuse, never guess


def test_cli_disabled_config_stamps_manifest_and_exits_zero(tmp_path):
    cfg = tmp_path / "strategy_config.json"
    cfg.write_text(json.dumps({"watchlist": ["AAA"]}), encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    rc = scheduler_main(
        [
            "--strategy-config",
            str(cfg),
            "--data-root",
            str(tmp_path),
            "--manifest",
            str(manifest_path),
            "--out",
            str(tmp_path / "shadow.jsonl"),
        ],
        tick_runner=fake_tick_runner,
        live_state_provider=fake_live_state,
        calendar=FakeCalendar({}),
    )
    assert rc == 0
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "disabled_config"  # absent section => OFF


# ─────────────────────────── launchd package (files only) ───────────────────────────
OPS_DIR = Path(__file__).resolve().parent.parent / "ops" / "renquant105"


def test_session_scheduler_plist_schedule():
    with open(OPS_DIR / "com.renquant.rq105-session-scheduler.plist", "rb") as fh:
        plist = plistlib.load(fh)
    assert plist["Label"] == "com.renquant.rq105-session-scheduler"
    args = plist["ProgramArguments"]
    assert args[-1].endswith("ops/renquant105/run_session_scheduler.sh")
    intervals = plist["StartCalendarInterval"]
    assert {d["Weekday"] for d in intervals} == {1, 2, 3, 4, 5}
    assert all((d["Hour"], d["Minute"]) == (6, 25) for d in intervals)


def test_session_scheduler_wrapper_exists_and_references_module():
    wrapper = (OPS_DIR / "run_session_scheduler.sh").read_text(encoding="utf-8")
    assert "renquant_orchestrator.intraday_session_scheduler" in wrapper
    assert "renquant-orchestrator-run" in wrapper  # pinned checkout, never the working tree


def test_session_scheduler_wrapper_cli_args_are_valid():
    """Shell script must only pass arguments the CLI actually accepts.

    Regression: the deployed script had ``--mode paper`` which the CLI
    does not recognise, causing an argparse exit on every launch."""
    import re
    import shlex

    wrapper = (OPS_DIR / "run_session_scheduler.sh").read_text(encoding="utf-8")
    # Extract the python -m ... invocation (multi-line backslash-continued)
    pattern = re.compile(
        r'"\$.*python".*-m\s+renquant_orchestrator\.intraday_session_scheduler'
        r'((?:\s*\\\n\s*.*?)*)\s*>>',
        re.DOTALL,
    )
    m = pattern.search(wrapper)
    assert m, "could not find scheduler invocation in wrapper script"
    raw_args = m.group(1).replace("\\\n", " ")
    # Replace shell variables with dummy values so shlex can parse
    raw_args = re.sub(r'"\$[^"]*"', "DUMMY", raw_args)
    raw_args = re.sub(r"\$\w+", "DUMMY", raw_args)
    tokens = shlex.split(raw_args.strip())
    # Validate against the REAL CLI's accepted arguments by scanning the
    # module source for add_argument calls (avoids importing heavy deps
    # or running the parser with side-effects).
    import re as re_mod

    flags_in_wrapper = [t for t in tokens if t.startswith("--")]
    src = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "renquant_orchestrator"
        / "intraday_session_scheduler.py"
    ).read_text()
    defined_flags = set(re_mod.findall(r'add_argument\(\s*"(--[^"]+)"', src))
    unknown = [f for f in flags_in_wrapper if f not in defined_flags]
    assert unknown == [], (
        f"run_session_scheduler.sh passes unrecognised CLI args: {unknown}. "
        f"The CLI will reject these with 'unrecognized arguments'."
    )
