"""Native-vs-umbrella live parity fixture.

This module is the offboard gate for the remaining live.runner bridges. It
does not place orders. It compares two already-produced readonly run bundles:

* bridge bundle: current orchestrator live-bridge/daily-bridge handoff
* native bundle: candidate native orchestrator/pipeline execution path

The bridge jobs may leave ``umbrella_bridge`` only after this comparator passes
for prod and readonly-shadow fixtures.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


VOLATILE_KEYS = {
    "created_at",
    "elapsed_sec",
    "run_id",
    "timestamp",
    "updated_at",
    "wall_time",
}


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): _json_safe(v)
            for k, v in sorted(value.items())
            if str(k) not in VOLATILE_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _sort_key(row: Any) -> str:
    if isinstance(row, dict):
        preferred = (
            row.get("ticker"),
            row.get("action"),
            row.get("stage"),
            row.get("source_job"),
            row.get("source_task"),
            row.get("blocked_by"),
        )
        return json.dumps({"preferred": preferred, "row": row}, sort_keys=True, default=str)
    return json.dumps(row, sort_keys=True, default=str)


def _normalized_rows(rows: Any) -> list[Any]:
    if not isinstance(rows, list):
        return []
    return sorted((_json_safe(row) for row in rows), key=_sort_key)


def normalize_live_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """Reduce a live run bundle to the fields required for offboard parity."""
    state_mutations = []
    for field in ("state_mutations", "execution_audit", "submitted_orders"):
        if field in bundle:
            state_mutations = bundle[field]
            break
    return {
        "decision_trace": _normalized_rows(bundle.get("decision_trace")),
        "order_intents": _normalized_rows(bundle.get("order_intents")),
        "state_mutations": _normalized_rows(state_mutations),
    }


def _bundle_input_errors(label: str, bundle: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ("decision_trace", "order_intents"):
        if field not in bundle:
            errors.append(f"{label}:missing_{field}")
        elif not isinstance(bundle.get(field), list):
            errors.append(f"{label}:invalid_{field}")
    if not any(
        field in bundle
        for field in ("state_mutations", "execution_audit", "submitted_orders")
    ):
        errors.append(f"{label}:missing_state_mutation_source")
    return errors


def compare_live_bundles(
    bridge_bundle: dict[str, Any],
    native_bundle: dict[str, Any],
) -> dict[str, Any]:
    """Return a machine-readable parity verdict for two live bundles."""
    input_errors = (
        _bundle_input_errors("bridge", bridge_bundle)
        + _bundle_input_errors("native", native_bundle)
    )
    bridge = normalize_live_bundle(bridge_bundle)
    native = normalize_live_bundle(native_bundle)
    mismatches: dict[str, dict[str, Any]] = {}
    for key in ("decision_trace", "order_intents", "state_mutations"):
        if bridge[key] != native[key]:
            mismatches[key] = {
                "bridge": bridge[key],
                "native": native[key],
            }
    return {
        "schema_version": 1,
        "ok": not input_errors and not mismatches,
        "checked_fields": ["decision_trace", "order_intents", "state_mutations"],
        "input_errors": input_errors,
        "mismatches": mismatches,
        "summary": {
            "decision_trace_rows": len(bridge["decision_trace"]),
            "order_intents": len(bridge["order_intents"]),
            "state_mutations": len(bridge["state_mutations"]),
        },
    }


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"bundle must be a JSON object: {path}")
    return payload


def run_live_parity_fixture(
    *,
    bridge_bundle: str | Path,
    native_bundle: str | Path,
    output_json: str | Path | None = None,
) -> dict[str, Any]:
    verdict = compare_live_bundles(
        _load_json(Path(bridge_bundle)),
        _load_json(Path(native_bundle)),
    )
    if output_json is not None:
        out = Path(output_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(verdict, indent=2, sort_keys=True) + "\n")
    return verdict


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="renquant-orchestrator live-parity-fixture")
    parser.add_argument("--bridge-bundle", required=True)
    parser.add_argument("--native-bundle", required=True)
    parser.add_argument("--output-json", default=None)
    parser.add_argument(
        "--fail-on-diff",
        action="store_true",
        help="return non-zero when parity does not hold",
    )
    args = parser.parse_args(argv)

    verdict = run_live_parity_fixture(
        bridge_bundle=args.bridge_bundle,
        native_bundle=args.native_bundle,
        output_json=args.output_json,
    )
    print(json.dumps(verdict, indent=2, sort_keys=True))
    return 2 if args.fail_on_diff and not verdict["ok"] else 0


__all__ = [
    "compare_live_bundles",
    "main",
    "normalize_live_bundle",
    "run_live_parity_fixture",
]


if __name__ == "__main__":
    raise SystemExit(main())
