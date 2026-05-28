#!/usr/bin/env python
"""PatchTST training, orchestrated through PatchTstTrainingPipeline.

Runs the pinned ``renquant-model`` PatchTST trainer via the pipeline's
Task/Job/Pipeline shell (ValidateManifest → LoadFrame → TrainPatchTst →
RunSanityTriad → BuildArtifactManifest), using the SequenceTrainer adapter that
wraps the lifted HF trainer + shapes its summary into a model-evidence-contract
checkpoint. Its data-side ``kernel.*`` deps resolve from the umbrella via
``RENQUANT_STRATEGY_DIR`` (same model-in-subrepo / data-from-baseline split as the
GBDT driver).

PatchTST weights are NOT byte-reproducible (torch/MPS); parity is structural.

Usage:
    python src/renquant_orchestrator/train_patchtst.py --cut cut1_covid --epochs 1 --device mps
"""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import sys
from pathlib import Path

GITHUB = Path(__file__).resolve().parents[3]          # …/github
UMBRELLA = GITHUB / "RenQuant"
STRATEGY_DIR = UMBRELLA / "backtesting" / "renquant_104"
_PIN_SRCS = ["renquant-common", "renquant-base-data", "renquant-artifacts", "renquant-model"]

log = logging.getLogger("orchestrator.train_patchtst")


def _bootstrap() -> None:
    for name in _PIN_SRCS:
        src = GITHUB / name / "src"
        if src.is_dir() and str(src) not in sys.path:
            sys.path.insert(0, str(src))
    os.environ.setdefault("RENQUANT_STRATEGY_DIR", str(STRATEGY_DIR))
    for p in (str(STRATEGY_DIR), str(UMBRELLA)):
        if p not in sys.path:
            sys.path.insert(0, p)


_bootstrap()

from renquant_model_patchtst.pipelines import PatchTstTrainingContext  # noqa: E402
from renquant_model_patchtst.training import build_training_pipeline  # noqa: E402


def _lookahead_days(label: str) -> int:
    m = re.search(r"fwd_(\d+)d", str(label))
    return int(m.group(1)) if m else 60


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--dataset", default=str(UMBRELLA / "data" / "transformer_v4_wl200_clean.parquet"))
    p.add_argument("--cut", default="cut1_covid")
    p.add_argument("--label", default="fwd_60d_excess")
    p.add_argument("--epochs", type=int, default=1)
    p.add_argument("--device", default="mps", choices=["cpu", "mps", "cuda"])
    p.add_argument("--seq-len", type=int, default=32)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--save-model", action="store_true")
    p.add_argument("--output-dir", default=str(UMBRELLA / "artifacts" / "hf_patchtst"))
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    args = parse_args(argv)
    dataset = Path(args.dataset)

    fp = "sha256:" + hashlib.sha256(
        f"{dataset.name}:{dataset.stat().st_size if dataset.exists() else 0}".encode()
    ).hexdigest()
    manifest = {
        "dataset_id": dataset.stem, "fingerprint": fp, "schema_version": "transformer_v4",
        "uri": f"object://renquant-data/{dataset.name}", "asset_class": "equity",
        "label_col": args.label, "lookahead_days": _lookahead_days(args.label),
        "split_policy": "purged-walk-forward",
    }
    model_config = {
        "architecture": "hf_patchtst", "dataset": str(dataset), "cut": args.cut,
        "label": args.label, "epochs": args.epochs, "device": args.device,
        "seq_len": args.seq_len, "seed": args.seed, "save_model": args.save_model,
        "embargo_days": _lookahead_days(args.label),
    }
    sys.stderr.write("[orchestrator.train_patchtst] PatchTstTrainingPipeline via "
                     "renquant_model_patchtst (pin); data deps from umbrella\n")
    ctx = PatchTstTrainingContext(
        dataset_manifest=manifest, model_config=model_config,
        output_dir=Path(args.output_dir),
    )
    result = build_training_pipeline().run(ctx)
    log.info("Pipeline %s ok=%s elapsed=%.1fs steps=%s", result.name, result.ok,
             result.elapsed_sec, [s.job_name for s in result.steps])
    if ctx.checkpoint_artifact:
        log.info("checkpoint: %s oos_mean_ic=%+.4f per_regime=%s",
                 ctx.checkpoint_artifact["artifact_id"],
                 ctx.checkpoint_artifact["oos_mean_ic"],
                 ctx.checkpoint_artifact.get("per_regime_ic"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
