from __future__ import annotations

import json
from pathlib import Path

from renquant_orchestrator.cli import main
from renquant_orchestrator.live_parity import compare_live_bundles, normalize_live_bundle


def _bundle(*, qty: int = 1) -> dict:
    return {
        "run_id": "volatile-run-id",
        "created_at": "2026-06-08T12:00:00Z",
        "decision_trace": [
            {"ticker": "MSFT", "stage": "score", "rank_score": 0.2},
            {"ticker": "AAPL", "stage": "score", "rank_score": 0.7},
        ],
        "order_intents": [
            {
                "ticker": "AAPL",
                "action": "buy",
                "quantity": qty,
                "attribution": {
                    "source_job": "PanelScoringJob",
                    "source_task": "EmitAttributedOrderIntentsTask",
                    "elapsed_sec": 0.1,
                    "run_id": "volatile-nested-run",
                },
            }
        ],
        "state_mutations": [
            {"ticker": "AAPL", "action": "buy", "quantity": qty, "timestamp": "now"}
        ],
    }


def test_normalize_live_bundle_strips_volatile_fields_and_sorts_rows() -> None:
    normalized = normalize_live_bundle(_bundle())

    assert normalized["decision_trace"][0]["ticker"] == "AAPL"
    assert "created_at" not in normalized
    assert "elapsed_sec" not in normalized["order_intents"][0]["attribution"]
    assert "run_id" not in normalized["order_intents"][0]["attribution"]
    assert "timestamp" not in normalized["state_mutations"][0]


def test_compare_live_bundles_passes_for_equivalent_outputs() -> None:
    bridge = _bundle()
    native = _bundle()
    native["decision_trace"] = list(reversed(native["decision_trace"]))

    verdict = compare_live_bundles(bridge, native)

    assert verdict["ok"] is True
    assert verdict["mismatches"] == {}
    assert verdict["summary"] == {
        "decision_trace_rows": 2,
        "order_intents": 1,
        "state_mutations": 1,
    }


def test_compare_live_bundles_reports_order_and_state_diffs() -> None:
    verdict = compare_live_bundles(_bundle(qty=1), _bundle(qty=2))

    assert verdict["ok"] is False
    assert set(verdict["mismatches"]) == {"order_intents", "state_mutations"}


def test_compare_live_bundles_sorts_rows_with_duplicate_preferred_keys() -> None:
    bridge = _bundle()
    native = _bundle()
    bridge["decision_trace"] = [
        {"ticker": "AAPL", "stage": "score", "rank_score": 0.2},
        {"ticker": "AAPL", "stage": "score", "rank_score": 0.7},
    ]
    native["decision_trace"] = list(reversed(bridge["decision_trace"]))

    verdict = compare_live_bundles(bridge, native)

    assert verdict["ok"] is True


def test_compare_live_bundles_respects_explicit_empty_state_mutations() -> None:
    bridge = _bundle()
    native = _bundle()
    bridge["state_mutations"] = []
    bridge["execution_audit"] = [{"ticker": "AAPL", "action": "buy"}]
    native["state_mutations"] = []

    verdict = compare_live_bundles(bridge, native)

    assert verdict["ok"] is True


def test_live_parity_fixture_cli_writes_verdict(tmp_path: Path, capsys) -> None:
    bridge = tmp_path / "bridge.json"
    native = tmp_path / "native.json"
    output = tmp_path / "verdict.json"
    bridge.write_text(json.dumps(_bundle()), encoding="utf-8")
    native.write_text(json.dumps(_bundle()), encoding="utf-8")

    rc = main([
        "live-parity-fixture",
        "--bridge-bundle",
        str(bridge),
        "--native-bundle",
        str(native),
        "--output-json",
        str(output),
        "--fail-on-diff",
    ])

    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert json.loads(output.read_text())["ok"] is True


def test_live_parity_fixture_cli_fails_on_diff(tmp_path: Path) -> None:
    bridge = tmp_path / "bridge.json"
    native = tmp_path / "native.json"
    bridge.write_text(json.dumps(_bundle(qty=1)), encoding="utf-8")
    native.write_text(json.dumps(_bundle(qty=2)), encoding="utf-8")

    rc = main([
        "live-parity-fixture",
        "--bridge-bundle",
        str(bridge),
        "--native-bundle",
        str(native),
        "--fail-on-diff",
    ])

    assert rc == 2
