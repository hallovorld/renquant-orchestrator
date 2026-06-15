from __future__ import annotations

import json
from pathlib import Path

from renquant_orchestrator.cli import main as cli_main
from renquant_orchestrator.native_live_inference import (
    NATIVE_INFERENCE_PRODUCER,
    run_native_live_inference,
)


class FakePipeline:
    def __init__(self) -> None:
        self.seen = []

    def run(self, ctx) -> None:  # noqa: ANN001
        self.seen.append(ctx)
        ctx.order_intents = [{"ticker": "AAPL", "action": "buy", "quantity": 2}]
        ctx.decision_trace = [{"ticker": "AAPL", "stage": "native_fixture"}]
        ctx.scores = {"AAPL": 0.91}


def _context(path: Path) -> None:
    path.write_text(
        json.dumps({
            "config": {"watchlist": ["AAPL"]},
            "market_snapshot": {"as_of": "2026-06-15"},
            "account_snapshot": {"positions": {}},
        }),
        encoding="utf-8",
    )


def test_native_live_inference_writes_provenance_payload(tmp_path: Path) -> None:
    context = tmp_path / "context.json"
    output = tmp_path / "native-inference.json"
    metadata = tmp_path / "metadata.json"
    _context(context)
    metadata.write_text(json.dumps({"mode": "live"}), encoding="utf-8")
    pipeline = FakePipeline()

    payload = run_native_live_inference(
        context_json=context,
        output_json=output,
        metadata_json=metadata,
        pipeline=pipeline,
    )

    assert pipeline.seen
    assert payload["source"] == "renquant_pipeline.live_context_inference"
    assert payload["market_as_of"] == "2026-06-15"
    assert payload["decision_trace"] == [{"ticker": "AAPL", "stage": "native_fixture"}]
    assert payload["order_intents"] == [{"ticker": "AAPL", "action": "buy", "quantity": 2}]
    assert payload["metadata"]["mode"] == "live"
    assert payload["metadata"]["native_inference_producer"] == {
        "source": NATIVE_INFERENCE_PRODUCER,
        "context_json": str(context),
        "sell_only": False,
    }
    assert json.loads(output.read_text(encoding="utf-8")) == payload


def test_native_live_inference_cli_writes_payload(monkeypatch, tmp_path: Path, capsys) -> None:
    import renquant_orchestrator.native_live_inference as mod

    context = tmp_path / "context.json"
    output = tmp_path / "native-inference.json"
    _context(context)

    def fake_run_native_inference_snapshot(ctx, *, sell_only, pipeline=None):
        class Snapshot:
            def to_runtime_payload(self):
                return {
                    "schema_version": 1,
                    "source": "renquant_pipeline.live_context_inference",
                    "market_as_of": ctx.market_snapshot["as_of"],
                    "decision_trace": [{"ticker": "AAPL", "stage": "cli"}],
                    "order_intents": [],
                    "scores": {},
                    "blocked_by": {},
                    "pending_broker_tickers": [],
                    "buy_blocked": False,
                }

        assert sell_only is True
        return Snapshot()

    monkeypatch.setattr(
        "renquant_pipeline.run_native_inference_snapshot",
        fake_run_native_inference_snapshot,
    )

    rc = cli_main([
        "native-live-inference",
        "--context-json",
        str(context),
        "--output-json",
        str(output),
        "--sell-only",
    ])

    assert rc == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed == json.loads(output.read_text(encoding="utf-8"))
    assert printed["metadata"]["native_inference_producer"]["source"] == (
        NATIVE_INFERENCE_PRODUCER
    )
