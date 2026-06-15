from __future__ import annotations

import json
from pathlib import Path

from renquant_orchestrator.cli import main as cli_main
from renquant_orchestrator.native_live_context import (
    NATIVE_CONTEXT_PRODUCER,
    build_native_live_context,
)


def _write_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    config = tmp_path / "strategy_config.json"
    market = tmp_path / "market.json"
    account = tmp_path / "account.json"
    config.write_text(json.dumps({"watchlist": ["AAPL"]}), encoding="utf-8")
    market.write_text(json.dumps({"as_of": "2026-06-15"}), encoding="utf-8")
    account.write_text(json.dumps({"positions": {}}), encoding="utf-8")
    return config, market, account


def test_build_native_live_context_writes_hydrated_context(tmp_path: Path) -> None:
    config, market, account = _write_inputs(tmp_path)
    metadata = tmp_path / "metadata.json"
    output = tmp_path / "context.json"
    metadata.write_text(json.dumps({"mode": "live"}), encoding="utf-8")

    payload = build_native_live_context(
        strategy_config_json=config,
        market_snapshot_json=market,
        account_snapshot_json=account,
        metadata_json=metadata,
        output_json=output,
    )

    assert payload["source"] == "native_live_context_fixture"
    assert payload["config"] == {"watchlist": ["AAPL"]}
    assert payload["market_snapshot"] == {"as_of": "2026-06-15"}
    assert payload["account_snapshot"] == {"positions": {}}
    assert payload["metadata"]["mode"] == "live"
    assert payload["metadata"]["native_context_producer"] == {
        "source": NATIVE_CONTEXT_PRODUCER,
        "strategy_config_json": str(config),
        "market_snapshot_json": str(market),
        "account_snapshot_json": str(account),
    }
    assert json.loads(output.read_text(encoding="utf-8")) == payload


def test_native_live_context_cli_writes_payload(tmp_path: Path, capsys) -> None:
    config, market, account = _write_inputs(tmp_path)
    output = tmp_path / "context.json"

    rc = cli_main([
        "native-live-context",
        "--strategy-config-json",
        str(config),
        "--market-snapshot-json",
        str(market),
        "--account-snapshot-json",
        str(account),
        "--output-json",
        str(output),
    ])

    assert rc == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == json.loads(output.read_text(encoding="utf-8"))
    assert printed["metadata"]["native_context_producer"]["source"] == (
        NATIVE_CONTEXT_PRODUCER
    )
