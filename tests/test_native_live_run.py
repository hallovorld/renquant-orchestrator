from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

from renquant_common import validate_live_run_bundle
import renquant_pipeline

from renquant_orchestrator import native_live_run
from renquant_orchestrator.native_live_run import main, run_native_live_candidate


def _inference_payload() -> dict:
    return {
        "source": "renquant_pipeline.live_context_inference",
        "decision_trace": [{"ticker": "AAPL", "stage": "score"}],
        "order_intents": [{"ticker": "AAPL", "action": "buy", "quantity": 2}],
    }


class _Contract:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def to_payload(self) -> dict[str, Any]:
        return dict(self._payload)


def _install_live_state_contract_stub(monkeypatch, payload: dict[str, Any]) -> None:
    def _load_live_state_contract(*_args, **_kwargs) -> _Contract:
        return _Contract(payload)

    monkeypatch.setattr(
        renquant_pipeline,
        "load_live_state_contract",
        _load_live_state_contract,
        raising=False,
    )


def _install_live_commit_and_persistence_stubs(
    monkeypatch,
    *,
    live_state: Path,
    trade_journal: Path,
    lifecycle_journal: Path,
    runs_db: Path,
) -> None:
    def fake_live_commit_execution_payload(**_kwargs) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "source": "renquant_execution.execution",
            "broker_name": "paper",
            "readonly": False,
            "dry_run": False,
            "order_intents": [
                {"symbol": "AAPL", "action": "BUY", "quantity": 2.0}
            ],
            "submitted_orders": [
                {
                    "order_id": "ord-1",
                    "status": "filled",
                    "symbol": "AAPL",
                    "action": "BUY",
                    "quantity": 2.0,
                }
            ],
            "state_mutations": [
                {
                    "mutation_id": "planned-order-1-live-state",
                    "mutation_type": "planned_live_state_update",
                    "readonly": True,
                    "committed": False,
                    "symbol": "AAPL",
                    "action": "BUY",
                    "source_order_id": "ord-1",
                    "status": "filled",
                    "filled_qty": 2.0,
                    "filled_avg_price": 10.0,
                },
                {
                    "mutation_id": "planned-order-1-trade-log",
                    "mutation_type": "planned_trade_log_append",
                    "readonly": True,
                    "committed": False,
                    "symbol": "AAPL",
                    "action": "BUY",
                    "source_order_id": "ord-1",
                    "status": "filled",
                    "filled_qty": 2.0,
                    "filled_avg_price": 10.0,
                },
            ],
            "execution_audit": [
                {"broker": "paper", "dry_run": False, "n_intents": 1, "n_submitted": 1}
            ],
        }

    def fake_commit_live_persistence(plan: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        assert kwargs == {
            "live_state_path": live_state,
            "trade_journal_path": trade_journal,
            "runs_db_path": runs_db,
            "strategy": "renquant_104_live",
            "lifecycle_journal_path": lifecycle_journal,
        }
        out = dict(plan)
        out["state_mutations"] = [
            {
                **row,
                "readonly": False,
                "committed": True,
                "path": str(live_state)
                if row["mutation_type"] == "planned_live_state_update"
                else str(trade_journal),
            }
            for row in plan["state_mutations"]
        ]
        out["persistence_audit"] = {
            "committed_mutation_count": 2,
            "live_state_path": str(live_state),
            "trade_journal_path": str(trade_journal),
        }
        return out

    monkeypatch.setattr(
        native_live_run,
        "_live_commit_execution_payload",
        fake_live_commit_execution_payload,
    )
    monkeypatch.setattr(
        native_live_run,
        "_commit_live_persistence",
        fake_commit_live_persistence,
    )


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


def test_native_live_candidate_can_emit_executed_live_commit_bundle(
    monkeypatch,
    tmp_path: Path,
) -> None:
    inference = tmp_path / "inference.json"
    execution = tmp_path / "execution.json"
    commit_plan = tmp_path / "commit-plan.json"
    bundle = tmp_path / "native-bundle.json"
    inference.write_text(json.dumps(_inference_payload()), encoding="utf-8")

    def fake_live_commit_execution_payload(**kwargs) -> dict[str, Any]:
        assert kwargs == {
            "broker_name": "paper",
            "order_intents": _inference_payload()["order_intents"],
            "dry_run": False,
        }
        return {
            "schema_version": 1,
            "source": "renquant_execution.execution",
            "broker_name": "paper",
            "readonly": False,
            "dry_run": False,
            "order_intents": [
                {"symbol": "AAPL", "action": "BUY", "quantity": 2.0}
            ],
            "submitted_orders": [
                {
                    "order_id": "ord-1",
                    "status": "filled",
                    "symbol": "AAPL",
                    "action": "BUY",
                    "quantity": 2.0,
                }
            ],
            "state_mutations": [
                {
                    "mutation_id": "planned-order-1",
                    "mutation_type": "order_submission",
                    "readonly": False,
                    "symbol": "AAPL",
                    "action": "BUY",
                }
            ],
            "execution_audit": [
                {"broker": "paper", "dry_run": False, "n_intents": 1, "n_submitted": 1}
            ],
        }

    monkeypatch.setattr(
        native_live_run,
        "_live_commit_execution_payload",
        fake_live_commit_execution_payload,
    )

    payload = run_native_live_candidate(
        inference_json=inference,
        execution_output_json=execution,
        commit_plan_output_json=commit_plan,
        output_json=bundle,
        broker_name="paper",
        execute_live=True,
    )

    assert payload["metadata"]["readonly"] is False
    assert payload["state_mutations"][0]["readonly"] is False
    execution_payload = json.loads(execution.read_text(encoding="utf-8"))
    assert execution_payload["readonly"] is False
    commit_payload = json.loads(commit_plan.read_text(encoding="utf-8"))
    assert commit_payload["readonly"] is False
    assert commit_payload["state_mutations"][0]["readonly"] is False


def test_native_live_candidate_can_commit_persistence_after_live_execution(
    monkeypatch,
    tmp_path: Path,
) -> None:
    inference = tmp_path / "inference.json"
    execution = tmp_path / "execution.json"
    commit_plan = tmp_path / "commit-plan.json"
    live_state = tmp_path / "live_state.alpaca.json"
    trade_journal = tmp_path / "trades.jsonl"
    lifecycle_journal = tmp_path / "lifecycle.jsonl"
    runs_db = tmp_path / "runs.alpaca.db"
    bundle = tmp_path / "native-bundle.json"
    inference.write_text(json.dumps(_inference_payload()), encoding="utf-8")
    _install_live_commit_and_persistence_stubs(
        monkeypatch,
        live_state=live_state,
        trade_journal=trade_journal,
        lifecycle_journal=lifecycle_journal,
        runs_db=runs_db,
    )

    payload = run_native_live_candidate(
        inference_json=inference,
        execution_output_json=execution,
        commit_plan_output_json=commit_plan,
        output_json=bundle,
        broker_name="paper",
        execute_live=True,
        commit_persistence=True,
        live_state_output_json=live_state,
        trade_journal_output_json=trade_journal,
        lifecycle_journal_output_json=lifecycle_journal,
        runs_db=runs_db,
        live_state_strategy="renquant_104_live",
    )

    assert payload["metadata"]["readonly"] is False
    assert payload["metadata"]["persistence_audit"]["committed_mutation_count"] == 2
    assert all(row["committed"] is True for row in payload["state_mutations"])
    execution_payload = json.loads(execution.read_text(encoding="utf-8"))
    assert execution_payload["persistence_audit"]["live_state_path"] == str(live_state)
    commit_payload = json.loads(commit_plan.read_text(encoding="utf-8"))
    assert all(row["committed"] is True for row in commit_payload["state_mutations"])


def test_native_live_candidate_posts_persistence_alert_after_commit(
    monkeypatch,
    tmp_path: Path,
) -> None:
    inference = tmp_path / "inference.json"
    live_state = tmp_path / "live_state.alpaca.json"
    trade_journal = tmp_path / "trades.jsonl"
    lifecycle_journal = tmp_path / "lifecycle.jsonl"
    runs_db = tmp_path / "runs.alpaca.db"
    bundle = tmp_path / "native-bundle.json"
    inference.write_text(json.dumps(_inference_payload()), encoding="utf-8")
    _install_live_commit_and_persistence_stubs(
        monkeypatch,
        live_state=live_state,
        trade_journal=trade_journal,
        lifecycle_journal=lifecycle_journal,
        runs_db=runs_db,
    )

    def fake_post_live_persistence_alert(ntfy_url: str, payload: dict[str, Any]) -> bool:
        assert ntfy_url == "https://ntfy.example/native-live"
        assert payload["persistence_audit"]["committed_mutation_count"] == 2
        assert all(row["committed"] is True for row in payload["state_mutations"])
        return True

    monkeypatch.setattr(
        native_live_run,
        "_post_live_persistence_alert",
        fake_post_live_persistence_alert,
    )

    payload = run_native_live_candidate(
        inference_json=inference,
        output_json=bundle,
        broker_name="paper",
        execute_live=True,
        commit_persistence=True,
        live_state_output_json=live_state,
        trade_journal_output_json=trade_journal,
        lifecycle_journal_output_json=lifecycle_journal,
        runs_db=runs_db,
        live_state_strategy="renquant_104_live",
        persistence_ntfy_url="https://ntfy.example/native-live",
    )

    assert payload["metadata"]["persistence_alert"] == {
        "attempted": True,
        "ok": True,
    }


def test_native_live_candidate_records_persistence_alert_failure_without_rollback(
    monkeypatch,
    tmp_path: Path,
) -> None:
    inference = tmp_path / "inference.json"
    live_state = tmp_path / "live_state.alpaca.json"
    trade_journal = tmp_path / "trades.jsonl"
    lifecycle_journal = tmp_path / "lifecycle.jsonl"
    runs_db = tmp_path / "runs.alpaca.db"
    bundle = tmp_path / "native-bundle.json"
    inference.write_text(json.dumps(_inference_payload()), encoding="utf-8")
    _install_live_commit_and_persistence_stubs(
        monkeypatch,
        live_state=live_state,
        trade_journal=trade_journal,
        lifecycle_journal=lifecycle_journal,
        runs_db=runs_db,
    )

    def fake_post_live_persistence_alert(_url: str, _payload: dict[str, Any]) -> bool:
        raise RuntimeError("ntfy down")

    monkeypatch.setattr(
        native_live_run,
        "_post_live_persistence_alert",
        fake_post_live_persistence_alert,
    )

    payload = run_native_live_candidate(
        inference_json=inference,
        output_json=bundle,
        broker_name="paper",
        execute_live=True,
        commit_persistence=True,
        live_state_output_json=live_state,
        trade_journal_output_json=trade_journal,
        lifecycle_journal_output_json=lifecycle_journal,
        runs_db=runs_db,
        live_state_strategy="renquant_104_live",
        persistence_ntfy_url="https://ntfy.example/native-live",
    )

    assert all(row["committed"] is True for row in payload["state_mutations"])
    assert payload["metadata"]["persistence_alert"] == {
        "attempted": True,
        "ok": False,
        "error": "RuntimeError: ntfy down",
    }


def test_native_live_candidate_rejects_commit_persistence_without_paths(tmp_path: Path) -> None:
    inference = tmp_path / "inference.json"
    inference.write_text(json.dumps(_inference_payload()), encoding="utf-8")

    try:
        run_native_live_candidate(
            inference_json=inference,
            output_json=tmp_path / "native-bundle.json",
            broker_name="paper",
            execute_live=True,
            commit_persistence=True,
        )
    except ValueError as exc:
        assert "--live-state-output-json" in str(exc)
    else:
        raise AssertionError("expected missing persistence path rejection")


def test_native_live_candidate_rejects_persistence_alert_without_commit(tmp_path: Path) -> None:
    inference = tmp_path / "inference.json"
    inference.write_text(json.dumps(_inference_payload()), encoding="utf-8")

    try:
        run_native_live_candidate(
            inference_json=inference,
            output_json=tmp_path / "native-bundle.json",
            broker_name="paper",
            execute_live=True,
            persistence_ntfy_url="https://ntfy.example/native-live",
        )
    except ValueError as exc:
        assert "--persistence-ntfy-url requires --commit-persistence" in str(exc)
    else:
        raise AssertionError("expected persistence alert without commit rejection")


def test_native_live_candidate_rejects_readonly_execute_live(tmp_path: Path) -> None:
    inference = tmp_path / "inference.json"
    inference.write_text(json.dumps(_inference_payload()), encoding="utf-8")

    try:
        run_native_live_candidate(
            inference_json=inference,
            output_json=tmp_path / "native-bundle.json",
            broker_name="readonly-alpaca",
            execute_live=True,
        )
    except ValueError as exc:
        assert "broker-name that can commit orders" in str(exc)
    else:
        raise AssertionError("expected readonly execute-live rejection")


def test_native_live_candidate_attaches_pipeline_live_state_contract(
    monkeypatch,
    tmp_path: Path,
) -> None:
    inference = tmp_path / "inference.json"
    bundle = tmp_path / "native-bundle.json"
    contract = tmp_path / "live-state-contract.json"
    strategy_dir = tmp_path / "strategy"
    strategy_dir.mkdir()
    _install_live_state_contract_stub(
        monkeypatch,
        {
            "schema_version": 1,
            "source": "live_state_file",
            "path": str(strategy_dir / "live_state.alpaca.json"),
            "used_legacy": False,
            "warnings": [],
            "state": {"cash": 1000.0},
            "account_snapshot": {
                "positions": {"AAPL": {"quantity": 3, "ticker": "AAPL"}}
            },
        },
    )
    inference.write_text(json.dumps(_inference_payload()), encoding="utf-8")

    payload = run_native_live_candidate(
        inference_json=inference,
        output_json=bundle,
        broker_name="alpaca",
        strategy_dir=strategy_dir,
        live_state_contract_output_json=contract,
    )

    assert payload["metadata"]["live_state_contract"] == {
        "account_snapshot_position_count": 1,
        "artifact_path": str(contract),
        "path": str(strategy_dir / "live_state.alpaca.json"),
        "schema_version": 1,
        "source": "live_state_file",
        "used_legacy": False,
        "warnings": [],
    }
    contract_payload = json.loads(contract.read_text(encoding="utf-8"))
    assert contract_payload["account_snapshot"]["positions"] == {
        "AAPL": {"quantity": 3, "ticker": "AAPL"}
    }


def test_native_live_run_cli_accepts_live_state_contract_args(monkeypatch, tmp_path: Path, capsys) -> None:
    inference = tmp_path / "inference.json"
    bundle = tmp_path / "native-bundle.json"
    contract = tmp_path / "live-state-contract.json"
    strategy_dir = tmp_path / "strategy"
    strategy_dir.mkdir()
    _install_live_state_contract_stub(
        monkeypatch,
        {
            "schema_version": 1,
            "source": "live_state_file",
            "path": str(strategy_dir / "live_state.alpaca.json"),
            "used_legacy": False,
            "warnings": [],
            "state": {},
            "account_snapshot": {"positions": {"IBM": {"quantity": 1}}},
        },
    )
    inference.write_text(json.dumps(_inference_payload()), encoding="utf-8")

    rc = main([
        "--inference-json",
        str(inference),
        "--output-json",
        str(bundle),
        "--broker-name",
        "alpaca",
        "--strategy-dir",
        str(strategy_dir),
        "--live-state-contract-output-json",
        str(contract),
    ])

    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["metadata"]["live_state_contract"]["source"] == "live_state_file"
    assert json.loads(contract.read_text(encoding="utf-8"))["source"] == "live_state_file"


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
