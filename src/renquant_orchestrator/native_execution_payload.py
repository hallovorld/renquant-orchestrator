"""Build readonly native execution payloads from native inference output."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from renquant_execution import ExecutionContext, ExecutionPipeline, execution_payload, normalize_order_intent


def _load_json(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"payload must be a JSON object: {path}")
    return payload


def _order_intents(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("order_intents")
    if not isinstance(raw, list):
        raise ValueError("inference payload missing required list field: order_intents")
    intents: list[dict[str, Any]] = []
    for idx, row in enumerate(raw):
        if not isinstance(row, dict):
            raise ValueError(f"order_intents[{idx}] must be an object")
        intents.append(dict(row))
    return intents


def _readonly_submitter(
    _broker_name: str,
    order_intents: list[dict[str, Any]],
    dry_run: bool,
) -> list[dict[str, Any]]:
    if not dry_run:
        raise ValueError("native execution payload generation is readonly-only")
    submitted: list[dict[str, Any]] = []
    for idx, intent in enumerate(order_intents, start=1):
        submitted.append({
            "order_id": f"readonly-dry-{idx}",
            "status": "dry_run",
            **normalize_order_intent(intent),
        })
    return submitted


def build_readonly_execution_payload(
    *,
    inference_payload: dict[str, Any],
    broker_name: str = "readonly-native",
) -> dict[str, Any]:
    """Return an execution payload without connecting to any live broker."""
    ctx = ExecutionContext(
        broker_name=broker_name,
        order_intents=_order_intents(inference_payload),
        dry_run=True,
    )
    result = ExecutionPipeline(_readonly_submitter).run(ctx)
    if not result.ok:
        raise ValueError("readonly native execution payload generation failed")
    payload = execution_payload(ctx)
    if not ctx.order_intents:
        payload["execution_audit"] = [
            {
                "kind": "bridge_context",
                "n_order_intents": 0,
                "reason": "no_execution_rows",
            }
        ]
    payload["readonly"] = True
    payload["inference_source"] = inference_payload.get("source")
    return payload


def write_readonly_execution_payload(
    *,
    inference_json: str | Path,
    output_json: str | Path,
    broker_name: str = "readonly-native",
) -> dict[str, Any]:
    payload = build_readonly_execution_payload(
        inference_payload=_load_json(inference_json),
        broker_name=broker_name,
    )
    out = Path(output_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="renquant-orchestrator native-execution-payload")
    parser.add_argument("--inference-json", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--broker-name", default="readonly-native")
    args = parser.parse_args(argv)

    payload = write_readonly_execution_payload(
        inference_json=args.inference_json,
        output_json=args.output_json,
        broker_name=args.broker_name,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


__all__ = [
    "build_readonly_execution_payload",
    "main",
    "write_readonly_execution_payload",
]


if __name__ == "__main__":
    raise SystemExit(main())
