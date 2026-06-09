"""Build a native bundle from payloads, then compare it to a bridge bundle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .live_parity import run_live_parity_fixture
from .native_live_bundle import write_native_live_bundle


def run_live_parity_from_payloads(
    *,
    bridge_bundle: str | Path,
    inference_json: str | Path,
    native_bundle_output: str | Path,
    execution_json: str | Path | None = None,
    metadata_json: str | Path | None = None,
    output_json: str | Path | None = None,
) -> dict:
    """Build the native bundle and compare it against a bridge bundle."""
    write_native_live_bundle(
        inference_json=inference_json,
        execution_json=execution_json,
        metadata_json=metadata_json,
        output_json=native_bundle_output,
    )
    return run_live_parity_fixture(
        bridge_bundle=bridge_bundle,
        native_bundle=native_bundle_output,
        output_json=output_json,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="renquant-orchestrator live-parity-from-payloads")
    parser.add_argument("--bridge-bundle", required=True)
    parser.add_argument("--inference-json", required=True)
    parser.add_argument("--execution-json", default=None)
    parser.add_argument("--metadata-json", default=None)
    parser.add_argument("--native-bundle-output", required=True)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--fail-on-diff", action="store_true")
    args = parser.parse_args(argv)

    verdict = run_live_parity_from_payloads(
        bridge_bundle=args.bridge_bundle,
        inference_json=args.inference_json,
        execution_json=args.execution_json,
        metadata_json=args.metadata_json,
        native_bundle_output=args.native_bundle_output,
        output_json=args.output_json,
    )
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 2 if args.fail_on_diff and not verdict["ok"] else 0


__all__ = [
    "main",
    "run_live_parity_from_payloads",
]


if __name__ == "__main__":
    raise SystemExit(main())
