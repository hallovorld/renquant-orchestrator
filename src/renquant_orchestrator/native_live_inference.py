"""Native live inference producer for offboard rehearsal payloads."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any


NATIVE_INFERENCE_PRODUCER = "renquant_orchestrator.native_live_inference"


def _load_json_object(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"payload must be a JSON object: {path}")
    return payload


def _to_namespace(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**value)
    return value


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _producer_metadata(
    *,
    context_json: str | Path,
    sell_only: bool,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    out = dict(metadata or {})
    out.setdefault("stage", "native_live_inference")
    out.setdefault("runner", NATIVE_INFERENCE_PRODUCER)
    out["native_inference_producer"] = {
        "source": NATIVE_INFERENCE_PRODUCER,
        "context_json": str(context_json),
        "sell_only": bool(sell_only),
    }
    return out


def run_native_live_inference(
    *,
    context_json: str | Path,
    output_json: str | Path,
    sell_only: bool = False,
    metadata_json: str | Path | None = None,
    pipeline: Any | None = None,
) -> dict[str, Any]:
    """Run native inference on an already-hydrated context JSON.

    The caller owns hydration of market data, holdings, prices, models, and
    config. This function does not import or delegate to umbrella live.runner,
    does not submit orders, and does not mutate persistent live state.
    """
    from renquant_pipeline import run_native_inference_snapshot

    context_payload = _load_json_object(context_json)
    metadata_payload = _load_json_object(metadata_json) if metadata_json else None
    snapshot = run_native_inference_snapshot(
        _to_namespace(context_payload),
        sell_only=sell_only,
        pipeline=pipeline,
    )
    payload = snapshot.to_runtime_payload()
    payload["metadata"] = _producer_metadata(
        context_json=context_json,
        sell_only=sell_only,
        metadata=metadata_payload,
    )
    _write_json(output_json, payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="renquant-orchestrator native-live-inference")
    parser.add_argument("--context-json", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--metadata-json", default=None)
    parser.add_argument("--sell-only", action="store_true")
    args = parser.parse_args(argv)

    payload = run_native_live_inference(
        context_json=args.context_json,
        output_json=args.output_json,
        metadata_json=args.metadata_json,
        sell_only=args.sell_only,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


__all__ = [
    "NATIVE_INFERENCE_PRODUCER",
    "main",
    "run_native_live_inference",
]


if __name__ == "__main__":
    raise SystemExit(main())
