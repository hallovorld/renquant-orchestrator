from __future__ import annotations

import json
from pathlib import Path

from renquant_orchestrator.cli import main
from renquant_orchestrator.live_parity_payloads import run_live_parity_from_payloads


def _bridge_bundle(quantity: int = 1) -> dict:
    return {
        "schema_version": 1,
        "source": "live_runner_bridge",
        "decision_trace": [{"ticker": "AAPL", "stage": "score"}],
        "order_intents": [{"ticker": "AAPL", "action": "buy", "quantity": quantity}],
        "submitted_orders": [{"ticker": "AAPL", "action": "buy", "quantity": quantity}],
    }


def _inference_payload(quantity: int = 1) -> dict:
    return {
        "decision_trace": [{"ticker": "AAPL", "stage": "score"}],
        "order_intents": [{"ticker": "AAPL", "action": "buy", "quantity": quantity}],
    }


def _execution_payload(quantity: int = 1) -> dict:
    return {
        "submitted_orders": [{"ticker": "AAPL", "action": "buy", "quantity": quantity}],
    }


def test_live_parity_from_payloads_builds_native_bundle_and_verdict(tmp_path: Path) -> None:
    bridge = tmp_path / "bridge.json"
    inference = tmp_path / "inference.json"
    execution = tmp_path / "execution.json"
    native = tmp_path / "native.json"
    verdict_json = tmp_path / "verdict.json"
    bridge.write_text(json.dumps(_bridge_bundle()), encoding="utf-8")
    inference.write_text(json.dumps(_inference_payload()), encoding="utf-8")
    execution.write_text(json.dumps(_execution_payload()), encoding="utf-8")

    verdict = run_live_parity_from_payloads(
        bridge_bundle=bridge,
        inference_json=inference,
        execution_json=execution,
        native_bundle_output=native,
        output_json=verdict_json,
    )

    assert verdict["ok"] is True
    assert json.loads(native.read_text(encoding="utf-8"))["source"] == "native_live_bundle"
    assert json.loads(verdict_json.read_text(encoding="utf-8"))["ok"] is True


def test_live_parity_from_payloads_cli_fails_on_diff(tmp_path: Path) -> None:
    bridge = tmp_path / "bridge.json"
    inference = tmp_path / "inference.json"
    execution = tmp_path / "execution.json"
    native = tmp_path / "native.json"
    bridge.write_text(json.dumps(_bridge_bundle(quantity=1)), encoding="utf-8")
    inference.write_text(json.dumps(_inference_payload(quantity=2)), encoding="utf-8")
    execution.write_text(json.dumps(_execution_payload(quantity=2)), encoding="utf-8")

    rc = main([
        "live-parity-from-payloads",
        "--bridge-bundle",
        str(bridge),
        "--inference-json",
        str(inference),
        "--execution-json",
        str(execution),
        "--native-bundle-output",
        str(native),
        "--fail-on-diff",
    ])

    assert rc == 2
