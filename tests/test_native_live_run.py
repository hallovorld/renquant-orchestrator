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
            "run_id": "native-live-20260612",
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
            "lifecycle_journal_row_count": 1,
            "live_state_snapshot_row_count": 1,
            "live_state_path": str(live_state),
            "trade_journal_path": str(trade_journal),
            "runs_db_path": str(runs_db),
            "run_id": "native-live-20260612",
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
        run_id="native-live-20260612",
        live_state_output_json=live_state,
        trade_journal_output_json=trade_journal,
        lifecycle_journal_output_json=lifecycle_journal,
        runs_db=runs_db,
        live_state_strategy="renquant_104_live",
    )

    assert payload["metadata"]["readonly"] is False
    assert payload["metadata"]["run_id"] == "native-live-20260612"
    assert payload["metadata"]["persistence_audit"]["committed_mutation_count"] == 2
    assert payload["metadata"]["persistence_audit"]["live_state_snapshot_row_count"] == 1
    assert all(row["committed"] is True for row in payload["state_mutations"])
    execution_payload = json.loads(execution.read_text(encoding="utf-8"))
    assert execution_payload["persistence_audit"]["run_id"] == "native-live-20260612"
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
        run_id="native-live-20260612",
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
        run_id="native-live-20260612",
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


def test_native_live_candidate_rejects_commit_persistence_without_audit_evidence(
    tmp_path: Path,
) -> None:
    inference = tmp_path / "inference.json"
    inference.write_text(json.dumps(_inference_payload()), encoding="utf-8")

    try:
        run_native_live_candidate(
            inference_json=inference,
            output_json=tmp_path / "native-bundle.json",
            broker_name="paper",
            execute_live=True,
            commit_persistence=True,
            live_state_output_json=tmp_path / "live_state.alpaca.json",
            trade_journal_output_json=tmp_path / "trades.jsonl",
        )
    except ValueError as exc:
        assert "--run-id" in str(exc)
        assert "--runs-db" in str(exc)
        assert "--lifecycle-journal-output-json" in str(exc)
    else:
        raise AssertionError("expected missing persistence audit evidence rejection")


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

# --- R5 persistence guard on the native live path (T6/D6-F3, shadow-soak) --------
#
# The guard is armed by passing run-manifest + strategy-config + model-sha
# inputs; legacy invocations (none of them) are unchanged — and, per the
# honest-scope statement, UNPROTECTED. These tests drive the REAL guard
# implementation (native_persistence_guard) with injected git probe /
# fingerprint authorities, wrapped through the module's
# _verify_persistence_guard indirection. Incident tokens are REAL detached
# OpenSSH signatures made with the committed placeholder test key.

import datetime as _dt
import hashlib as _hashlib
import subprocess as _subprocess

import pytest

from renquant_orchestrator.native_live_context import (
    canonical_json_sha256 as _canonical_json_sha256,
)
from renquant_orchestrator.native_persistence_guard import (
    CHECK_RUN_MANIFEST as _CHECK_RUN_MANIFEST,
    IncidentTokenError,
    PersistenceGuardError,
    SIGNATURE_NAMESPACE as _SIGNATURE_NAMESPACE,
    verify_persistence_guard,
)
from renquant_orchestrator.shadow_ab_runner import EXPERIMENT_PIN_REPOS

_GUARD_RUN_ID = "native-live-20260612"
_GUARD_MODEL_SHA = "sha256:fp-model-1"
_GUARD_ALLOWED_SIGNERS = (
    Path(__file__).resolve().parents[1] / "security" / "persistence_guard_allowed_signers"
)
_GUARD_FIXTURE_KEY = (
    Path(__file__).resolve().parent / "fixtures" / "persistence_guard_test_key"
)
_GUARD_TEST_PRINCIPAL = "persistence-guard-test-operator"


def _guard_commit(name: str) -> str:
    return _hashlib.sha1(name.encode("utf-8")).hexdigest()


def _guard_world(tmp_path: Path) -> dict[str, Path]:
    repos = {}
    for name in EXPERIMENT_PIN_REPOS:
        repo_dir = tmp_path / "repos" / name
        repo_dir.mkdir(parents=True, exist_ok=True)
        repos[name] = {"path": str(repo_dir), "commit": _guard_commit(name)}
    manifest = tmp_path / "run_manifest.json"
    manifest.write_text(
        json.dumps({"schema_version": 1, "repos": repos, "data_revision": "rev-1"}),
        encoding="utf-8",
    )
    model = tmp_path / "model.pt"
    model.write_text("model-1", encoding="utf-8")
    config = tmp_path / "configs" / "strategy_config.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        json.dumps({"ranking": {"panel_scoring": {"artifact_path": str(model)}}}),
        encoding="utf-8",
    )
    return {"manifest": manifest, "config": config}


def _install_guard_authorities(
    monkeypatch, manifest: Path, *, drift: set[str] = frozenset()
) -> None:
    repos = json.loads(manifest.read_text(encoding="utf-8"))["repos"]
    head_by_path = {
        entry["path"]: ("f" * 40 if name in drift else entry["commit"])
        for name, entry in repos.items()
    }

    def probe(args):
        path = args[1]
        if list(args[2:]) == ["rev-parse", "HEAD"]:
            return _subprocess.CompletedProcess(
                list(args), 0, stdout=head_by_path[path] + "\n", stderr=""
            )
        if list(args[2:]) == ["status", "--porcelain"]:
            return _subprocess.CompletedProcess(list(args), 0, stdout="", stderr="")
        raise AssertionError(f"unexpected git probe: {args}")

    def fake_fingerprint(path: str | Path) -> str:
        return "sha256:fp-" + Path(path).read_text(encoding="utf-8").strip()

    def guarded(**kwargs):
        return verify_persistence_guard(
            **kwargs,
            git_probe=probe,
            fingerprint_from_path=fake_fingerprint,
            allowed_signers=_GUARD_ALLOWED_SIGNERS,
        )

    monkeypatch.setattr(native_live_run, "_verify_persistence_guard", guarded)


def _guard_incident_token(
    tmp_path: Path, world: dict[str, Path], *, expired: bool = False
) -> Path:
    """A SIGNED incident token bound to this run's id, failed check, and
    model/config identities (the #465 r1 signed-override contract)."""
    now = _dt.datetime.now(_dt.timezone.utc)
    issued = now - _dt.timedelta(hours=2)
    expires = (now - _dt.timedelta(hours=1)) if expired else (now + _dt.timedelta(hours=1))
    config_sha = _canonical_json_sha256(
        json.loads(world["config"].read_text(encoding="utf-8"))
    )
    token = {
        "schema_version": 1,
        "kind": "persistence_guard_incident_token",
        "incident": "INC-2026-07-10-pin-migration",
        "operator": _GUARD_TEST_PRINCIPAL,
        "reason": "planned pin bump mid-incident; verified manually",
        "issued_at": issued.isoformat(),
        "expires_at": expires.isoformat(),
        "scope": {
            "run_id": _GUARD_RUN_ID,
            "checks": [_CHECK_RUN_MANIFEST],
            "model_content_sha256": _GUARD_MODEL_SHA,
            "strategy_config_sha256": config_sha,
        },
    }
    path = tmp_path / "incident_token.json"
    path.write_text(json.dumps(token), encoding="utf-8")
    key_copy = tmp_path / "signing_key"
    key_copy.write_bytes(_GUARD_FIXTURE_KEY.read_bytes())
    key_copy.chmod(0o600)
    _subprocess.run(
        [
            "ssh-keygen", "-Y", "sign",
            "-f", str(key_copy),
            "-n", _SIGNATURE_NAMESPACE,
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def _run_guarded_persistence(tmp_path: Path, world: dict[str, Path], **overrides):
    live_state = tmp_path / "live_state.alpaca.json"
    trade_journal = tmp_path / "trades.jsonl"
    lifecycle_journal = tmp_path / "lifecycle.jsonl"
    runs_db = tmp_path / "runs.alpaca.db"
    inference = tmp_path / "inference.json"
    inference.write_text(json.dumps(_inference_payload()), encoding="utf-8")
    kwargs = dict(
        inference_json=inference,
        execution_output_json=tmp_path / "execution.json",
        commit_plan_output_json=tmp_path / "commit-plan.json",
        output_json=tmp_path / "native-bundle.json",
        broker_name="paper",
        execute_live=True,
        commit_persistence=True,
        run_id=_GUARD_RUN_ID,
        live_state_output_json=live_state,
        trade_journal_output_json=trade_journal,
        lifecycle_journal_output_json=lifecycle_journal,
        runs_db=runs_db,
        live_state_strategy="renquant_104_live",
        run_manifest_json=world["manifest"],
        strategy_config_json=world["config"],
        model_content_sha256=_GUARD_MODEL_SHA,
        repo_root=tmp_path,
    )
    kwargs.update(overrides)
    return run_native_live_candidate(**kwargs), live_state, trade_journal


def test_guarded_commit_persistence_binds_verified_identities_into_audit(
    monkeypatch, tmp_path: Path
) -> None:
    world = _guard_world(tmp_path)
    _install_guard_authorities(monkeypatch, world["manifest"])
    _install_live_commit_and_persistence_stubs(
        monkeypatch,
        live_state=tmp_path / "live_state.alpaca.json",
        trade_journal=tmp_path / "trades.jsonl",
        lifecycle_journal=tmp_path / "lifecycle.jsonl",
        runs_db=tmp_path / "runs.alpaca.db",
    )

    payload, _, _ = _run_guarded_persistence(tmp_path, world)

    guard = payload["metadata"]["persistence_audit"]["persistence_guard"]
    assert guard["armed"] is True
    assert guard["verified"] is True
    assert guard["enforced"] is True
    assert guard["override"] is None
    assert guard["run_id"] == _GUARD_RUN_ID
    assert guard["run_manifest"]["resolved_repos"] == {
        name: _guard_commit(name) for name in EXPERIMENT_PIN_REPOS
    }
    assert guard["artifacts"]["model_content_sha256"] == _GUARD_MODEL_SHA
    assert guard["artifacts"]["verified"] is True
    # the same block is exposed at metadata top level for readonly parity
    assert payload["metadata"]["persistence_guard"] == guard


def test_guard_blocks_mutation_before_any_side_effect(monkeypatch, tmp_path: Path) -> None:
    world = _guard_world(tmp_path)
    _install_guard_authorities(monkeypatch, world["manifest"], drift={"renquant-pipeline"})
    broker_calls: list[dict] = []

    def recording_live_commit(**kwargs):
        broker_calls.append(kwargs)
        raise AssertionError("broker must not be reached when the guard blocks")

    monkeypatch.setattr(
        native_live_run, "_live_commit_execution_payload", recording_live_commit
    )
    monkeypatch.setattr(
        native_live_run,
        "_commit_live_persistence",
        lambda *_a, **_k: (_ for _ in ()).throw(
            AssertionError("persistence must not be reached when the guard blocks")
        ),
    )

    with pytest.raises(PersistenceGuardError, match="FAILED CLOSED"):
        _run_guarded_persistence(tmp_path, world)

    assert broker_calls == []
    assert not (tmp_path / "live_state.alpaca.json").exists()
    assert not (tmp_path / "trades.jsonl").exists()
    assert not (tmp_path / "execution.json").exists()
    assert not (tmp_path / "native-bundle.json").exists()


def test_guard_override_with_valid_incident_token_is_stamped(
    monkeypatch, tmp_path: Path
) -> None:
    world = _guard_world(tmp_path)
    _install_guard_authorities(monkeypatch, world["manifest"], drift={"renquant-pipeline"})
    _install_live_commit_and_persistence_stubs(
        monkeypatch,
        live_state=tmp_path / "live_state.alpaca.json",
        trade_journal=tmp_path / "trades.jsonl",
        lifecycle_journal=tmp_path / "lifecycle.jsonl",
        runs_db=tmp_path / "runs.alpaca.db",
    )
    token = _guard_incident_token(tmp_path, world)

    payload, _, _ = _run_guarded_persistence(
        tmp_path, world, incident_token_json=token
    )

    guard = payload["metadata"]["persistence_audit"]["persistence_guard"]
    assert guard["verified"] is False
    assert guard["override"]["incident"] == "INC-2026-07-10-pin-migration"
    assert guard["override"]["operator"] == _GUARD_TEST_PRINCIPAL
    assert guard["override"]["overridden_checks"] == ["run_manifest"]
    assert guard["override"]["signature"]["verified"] is True
    assert guard["override"]["signature"]["principal"] == _GUARD_TEST_PRINCIPAL
    assert guard["override"]["scope"]["model_content_sha256"] == _GUARD_MODEL_SHA
    assert guard["failures"][0]["check"] == "run_manifest"


def test_guard_expired_token_blocks_mutation(monkeypatch, tmp_path: Path) -> None:
    world = _guard_world(tmp_path)
    _install_guard_authorities(monkeypatch, world["manifest"], drift={"renquant-pipeline"})
    monkeypatch.setattr(
        native_live_run,
        "_live_commit_execution_payload",
        lambda **_k: (_ for _ in ()).throw(AssertionError("broker must not be reached")),
    )
    token = _guard_incident_token(tmp_path, world, expired=True)

    with pytest.raises(IncidentTokenError, match="EXPIRED"):
        _run_guarded_persistence(tmp_path, world, incident_token_json=token)

    assert not (tmp_path / "live_state.alpaca.json").exists()


def test_guard_unsigned_token_blocks_mutation(monkeypatch, tmp_path: Path) -> None:
    """A fabricated (unsigned) token JSON never unblocks a live mutation."""
    world = _guard_world(tmp_path)
    _install_guard_authorities(monkeypatch, world["manifest"], drift={"renquant-pipeline"})
    monkeypatch.setattr(
        native_live_run,
        "_live_commit_execution_payload",
        lambda **_k: (_ for _ in ()).throw(AssertionError("broker must not be reached")),
    )
    token = _guard_incident_token(tmp_path, world)
    Path(str(token) + ".sig").unlink()  # fabricate: payload without signature

    with pytest.raises(IncidentTokenError, match="NO detached signature"):
        _run_guarded_persistence(tmp_path, world, incident_token_json=token)

    assert not (tmp_path / "live_state.alpaca.json").exists()


def test_partial_guard_arming_fails_closed(tmp_path: Path) -> None:
    inference = tmp_path / "inference.json"
    inference.write_text(json.dumps(_inference_payload()), encoding="utf-8")
    with pytest.raises(ValueError, match="armed but incomplete"):
        run_native_live_candidate(
            inference_json=inference,
            output_json=tmp_path / "native-bundle.json",
            run_manifest_json=tmp_path / "run_manifest.json",
        )


def test_readonly_guard_soak_records_would_have_blocked(monkeypatch, tmp_path: Path) -> None:
    world = _guard_world(tmp_path)
    _install_guard_authorities(monkeypatch, world["manifest"], drift={"renquant-pipeline"})
    inference = tmp_path / "inference.json"
    inference.write_text(json.dumps(_inference_payload()), encoding="utf-8")

    payload = run_native_live_candidate(
        inference_json=inference,
        output_json=tmp_path / "native-bundle.json",
        run_manifest_json=world["manifest"],
        strategy_config_json=world["config"],
        model_content_sha256=_GUARD_MODEL_SHA,
        repo_root=tmp_path,
    )

    guard = payload["metadata"]["persistence_guard"]
    assert guard["enforced"] is False
    assert guard["verified"] is False
    assert guard["would_have_blocked"] is True
    assert payload["metadata"]["readonly"] is True
    assert "persistence_audit" not in payload["metadata"]


def test_legacy_readonly_invocation_is_byte_identical(tmp_path: Path) -> None:
    inference = tmp_path / "inference.json"
    inference.write_text(json.dumps(_inference_payload()), encoding="utf-8")

    payload = run_native_live_candidate(
        inference_json=inference,
        output_json=tmp_path / "native-bundle.json",
    )

    assert "persistence_guard" not in payload["metadata"]
    assert "persistence_guard" not in json.dumps(payload)


def test_unguarded_commit_persistence_is_visibly_marked(monkeypatch, tmp_path: Path) -> None:
    live_state = tmp_path / "live_state.alpaca.json"
    trade_journal = tmp_path / "trades.jsonl"
    lifecycle_journal = tmp_path / "lifecycle.jsonl"
    runs_db = tmp_path / "runs.alpaca.db"
    inference = tmp_path / "inference.json"
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
        output_json=tmp_path / "native-bundle.json",
        broker_name="paper",
        execute_live=True,
        commit_persistence=True,
        run_id=_GUARD_RUN_ID,
        live_state_output_json=live_state,
        trade_journal_output_json=trade_journal,
        lifecycle_journal_output_json=lifecycle_journal,
        runs_db=runs_db,
        live_state_strategy="renquant_104_live",
    )

    guard = payload["metadata"]["persistence_audit"]["persistence_guard"]
    assert guard["armed"] is False
    assert guard["verified"] is False
    assert "UNGUARDED" in guard["note"]
    # the pre-guard audit fields are unchanged
    assert payload["metadata"]["persistence_audit"]["committed_mutation_count"] == 2


def test_native_live_run_cli_accepts_guard_args(monkeypatch, tmp_path: Path, capsys) -> None:
    captured: dict = {}

    def fake_run(**kwargs):
        captured.update(kwargs)
        return {"schema_version": 1}

    monkeypatch.setattr(native_live_run, "run_native_live_candidate", fake_run)

    rc = main([
        "--inference-json", str(tmp_path / "inference.json"),
        "--output-json", str(tmp_path / "bundle.json"),
        "--run-id", _GUARD_RUN_ID,
        "--run-manifest-json", str(tmp_path / "run_manifest.json"),
        "--strategy-config-json", str(tmp_path / "strategy_config.json"),
        "--model-content-sha256", _GUARD_MODEL_SHA,
        "--calibrator-content-sha256", "sha256:fp-cal-1",
        "--decision-snapshot-digest", "digest-1",
        "--incident-token-json", str(tmp_path / "token.json"),
        "--incident-token-signature", str(tmp_path / "token.json.sig"),
        "--repo-root", str(tmp_path),
    ])

    assert rc == 0
    assert captured["run_manifest_json"] == str(tmp_path / "run_manifest.json")
    assert captured["strategy_config_json"] == str(tmp_path / "strategy_config.json")
    assert captured["model_content_sha256"] == _GUARD_MODEL_SHA
    assert captured["calibrator_content_sha256"] == "sha256:fp-cal-1"
    assert captured["decision_snapshot_digest"] == "digest-1"
    assert captured["incident_token_json"] == str(tmp_path / "token.json")
    assert captured["incident_token_signature"] == str(tmp_path / "token.json.sig")
    assert captured["repo_root"] == str(tmp_path)
