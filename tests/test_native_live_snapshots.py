from __future__ import annotations

import json
from pathlib import Path

from renquant_orchestrator.cli import main as cli_main
from renquant_orchestrator.native_live_snapshots import (
    ACCOUNT_SNAPSHOT_PRODUCER,
    MARKET_SNAPSHOT_PRODUCER,
    build_native_live_account_snapshot,
    build_native_live_market_snapshot,
)


class FakeBroker:
    def __init__(self) -> None:
        self.connected = False
        self.disconnected = False
        self.mutations = []

    def connect(self) -> None:
        self.connected = True

    def disconnect(self) -> None:
        self.disconnected = True

    def get_cash(self) -> float:
        return 12345.0

    def get_account_value(self) -> float:
        return 23456.0

    def get_all_positions(self) -> list[dict]:
        return [
            {"symbol": "aapl", "qty": 2, "avg_entry_price": 100.0},
            {"ticker": "MSFT", "quantity": 0},
        ]

    def get_open_orders(self) -> set[str]:
        return {"msft", "AAPL"}

    def place_order(self, *_args, **_kwargs):  # pragma: no cover - must not be called
        self.mutations.append("place_order")
        raise AssertionError("snapshot fixture must not place orders")

    def cancel_order(self, *_args, **_kwargs):  # pragma: no cover - must not be called
        self.mutations.append("cancel_order")
        raise AssertionError("snapshot fixture must not cancel orders")


def test_account_snapshot_uses_readonly_broker_apis(tmp_path: Path) -> None:
    broker = FakeBroker()
    output = tmp_path / "account.json"

    payload = build_native_live_account_snapshot(
        broker_name="readonly-alpaca",
        output_json=output,
        broker_factory=lambda name: broker,
    )

    assert broker.connected is True
    assert broker.disconnected is True
    assert broker.mutations == []
    assert payload["source"] == "native_live_account_snapshot"
    assert payload["broker_name"] == "readonly-alpaca"
    assert payload["cash"] == 12345.0
    assert payload["portfolio_value"] == 23456.0
    assert payload["open_orders"] == ["AAPL", "MSFT"]
    assert payload["positions"] == {
        "AAPL": {
            "symbol": "AAPL",
            "ticker": "AAPL",
            "quantity": 2.0,
            "avg_entry_price": 100.0,
        }
    }
    assert payload["metadata"]["native_account_snapshot_producer"] == {
        "source": ACCOUNT_SNAPSHOT_PRODUCER,
        "broker_name": "readonly-alpaca",
        "readonly": True,
    }
    assert json.loads(output.read_text(encoding="utf-8")) == payload


def test_market_snapshot_from_explicit_prices(tmp_path: Path) -> None:
    prices = tmp_path / "prices.json"
    output = tmp_path / "market.json"
    prices.write_text(json.dumps({"prices": {"aapl": 101.25, "MSFT": "202.5"}}), encoding="utf-8")

    payload = build_native_live_market_snapshot(
        as_of="2026-06-15T20:00:00Z",
        prices_json=prices,
        output_json=output,
    )

    assert payload["source"] == "native_live_market_snapshot"
    assert payload["as_of"] == "2026-06-15T20:00:00Z"
    assert payload["prices"] == {"AAPL": 101.25, "MSFT": 202.5}
    assert payload["metadata"]["native_market_snapshot_producer"] == {
        "source": MARKET_SNAPSHOT_PRODUCER,
        "prices_json": str(prices),
    }
    assert json.loads(output.read_text(encoding="utf-8")) == payload


def test_market_snapshot_cli_writes_payload(tmp_path: Path, capsys) -> None:
    prices = tmp_path / "prices.json"
    output = tmp_path / "market.json"
    prices.write_text(json.dumps({"AAPL": 101.25}), encoding="utf-8")

    rc = cli_main([
        "native-live-market-snapshot",
        "--as-of",
        "2026-06-15",
        "--prices-json",
        str(prices),
        "--output-json",
        str(output),
    ])

    assert rc == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == json.loads(output.read_text(encoding="utf-8"))
    assert printed["metadata"]["native_market_snapshot_producer"]["source"] == (
        MARKET_SNAPSHOT_PRODUCER
    )
