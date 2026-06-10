"""Readonly native live-run candidate assembled from native payload contracts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

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


def _candidate_metadata(
    *,
    broker_name: str,
    metadata_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    metadata = dict(metadata_payload or {})
    metadata.setdefault("stage", "native_live_run_candidate")
    metadata.setdefault("readonly", True)
    metadata.setdefault("broker_name", broker_name)
    metadata.setdefault("runner", "renquant_orchestrator.native_live_run")
    return metadata


def run_native_live_candidate(
    *,
    inference_json: str | Path,
    output_json: str | Path,
    execution_json: str | Path | None = None,
    execution_output_json: str | Path | None = None,
    metadata_json: str | Path | None = None,
    broker_name: str = "readonly-native",
) -> dict[str, Any]:
    """Build a readonly native live bundle without importing umbrella live.runner."""
    inference_payload = _load_json(inference_json)
    execution_payload = (
        _load_json(execution_json)
        if execution_json
        else build_readonly_execution_payload(
            inference_payload=inference_payload,
            broker_name=broker_name,
        )
    )
    if execution_output_json:
        _write_json(execution_output_json, execution_payload)

    metadata_payload = _load_json(metadata_json) if metadata_json else None
    bundle = build_native_live_bundle(
        inference_payload=inference_payload,
        execution_payload=execution_payload,
        metadata=_candidate_metadata(
            broker_name=broker_name,
            metadata_payload=metadata_payload,
        ),
    )
    _write_json(output_json, bundle)
    return bundle


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="renquant-orchestrator native-live-run")
    parser.add_argument("--inference-json", required=True)
    parser.add_argument("--execution-json", default=None)
    parser.add_argument("--execution-output-json", default=None)
    parser.add_argument("--metadata-json", default=None)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--broker-name", default="readonly-native")
    args = parser.parse_args(argv)

    bundle = run_native_live_candidate(
        inference_json=args.inference_json,
        execution_json=args.execution_json,
        execution_output_json=args.execution_output_json,
        metadata_json=args.metadata_json,
        output_json=args.output_json,
        broker_name=args.broker_name,
    )
    print(json.dumps(bundle, indent=2, sort_keys=True))
    return 0


__all__ = [
    "main",
    "run_native_live_candidate",
]


if __name__ == "__main__":
    raise SystemExit(main())
