from __future__ import annotations

import json
from pathlib import Path

import pytest

from renquant_orchestrator.cli import main as cli_main
from renquant_orchestrator.native_live_snapshots import (
    ACCOUNT_SNAPSHOT_PRODUCER,
    MARKET_SNAPSHOT_PRODUCER,
    _as_float,
    _load_json_object,
    _normalize_position,
    _normalize_positions,
    _position_quantity,
    _position_symbol,
    _prices_from_payload,
    _write_json,
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


# ---------------------------------------------------------------------------
# Unit tests for pure helper functions
# ---------------------------------------------------------------------------


class TestAsFloat:
    def test_none_returns_default(self) -> None:
        assert _as_float(None) == 0.0

    def test_none_returns_custom_default(self) -> None:
        assert _as_float(None, default=-1.0) == -1.0

    def test_int_to_float(self) -> None:
        assert _as_float(5) == 5.0

    def test_string_number(self) -> None:
        assert _as_float("3.5") == 3.5

    def test_float_passthrough(self) -> None:
        assert _as_float(2.25) == 2.25


class TestPositionSymbol:
    def test_symbol_key_strips_and_uppercases(self) -> None:
        assert _position_symbol({"symbol": " aapl "}) == "AAPL"

    def test_ticker_key_fallback(self) -> None:
        assert _position_symbol({"ticker": "msft"}) == "MSFT"

    def test_symbol_takes_priority_over_ticker(self) -> None:
        assert _position_symbol({"symbol": "GOOG", "ticker": "MSFT"}) == "GOOG"

    def test_missing_both_returns_none(self) -> None:
        assert _position_symbol({"price": 100}) is None

    def test_empty_string_returns_none(self) -> None:
        assert _position_symbol({"symbol": ""}) is None

    def test_whitespace_only_returns_none(self) -> None:
        assert _position_symbol({"symbol": "   "}) is None


class TestPositionQuantity:
    def test_quantity_key(self) -> None:
        assert _position_quantity({"quantity": 10}) == 10.0

    def test_qty_key(self) -> None:
        assert _position_quantity({"qty": 3}) == 3.0

    def test_shares_key(self) -> None:
        assert _position_quantity({"shares": 7}) == 7.0

    def test_no_key_returns_zero(self) -> None:
        assert _position_quantity({"symbol": "X"}) == 0.0

    def test_quantity_priority_over_qty(self) -> None:
        assert _position_quantity({"quantity": 5, "qty": 9}) == 5.0


class TestNormalizePosition:
    def test_normalizes_symbol_and_quantity(self) -> None:
        result = _normalize_position({"symbol": " aapl ", "qty": 5})
        assert result is not None
        assert result["ticker"] == "AAPL"
        assert result["symbol"] == "AAPL"
        assert result["quantity"] == 5.0
        assert "qty" not in result

    def test_empty_symbol_returns_none(self) -> None:
        assert _normalize_position({"symbol": "", "quantity": 5}) is None

    def test_missing_symbol_returns_none(self) -> None:
        assert _normalize_position({"price": 100, "quantity": 5}) is None

    def test_zero_quantity_returns_none(self) -> None:
        assert _normalize_position({"symbol": "AAPL", "quantity": 0}) is None

    def test_preserves_extra_fields(self) -> None:
        result = _normalize_position(
            {"symbol": "GOOG", "quantity": 3, "avg_entry_price": 150.0}
        )
        assert result is not None
        assert result["avg_entry_price"] == 150.0

    def test_removes_shares_key(self) -> None:
        result = _normalize_position({"symbol": "META", "shares": 10})
        assert result is not None
        assert "shares" not in result
        assert result["quantity"] == 10.0


class TestNormalizePositions:
    def test_dedupes_by_ticker_last_wins(self) -> None:
        rows = [
            {"symbol": "AAPL", "quantity": 1},
            {"symbol": "aapl", "quantity": 5},
        ]
        result = _normalize_positions(rows)
        assert len(result) == 1
        assert result["AAPL"]["quantity"] == 5.0

    def test_filters_zero_quantity(self) -> None:
        rows = [
            {"symbol": "AAPL", "quantity": 0},
            {"symbol": "MSFT", "quantity": 3},
        ]
        result = _normalize_positions(rows)
        assert "AAPL" not in result
        assert "MSFT" in result

    def test_non_dict_item_raises(self) -> None:
        with pytest.raises(ValueError, match="must be an object"):
            _normalize_positions([{"symbol": "AAPL", "quantity": 1}, "not-a-dict"])

    def test_empty_list(self) -> None:
        assert _normalize_positions([]) == {}


class TestPricesFromPayload:
    def test_flat_dict_no_prices_key(self) -> None:
        result = _prices_from_payload({"aapl": 100.0, "msft": 200.0})
        assert result == {"AAPL": 100.0, "MSFT": 200.0}

    def test_nested_prices_key(self) -> None:
        result = _prices_from_payload({"prices": {"goog": "150.5"}})
        assert result == {"GOOG": 150.5}

    def test_prices_key_non_dict_raises(self) -> None:
        with pytest.raises(ValueError, match="must be a JSON object"):
            _prices_from_payload({"prices": [1, 2, 3]})

    def test_uppercases_and_strips_symbols(self) -> None:
        result = _prices_from_payload({" tsla ": 300.0})
        assert result == {"TSLA": 300.0}

    def test_skips_empty_symbol(self) -> None:
        result = _prices_from_payload({"": 100.0, "AAPL": 200.0})
        assert result == {"AAPL": 200.0}


class TestLoadJsonObject:
    def test_loads_dict(self, tmp_path: Path) -> None:
        p = tmp_path / "data.json"
        p.write_text(json.dumps({"key": "value"}), encoding="utf-8")
        assert _load_json_object(p) == {"key": "value"}

    def test_list_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "data.json"
        p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        with pytest.raises(ValueError, match="must be a JSON object"):
            _load_json_object(p)


class TestWriteJson:
    def test_creates_parent_dirs_and_writes(self, tmp_path: Path) -> None:
        p = tmp_path / "sub" / "dir" / "out.json"
        _write_json(p, {"b": 2, "a": 1})
        content = json.loads(p.read_text(encoding="utf-8"))
        assert content == {"a": 1, "b": 2}

    def test_output_is_sorted_and_indented(self, tmp_path: Path) -> None:
        p = tmp_path / "out.json"
        _write_json(p, {"z": 1, "a": 2})
        raw = p.read_text(encoding="utf-8")
        assert raw.endswith("\n")
        lines = raw.strip().split("\n")
        assert lines[1].strip().startswith('"a"')
        assert lines[2].strip().startswith('"z"')


class TestAccountSnapshotMetadataInjection:
    def test_metadata_json_merged_into_output(self, tmp_path: Path) -> None:
        meta = tmp_path / "meta.json"
        meta.write_text(json.dumps({"run_id": "abc123", "env": "test"}), encoding="utf-8")
        output = tmp_path / "account.json"
        broker = FakeBroker()

        payload = build_native_live_account_snapshot(
            broker_name="readonly-alpaca",
            output_json=output,
            metadata_json=meta,
            broker_factory=lambda name: broker,
        )

        assert payload["metadata"]["run_id"] == "abc123"
        assert payload["metadata"]["env"] == "test"
        assert "native_account_snapshot_producer" in payload["metadata"]


class TestMarketSnapshotMetadataInjection:
    def test_metadata_json_merged_into_output(self, tmp_path: Path) -> None:
        meta = tmp_path / "meta.json"
        meta.write_text(json.dumps({"run_id": "xyz789"}), encoding="utf-8")
        prices = tmp_path / "prices.json"
        prices.write_text(json.dumps({"AAPL": 100.0}), encoding="utf-8")
        output = tmp_path / "market.json"

        payload = build_native_live_market_snapshot(
            as_of="2026-07-01",
            prices_json=prices,
            output_json=output,
            metadata_json=meta,
        )

        assert payload["metadata"]["run_id"] == "xyz789"
        assert "native_market_snapshot_producer" in payload["metadata"]
