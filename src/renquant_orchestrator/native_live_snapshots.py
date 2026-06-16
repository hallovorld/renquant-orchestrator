"""Native live account/market snapshot fixtures for offboard rehearsal."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable


ACCOUNT_SNAPSHOT_PRODUCER = "renquant_orchestrator.native_live_account_snapshot"
MARKET_SNAPSHOT_PRODUCER = "renquant_orchestrator.native_live_market_snapshot"
BrokerFactory = Callable[[str], Any]


def _load_json_object(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"payload must be a JSON object: {path}")
    return payload


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _as_float(value: Any, *, default: float = 0.0) -> float:
    if value is None:
        return default
    return float(value)


def _position_symbol(row: dict[str, Any]) -> str | None:
    symbol = row.get("symbol") or row.get("ticker")
    if symbol is None:
        return None
    symbol_s = str(symbol).strip().upper()
    return symbol_s or None


def _position_quantity(row: dict[str, Any]) -> float:
    return _as_float(row.get("quantity", row.get("qty", row.get("shares"))))


def _normalize_position(row: dict[str, Any]) -> dict[str, Any] | None:
    symbol = _position_symbol(row)
    if not symbol:
        return None
    quantity = _position_quantity(row)
    if quantity == 0.0:
        return None
    normalized = dict(row)
    normalized["ticker"] = symbol
    normalized["symbol"] = symbol
    normalized["quantity"] = quantity
    normalized.pop("qty", None)
    normalized.pop("shares", None)
    return normalized


def _normalize_positions(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    positions: dict[str, dict[str, Any]] = {}
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"broker positions[{idx}] must be an object")
        normalized = _normalize_position(row)
        if normalized is not None:
            positions[normalized["ticker"]] = normalized
    return positions


def build_native_live_account_snapshot(
    *,
    broker_name: str,
    output_json: str | Path,
    metadata_json: str | Path | None = None,
    broker_factory: BrokerFactory | None = None,
) -> dict[str, Any]:
    """Build a readonly account snapshot from broker read APIs only."""
    if broker_factory is None:
        from renquant_execution import get_broker

        broker_factory = get_broker
    metadata = _load_json_object(metadata_json) if metadata_json else {}
    broker = broker_factory(broker_name)
    broker.connect()
    try:
        payload = {
            "schema_version": 1,
            "source": "native_live_account_snapshot",
            "broker_name": broker_name,
            "cash": broker.get_cash(),
            "portfolio_value": broker.get_account_value(),
            "positions": _normalize_positions(list(broker.get_all_positions() or [])),
            "open_orders": sorted(str(item).upper() for item in broker.get_open_orders()),
            "metadata": {
                **metadata,
                "native_account_snapshot_producer": {
                    "source": ACCOUNT_SNAPSHOT_PRODUCER,
                    "broker_name": broker_name,
                    "readonly": True,
                },
            },
        }
    finally:
        broker.disconnect()
    _write_json(output_json, payload)
    return payload


def _prices_from_payload(payload: dict[str, Any]) -> dict[str, float]:
    raw = payload.get("prices", payload)
    if not isinstance(raw, dict):
        raise ValueError("price snapshot must be a JSON object or contain prices object")
    prices: dict[str, float] = {}
    for symbol, value in raw.items():
        symbol_s = str(symbol).strip().upper()
        if symbol_s:
            prices[symbol_s] = float(value)
    return prices


def build_native_live_market_snapshot(
    *,
    as_of: str,
    prices_json: str | Path,
    output_json: str | Path,
    metadata_json: str | Path | None = None,
) -> dict[str, Any]:
    """Build a native market snapshot from explicit price inputs."""
    metadata = _load_json_object(metadata_json) if metadata_json else {}
    payload = {
        "schema_version": 1,
        "source": "native_live_market_snapshot",
        "as_of": as_of,
        "prices": _prices_from_payload(_load_json_object(prices_json)),
        "metadata": {
            **metadata,
            "native_market_snapshot_producer": {
                "source": MARKET_SNAPSHOT_PRODUCER,
                "prices_json": str(prices_json),
            },
        },
    }
    _write_json(output_json, payload)
    return payload


def account_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="renquant-orchestrator native-live-account-snapshot")
    parser.add_argument("--broker-name", default="readonly-alpaca")
    parser.add_argument("--metadata-json", default=None)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)
    payload = build_native_live_account_snapshot(
        broker_name=args.broker_name,
        metadata_json=args.metadata_json,
        output_json=args.output_json,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def market_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="renquant-orchestrator native-live-market-snapshot")
    parser.add_argument("--as-of", required=True)
    parser.add_argument("--prices-json", required=True)
    parser.add_argument("--metadata-json", default=None)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)
    payload = build_native_live_market_snapshot(
        as_of=args.as_of,
        prices_json=args.prices_json,
        metadata_json=args.metadata_json,
        output_json=args.output_json,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="renquant-orchestrator native-live-snapshots")
    sub = parser.add_subparsers(dest="command", required=True)
    account = sub.add_parser("account")
    account.add_argument("--broker-name", default="readonly-alpaca")
    account.add_argument("--metadata-json", default=None)
    account.add_argument("--output-json", required=True)
    market = sub.add_parser("market")
    market.add_argument("--as-of", required=True)
    market.add_argument("--prices-json", required=True)
    market.add_argument("--metadata-json", default=None)
    market.add_argument("--output-json", required=True)
    args = parser.parse_args(argv)
    if args.command == "account":
        return account_main([
            "--broker-name", args.broker_name,
            "--output-json", args.output_json,
            *(["--metadata-json", args.metadata_json] if args.metadata_json else []),
        ])
    if args.command == "market":
        return market_main([
            "--as-of", args.as_of,
            "--prices-json", args.prices_json,
            "--output-json", args.output_json,
            *(["--metadata-json", args.metadata_json] if args.metadata_json else []),
        ])
    raise AssertionError(f"unhandled snapshot command: {args.command}")


__all__ = [
    "ACCOUNT_SNAPSHOT_PRODUCER",
    "MARKET_SNAPSHOT_PRODUCER",
    "account_main",
    "build_native_live_account_snapshot",
    "build_native_live_market_snapshot",
    "main",
    "market_main",
]
