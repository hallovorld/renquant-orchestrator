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
import importlib.util
import json
import logging
import sys
import uuid
from pathlib import Path

import pandas as pd

GITHUB = Path(__file__).resolve().parents[3]          # …/github
DEFAULT_DATA_DIR = GITHUB / "RenQuant" / "data"        # data lives in the umbrella (gitignored)
DEFAULT_STRATEGY_CONFIG = GITHUB / "renquant-strategy-104" / "configs" / "strategy_config.json"
LEGACY_STRATEGY_CONFIG = GITHUB / "RenQuant" / "backtesting" / "renquant_104" / "strategy_config.json"
_LEGACY_CONFIG_CONSISTENCY = (GITHUB / "renquant-pipeline" / "src" / "renquant_pipeline"
                              / "kernel" / "config_consistency.py")
_PIN_SRCS = ["renquant-common", "renquant-base-data", "renquant-artifacts", "renquant-model"]

log = logging.getLogger("orchestrator.train_gbdt")


def _production_fingerprint(strategy_config_path: Path) -> tuple[str | None, dict | None]:
    """Compute the production config fingerprint from the strategy config, using the
    shared config_consistency implementation. This is the same function + config
    the runtime scorer uses, so the stamped fingerprint matches the scorer's live
    check and the artifact loads."""
    if not strategy_config_path.exists():
        log.warning("strategy config or config_consistency missing — falling back to content fp")
        return None, None
    try:
        from renquant_common.config_consistency import (  # noqa: PLC0415
            _model_relevant_fields,
            fingerprint_config,
        )
    except ImportError:
        if not _LEGACY_CONFIG_CONSISTENCY.exists():
            log.warning(
                "config_consistency unavailable — falling back to content fp",
            )
            return None, None
        spec = importlib.util.spec_from_file_location(
            "_cc_fp",
            _LEGACY_CONFIG_CONSISTENCY,
        )
        cc = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cc)
        fingerprint_config = cc.fingerprint_config
        _model_relevant_fields = cc._model_relevant_fields
    cfg = json.loads(strategy_config_path.read_text())
    return fingerprint_config(cfg), _model_relevant_fields(cfg)


def _default_strategy_config() -> Path:
    """Prefer the strategy subrepo config, but keep umbrella fallback during migration."""
    return DEFAULT_STRATEGY_CONFIG if DEFAULT_STRATEGY_CONFIG.exists() else LEGACY_STRATEGY_CONFIG


UMBRELLA = GITHUB / "RenQuant"
STRATEGY_DIR = UMBRELLA / "backtesting" / "renquant_104"


def _bootstrap() -> None:
    for name in _PIN_SRCS:
        src = GITHUB / name / "src"
        if src.is_dir() and str(src) not in sys.path:
            sys.path.insert(0, str(src))
    # Umbrella on path for the not-yet-lifted sentiment training gate (needs the HMM
    # regime detector). Data-load + normalization + model stay in renquant-model.
    for p in (str(STRATEGY_DIR), str(UMBRELLA)):
        if p not in sys.path:
            sys.path.insert(0, p)


_bootstrap()

from renquant_common import Job, Pipeline, Task  # noqa: E402
from renquant_model_gbdt import (  # noqa: E402
    ArtifactContractJob, BuildNormalizationTask, GbdtTrainingContext,
    LoadPanelTask, ModelTrainingJob, build_training_pipeline,
)
from renquant_model_gbdt.panel_trainer import (  # noqa: E402
    DEFAULT_LABEL, DEFAULT_N_ROUNDS, PANEL_LTR_PARAMS,
)


class _Seq(Job):
    """A Job that runs a fixed list of Tasks in order."""

    def __init__(self, tasks: list) -> None:
        self._tasks = tasks

    @property
    def tasks(self) -> list:
        return self._tasks


class SentimentGateTask(Task):
    """Per-regime sentiment training gate (PRIME DIRECTIVE) via the umbrella's proven
    HMM-regime replay — bridged here until the regime detector is lifted to a pin.
    Zeroes sentiment features in disabled-regime training rows + records the
    sentiment_runtime_gate_contract the panel scorer requires."""

    def run(self, ctx: GbdtTrainingContext) -> bool | None:
        from scripts.train_production_model import (  # noqa: PLC0415
            apply_sentiment_training_gate, build_fingerprint_config,
            build_sentiment_training_regime_map,
        )
        fp_cfg = build_fingerprint_config(
            fingerprint_config_path=None, watchlist_file=None,
            label_used=ctx.label, feat_cols=ctx.feat_cols,
        )
        regime_map = build_sentiment_training_regime_map(ctx.train["date"].unique(), fp_cfg)
        ctx.train, contract = apply_sentiment_training_gate(
            ctx.train, ctx.feat_cols, fp_cfg, regime_map)
        if contract:
            ctx.extra_artifact_fields.update(contract)
            log.info("Sentiment gate: zeroed %d rows in regimes %s",
                     contract.get("sentiment_runtime_gate_zeroed_rows"),
                     contract.get("sentiment_runtime_gate_disabled_regimes"))
        return True


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
    p.add_argument("--strategy-config", type=str, default=None,
                   help="Strategy config whose model-relevant fields set the production "
                        "config_fingerprint (default: renquant-strategy-104 config, "
                        "falling back to umbrella strategy_config.json). "
                        "Pass 'none' to stamp a self-describing content hash instead.")
    p.add_argument("--skip-sentiment-gate", action="store_true",
                   help="Skip the per-regime sentiment training gate (self-contained "
                        "research mode; the artifact then fails the production panel "
                        "contract's sentiment requirement).")
    p.add_argument("--drop-sentiment", action="store_true",
                   help="Exclude the 3 sentiment features (mean_sentiment / n_articles_log "
                        "/ sentiment_pos_share). 2026-05-28 placebo-clean WF showed they "
                        "DILUTE the signal (clean IC -0.005 → +0.010). Implies "
                        "--skip-sentiment-gate (no sentiment features → no gate needed → "
                        "fully self-contained, no umbrella bridge).")
    p.add_argument("--exclude-features", type=str, default=None,
                   help="Comma-separated extra feature columns to drop.")
    p.add_argument("--skip-cv", action="store_true")
    p.add_argument("--training-window-years", type=float, default=None,
                   help="Diagnostic: width of the training window in years. "
                        "Stamped into training_runs.training_window_years for "
                        "post-hoc analysis; does NOT change training behaviour.")
    return p.parse_args(argv)


_SENTIMENT_FEATURES = ["mean_sentiment", "n_articles_log", "sentiment_pos_share"]


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

    # Production config fingerprint so the runtime scorer can load the artifact.
    fp, fp_fields = (None, None)
    if args.strategy_config is None or args.strategy_config.lower() != "none":
        sc_path = Path(args.strategy_config) if args.strategy_config else _default_strategy_config()
        fp, fp_fields = _production_fingerprint(sc_path)

    # Feature exclusion. --drop-sentiment removes the 3 sentiment features (found to
    # dilute the signal) and implies skipping the sentiment gate (no sentiment feature
    # → no gate → fully self-contained, no umbrella bridge).
    exclude = list(_SENTIMENT_FEATURES) if args.drop_sentiment else []
    if args.exclude_features:
        exclude += [c.strip() for c in args.exclude_features.split(",") if c.strip()]
    skip_gate = args.skip_sentiment_gate or args.drop_sentiment

    sys.stderr.write(
        f"[orchestrator.train_gbdt] self-contained pin training; data_dir={data_dir}; "
        f"config_fp={fp or 'content-hash'}; drop_sentiment={args.drop_sentiment}\n")
    ctx = GbdtTrainingContext(
        label=args.label or DEFAULT_LABEL, params=params, num_boost_round=args.num_boost_round,
        cv_n_splits=args.cv_n_splits, cv_embargo_days=args.cv_embargo_days, skip_cv=args.skip_cv,
        data_dir=str(data_dir), cutoff_date=cutoff_date, side_label=args.side_label,
        output_path=str(out_path), train_run_id=str(uuid.uuid4())[:8],
        config_fingerprint=fp, config_fingerprint_fields=fp_fields,
        exclude_features=exclude or None,
        training_notes="alpha158 + SEC fund panel-LTR, self-contained subrepo training",
    )
    # Assemble the pipeline: model's data + model + contract Jobs, with the
    # production sentiment gate inserted between panel load and normalization
    # (zeroing must precede normalization, matching the production trainer).
    if skip_gate:
        pipeline = build_training_pipeline()
    else:
        pipeline = Pipeline([
            _Seq([LoadPanelTask(), SentimentGateTask(), BuildNormalizationTask()]),
            ModelTrainingJob(),
            ArtifactContractJob(),
        ], name="panel-gbdt-training")
    result = pipeline.run(ctx)
    log.info("Pipeline %s ok=%s elapsed=%.1fs steps=%s", result.name, result.ok,
             result.elapsed_sec, [s.job_name for s in result.steps])
    if ctx.artifact and ctx.artifact.get("oos_per_fold_ic"):
        log.info("OOS IC: mean=%+.4f folds=%s", ctx.artifact.get("oos_mean_ic"),
                 [round(x, 4) for x in ctx.artifact["oos_per_fold_ic"]])
    log.info("Feature cols (n=%d)", len(ctx.feat_cols))

    # Record the run to data/sim_runs.db::training_runs (best-effort, non-fatal).
    # Then refresh renquant-model/README.md so the "Latest models" table is current.
    _record_and_refresh(ctx, args, elapsed_sec=result.elapsed_sec)
    return 0


def _record_and_refresh(ctx, args, *, elapsed_sec: float) -> None:
    import datetime as _dt
    import os
    import sqlite3
    import subprocess
    import sys
    from pathlib import Path as _Path
    # Derive DB path from RENQUANT_STRATEGY_DIR when set (preferred over a
    # machine-specific hardcode); env var still wins.
    strat = os.environ.get("RENQUANT_STRATEGY_DIR")
    default_db = (_Path(strat).resolve().parent.parent / "data" / "sim_runs.db"
                  if strat else _Path("data") / "sim_runs.db")
    db = _Path(os.environ.get("RENQUANT_TRAINING_DB", str(default_db)))
    if not db.exists():
        return
    try:
        from renquant_pipeline.kernel.persistence import record_training_run  # noqa: PLC0415
        conn = sqlite3.connect(str(db))
        record_training_run(
            conn,
            run_date=_dt.datetime.utcnow(),
            strategy=os.environ.get("RENQUANT_STRATEGY_NAME", "renquant_104"),
            artifact_type="panel_ltr_xgboost",
            oos_mean_ic=ctx.artifact.get("oos_mean_ic") if ctx.artifact else None,
            n_features=len(ctx.feat_cols) if ctx.feat_cols else None,
            artifact_path=str(args.output_path) if args.output_path else None,
            elapsed_sec=elapsed_sec,
            trigger=os.environ.get("RENQUANT_TRAIN_TRIGGER", "manual"),
            device="cpu",
            deterministic=True,
            notes=f"side_label={args.side_label or '-'} train_cutoff={args.train_cutoff or '-'}",
            training_window_years=getattr(args, "training_window_years", None),
            also_log_jsonl=False,
        )
        conn.commit()
        conn.close()
    except Exception as exc:  # noqa: BLE001
        log.warning("record_training_run skipped: %s", exc)
    # Refresh README — best-effort
    readme_refresh = _Path(__file__).resolve().parents[3] / "renquant-model" / "scripts" / "refresh_readme_latest_models.py"
    readme = _Path(__file__).resolve().parents[3] / "renquant-model" / "README.md"
    if readme_refresh.exists() and readme.exists():
        try:
            subprocess.run(
                [sys.executable, str(readme_refresh), "--db", str(db), "--readme", str(readme)],
                check=False, timeout=30,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("README refresh skipped: %s", exc)


if __name__ == "__main__":
    raise SystemExit(main())
