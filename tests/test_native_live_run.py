from __future__ import annotations

import ast
import json
from pathlib import Path

from renquant_common import validate_live_run_bundle

from renquant_orchestrator.native_live_run import run_native_live_candidate


def _inference_payload() -> dict:
    return {
        "source": "renquant_pipeline.live_context_inference",
        "decision_trace": [{"ticker": "AAPL", "stage": "score"}],
        "order_intents": [{"ticker": "AAPL", "action": "buy", "quantity": 2}],
    }


def test_native_live_candidate_writes_readonly_execution_and_bundle(tmp_path: Path) -> None:
    inference = tmp_path / "inference.json"
    execution = tmp_path / "execution.json"
    commit_plan = tmp_path / "commit-plan.json"
    bundle = tmp_path / "native-bundle.json"
    inference.write_text(json.dumps(_inference_payload()), encoding="utf-8")

    payload = run_native_live_candidate(
        inference_json=inference,
        execution_output_json=execution,
        commit_plan_output_json=commit_plan,
        output_json=bundle,
        broker_name="readonly-alpaca",
    )

    assert payload["source"] == "native_live_bundle"
    assert payload["metadata"] == {
        "broker_name": "readonly-alpaca",
        "readonly": True,
        "runner": "renquant_orchestrator.native_live_run",
        "stage": "native_live_run_candidate",
    }
    assert payload["submitted_orders"] == [
        {
            "action": "BUY",
            "order_id": "readonly-dry-1",
            "quantity": 2.0,
            "status": "dry_run",
            "symbol": "AAPL",
        }
    ]
    assert json.loads(bundle.read_text(encoding="utf-8")) == payload
    execution_payload = json.loads(execution.read_text(encoding="utf-8"))
    assert execution_payload["readonly"] is True
    assert execution_payload["broker_name"] == "readonly-alpaca"
    commit_payload = json.loads(commit_plan.read_text(encoding="utf-8"))
    assert commit_payload["source"] == "renquant_execution.live_commit_plan"
    assert commit_payload["readonly"] is True
    assert commit_payload["broker_name"] == "readonly-alpaca"
    assert commit_payload["state_mutations"][0]["mutation_type"] == "order_submission"
    assert validate_live_run_bundle(payload).source == "native_live_bundle"


def test_native_live_candidate_accepts_existing_execution_and_metadata(tmp_path: Path) -> None:
    inference = tmp_path / "inference.json"
    execution = tmp_path / "execution.json"
    metadata = tmp_path / "metadata.json"
    bundle = tmp_path / "native-bundle.json"
    inference.write_text(json.dumps(_inference_payload()), encoding="utf-8")
    execution.write_text(
        json.dumps({
            "execution_audit": [{"broker": "fixture", "dry_run": True}],
            "submitted_orders": [],
        }),
        encoding="utf-8",
    )
    metadata.write_text(json.dumps({"mode": "shadow"}), encoding="utf-8")

    payload = run_native_live_candidate(
        inference_json=inference,
        execution_json=execution,
        metadata_json=metadata,
        output_json=bundle,
        broker_name="readonly-alpaca",
    )

    assert payload["metadata"]["mode"] == "shadow"
    assert payload["metadata"]["stage"] == "native_live_run_candidate"
    assert payload["execution_audit"] == [{"broker": "fixture", "dry_run": True}]


def test_native_live_candidate_source_does_not_import_umbrella_live_runner() -> None:
    source_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "renquant_orchestrator"
        / "native_live_run.py"
    )
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)

    assert "live.runner" not in imported_modules
    assert "live" not in imported_modules
