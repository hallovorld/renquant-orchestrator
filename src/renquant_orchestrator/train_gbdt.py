#!/usr/bin/env python
"""GBDT panel-LTR training, orchestrated across the pinned subrepos.

Training is one ``renquant_common`` Task/Job/Pipeline chain:

    DataPrepJob         LoadPanelTask → SentimentGateTask → BuildNormalizationTask
    ModelTrainingJob    WalkForwardCVTask → TrainBoosterTask → BuildArtifactTask   (renquant-model engine)
    ArtifactContractJob StampFingerprintTask → AttachSmokeTask → WriteArtifactTask

The model-side Job comes from the pinned ``renquant-model`` engine; the data- and
contract-side Tasks reuse the umbrella's loaders/stampers (they read on-disk
stats/fund files + strategy configs that are not yet lifted to a pin). The
artifact is byte-identical to the umbrella's ``scripts/train_production_model.py``
for the same args, excluding the two fields that script randomizes
(train_run_id=uuid4, trained_date=utcnow).

This module lives in the orchestrator — it is integration glue across repos, not
umbrella code. Run it from anywhere; data files resolve against the umbrella root.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from pathlib import Path

import pandas as pd

GITHUB = Path(__file__).resolve().parents[3]          # …/github
UMBRELLA = GITHUB / "RenQuant"
STRATEGY_DIR = UMBRELLA / "backtesting" / "renquant_104"
_PIN_SRCS = ["renquant-common", "renquant-base-data", "renquant-artifacts", "renquant-model"]

log = logging.getLogger("orchestrator.train_gbdt")


def _bootstrap() -> None:
    for name in _PIN_SRCS:
        src = GITHUB / name / "src"
        if src.is_dir() and str(src) not in sys.path:
            sys.path.insert(0, str(src))
    for p in (str(STRATEGY_DIR), str(UMBRELLA)):
        if p not in sys.path:
            sys.path.insert(0, p)


_bootstrap()  # precede renquant_common / engine imports

from renquant_common import Job, Pipeline, Task  # noqa: E402
from renquant_model_gbdt import GbdtTrainingContext, ModelTrainingJob  # noqa: E402


# ── Umbrella data-side Tasks (read on-disk panel/stats/fund + strategy config) ──

class LoadPanelTask(Task):
    """Load + slice the panel; seed cutoff/side_label artifact fields (in order)."""

    def __init__(self, load_fn, infer_fn, args, cutoff_date) -> None:
        self.load_fn, self.infer_fn, self.args, self.cutoff_date = load_fn, infer_fn, args, cutoff_date

    def run(self, ctx: GbdtTrainingContext) -> bool | None:
        train, feat_cols, label = self.load_fn(
            self.cutoff_date, watchlist_file=self.args.watchlist_file,
            label_override=self.args.label, cutoff_embargo_days=self.args.cutoff_embargo_days,
        )
        ctx.train, ctx.feat_cols, ctx.label = train, feat_cols, label
        ctx.lookahead_days = self.infer_fn(label)
        if self.cutoff_date is not None:
            embargo = int(ctx.lookahead_days if self.args.cutoff_embargo_days is None
                          else self.args.cutoff_embargo_days)
            ctx.extra_artifact_fields["cutoff_date"] = self.cutoff_date.isoformat()
            ctx.extra_artifact_fields["cutoff_embargo_days"] = embargo
            ctx.extra_artifact_fields["effective_train_cutoff_date"] = (
                self.cutoff_date - pd.offsets.BDay(embargo)
            ).isoformat()
        if self.args.side_label is not None:
            ctx.extra_artifact_fields["side_label"] = self.args.side_label
        return True


class SentimentGateTask(Task):
    """Apply the per-regime sentiment training gate; record its contract fields."""

    def __init__(self, build_fp, build_regime_map, apply_gate, args) -> None:
        self.build_fp, self.build_regime_map, self.apply_gate, self.args = (
            build_fp, build_regime_map, apply_gate, args)

    def run(self, ctx: GbdtTrainingContext) -> bool | None:
        fp_cfg = self.build_fp(
            fingerprint_config_path=self.args.fingerprint_config,
            watchlist_file=self.args.watchlist_file, label_used=ctx.label, feat_cols=ctx.feat_cols,
        )
        regime_map = self.build_regime_map(ctx.train["date"].unique(), fp_cfg)
        ctx.train, sentiment_contract = self.apply_gate(ctx.train, ctx.feat_cols, fp_cfg, regime_map)
        if sentiment_contract:
            ctx.extra_artifact_fields.update(sentiment_contract)
        return True


class BuildNormalizationTask(Task):
    """Fit the inference normalization chain; expose it as the CV per-fold builder."""

    def __init__(self, build_norm) -> None:
        self.build_norm = build_norm

    def run(self, ctx: GbdtTrainingContext) -> bool | None:
        ctx.mu, ctx.sd, ctx.norm_kind, ctx.raw_clip_low, ctx.raw_clip_high = (
            self.build_norm(ctx.train, ctx.feat_cols))
        ctx.normalization_builder = self.build_norm
        return True


# ── Umbrella contract-side Tasks ──

class StampFingerprintTask(Task):
    def __init__(self, stamp_fn, args) -> None:
        self.stamp_fn, self.args = stamp_fn, args

    def run(self, ctx: GbdtTrainingContext) -> bool | None:
        fp = self.stamp_fn(
            ctx.artifact, fingerprint_config_path=self.args.fingerprint_config,
            watchlist_file=self.args.watchlist_file, label_used=ctx.label, feat_cols=ctx.feat_cols,
        )
        log.info("Fingerprint: %s", fp)
        return True


class AttachSmokeTask(Task):
    def __init__(self, smoke_fn) -> None:
        self.smoke_fn = smoke_fn

    def run(self, ctx: GbdtTrainingContext) -> bool | None:
        self.smoke_fn(ctx.artifact, ctx.booster, ctx.feat_cols)
        return True


class WriteArtifactTask(Task):
    def __init__(self, out_path: Path) -> None:
        self.out_path = out_path

    def run(self, ctx: GbdtTrainingContext) -> bool | None:
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self.out_path.write_text(json.dumps(ctx.artifact))
        log.info("Saved artifact: %s  (size=%.1f MB)", self.out_path,
                 self.out_path.stat().st_size / 1e6)
        return True


class _Sequence(Job):
    """A Job that runs a fixed list of Tasks in order."""

    def __init__(self, tasks: list[Task]) -> None:
        self._tasks = tasks

    @property
    def tasks(self) -> list[Task]:
        return self._tasks


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--train-cutoff", type=str, default=None)
    p.add_argument("--output-path", type=str, default=None)
    p.add_argument("--side-label", type=str, default=None)
    p.add_argument("--label", type=str, default=None)
    p.add_argument("--watchlist-file", type=str, default=None)
    p.add_argument("--fingerprint-config", type=str, default=None)
    p.add_argument("--cutoff-embargo-days", type=int, default=None)
    p.add_argument("--cv-n-splits", type=int, default=3)
    p.add_argument("--cv-embargo-days", type=int, default=60)
    p.add_argument("--skip-cv", action="store_true")
    return p.parse_args(argv)


def build_pipeline(args, fns, cutoff_date, out_path):
    """Assemble the end-to-end GBDT training Pipeline from umbrella + engine Tasks."""
    return Pipeline([
        _Sequence([
            LoadPanelTask(fns["load"], fns["infer"], args, cutoff_date),
            SentimentGateTask(fns["build_fp"], fns["regime_map"], fns["gate"], args),
            BuildNormalizationTask(fns["norm"]),
        ]),
        ModelTrainingJob(),  # ← renquant-model engine: CV → booster → artifact
        _Sequence([
            StampFingerprintTask(fns["stamp"], args),
            AttachSmokeTask(fns["smoke"]),
            WriteArtifactTask(out_path),
        ]),
    ], name="panel-gbdt-training")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    args = parse_args(argv)

    from scripts.train_production_model import (  # noqa: PLC0415
        LABEL, N_ROUNDS, PARAMS,
        apply_sentiment_training_gate, attach_inference_smoke, build_fingerprint_config,
        build_normalization, build_sentiment_training_regime_map,
        infer_label_lookahead_days, load_and_slice_panel, stamp_fingerprint,
    )
    sys.stderr.write(
        "[orchestrator.train_gbdt] model-side Job=renquant_model_gbdt.ModelTrainingJob (pin); "
        "data/contract Tasks=umbrella scripts.train_production_model\n"
    )

    cutoff_date = pd.Timestamp(args.train_cutoff) if args.train_cutoff else None
    if cutoff_date is not None and not args.side_label:
        raise SystemExit("--side-label is required when --train-cutoff is set")
    out_path = (Path(args.output_path) if args.output_path
                else UMBRELLA / "data" / "panel-ltr-prod-alpha158-fund-fwd60d.json")
    if cutoff_date is not None and "walkforward" not in str(out_path).lower():
        raise SystemExit(
            f"--train-cutoff set but --output-path {str(out_path)!r} does not contain "
            "'walkforward'. §5.13.13: refusing to risk overwriting production artifact.")

    label_used = args.label or LABEL
    notes = (
        "alpha158 + SEC fund (5) + PEAD (3, E47 promoted 2026-05-08) on R1K "
        "291 tickers, fwd_60d label. PEAD real_signal lift +0.022 over "
        "alpha158+5fund baseline (paired §5.2 sanity passed)."
        + (f" [side_label={args.side_label}]" if args.side_label else "")
    )
    fns = {
        "load": load_and_slice_panel, "infer": infer_label_lookahead_days,
        "build_fp": build_fingerprint_config, "regime_map": build_sentiment_training_regime_map,
        "gate": apply_sentiment_training_gate, "norm": build_normalization,
        "stamp": stamp_fingerprint, "smoke": attach_inference_smoke,
    }
    pipeline = build_pipeline(args, fns, cutoff_date, out_path)
    ctx = GbdtTrainingContext(
        label=label_used, params=PARAMS, num_boost_round=N_ROUNDS,
        cv_n_splits=args.cv_n_splits, cv_embargo_days=args.cv_embargo_days,
        skip_cv=args.skip_cv, train_run_id=str(uuid.uuid4())[:8], training_notes=notes,
    )
    result = pipeline.run(ctx)
    log.info("Pipeline %s ok=%s elapsed=%.1fs steps=%s", result.name, result.ok,
             result.elapsed_sec, [s.job_name for s in result.steps])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
