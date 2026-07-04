from __future__ import annotations

import json
from pathlib import Path

import pytest

from renquant_orchestrator.cli import main
from renquant_orchestrator.native_execution_payload import (
    build_readonly_execution_payload,
    write_readonly_execution_payload,
)


def _inference_payload(quantity: int = 2) -> dict:
    return {
        "source": "renquant_pipeline.runtime_inference",
        "decision_trace": [{"ticker": "AAPL", "stage": "score"}],
        "order_intents": [{"ticker": "AAPL", "action": "buy", "quantity": quantity}],
    }


def test_build_readonly_execution_payload_does_not_connect_to_broker() -> None:
    payload = build_readonly_execution_payload(
        inference_payload=_inference_payload(),
        broker_name="readonly-alpaca",
    )

    assert payload["source"] == "renquant_execution.execution"
    assert payload["broker_name"] == "readonly-alpaca"
    assert payload["dry_run"] is True
    assert payload["readonly"] is True
    assert payload["inference_source"] == "renquant_pipeline.runtime_inference"
    assert payload["order_intents"] == _inference_payload()["order_intents"]
    assert payload["submitted_orders"] == [
        {
            "order_id": "readonly-dry-1",
            "status": "dry_run",
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 2.0,
        }
    ]
    assert payload["execution_audit"] == [
        {
            "broker": "readonly-alpaca",
            "dry_run": True,
            "n_intents": 1,
            "n_submitted": 1,
            "n_skipped": 0,
        }
    ]


def test_build_readonly_execution_payload_uses_bridge_compatible_no_trade_audit() -> None:
    payload = build_readonly_execution_payload(
        inference_payload={"source": "fixture", "order_intents": []},
        broker_name="readonly-alpaca",
    )

    assert payload["submitted_orders"] == []
    assert payload["execution_audit"] == [
        {
            "kind": "bridge_context",
            "n_order_intents": 0,
            "reason": "no_execution_rows",
        }
    ]


def test_native_execution_payload_requires_order_intent_list() -> None:
    with pytest.raises(ValueError, match="order_intents"):
        build_readonly_execution_payload(inference_payload={})


def test_native_execution_payload_rejects_malformed_intent() -> None:
    with pytest.raises(ValueError, match="missing action"):
        build_readonly_execution_payload(inference_payload={"order_intents": [{"ticker": "AAPL"}]})


def test_native_execution_payload_cli_writes_json(tmp_path: Path, capsys) -> None:
    inference = tmp_path / "inference.json"
    output = tmp_path / "execution.json"
    inference.write_text(json.dumps(_inference_payload()), encoding="utf-8")

    rc = main([
        "native-execution-payload",
        "--inference-json",
        str(inference),
        "--output-json",
        str(output),
        "--broker-name",
        "readonly-alpaca",
    ])

    assert rc == 0
    stdout_payload = json.loads(capsys.readouterr().out)
    file_payload = json.loads(output.read_text(encoding="utf-8"))
    assert stdout_payload == file_payload
    assert file_payload["readonly"] is True


def test_write_native_execution_payload_rejects_non_object_json(tmp_path: Path) -> None:
    inference = tmp_path / "inference.json"
    output = tmp_path / "execution.json"
    inference.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="payload must be a JSON object"):
        write_readonly_execution_payload(inference_json=inference, output_json=output)
