"""S3-P4 observe-only entry loop — the wiring's own contract.

The decision core (`intraday_entry_decision`) has its own suite; these tests
cover what THIS module adds: config-fed guardrails (orch#1050), fail-closed
occupancy evidence, recompute-from-log session totals, the batch-side refusal
contract, and the no-broker-vocabulary assertion on every persisted record.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from renquant_orchestrator import rq105_entry_loop_shadow as mod

ET = ZoneInfo("America/New_York")
SESSION = "2026-08-24"
AS_OF = "2026-08-24T12:00:00-04:00"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
def _pinned_cfg(tmp_path, cap=10):
    p = tmp_path / "strategy_config.json"
    body = {"max_concurrent_positions": cap} if cap is not None else {}
    p.write_text(json.dumps(body))
    return p


def _shadow_log(tmp_path, rows):
    p = tmp_path / "shadow.jsonl"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    return p


def _shadow_row(ticker, score, *, mid=100.0, status="ok",
                as_of=AS_OF, session=SESSION):
    return {"session_date": session, "as_of": as_of, "ticker": ticker,
            "shadow_score": score, "intraday_mid": mid, "quote_status": status}


def _scheduler_log(tmp_path, *, positions=("AAPL", "MSFT"), tick_at=None,
                   pending=(), reservations=()):
    p = tmp_path / "sched.jsonl"
    rec = {
        "session_date": SESSION,
        "tick_at": tick_at or "2026-08-24T11:55:00-04:00",
        "inputs": {"live_state": {
            "positions": {t: {"qty": 1} for t in positions},
            "pending_broker_tickers": list(pending),
            "open_buy_reservations": {t: {} for t in reservations},
        }},
    }
    p.write_text(json.dumps(rec) + "\n")
    return p


def _fake_signal(scores):
    return {"signal_version": "2026-08-21-live-abc:deadbeef", "as_of": "2026-08-21",
            "scores": scores}


class _Cal:  # the loader is monkeypatched; the calendar is never consulted
    pass


def _run(tmp_path, monkeypatch, *, batch_scores=None, batch_exc=None,
         rows=(), positions=("HELD1",), cap=10, intents_log=None,
         tick_at=None, as_of=AS_OF):
    if batch_exc is not None:
        def fake_loader(**kw):
            raise batch_exc
    else:
        def fake_loader(**kw):
            return _fake_signal(batch_scores or {})
    monkeypatch.setattr(mod, "load_frozen_daily_signal", fake_loader)
    intents = intents_log or (tmp_path / "intents.jsonl")
    record = mod.run_entry_loop_tick(
        session_date=SESSION,
        as_of=as_of,
        db_path=tmp_path / "runs.db",           # untouched: loader is faked
        calendar=_Cal(),
        shadow_log=_shadow_log(
            tmp_path, [{**r, "as_of": as_of} for r in rows]),
        scheduler_log=_scheduler_log(
            tmp_path, positions=positions,
            tick_at=tick_at or (
                dt.datetime.fromisoformat(as_of) - dt.timedelta(minutes=5)
            ).isoformat()),
        pinned_config=_pinned_cfg(tmp_path, cap=cap),
        intents_log=intents,
        env={},
    )
    return record, intents


# ---------------------------------------------------------------------------
# guardrails come from the pinned config (orch#1050)
# ---------------------------------------------------------------------------
def test_cap_comes_from_the_pinned_config_never_the_dataclass_default(tmp_path):
    g = mod.guardrails_from_pinned_config(_pinned_cfg(tmp_path, cap=10))
    assert g.max_concurrent_positions == 10
    assert g.max_entries_per_day == 2 and g.max_notional_per_day == 1500.0


@pytest.mark.parametrize("cap", [None, True, -1, "8"])
def test_an_unusable_cap_refuses_instead_of_defaulting(tmp_path, cap):
    with pytest.raises(ValueError, match="orch#1050"):
        mod.guardrails_from_pinned_config(_pinned_cfg(tmp_path, cap=cap))


# ---------------------------------------------------------------------------
# occupancy evidence, fail-closed
# ---------------------------------------------------------------------------
def test_occupancy_unions_positions_pending_and_reservations(tmp_path):
    log = _scheduler_log(tmp_path, positions=("AAPL", "MSFT"),
                         pending=("MSFT", "NVDA"), reservations=("TSLA",))
    n, why = mod.held_plus_pending_from_scheduler_log(
        log, session_date=SESSION,
        as_of_et=dt.datetime(2026, 8, 24, 12, 0, tzinfo=ET), max_age_min=30)
    assert n == 4, why  # AAPL MSFT NVDA TSLA — MSFT deduped


def test_a_stale_tick_refuses_occupancy(tmp_path):
    log = _scheduler_log(tmp_path, tick_at="2026-08-24T10:00:00-04:00")
    n, why = mod.held_plus_pending_from_scheduler_log(
        log, session_date=SESSION,
        as_of_et=dt.datetime(2026, 8, 24, 12, 0, tzinfo=ET), max_age_min=30)
    assert n is None and "stale" in why


def test_a_missing_log_refuses_occupancy(tmp_path):
    n, why = mod.held_plus_pending_from_scheduler_log(
        tmp_path / "absent.jsonl", session_date=SESSION,
        as_of_et=dt.datetime(2026, 8, 24, 12, 0, tzinfo=ET), max_age_min=30)
    assert n is None


def test_occupancy_refusal_becomes_a_session_block_not_zero_slots(
        tmp_path, monkeypatch):
    record, _ = _run(tmp_path, monkeypatch,
                     batch_scores={"AAPL": 1.0},
                     rows=[_shadow_row("AAPL", 0.5)],
                     tick_at="2026-08-24T09:00:00-04:00")  # stale
    assert record["session_block"] and "occupancy_unknown" in record["session_block"]
    assert record["intents"] == []


# ---------------------------------------------------------------------------
# the tick end-to-end
# ---------------------------------------------------------------------------
def test_happy_path_records_an_intent_with_config_cap_provenance(
        tmp_path, monkeypatch):
    record, intents = _run(tmp_path, monkeypatch,
                           batch_scores={"AAPL": 1.2, "MSFT": 0.8},
                           rows=[_shadow_row("AAPL", 0.9),
                                 _shadow_row("MSFT", -0.1),   # intraday veto
                                 _shadow_row("NVDA", 2.0)])   # not batch admitted
    assert record["session_block"] is None
    tickers = [i["ticker"] for i in record["intents"]]
    assert tickers == ["AAPL"]
    assert record["rejections"]["MSFT"] == "intraday_veto"
    assert record["rejections"]["NVDA"] == "not_batch_admitted"
    assert record["guardrails"]["max_concurrent_positions"] == 10
    assert record["guardrails"]["cap_source"].endswith("strategy_config.json")
    assert record["observe_only"] is True
    on_disk = [json.loads(l) for l in intents.read_text().splitlines()]
    assert len(on_disk) == 1 and on_disk[0]["kind"] == mod.RECORD_KIND


def test_batch_refusal_is_recorded_with_its_reason(tmp_path, monkeypatch):
    from renquant_orchestrator.intraday_session_inputs import FrozenSignalError
    record, _ = _run(tmp_path, monkeypatch,
                     batch_exc=FrozenSignalError("no qualifying run for X"),
                     rows=[_shadow_row("AAPL", 0.9)])
    assert "batch_side_refused" in record["session_block"]
    assert "no qualifying run" in record["session_block"]
    assert record["intents"] == []


def test_no_shadow_rows_is_a_named_block(tmp_path, monkeypatch):
    record, _ = _run(tmp_path, monkeypatch, batch_scores={"AAPL": 1.0}, rows=[])
    assert "no_shadow_rows_for_as_of" in record["session_block"]


def test_session_totals_accumulate_across_ticks_and_exhaust_the_budget(
        tmp_path, monkeypatch):
    intents = tmp_path / "intents.jsonl"
    # distinct as_of per tick — the idempotency gate (orch#1059 P1-2) is
    # keyed on (session, as_of), so reusing one as_of would be a RETRY
    for ticker, hour in (("AAA", "10:00"), ("BBB", "12:00")):
        _run(tmp_path, monkeypatch, batch_scores={ticker: 1.0},
             rows=[_shadow_row(ticker, 1.0)], intents_log=intents,
             as_of=f"2026-08-24T{hour}:00-04:00")
    entries, notional = mod.session_totals_from_intents_log(
        intents, session_date=SESSION)
    assert entries == 2 and notional == pytest.approx(1500.0)
    record, _ = _run(tmp_path, monkeypatch, batch_scores={"CCC": 1.0},
                     rows=[_shadow_row("CCC", 1.0)], intents_log=intents,
                     as_of="2026-08-24T14:00:00-04:00")
    assert record["intents"] == []
    assert record["rejections"]["CCC"] == "daily_entry_budget_exhausted"


def test_position_cap_full_uses_the_CONFIG_cap(tmp_path, monkeypatch):
    record, _ = _run(tmp_path, monkeypatch, batch_scores={"AAPL": 1.0},
                     rows=[_shadow_row("AAPL", 1.0)],
                     positions=tuple(f"H{i}" for i in range(10)), cap=10)
    assert record["rejections"]["AAPL"] == "position_cap_full"
    record2, _ = _run(tmp_path, monkeypatch, batch_scores={"AAPL": 1.0},
                      rows=[_shadow_row("AAPL", 1.0)],
                      positions=tuple(f"H{i}" for i in range(10)), cap=12,
                      as_of="2026-08-24T14:00:00-04:00")
    assert [i["ticker"] for i in record2["intents"]] == ["AAPL"]


def test_a_record_with_broker_vocabulary_refuses_to_persist(
        tmp_path, monkeypatch):
    monkeypatch.setattr(
        mod, "session_totals_from_intents_log",
        lambda *a, **k: (0, 0.0))
    real_dumps = json.dumps

    def poisoned(obj, **kw):
        if isinstance(obj, dict) and obj.get("kind") == mod.RECORD_KIND:
            obj = {**obj, "order_id": "oops"}
        return real_dumps(obj, **kw)
    monkeypatch.setattr(mod.json, "dumps", poisoned)
    with pytest.raises(AssertionError, match="broker vocabulary"):
        _run(tmp_path, monkeypatch, batch_scores={"AAPL": 1.0},
             rows=[_shadow_row("AAPL", 1.0)])


def test_stale_quotes_fail_closed_per_name(tmp_path, monkeypatch):
    record, _ = _run(tmp_path, monkeypatch,
                     batch_scores={"AAPL": 1.0, "MSFT": 1.0},
                     rows=[_shadow_row("AAPL", 1.0, status="stale"),
                           _shadow_row("MSFT", 1.0)])
    assert record["rejections"]["AAPL"] == "intraday_quote_censored"
    assert [i["ticker"] for i in record["intents"]] == ["MSFT"]


# ── [codex on orch#1059] P1-1: serving failure gates the decision ────────────
def test_a_failed_serving_persists_a_named_refusal_not_a_plan(
        tmp_path, monkeypatch):
    def fake_loader(**kw):
        return _fake_signal({"AAPL": 1.0})
    monkeypatch.setattr(mod, "load_frozen_daily_signal", fake_loader)
    intents = tmp_path / "intents.jsonl"
    record = mod.run_entry_loop_tick(
        session_date=SESSION, as_of=AS_OF, db_path=tmp_path / "runs.db",
        calendar=_Cal(),
        shadow_log=_shadow_log(tmp_path, [_shadow_row("AAPL", 1.0)]),
        scheduler_log=_scheduler_log(tmp_path),
        pinned_config=_pinned_cfg(tmp_path),
        intents_log=intents, serving_rc=3, env={})
    assert "serving_failed rc=3" in record["session_block"]
    assert record["intents"] == []
    on_disk = [json.loads(l) for l in intents.read_text().splitlines()]
    assert len(on_disk) == 1, "the refusal must be PERSISTED, not silent"


# ── [codex on orch#1059] P1-2: one (session, as_of) decides exactly once ─────
def test_a_retried_tick_returns_the_existing_record_and_appends_nothing(
        tmp_path, monkeypatch):
    intents = tmp_path / "intents.jsonl"
    r1, _ = _run(tmp_path, monkeypatch, batch_scores={"AAPL": 1.0},
                 rows=[_shadow_row("AAPL", 1.0)], intents_log=intents)
    assert [i["ticker"] for i in r1["intents"]] == ["AAPL"]
    r2, _ = _run(tmp_path, monkeypatch, batch_scores={"AAPL": 1.0},
                 rows=[_shadow_row("AAPL", 1.0)], intents_log=intents)
    assert r2.get("duplicate_tick") is True
    assert [i["ticker"] for i in r2["intents"]] == ["AAPL"]
    on_disk = [json.loads(l) for l in intents.read_text().splitlines()]
    assert len(on_disk) == 1, "a retry must not append a twin record"
    entries, notional = mod.session_totals_from_intents_log(
        intents, session_date=SESSION)
    assert entries == 1 and notional == pytest.approx(750.0)


def test_totals_ignore_a_duplicate_record_even_if_one_slips_in(tmp_path):
    """Defense in depth: if a twin record ever reaches the log (e.g. a
    pre-fix log), the totals still count the tick once."""
    intents = tmp_path / "intents.jsonl"
    rec = {"kind": mod.RECORD_KIND, "session_date": SESSION,
           "as_of": "2026-08-24T12:00:00-04:00",
           "intents": [{"ticker": "AAPL", "notional_budget": 750.0}]}
    intents.write_text(json.dumps(rec) + "\n" + json.dumps(rec) + "\n")
    entries, notional = mod.session_totals_from_intents_log(
        intents, session_date=SESSION)
    assert entries == 1 and notional == pytest.approx(750.0)


def test_concurrent_retries_serialize_on_the_writer_lock(tmp_path, monkeypatch):
    """Two threads race the same tick: exactly one record lands; the loser
    reports duplicate_tick. The lock's re-check is what makes this true —
    both threads pass the pre-work idempotency gate before either writes."""
    import threading

    def fake_loader(**kw):
        return _fake_signal({"AAPL": 1.0})
    monkeypatch.setattr(mod, "load_frozen_daily_signal", fake_loader)
    shadow = _shadow_log(tmp_path, [_shadow_row("AAPL", 1.0)])
    sched = _scheduler_log(tmp_path)
    cfg = _pinned_cfg(tmp_path)
    intents = tmp_path / "intents.jsonl"
    barrier = threading.Barrier(2)
    results = []

    real_existing = mod._existing_tick_record

    def gated_existing(*a, **k):
        out = real_existing(*a, **k)
        barrier.wait(timeout=5)   # both threads pass the pre-gate together
        return out
    monkeypatch.setattr(mod, "_existing_tick_record", gated_existing)

    def worker():
        results.append(mod.run_entry_loop_tick(
            session_date=SESSION, as_of=AS_OF, db_path=tmp_path / "runs.db",
            calendar=_Cal(), shadow_log=shadow, scheduler_log=sched,
            pinned_config=cfg, intents_log=intents, env={}))

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
    on_disk = [json.loads(l) for l in intents.read_text().splitlines()]
    assert len(on_disk) == 1, "concurrent retries must not append twins"
    assert sum(1 for r in results if r.get("duplicate_tick")) == 1
