"""Build native live-run bundles for live.runner offboard parity.

The remaining umbrella bridge jobs can only be removed after the native path
emits the same decision trace, order intents, and state mutations as
``live.runner``. This module owns the native bundle envelope used by
``live-parity-fixture``; it performs no broker mutation.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"payload must be a JSON object: {path}")
    return payload


def _list_field(payload: dict[str, Any], key: str, *, required: bool) -> list[dict[str, Any]] | None:
    if key not in payload:
        if required:
            raise ValueError(f"payload missing required list field: {key}")
        return None
    value = payload[key]
    if not isinstance(value, list):
        raise ValueError(f"payload field must be a list: {key}")
    rows: list[dict[str, Any]] = []
    for idx, row in enumerate(value):
        if not isinstance(row, dict):
            raise ValueError(f"payload field {key}[{idx}] must be an object")
        rows.append(dict(row))
    return rows


def _metadata_row(
    *,
    order_intents: list[dict[str, Any]],
    submitted_orders: list[dict[str, Any]] | None,
    reason: str,
) -> dict[str, Any]:
    return {
        "stage": "native_live_bundle",
        "reason": reason,
        "n_order_intents": len(order_intents),
        "n_submitted_orders": len(submitted_orders or []),
    }


def build_native_live_bundle(
    *,
    inference_payload: dict[str, Any],
    execution_payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a parity-ready native live bundle from native pipeline outputs."""
    decision_trace = _list_field(inference_payload, "decision_trace", required=True)
    order_intents = _list_field(inference_payload, "order_intents", required=True)
    assert decision_trace is not None
    assert order_intents is not None

    execution_payload = execution_payload or {}
    submitted_orders = _list_field(execution_payload, "submitted_orders", required=False)
    execution_audit = (
        _list_field(execution_payload, "execution_audit", required=False)
        or _list_field(execution_payload, "audit_rows", required=False)
    )
    state_mutations = _list_field(execution_payload, "state_mutations", required=False)

    bundle: dict[str, Any] = {
        "schema_version": 1,
        "source": "native_live_bundle",
        "decision_trace": decision_trace,
        "order_intents": order_intents,
    }
    if metadata:
        bundle["metadata"] = dict(metadata)

    if state_mutations is not None:
        bundle["state_mutations"] = state_mutations
    elif submitted_orders is not None:
        bundle["submitted_orders"] = submitted_orders
        if execution_audit is not None:
            bundle["execution_audit"] = execution_audit
    elif execution_audit is not None:
        bundle["execution_audit"] = execution_audit
    else:
        bundle["execution_audit"] = [
            _metadata_row(
                order_intents=order_intents,
                submitted_orders=None,
                reason="no_execution_payload",
            )
        ]
    return bundle


def write_native_live_bundle(
    *,
    inference_json: str | Path,
    output_json: str | Path,
    execution_json: str | Path | None = None,
    metadata_json: str | Path | None = None,
) -> dict[str, Any]:
    bundle = build_native_live_bundle(
        inference_payload=_load_json(inference_json),
        execution_payload=_load_json(execution_json) if execution_json else None,
        metadata=_load_json(metadata_json) if metadata_json else None,
    )
    out = Path(output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="renquant-orchestrator native-live-bundle")
    parser.add_argument("--inference-json", required=True)
    parser.add_argument("--execution-json", default=None)
    parser.add_argument("--metadata-json", default=None)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)

    bundle = write_native_live_bundle(
        inference_json=args.inference_json,
        execution_json=args.execution_json,
        metadata_json=args.metadata_json,
        output_json=args.output_json,
    )
    print(json.dumps(bundle, indent=2, sort_keys=True))
    return 0


__all__ = [
    "build_native_live_bundle",
    "main",
    "write_native_live_bundle",
]


if __name__ == "__main__":
    raise SystemExit(main())
