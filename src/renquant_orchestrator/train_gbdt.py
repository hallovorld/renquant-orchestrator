#!/usr/bin/env python
"""GBDT panel-LTR training — fully self-contained in the subrepos.

Trains the panel-LTR model entirely from the pinned ``renquant-model`` engine:
its own data-side pipeline (load panel → fit normalization, from ``--data-dir``)
plus the model-side (walk-forward CV → booster → version:3 artifact) plus the
contract-side (content fingerprint → inference smoke → persist). NO umbrella code
and NO ``kernel.*`` — only the model/common/base-data/artifacts pins + a data dir.

The booster math is byte-identical to the umbrella's production trainer (pinned by
renquant-model's test_panel_trainer_parity). The artifact carries a self-describing
content fingerprint rather than the umbrella's strategy-config fingerprint, and the
umbrella's per-regime sentiment training gate (which needs the HMM regime detector)
is not applied here — it can be lifted + injected as a Task later.

Usage:
    python src/renquant_orchestrator/train_gbdt.py
    python src/renquant_orchestrator/train_gbdt.py --train-cutoff 2024-06-01 --side-label wf
    python src/renquant_orchestrator/train_gbdt.py --data-dir /path/to/data --output-path out.json
"""
from __future__ import annotations

import argparse
import logging
import sys
import uuid
from pathlib import Path

import pandas as pd

GITHUB = Path(__file__).resolve().parents[3]          # …/github
DEFAULT_DATA_DIR = GITHUB / "RenQuant" / "data"        # data lives in the umbrella (gitignored)
_PIN_SRCS = ["renquant-common", "renquant-base-data", "renquant-artifacts", "renquant-model"]

log = logging.getLogger("orchestrator.train_gbdt")


def _bootstrap() -> None:
    for name in _PIN_SRCS:
        src = GITHUB / name / "src"
        if src.is_dir() and str(src) not in sys.path:
            sys.path.insert(0, str(src))


_bootstrap()

from renquant_model_gbdt import GbdtTrainingContext, build_training_pipeline  # noqa: E402
from renquant_model_gbdt.panel_trainer import (  # noqa: E402
    DEFAULT_LABEL, DEFAULT_N_ROUNDS, PANEL_LTR_PARAMS,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--data-dir", type=str, default=None,
                   help="Directory with alpha158/fund parquets + stats (default: umbrella data/).")
    p.add_argument("--output-path", type=str, default=None)
    p.add_argument("--train-cutoff", type=str, default=None)
    p.add_argument("--side-label", type=str, default=None)
    p.add_argument("--label", type=str, default=None)
    p.add_argument("--num-boost-round", type=int, default=DEFAULT_N_ROUNDS)
    p.add_argument("--cv-n-splits", type=int, default=3)
    p.add_argument("--cv-embargo-days", type=int, default=60)
    p.add_argument("--nthread", type=int, default=None)
    p.add_argument("--skip-cv", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    args = parse_args(argv)

    data_dir = Path(args.data_dir) if args.data_dir else DEFAULT_DATA_DIR
    cutoff_date = pd.Timestamp(args.train_cutoff) if args.train_cutoff else None
    if cutoff_date is not None and not args.side_label:
        raise SystemExit("--side-label is required when --train-cutoff is set")
    out_path = (Path(args.output_path) if args.output_path
                else data_dir / "panel-ltr-prod-alpha158-fund-fwd60d.json")
    if cutoff_date is not None and "walkforward" not in str(out_path).lower():
        raise SystemExit(
            f"--train-cutoff set but --output-path {str(out_path)!r} does not contain "
            "'walkforward'. §5.13.13: refusing to risk overwriting production artifact.")

    params = dict(PANEL_LTR_PARAMS)
    if args.nthread:
        params["nthread"] = args.nthread

    sys.stderr.write(
        f"[orchestrator.train_gbdt] self-contained pin training; data_dir={data_dir}\n")
    ctx = GbdtTrainingContext(
        label=args.label or DEFAULT_LABEL, params=params, num_boost_round=args.num_boost_round,
        cv_n_splits=args.cv_n_splits, cv_embargo_days=args.cv_embargo_days, skip_cv=args.skip_cv,
        data_dir=str(data_dir), cutoff_date=cutoff_date, side_label=args.side_label,
        output_path=str(out_path), train_run_id=str(uuid.uuid4())[:8],
        training_notes="alpha158 + SEC fund panel-LTR, self-contained subrepo training",
    )
    result = build_training_pipeline().run(ctx)
    log.info("Pipeline %s ok=%s elapsed=%.1fs steps=%s", result.name, result.ok,
             result.elapsed_sec, [s.job_name for s in result.steps])
    if ctx.artifact and ctx.artifact.get("oos_per_fold_ic"):
        log.info("OOS IC: mean=%+.4f folds=%s", ctx.artifact.get("oos_mean_ic"),
                 [round(x, 4) for x in ctx.artifact["oos_per_fold_ic"]])
    log.info("Feature cols (n=%d)", len(ctx.feat_cols))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
