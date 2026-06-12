"""Native live-run candidate assembled from native payload contracts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from renquant_execution import build_live_commit_plan

from .native_execution_payload import build_readonly_execution_payload
from .native_live_bundle import build_native_live_bundle


def _load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"payload must be a JSON object: {path}")
    return payload


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _live_commit_execution_payload(
    *,
    broker_name: str,
    order_intents: list[dict[str, Any]],
    dry_run: bool,
) -> dict[str, Any]:
    if broker_name.startswith("readonly"):
        raise ValueError("--execute-live requires a broker-name that can commit orders")
    try:
        from renquant_execution import execute_live_commit, get_broker
    except ImportError as exc:
        raise RuntimeError(
            "--execute-live requires renquant-execution with execute_live_commit"
        ) from exc

    broker = get_broker(broker_name)
    broker.connect()
    try:
        plan = execute_live_commit(
            broker=broker,
            order_intents=order_intents,
            dry_run=dry_run,
        )
    finally:
        broker.disconnect()

    payload = plan.to_payload()
    payload["source"] = "renquant_execution.execution"
    payload["dry_run"] = bool(dry_run)
    payload["live_commit_source"] = "renquant_execution.live_commit_plan"
    return payload


def _commit_plan_payload(execution_payload: dict[str, Any]) -> dict[str, Any]:
    if execution_payload.get("readonly", True):
        return build_live_commit_plan(execution_payload).to_payload()
    payload = dict(execution_payload)
    payload["source"] = "renquant_execution.live_commit_plan"
    return payload


def _commit_live_persistence(plan: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
    try:
        from renquant_execution import commit_live_persistence
    except ImportError as exc:
        raise RuntimeError(
            "--commit-persistence requires renquant-execution with "
            "commit_live_persistence"
        ) from exc
    return commit_live_persistence(plan, **kwargs)


def _commit_persistence_payload(
    execution_payload: dict[str, Any],
    *,
    live_state_output_json: str | Path,
    trade_journal_output_json: str | Path,
) -> dict[str, Any]:
    return _commit_live_persistence(
        _commit_plan_payload(execution_payload),
        live_state_path=live_state_output_json,
        trade_journal_path=trade_journal_output_json,
    )


def _live_state_contract_payload(
    *,
    strategy_dir: str | Path,
    broker_name: str,
    runs_db: str | Path | None,
    strategy: str,
    max_age_days: int | None,
) -> dict[str, Any]:
    try:
        from renquant_pipeline import load_live_state_contract
    except ImportError as exc:
        raise RuntimeError(
            "native live-state contract requires renquant-pipeline with "
            "load_live_state_contract; merge/pin the pipeline contract first"
        ) from exc

    contract = load_live_state_contract(
        strategy_dir,
        broker_name,
        runs_db=runs_db,
        strategy=strategy,
        max_age_days=max_age_days,
    )
    return contract.to_payload()


def _live_state_metadata(contract_payload: dict[str, Any]) -> dict[str, Any]:
    account_snapshot = contract_payload.get("account_snapshot")
    positions = account_snapshot.get("positions") if isinstance(account_snapshot, dict) else None
    return {
        "schema_version": contract_payload.get("schema_version"),
        "source": contract_payload.get("source"),
        "path": contract_payload.get("path"),
        "used_legacy": bool(contract_payload.get("used_legacy")),
        "warnings": list(contract_payload.get("warnings") or []),
        "account_snapshot_position_count": len(positions) if isinstance(positions, dict) else 0,
    }


def _attach_live_state_contract(
    inference_payload: dict[str, Any],
    metadata_payload: dict[str, Any] | None,
    *,
    strategy_dir: str | Path | None,
    broker_name: str,
    live_state_broker_name: str | None,
    runs_db: str | Path | None,
    strategy: str,
    max_age_days: int | None,
    output_json: str | Path | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    if strategy_dir is None:
        return inference_payload, metadata_payload

    contract_payload = _live_state_contract_payload(
        strategy_dir=strategy_dir,
        broker_name=live_state_broker_name or broker_name,
        runs_db=runs_db,
        strategy=strategy,
        max_age_days=max_age_days,
    )
    if output_json:
        _write_json(output_json, contract_payload)

    enriched_inference = dict(inference_payload)
    if "account_snapshot" not in enriched_inference and contract_payload.get("account_snapshot"):
        enriched_inference["account_snapshot"] = dict(contract_payload["account_snapshot"])

    metadata = dict(metadata_payload or {})
    metadata["live_state_contract"] = _live_state_metadata(contract_payload)
    if output_json:
        metadata["live_state_contract"]["artifact_path"] = str(output_json)
    return enriched_inference, metadata


def _candidate_metadata(
    *,
    broker_name: str,
    metadata_payload: dict[str, Any] | None,
    readonly: bool,
) -> dict[str, Any]:
    metadata = dict(metadata_payload or {})
    metadata.setdefault("stage", "native_live_run_candidate")
    metadata.setdefault("readonly", readonly)
    metadata.setdefault("broker_name", broker_name)
    metadata.setdefault("runner", "renquant_orchestrator.native_live_run")
    return metadata


def run_native_live_candidate(
    *,
    inference_json: str | Path,
    output_json: str | Path,
    execution_json: str | Path | None = None,
    execution_output_json: str | Path | None = None,
    commit_plan_output_json: str | Path | None = None,
    metadata_json: str | Path | None = None,
    strategy_dir: str | Path | None = None,
    runs_db: str | Path | None = None,
    live_state_broker_name: str | None = None,
    live_state_strategy: str = "renquant_104",
    max_live_state_age_days: int | None = None,
    live_state_contract_output_json: str | Path | None = None,
    broker_name: str = "readonly-native",
    execute_live: bool = False,
    dry_run: bool = False,
    commit_persistence: bool = False,
    live_state_output_json: str | Path | None = None,
    trade_journal_output_json: str | Path | None = None,
) -> dict[str, Any]:
    """Build a native live bundle without importing umbrella live.runner."""
    if execute_live and execution_json:
        raise ValueError("--execute-live cannot be combined with --execution-json")
    if commit_persistence and not execute_live:
        raise ValueError("--commit-persistence requires --execute-live")
    if commit_persistence and dry_run:
        raise ValueError("--commit-persistence cannot be combined with --dry-run")
    if commit_persistence and (not live_state_output_json or not trade_journal_output_json):
        raise ValueError(
            "--commit-persistence requires --live-state-output-json and "
            "--trade-journal-output-json"
        )
    inference_payload = _load_json(inference_json)
    metadata_payload = _load_json(metadata_json) if metadata_json else None
    inference_payload, metadata_payload = _attach_live_state_contract(
        inference_payload,
        metadata_payload,
        strategy_dir=strategy_dir,
        broker_name=broker_name,
        live_state_broker_name=live_state_broker_name,
        runs_db=runs_db,
        strategy=live_state_strategy,
        max_age_days=max_live_state_age_days,
        output_json=live_state_contract_output_json,
    )
    if execution_json:
        execution_payload = _load_json(execution_json)
    elif execute_live:
        execution_payload = _live_commit_execution_payload(
            broker_name=broker_name,
            order_intents=list(inference_payload.get("order_intents") or []),
            dry_run=dry_run,
        )
    else:
        execution_payload = build_readonly_execution_payload(
            inference_payload=inference_payload,
            broker_name=broker_name,
        )
    if commit_persistence:
        execution_payload = _commit_persistence_payload(
            execution_payload,
            live_state_output_json=live_state_output_json,
            trade_journal_output_json=trade_journal_output_json,
        )
    if execution_output_json:
        _write_json(execution_output_json, execution_payload)
    if commit_plan_output_json:
        _write_json(commit_plan_output_json, _commit_plan_payload(execution_payload))
    if execution_payload.get("persistence_audit"):
        metadata_payload = dict(metadata_payload or {})
        metadata_payload["persistence_audit"] = dict(execution_payload["persistence_audit"])

    bundle = build_native_live_bundle(
        inference_payload=inference_payload,
        execution_payload=execution_payload,
        metadata=_candidate_metadata(
            broker_name=broker_name,
            metadata_payload=metadata_payload,
            readonly=bool(execution_payload.get("readonly", not execute_live)),
        ),
    )
    _write_json(output_json, bundle)
    return bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="renquant-orchestrator native-live-run")
    parser.add_argument("--inference-json", required=True)
    parser.add_argument("--execution-json", default=None)
    parser.add_argument("--execution-output-json", default=None)
    parser.add_argument("--commit-plan-output-json", default=None)
    parser.add_argument("--metadata-json", default=None)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--broker-name", default="readonly-native")
    parser.add_argument(
        "--execute-live",
        action="store_true",
        help="submit order intents through renquant-execution live commit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="with --execute-live, validate execution without placing orders",
    )
    parser.add_argument(
        "--commit-persistence",
        action="store_true",
        help="with --execute-live, commit filled order persistence artifacts",
    )
    parser.add_argument("--live-state-output-json", default=None)
    parser.add_argument("--trade-journal-output-json", default=None)
    parser.add_argument("--strategy-dir", default=None)
    parser.add_argument("--runs-db", default=None)
    parser.add_argument("--live-state-broker-name", default=None)
    parser.add_argument("--live-state-strategy", default="renquant_104")
    parser.add_argument("--max-live-state-age-days", type=int, default=None)
    parser.add_argument("--live-state-contract-output-json", default=None)
    args = parser.parse_args(argv)

    bundle = run_native_live_candidate(
        inference_json=args.inference_json,
        execution_json=args.execution_json,
        execution_output_json=args.execution_output_json,
        commit_plan_output_json=args.commit_plan_output_json,
        metadata_json=args.metadata_json,
        output_json=args.output_json,
        broker_name=args.broker_name,
        execute_live=args.execute_live,
        dry_run=args.dry_run,
        commit_persistence=args.commit_persistence,
        live_state_output_json=args.live_state_output_json,
        trade_journal_output_json=args.trade_journal_output_json,
        strategy_dir=args.strategy_dir,
        runs_db=args.runs_db,
        live_state_broker_name=args.live_state_broker_name,
        live_state_strategy=args.live_state_strategy,
        max_live_state_age_days=args.max_live_state_age_days,
        live_state_contract_output_json=args.live_state_contract_output_json,
    )
    print(json.dumps(bundle, indent=2, sort_keys=True))
    return 0


__all__ = [
    "main",
    "run_native_live_candidate",
]


if __name__ == "__main__":
    raise SystemExit(main())
