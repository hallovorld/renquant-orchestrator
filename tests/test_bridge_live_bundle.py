from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from renquant_common import validate_live_run_bundle

from renquant_orchestrator.bridge_live_bundle import (
    build_bridge_live_bundle,
    write_bridge_live_bundle,
)
from renquant_orchestrator.live_parity import compare_live_bundles


def test_build_bridge_live_bundle_from_committed_runner_context() -> None:
    ctx = SimpleNamespace(
        decision_trace=[{"ticker": "AAPL", "stage": "score", "rank_score": 0.8}],
        orders=[{"ticker": "AAPL", "action": "buy", "quantity": 3}],
        orders_placed=[{"ticker": "AAPL", "status": "filled", "shares": 3}],
        orders_skipped=[{"ticker": "MSFT", "skip_reason": "pending_duplicate"}],
        exits_placed=[("TSLA", SimpleNamespace(exit_type="stop_loss", qty=1))],
    )

    bundle = build_bridge_live_bundle(ctx, metadata={"broker": "alpaca_shadow"})

    contract = validate_live_run_bundle(bundle)
    assert contract.source == "live_runner_bridge"
    assert bundle["metadata"] == {"broker": "alpaca_shadow"}
    assert bundle["order_intents"][0]["ticker"] == "AAPL"
    assert {row["kind"] for row in bundle["execution_audit"]} == {
        "exit_placed",
        "order_placed",
        "order_skipped",
    }
    assert compare_live_bundles(bundle, bundle)["ok"] is True


def test_bridge_live_bundle_falls_back_when_execution_rows_absent() -> None:
    ctx = SimpleNamespace(
        config={"watchlist": ["AAPL"]},
        market_snapshot={"as_of": "2026-06-09"},
        order_intents=[{"ticker": "AAPL", "action": "buy", "quantity": 1}],
        scores={"AAPL": 0.7},
    )

    bundle = build_bridge_live_bundle(ctx)

    assert bundle["decision_trace"][0]["ticker"] == "AAPL"
    assert bundle["decision_trace"][0]["score"] == 0.7
    assert bundle["execution_audit"] == [
        {
            "kind": "bridge_context",
            "reason": "no_execution_rows",
            "n_order_intents": 1,
        }
    ]
    assert compare_live_bundles(bundle, bundle)["ok"] is True


def test_write_bridge_live_bundle_outputs_json(tmp_path: Path) -> None:
    ctx = SimpleNamespace(
        decision_trace=[SimpleNamespace(ticker="AAPL", stage="score")],
        orders=[{"ticker": "AAPL", "action": "buy", "quantity": 1}],
        orders_pending=[{"ticker": "AAPL", "order_id": "pending-1"}],
    )
    output = tmp_path / "bridge.json"

    written = write_bridge_live_bundle(ctx, output)

    assert written == output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["decision_trace"] == [{"stage": "score", "ticker": "AAPL"}]
    assert payload["execution_audit"][0]["kind"] == "order_pending"
