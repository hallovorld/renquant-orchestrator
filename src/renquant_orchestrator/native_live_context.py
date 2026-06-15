"""Native live context fixture builder for offboard rehearsal."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


NATIVE_CONTEXT_PRODUCER = "renquant_orchestrator.native_live_context"


def _load_json_object(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"payload must be a JSON object: {path}")
    return payload


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_native_live_context(
    *,
    strategy_config_json: str | Path,
    market_snapshot_json: str | Path,
    account_snapshot_json: str | Path,
    output_json: str | Path,
    metadata_json: str | Path | None = None,
) -> dict[str, Any]:
    """Build an already-hydrated native context JSON for inference rehearsal."""
    metadata = _load_json_object(metadata_json) if metadata_json else {}
    payload = {
        "schema_version": 1,
        "source": "native_live_context_fixture",
        "config": _load_json_object(strategy_config_json),
        "market_snapshot": _load_json_object(market_snapshot_json),
        "account_snapshot": _load_json_object(account_snapshot_json),
        "metadata": {
            **metadata,
            "native_context_producer": {
                "source": NATIVE_CONTEXT_PRODUCER,
                "strategy_config_json": str(strategy_config_json),
                "market_snapshot_json": str(market_snapshot_json),
                "account_snapshot_json": str(account_snapshot_json),
            },
        },
    }
    _write_json(output_json, payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="renquant-orchestrator native-live-context")
    parser.add_argument("--strategy-config-json", required=True)
    parser.add_argument("--market-snapshot-json", required=True)
    parser.add_argument("--account-snapshot-json", required=True)
    parser.add_argument("--metadata-json", default=None)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)

    payload = build_native_live_context(
        strategy_config_json=args.strategy_config_json,
        market_snapshot_json=args.market_snapshot_json,
        account_snapshot_json=args.account_snapshot_json,
        metadata_json=args.metadata_json,
        output_json=args.output_json,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


__all__ = [
    "NATIVE_CONTEXT_PRODUCER",
    "build_native_live_context",
    "main",
]


if __name__ == "__main__":
    raise SystemExit(main())
