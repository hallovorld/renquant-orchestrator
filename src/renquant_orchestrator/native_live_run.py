"""Native live-run candidate assembled from native payload contracts.

R5 persistence guard — SHADOW-SOAK STAGE (T6/D6-F3, doc/design/2026-07-10-
architecture-compliance-registry.md; scope corrected per Codex r1 on #465):
because ``--execute-live`` submits broker orders and ``--commit-persistence``
(#107) mutates live-state/trade-journal artifacts, this module supports an
OPT-IN fail-closed identity gate: pass ``--run-manifest-json`` +
``--strategy-config-json`` + ``--model-content-sha256`` (plus optionally
``--calibrator-content-sha256`` / ``--decision-snapshot-digest`` /
``--incident-token-json`` [+ ``--incident-token-signature``]) and every
verification in :mod:`renquant_orchestrator.native_persistence_guard` runs
BEFORE any broker submission or persistence mutation, failing closed on any
mismatch unless a SIGNED, expiring, single-run, identity-bound operator
incident token covers the failure. The verified identities are stamped into
the bundle metadata's ``persistence_audit``.

**This stage does NOT protect the path.** Arming is a caller decision: an
invocation without the guard arguments still submits orders and mutates
persistence UNVERIFIED, exactly as before — it is only stamped
``persistence_guard.armed: false`` in the bundle audit so the unverified
state is observable per run. No unarmed broker submit or persistence
mutation may be characterized as guarded. The enforcement default-flip
(guard REQUIRED for ``--commit-persistence``) is a separate, pre-registered
behavior-change step; its frozen rollout plan (soak criteria, operator key
replacement, orchestrator self-pin) lives in
``doc/progress/2026-07-10-r5-native-persistence-guard.md``.
"""
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
    runs_db_path: str | Path | None,
    lifecycle_journal_output_json: str | Path | None,
    live_state_strategy: str,
    run_id: str,
) -> dict[str, Any]:
    return _commit_live_persistence(
        _commit_plan_payload(execution_payload),
        live_state_path=live_state_output_json,
        trade_journal_path=trade_journal_output_json,
        run_id=run_id,
        runs_db_path=runs_db_path,
        strategy=live_state_strategy,
        lifecycle_journal_path=lifecycle_journal_output_json,
    )


def _verify_persistence_guard(**kwargs: Any) -> dict[str, Any]:
    """Indirection point (same convention as ``_commit_live_persistence``) so
    tests can inject probes/fingerprints; the real implementation is the R5
    guard module."""
    from .native_persistence_guard import verify_persistence_guard  # noqa: PLC0415

    return verify_persistence_guard(**kwargs)


def _unguarded_persistence_marker() -> dict[str, Any]:
    """Telemetry stamp for a persistence commit that ran WITHOUT identity
    verification (guard not armed). R5 requires the unverified state to be
    observable per run, not assumed."""
    return {
        "armed": False,
        "verified": False,
        "note": (
            "UNGUARDED persistence commit: no run-manifest/artifact "
            "verification was performed on this mutation (R5 guard not "
            "armed; see doc/design/2026-07-10-architecture-compliance-"
            "registry.md T6/R5 and native_persistence_guard.py)"
        ),
    }


def _post_live_persistence_alert(ntfy_url: str, execution_payload: dict[str, Any]) -> bool:
    try:
        from renquant_execution import post_live_persistence_alert
    except ImportError as exc:
        raise RuntimeError(
            "--persistence-ntfy-url requires renquant-execution with "
            "post_live_persistence_alert"
        ) from exc
    return bool(post_live_persistence_alert(ntfy_url, execution_payload))


def _persistence_alert_status(
    ntfy_url: str,
    execution_payload: dict[str, Any],
) -> dict[str, Any]:
    try:
        return {
            "attempted": True,
            "ok": _post_live_persistence_alert(ntfy_url, execution_payload),
        }
    except Exception as exc:
        return {
            "attempted": True,
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


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
    run_id: str | None,
) -> dict[str, Any]:
    metadata = dict(metadata_payload or {})
    metadata.setdefault("stage", "native_live_run_candidate")
    metadata.setdefault("readonly", readonly)
    metadata.setdefault("broker_name", broker_name)
    metadata.setdefault("runner", "renquant_orchestrator.native_live_run")
    if run_id:
        metadata.setdefault("run_id", run_id)
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
    run_id: str | None = None,
    broker_name: str = "readonly-native",
    execute_live: bool = False,
    dry_run: bool = False,
    commit_persistence: bool = False,
    live_state_output_json: str | Path | None = None,
    trade_journal_output_json: str | Path | None = None,
    lifecycle_journal_output_json: str | Path | None = None,
    persistence_ntfy_url: str | None = None,
    run_manifest_json: str | Path | None = None,
    strategy_config_json: str | Path | None = None,
    model_content_sha256: str | None = None,
    calibrator_content_sha256: str | None = None,
    decision_snapshot_digest: str | None = None,
    incident_token_json: str | Path | None = None,
    incident_token_signature: str | Path | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Build a native live bundle without importing umbrella live.runner.

    Passing ANY of ``run_manifest_json`` / ``strategy_config_json`` /
    ``model_content_sha256`` / ``calibrator_content_sha256`` /
    ``decision_snapshot_digest`` / ``incident_token_json`` /
    ``incident_token_signature`` ARMS the R5 persistence guard (see module
    docstring — shadow-soak stage, opt-in): the first three are then all
    required (partial arming fails closed), and verification runs before any
    broker or persistence side effect. On ``--execute-live`` a failing
    verdict raises; on readonly invocations it is recorded as
    ``would_have_blocked`` (shadow soak). Without any of them, this call is
    the pre-existing UNVERIFIED #107 behavior, only made visible in the audit.
    """
    guard_inputs = {
        "run_manifest_json": run_manifest_json,
        "strategy_config_json": strategy_config_json,
        "model_content_sha256": model_content_sha256,
        "calibrator_content_sha256": calibrator_content_sha256,
        "decision_snapshot_digest": decision_snapshot_digest,
        "incident_token_json": incident_token_json,
        "incident_token_signature": incident_token_signature,
    }
    guard_armed = any(value is not None for value in guard_inputs.values())
    if guard_armed:
        missing = [
            name
            for name in (
                "run_manifest_json",
                "strategy_config_json",
                "model_content_sha256",
            )
            if guard_inputs[name] is None
        ]
        if missing:
            raise ValueError(
                "persistence guard is armed but incomplete (fail-closed): "
                "--run-manifest-json, --strategy-config-json, and "
                "--model-content-sha256 are required together; missing: "
                + ", ".join(missing)
            )
    if execute_live and execution_json:
        raise ValueError("--execute-live cannot be combined with --execution-json")
    if persistence_ntfy_url and not commit_persistence:
        raise ValueError("--persistence-ntfy-url requires --commit-persistence")
    if commit_persistence and not execute_live:
        raise ValueError("--commit-persistence requires --execute-live")
    if commit_persistence and dry_run:
        raise ValueError("--commit-persistence cannot be combined with --dry-run")
    if commit_persistence and (not live_state_output_json or not trade_journal_output_json):
        raise ValueError(
            "--commit-persistence requires --live-state-output-json and "
            "--trade-journal-output-json"
        )
    if commit_persistence and (
        not run_id or not runs_db or not lifecycle_journal_output_json
    ):
        raise ValueError(
            "--commit-persistence requires --run-id, --runs-db, and "
            "--lifecycle-journal-output-json for persistence audit evidence"
        )
    inference_payload = _load_json(inference_json)
    metadata_payload = _load_json(metadata_json) if metadata_json else None

    # R5: verification happens HERE — before the live-state contract output,
    # before any broker submission, and before any persistence mutation. A
    # PersistenceGuardError from this call means nothing was touched.
    guard_result: dict[str, Any] | None = None
    if guard_armed:
        raw_meta = inference_payload.get("metadata")
        guard_result = _verify_persistence_guard(
            run_manifest_json=run_manifest_json,
            strategy_config_json=strategy_config_json,
            model_content_sha256=model_content_sha256,
            calibrator_content_sha256=calibrator_content_sha256,
            decision_snapshot_digest=decision_snapshot_digest,
            inference_metadata=raw_meta if isinstance(raw_meta, dict) else None,
            run_id=run_id,
            strategy_dir=strategy_dir,
            repo_root=repo_root,
            incident_token_json=incident_token_json,
            incident_token_signature=incident_token_signature,
            enforce=bool(execute_live),
        )

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
            runs_db_path=runs_db,
            lifecycle_journal_output_json=lifecycle_journal_output_json,
            live_state_strategy=live_state_strategy,
            run_id=run_id,
        )
    persistence_alert: dict[str, Any] | None = None
    if persistence_ntfy_url:
        persistence_alert = _persistence_alert_status(
            persistence_ntfy_url,
            execution_payload,
        )
    if execution_output_json:
        _write_json(execution_output_json, execution_payload)
    if commit_plan_output_json:
        _write_json(commit_plan_output_json, _commit_plan_payload(execution_payload))
    if execution_payload.get("persistence_audit"):
        metadata_payload = dict(metadata_payload or {})
        audit = dict(execution_payload["persistence_audit"])
        # Bind the audit to VERIFIED identities (or visibly mark it
        # unverified): the audit row for a live mutation must say which
        # pins/artifact shas were checked, by what, and with what verdict —
        # not merely that a mutation happened.
        audit["persistence_guard"] = (
            dict(guard_result) if guard_result is not None else _unguarded_persistence_marker()
        )
        metadata_payload["persistence_audit"] = audit
    if guard_result is not None:
        metadata_payload = dict(metadata_payload or {})
        metadata_payload["persistence_guard"] = dict(guard_result)
    if persistence_alert:
        metadata_payload = dict(metadata_payload or {})
        metadata_payload["persistence_alert"] = persistence_alert

    bundle = build_native_live_bundle(
        inference_payload=inference_payload,
        execution_payload=execution_payload,
        metadata=_candidate_metadata(
            broker_name=broker_name,
            metadata_payload=metadata_payload,
            readonly=bool(execution_payload.get("readonly", not execute_live)),
            run_id=run_id,
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
    parser.add_argument("--run-id", default=None)
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
    parser.add_argument("--lifecycle-journal-output-json", default=None)
    parser.add_argument(
        "--persistence-ntfy-url",
        default=None,
        help="with --commit-persistence, post a best-effort native persistence alert",
    )
    parser.add_argument("--strategy-dir", default=None)
    parser.add_argument("--runs-db", default=None)
    parser.add_argument("--live-state-broker-name", default=None)
    parser.add_argument("--live-state-strategy", default="renquant_104")
    parser.add_argument("--max-live-state-age-days", type=int, default=None)
    parser.add_argument("--live-state-contract-output-json", default=None)
    # R5 persistence-guard surface (module main only, like the live-commit
    # flags; the top-level cli.py subparser stays readonly-only by design).
    parser.add_argument(
        "--run-manifest-json",
        default=None,
        help="immutable run manifest (repos+commits); arms fail-closed pin "
        "verification before any live/persistence mutation",
    )
    parser.add_argument(
        "--strategy-config-json",
        default=None,
        help="strategy config whose resolved model/calibrator artifacts must "
        "match the frozen shas (unified fingerprint impl)",
    )
    parser.add_argument("--model-content-sha256", default=None)
    parser.add_argument("--calibrator-content-sha256", default=None)
    parser.add_argument(
        "--decision-snapshot-digest",
        default=None,
        help="optional frozen decision-snapshot digest the inference payload "
        "metadata must carry as verified",
    )
    parser.add_argument(
        "--incident-token-json",
        default=None,
        help="SIGNED expiring single-run operator incident token (the ONLY "
        "guard override; unsigned/forged/expired/mis-scoped tokens never "
        "unblock)",
    )
    parser.add_argument(
        "--incident-token-signature",
        default=None,
        help="detached ssh-keygen -Y signature over the token file "
        "(default: <token>.sig), verified against the committed "
        "security/persistence_guard_allowed_signers",
    )
    parser.add_argument("--repo-root", default=None)
    args = parser.parse_args(argv)

    bundle = run_native_live_candidate(
        inference_json=args.inference_json,
        execution_json=args.execution_json,
        execution_output_json=args.execution_output_json,
        commit_plan_output_json=args.commit_plan_output_json,
        metadata_json=args.metadata_json,
        output_json=args.output_json,
        run_id=args.run_id,
        broker_name=args.broker_name,
        execute_live=args.execute_live,
        dry_run=args.dry_run,
        commit_persistence=args.commit_persistence,
        live_state_output_json=args.live_state_output_json,
        trade_journal_output_json=args.trade_journal_output_json,
        lifecycle_journal_output_json=args.lifecycle_journal_output_json,
        persistence_ntfy_url=args.persistence_ntfy_url,
        strategy_dir=args.strategy_dir,
        runs_db=args.runs_db,
        live_state_broker_name=args.live_state_broker_name,
        live_state_strategy=args.live_state_strategy,
        max_live_state_age_days=args.max_live_state_age_days,
        live_state_contract_output_json=args.live_state_contract_output_json,
        run_manifest_json=args.run_manifest_json,
        strategy_config_json=args.strategy_config_json,
        model_content_sha256=args.model_content_sha256,
        calibrator_content_sha256=args.calibrator_content_sha256,
        decision_snapshot_digest=args.decision_snapshot_digest,
        incident_token_json=args.incident_token_json,
        incident_token_signature=args.incident_token_signature,
        repo_root=args.repo_root,
    )
    print(json.dumps(bundle, indent=2, sort_keys=True))
    return 0


__all__ = [
    "main",
    "run_native_live_candidate",
]


if __name__ == "__main__":
    raise SystemExit(main())
