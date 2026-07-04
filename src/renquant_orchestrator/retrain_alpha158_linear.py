"""Daily alpha158 linear retrain pipeline owned by renquant-orchestrator.

This keeps the existing production trust boundary: the umbrella checkout still
owns data/artifact paths and promotion, while feature materialization runs
through ``renquant-base-data`` and scorer/calibrator fitting run through
``renquant-model``.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import datetime as dt
from pathlib import Path
import sys

from renquant_common import Job, Pipeline, Task

from .retrain_common import (
    read_json_object,
    resolve_path,
    run_subprocess,
    staging_path,
    validate_repo_dir,
)
from .runtime_paths import default_github_root, default_repo_root


GITHUB = default_github_root()
DEFAULT_REPO_DIR = default_repo_root()
DEFAULT_DATASET = "alpha158_qlib_dataset.parquet"
DEFAULT_LABEL = "fwd_5d_excess"
DEFAULT_LOOKAHEAD_DAYS = 5


@dataclass
class RetrainLinearContext:
    repo_dir: Path
    scorer_out: Path
    calibrator_out: Path
    python: str = sys.executable
    rebuild_features: bool = True
    label: str = DEFAULT_LABEL
    estimator: str = "ols"
    alpha: float = 1.0
    lookahead_days: int = DEFAULT_LOOKAHEAD_DAYS
    dry_run: bool = False
    commands: list[list[str]] = field(default_factory=list)

    @property
    def data_dir(self) -> Path:
        return self.repo_dir / "data"

    @property
    def dataset(self) -> Path:
        return self.data_dir / DEFAULT_DATASET


def _run(ctx: RetrainLinearContext, cmd: list[str], *, cwd: Path | None = None) -> None:
    run_subprocess(ctx, cmd, cwd=cwd)


def _validate_scorer_artifact(path: Path) -> None:
    payload = read_json_object(path, "alpha158 linear training")
    if payload.get("kind") != "panel_linear":
        raise ValueError(f"alpha158 linear artifact kind={payload.get('kind')!r}; expected panel_linear")
    if not payload.get("feature_cols"):
        raise ValueError(f"alpha158 linear artifact missing feature_cols: {path}")
    expected = dt.date.today().isoformat()
    if payload.get("trained_date") != expected:
        raise ValueError(
            f"alpha158 linear artifact trained_date={payload.get('trained_date')!r}; expected {expected}: {path}"
        )


def _validate_calibrator_artifact(path: Path) -> None:
    payload = read_json_object(path, "alpha158 linear calibrator refit")
    if payload.get("kind") != "global_panel_calibration":
        raise ValueError(f"calibrator artifact kind={payload.get('kind')!r}; expected global_panel_calibration")


class BuildAlpha158PanelTask(Task):
    def run(self, ctx: RetrainLinearContext) -> bool | None:
        if not ctx.rebuild_features:
            return True
        _run(
            ctx,
            [
                ctx.python,
                "-m",
                "renquant_base_data.alpha158_qlib_panel",
                "--data-dir",
                str(ctx.data_dir),
            ],
        )
        return True


class TrainLinearScorerTask(Task):
    def run(self, ctx: RetrainLinearContext) -> bool | None:
        cmd = [
            ctx.python,
            "-m",
            "renquant_model_alpha158_linear.trainer",
            "--dataset",
            str(ctx.dataset),
            "--label",
            ctx.label,
            "--estimator",
            ctx.estimator,
            "--alpha",
            str(ctx.alpha),
            "--output",
            str(ctx.scorer_out),
        ]
        _run(ctx, cmd)
        if ctx.dry_run:
            return True
        _validate_scorer_artifact(ctx.scorer_out)
        return True


class RefitLinearCalibratorTask(Task):
    def run(self, ctx: RetrainLinearContext) -> bool | None:
        cmd = [
            ctx.python,
            "-m",
            "renquant_model_alpha158_linear.calibrator",
            "--data-dir",
            str(ctx.data_dir),
            "--scorer-artifact",
            str(ctx.scorer_out),
            "--out",
            str(ctx.calibrator_out),
            "--label-col",
            ctx.label,
            "--lookahead",
            str(ctx.lookahead_days),
        ]
        _run(ctx, cmd)
        if ctx.dry_run:
            return True
        _validate_calibrator_artifact(ctx.calibrator_out)
        return True


class RetrainLinearJob(Job):
    @property
    def tasks(self) -> list[Task]:
        return [
            BuildAlpha158PanelTask(),
            TrainLinearScorerTask(),
            RefitLinearCalibratorTask(),
        ]


def build_pipeline() -> Pipeline:
    return Pipeline([RetrainLinearJob()], name="daily-alpha158-linear-retrain")


def _default_scorer_artifact(repo_dir: Path) -> Path:
    return repo_dir / "backtesting" / "renquant_104" / "artifacts" / "panel-ltr.alpha158_linear.json"


def _default_calibrator_artifact(repo_dir: Path) -> Path:
    return repo_dir / "backtesting" / "renquant_104" / "artifacts" / "panel-rank-calibration.alpha158_linear.json"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-dir", type=Path, default=DEFAULT_REPO_DIR)
    parser.add_argument("--scorer-out", default=None)
    parser.add_argument("--calibrator-out", default=None)
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--skip-features", action="store_true")
    parser.add_argument("--label", default=DEFAULT_LABEL)
    parser.add_argument("--estimator", default="ols", choices=["ols", "ridge"])
    parser.add_argument("--alpha", type=float, default=1.0)
    parser.add_argument("--lookahead", type=int, default=DEFAULT_LOOKAHEAD_DAYS)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_dir = args.repo_dir.expanduser().resolve()
    validate_repo_dir(repo_dir)
    scorer_out = resolve_path(repo_dir, args.scorer_out) if args.scorer_out else _default_scorer_artifact(repo_dir)
    calibrator_out = (
        resolve_path(repo_dir, args.calibrator_out)
        if args.calibrator_out
        else _default_calibrator_artifact(repo_dir)
    )
    if args.staged:
        if not args.scorer_out:
            scorer_out = staging_path(scorer_out)
        if not args.calibrator_out:
            calibrator_out = staging_path(calibrator_out)
    ctx = RetrainLinearContext(
        repo_dir=repo_dir,
        scorer_out=scorer_out,
        calibrator_out=calibrator_out,
        rebuild_features=not args.skip_features,
        label=args.label,
        estimator=args.estimator,
        alpha=args.alpha,
        lookahead_days=args.lookahead,
        dry_run=args.dry_run,
    )
    build_pipeline().run(ctx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
