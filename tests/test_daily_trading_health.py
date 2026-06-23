"""Tests for ``daily_trading_health`` — the read-only daily trading-health surface.

The broker is always mocked (a stub ``snapshot_builder`` / inline snapshot dicts);
the ledger is always an in-memory SQLite DB. No test touches a real broker or the
shared production ledger.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from renquant_orchestrator import daily_trading_health as mod
from renquant_orchestrator.decision_ledger import connect, verdicts_for


AS_OF = "2026-06-22"
NOW = datetime(2026, 6, 22, 12, 0, tzinfo=timezone.utc)


def _fresh_artifact(tmp_path):
    art = tmp_path / "scorer.pkl"
    art.write_bytes(b"weights")
    return art


def _healthy_snapshot():
    return {
        "schema_version": 1,
        "broker_name": "readonly-alpaca",
        "cash": 2_000.0,
        "portfolio_value": 10_000.0,  # 20% cash -> deployed
        "positions": {"AAPL": {"ticker": "AAPL", "quantity": 10}},
        "open_orders": ["MSFT"],
    }


def _sell_only_snapshot():
    return {
        "schema_version": 1,
        "broker_name": "readonly-alpaca",
        "cash": 9_500.0,
        "portfolio_value": 10_000.0,  # 95% cash -> under-deployed
        "positions": {},
        "open_orders": [],
    }


def _stub_builder(snapshot):
    """A read-only broker stand-in: ignores output_json, returns a fixed snapshot.
    Asserts it is never asked to do anything but read."""

    def builder(**kwargs):
        assert "broker_name" in kwargs
        return dict(snapshot)

    return builder


# --- record shape ------------------------------------------------------------

def test_record_has_expected_fields(tmp_path):
    record = mod.build_daily_trading_health(
        as_of=AS_OF,
        snapshot_builder=_stub_builder(_healthy_snapshot()),
        run_bundle={
            "run_id": "2026-06-22-live-abc",
            "submitted_orders": [{"symbol": "AAPL", "side": "buy", "submitted_at": AS_OF}],
            "decision_trace": [{"symbol": "AAPL", "side": "buy"}],
        },
        artifact_path=_fresh_artifact(tmp_path),
        now=NOW,
    )
    payload = record.to_payload()

    assert payload["schema_version"] == mod.SCHEMA_VERSION
    assert payload["owner_repo"] == "renquant-orchestrator"
    assert payload["as_of"] == AS_OF
    assert payload["run_id"] == "2026-06-22-live-abc"
    assert set(payload["signals"]) == {"account_trading", "model_health", "cash_deployment"}
    for sig in payload["signals"].values():
        assert "status" in sig and "reason" in sig
    summary = payload["summary"]
    assert set(summary) >= {"health_verdict", "alert", "alert_title", "alert_body", "reasons"}


# --- healthy day does NOT alert ---------------------------------------------

def test_healthy_day_does_not_alert(tmp_path):
    record = mod.build_daily_trading_health(
        as_of=AS_OF,
        snapshot_builder=_stub_builder(_healthy_snapshot()),
        run_bundle={
            "submitted_orders": [{"symbol": "AAPL", "side": "buy", "submitted_at": AS_OF}],
        },
        artifact_path=_fresh_artifact(tmp_path),
        now=NOW,
    )

    assert record.health_verdict == "ok"
    assert record.alert_title is None and record.alert_body is None
    # emit_alert is a no-op for a healthy day even when not quiet
    assert record.account_trading["status"] == "ok"
    assert record.model_health["status"] == "ok"
    assert record.cash_deployment["status"] == "ok"


def test_emit_alert_returns_false_when_healthy():
    record = mod.TradingHealthRecord(as_of=AS_OF, run_id="r", health_verdict="ok")
    assert mod.emit_alert(record, topic="renquant", quiet=False) is False


# --- sell-only / high-cash day DOES alert -----------------------------------

def test_sell_only_high_cash_day_alerts(tmp_path):
    record = mod.build_daily_trading_health(
        as_of=AS_OF,
        snapshot_builder=_stub_builder(_sell_only_snapshot()),
        run_bundle={
            "submitted_orders": [],  # zero buys
            "decision_trace": [{"symbol": "AAPL", "side": "sell"}],
        },
        artifact_path=_fresh_artifact(tmp_path),
        now=NOW,
    )

    assert record.health_verdict == "bad"
    assert record.alert_title == "RenQuant 104 TRADING-HEALTH"
    assert record.alert_body
    # the under-deployment signal is the one that fires
    assert record.cash_deployment["status"] == "bad"
    assert "under-deployed" in record.cash_deployment["reason"]


def test_emit_alert_fires_when_bad_and_not_quiet(monkeypatch):
    sent = {}

    def fake_post(title, body, topic):
        sent.update(title=title, body=body, topic=topic)

    monkeypatch.setattr(mod, "post_ntfy", fake_post)
    record = mod.TradingHealthRecord(
        as_of=AS_OF, run_id="r", health_verdict="bad",
        alert_title="RenQuant 104 TRADING-HEALTH", alert_body="under-deployed",
    )

    assert mod.emit_alert(record, topic="renquant", quiet=False) is True
    assert sent["topic"] == "renquant"
    # quiet suppresses the network call
    sent.clear()
    assert mod.emit_alert(record, topic="renquant", quiet=True) is False
    assert sent == {}


def test_stale_model_artifact_alerts(tmp_path):
    record = mod.build_daily_trading_health(
        as_of=AS_OF,
        snapshot_builder=_stub_builder(_healthy_snapshot()),
        run_bundle={
            "submitted_orders": [{"symbol": "AAPL", "side": "buy", "submitted_at": AS_OF}],
        },
        artifact_path=None,  # no fresh scorer artifact
        now=NOW,
    )

    assert record.model_health["status"] == "bad"
    assert record.health_verdict == "bad"
    assert "model_health" in record.alert_body


def test_no_orders_for_many_days_alerts(tmp_path):
    record = mod.build_daily_trading_health(
        as_of=AS_OF,
        snapshot_builder=_stub_builder({
            **_healthy_snapshot(), "open_orders": [],
        }),
        run_bundle={
            "submitted_orders": [{"symbol": "AAPL", "side": "buy", "submitted_at": "2026-06-01"}],
        },
        artifact_path=_fresh_artifact(tmp_path),
        now=NOW,
    )

    assert record.account_trading["status"] == "bad"
    assert record.account_trading["days_since_last_order"] == 21
    assert record.health_verdict == "bad"


# --- graceful degradation ----------------------------------------------------

def test_missing_inputs_degrade_to_unknown_without_raising():
    record = mod.build_daily_trading_health(
        as_of=AS_OF,
        snapshot_builder=lambda **_: (_ for _ in ()).throw(RuntimeError("broker down")),
        run_bundle={},
        artifact_path=None,
        now=NOW,
    )

    # broker raised -> snapshot None -> account/cash unknown, model bad (no artifact)
    assert record.account_trading["status"] == "unknown"
    assert record.cash_deployment["status"] == "unknown"
    assert record.model_health["status"] == "bad"


def test_all_unknown_yields_unknown_verdict():
    # No snapshot, no orders, but a fresh-enough decision-free artifact substitute:
    # we force every signal to unknown by giving nothing usable + a future artifact.
    record = mod.TradingHealthRecord(as_of=AS_OF, run_id="r")
    record.account_trading = {"status": "unknown", "reason": "x"}
    record.model_health = {"status": "unknown", "reason": "x"}
    record.cash_deployment = {"status": "unknown", "reason": "x"}
    mod._decide_health(record)
    assert record.health_verdict == "unknown"
    assert record.alert_title is None


# --- per-signal builders -----------------------------------------------------

def test_cash_deployment_high_cash_with_buys_is_warn_not_bad():
    sig = mod.build_cash_deployment_signal(_sell_only_snapshot(), n_buys=3)
    assert sig["status"] == "warn"


def test_count_buys_prefers_submitted_orders():
    n = mod._count_buys(
        decision_trace=[{"side": "buy"}, {"side": "buy"}],
        submitted_orders=[{"side": "buy"}],
    )
    assert n == 1  # submitted_orders is the ground truth when present


def test_account_trading_recent_order_is_ok():
    sig = mod.build_account_trading_signal(
        {"open_orders": []},
        [{"side": "buy", "submitted_at": "2026-06-21"}],
        as_of=date(2026, 6, 22),
    )
    assert sig["status"] == "ok"
    assert sig["days_since_last_order"] == 1


# --- ledger persistence (in-memory) -----------------------------------------

def test_persist_to_ledger_writes_one_row_per_signal(tmp_path):
    record = mod.build_daily_trading_health(
        as_of=AS_OF,
        run_id="2026-06-22-live-xyz",
        snapshot_builder=_stub_builder(_sell_only_snapshot()),
        run_bundle={"submitted_orders": []},
        artifact_path=_fresh_artifact(tmp_path),
        now=NOW,
    )
    conn = connect(":memory:")
    try:
        added = mod.persist_to_ledger(record, conn=conn)
        assert added == 3
        rows = verdicts_for(conn, AS_OF, "book")
        gates = {r["gate"] for r in rows}
        assert gates == {
            "trading_health.account_trading",
            "trading_health.model_health",
            "trading_health.cash_deployment",
        }
        # the under-deployed cash signal persisted as a 'block' verdict
        cash = next(r for r in rows if r["gate"] == "trading_health.cash_deployment")
        assert cash["verdict"] == "block"
    finally:
        conn.close()


def test_persist_to_ledger_is_idempotent(tmp_path):
    record = mod.build_daily_trading_health(
        as_of=AS_OF,
        run_id="dup-run",
        snapshot_builder=_stub_builder(_healthy_snapshot()),
        run_bundle={"submitted_orders": [{"side": "buy", "submitted_at": AS_OF}]},
        artifact_path=_fresh_artifact(tmp_path),
        now=NOW,
    )
    conn = connect(":memory:")
    try:
        assert mod.persist_to_ledger(record, conn=conn) == 3
        assert mod.persist_to_ledger(record, conn=conn) == 0  # append-only no-op
    finally:
        conn.close()


# --- CLI ---------------------------------------------------------------------

def test_main_quiet_no_persist_emits_json(tmp_path, capsys, monkeypatch):
    import json

    snap = tmp_path / "snap.json"
    snap.write_text(json.dumps(_sell_only_snapshot()), encoding="utf-8")
    bundle = tmp_path / "bundle.json"
    bundle.write_text(json.dumps({"submitted_orders": []}), encoding="utf-8")

    # guard: even via the CLI, no real broker builder is invoked because an
    # explicit account snapshot is provided.
    monkeypatch.setattr(
        mod, "post_ntfy",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("quiet must not send")),
    )

    rc = mod.main([
        "--as-of", AS_OF,
        "--account-snapshot", str(snap),
        "--run-bundle", str(bundle),
        "--no-persist",
        "--quiet",
    ])
    out = json.loads(capsys.readouterr().out)
    assert rc == 2  # bad day -> non-zero exit
    assert out["summary"]["health_verdict"] == "bad"
    assert out["summary"]["alert"] is True
