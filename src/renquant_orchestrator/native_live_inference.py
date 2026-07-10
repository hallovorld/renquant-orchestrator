"""Native live inference producer for offboard rehearsal payloads."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any


NATIVE_INFERENCE_PRODUCER = "renquant_orchestrator.native_live_inference"


def _load_json_object(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"payload must be a JSON object: {path}")
    return payload


def _to_namespace(value: Any) -> Any:
    if isinstance(value, dict):
        return SimpleNamespace(**value)
    return value


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _producer_metadata(
    *,
    context_json: str | Path,
    sell_only: bool,
    metadata: dict[str, Any] | None,
) -> dict[str, Any]:
    out = dict(metadata or {})
    out.setdefault("stage", "native_live_inference")
    out.setdefault("runner", NATIVE_INFERENCE_PRODUCER)
    out["native_inference_producer"] = {
        "source": NATIVE_INFERENCE_PRODUCER,
        "context_json": str(context_json),
        "sell_only": bool(sell_only),
    }
    return out


def run_native_live_inference(
    *,
    context_json: str | Path,
    output_json: str | Path,
    sell_only: bool = False,
    metadata_json: str | Path | None = None,
    pipeline: Any | None = None,
    hydrate_pipeline_context: bool = False,
    session_date: str | None = None,
    broker_name: str | None = None,
    strategy_dir: str | Path | None = None,
    repo_root: str | Path | None = None,
    ohlcv_dir: str | Path | None = None,
    context_hydrator: Any | None = None,
) -> dict[str, Any]:
    """Run native inference on a context JSON.

    Two modes:

    * ``hydrate_pipeline_context=True`` (the §2a shadow-ab arm path,
      ``session_date`` then required): the digest-verified context JSON is
      hydrated into the pinned pipeline's REAL
      ``renquant_pipeline.context.InferenceContext`` — OHLCV via the
      pipeline's readonly LocalStore, holdings/cash from the sealed account
      snapshot, model/calibrator loaded downstream by the pipeline's own
      LoadScorerTask chain (the kernel panel-scoring alias production's
      bridge uses is installed first; pipeline-internal modules only) —
      before ``InferencePipeline.run``. This is the fix for the 2026-07-10
      first-real-session failure (``SimpleNamespace`` has no ``today``).
    * default (legacy, byte-identical): the caller owns hydration and the
      payload is passed as a namespace — the pre-existing fixture/offboard
      behavior.

    Neither mode imports or delegates to umbrella live.runner, submits
    orders, or mutates persistent live state.
    """
    from renquant_pipeline import run_native_inference_snapshot

    context_payload = _load_json_object(context_json)
    metadata_payload = _load_json_object(metadata_json) if metadata_json else None
    hydration_report: dict[str, Any] | None = None
    if hydrate_pipeline_context:
        from .native_context_hydration import (
            hydrate_pipeline_context as _hydrate,
            install_native_pipeline_aliases,
        )

        if not session_date:
            raise ValueError(
                "--hydrate-pipeline-context requires --session-date (the "
                "pipeline's ctx.today comes from the frozen session identity)"
            )
        aliases = install_native_pipeline_aliases()
        hydrator = context_hydrator or _hydrate
        ctx, hydration_report = hydrator(
            context_payload,
            session_date=session_date,
            broker_name=broker_name,
            strategy_dir=strategy_dir,
            repo_root=repo_root,
            ohlcv_dir=ohlcv_dir,
        )
        hydration_report = dict(hydration_report or {})
        hydration_report["pipeline_module_aliases"] = aliases
    else:
        ctx = _to_namespace(context_payload)
    snapshot = run_native_inference_snapshot(
        ctx,
        sell_only=sell_only,
        pipeline=pipeline,
    )
    payload = snapshot.to_runtime_payload()
    payload["metadata"] = _producer_metadata(
        context_json=context_json,
        sell_only=sell_only,
        metadata=metadata_payload,
    )
    if hydration_report is not None:
        payload["metadata"]["pipeline_context_hydration"] = hydration_report
    _write_json(output_json, payload)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="renquant-orchestrator native-live-inference")
    parser.add_argument("--context-json", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--metadata-json", default=None)
    parser.add_argument("--sell-only", action="store_true")
    parser.add_argument(
        "--hydrate-pipeline-context", action="store_true",
        help="hydrate the pinned pipeline's real InferenceContext (§2a arm path)",
    )
    parser.add_argument("--session-date", default=None)
    parser.add_argument("--broker-name", default=None)
    parser.add_argument("--strategy-dir", default=None)
    parser.add_argument("--repo-root", default=None)
    parser.add_argument("--ohlcv-dir", default=None)
    args = parser.parse_args(argv)

    payload = run_native_live_inference(
        context_json=args.context_json,
        output_json=args.output_json,
        metadata_json=args.metadata_json,
        sell_only=args.sell_only,
        hydrate_pipeline_context=args.hydrate_pipeline_context,
        session_date=args.session_date,
        broker_name=args.broker_name,
        strategy_dir=args.strategy_dir,
        repo_root=args.repo_root,
        ohlcv_dir=args.ohlcv_dir,
    )
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


__all__ = [
    "NATIVE_INFERENCE_PRODUCER",
    "main",
    "run_native_live_inference",
]


if __name__ == "__main__":
    raise SystemExit(main())
