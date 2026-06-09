"""Build bridge live-run bundles from legacy live.runner contexts.

The live.runner offboard plan compares the current umbrella bridge output
against the native multirepo output. This module keeps the bridge-side bundle
extraction pure and testable so a thin live.runner wrapper can call it after
``RunnerAdapter.commit(ctx)`` without owning any trading logic.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from renquant_common import validate_live_run_bundle


def _as_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return dict(row)
    if isinstance(row, tuple):
        return {"tuple": [_jsonable(item) for item in row]}
    attrs = {
        key: value
        for key, value in vars(row).items()
        if not key.startswith("_")
    } if hasattr(row, "__dict__") else {}
    if attrs:
        return {str(k): _jsonable(v) for k, v in attrs.items()}
    return {"value": _jsonable(row)}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "__dict__"):
        return _as_dict(value)
    return str(value)


def _rows(ctx: Any, attr: str) -> list[dict[str, Any]]:
    value = list(getattr(ctx, attr, []) or [])
    return [_as_dict(row) for row in value]


def _order_intents(ctx: Any) -> list[dict[str, Any]]:
    explicit = _rows(ctx, "order_intents")
    if explicit:
        return explicit
    return _rows(ctx, "orders")


def _execution_audit(ctx: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for attr, kind in (
        ("orders_placed", "order_placed"),
        ("orders_pending", "order_pending"),
        ("orders_skipped", "order_skipped"),
        ("exits_placed", "exit_placed"),
        ("exits_pending", "exit_pending"),
        ("exits_failed", "exit_failed"),
    ):
        for row in _rows(ctx, attr):
            rows.append({"kind": kind, **row})
    if rows:
        return rows
    return [{
        "kind": "bridge_context",
        "reason": "no_execution_rows",
        "n_order_intents": len(_order_intents(ctx)),
    }]


def build_bridge_live_bundle(
    ctx: Any,
    *,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a parity-ready bundle from a committed live.runner context."""
    bundle: dict[str, Any] = {
        "schema_version": 1,
        "source": "live_runner_bridge",
        "decision_trace": _rows(ctx, "decision_trace"),
        "order_intents": _order_intents(ctx),
        "execution_audit": _execution_audit(ctx),
    }
    if metadata:
        bundle["metadata"] = dict(metadata)
    validate_live_run_bundle(bundle)
    return bundle


def write_bridge_live_bundle(
    ctx: Any,
    path: str | Path,
    *,
    metadata: dict[str, Any] | None = None,
) -> Path:
    """Write a bridge live bundle as deterministic JSON."""
    bundle = build_bridge_live_bundle(ctx, metadata=metadata)
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(bundle, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return out


__all__ = [
    "build_bridge_live_bundle",
    "write_bridge_live_bundle",
]
