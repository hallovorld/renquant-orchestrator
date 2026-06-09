from __future__ import annotations

import json
from pathlib import Path

import pytest
from renquant_common import validate_live_run_bundle

from renquant_orchestrator.cli import main
from renquant_orchestrator.live_parity import compare_live_bundles
from renquant_orchestrator.native_live_bundle import build_native_live_bundle, write_native_live_bundle


def _inference_payload() -> dict:
    return {
        "decision_trace": [
            {"ticker": "AAPL", "stage": "score", "rank_score": 0.9},
            {"ticker": "MSFT", "stage": "score", "rank_score": 0.4},
        ],
        "order_intents": [
            {
                "ticker": "AAPL",
                "action": "buy",
                "quantity": 3,
                "attribution": {"source_job": "RuntimeInferencePipeline"},
            }
        ],
    }


def _execution_payload() -> dict:
    return {
        "submitted_orders": [
            {"ticker": "AAPL", "action": "buy", "quantity": 3, "status": "dry_run"}
        ],
        "audit_rows": [
            {"broker": "readonly-alpaca", "dry_run": True, "n_intents": 1, "n_submitted": 1}
        ],
    }


def test_build_native_live_bundle_is_parity_ready() -> None:
    bundle = build_native_live_bundle(
        inference_payload=_inference_payload(),
        execution_payload=_execution_payload(),
        metadata={"broker": "readonly-alpaca"},
    )

    assert bundle["source"] == "native_live_bundle"
    assert bundle["metadata"] == {"broker": "readonly-alpaca"}
    assert bundle["decision_trace"][0]["ticker"] == "AAPL"
    assert bundle["order_intents"][0]["ticker"] == "AAPL"
    assert bundle["submitted_orders"][0]["status"] == "dry_run"
    assert bundle["execution_audit"][0]["broker"] == "readonly-alpaca"

    contract = validate_live_run_bundle(bundle)
    assert contract.source == "native_live_bundle"
    verdict = compare_live_bundles(bundle, bundle)
    assert verdict["ok"] is True


def test_build_native_live_bundle_adds_no_execution_audit_source() -> None:
    bundle = build_native_live_bundle(inference_payload=_inference_payload())

    assert "execution_audit" in bundle
    assert bundle["execution_audit"] == [
        {
            "stage": "native_live_bundle",
            "reason": "no_execution_payload",
            "n_order_intents": 1,
            "n_submitted_orders": 0,
        }
    ]
    assert compare_live_bundles(bundle, bundle)["ok"] is True


def test_build_native_live_bundle_requires_inference_trace_and_intents() -> None:
    with pytest.raises(ValueError, match="decision_trace"):
        build_native_live_bundle(inference_payload={"order_intents": []})

    with pytest.raises(ValueError, match="order_intents"):
        build_native_live_bundle(inference_payload={"decision_trace": []})


def test_native_live_bundle_rejects_non_object_json(tmp_path: Path) -> None:
    inference = tmp_path / "inference.json"
    output = tmp_path / "native-bundle.json"
    inference.write_text("[]", encoding="utf-8")

    with pytest.raises(ValueError, match="payload must be a JSON object"):
        write_native_live_bundle(inference_json=inference, output_json=output)


def test_native_live_bundle_cli_writes_json(tmp_path: Path, capsys) -> None:
    inference = tmp_path / "inference.json"
    execution = tmp_path / "execution.json"
    metadata = tmp_path / "metadata.json"
    output = tmp_path / "native-bundle.json"
    inference.write_text(json.dumps(_inference_payload()), encoding="utf-8")
    execution.write_text(json.dumps(_execution_payload()), encoding="utf-8")
    metadata.write_text(json.dumps({"broker": "readonly-alpaca"}), encoding="utf-8")

    rc = main([
        "native-live-bundle",
        "--inference-json",
        str(inference),
        "--execution-json",
        str(execution),
        "--metadata-json",
        str(metadata),
        "--output-json",
        str(output),
    ])

    assert rc == 0
    stdout_bundle = json.loads(capsys.readouterr().out)
    file_bundle = json.loads(output.read_text(encoding="utf-8"))
    assert stdout_bundle == file_bundle
    assert file_bundle["metadata"]["broker"] == "readonly-alpaca"
