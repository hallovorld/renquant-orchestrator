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
import json
import os
from pathlib import Path
import subprocess
import sys

from renquant_common import Job, Pipeline, Task

from .runtime_paths import resolve_subrepo_root


GITHUB = Path(__file__).resolve().parents[3]
DEFAULT_REPO_DIR = GITHUB / "RenQuant"
DEFAULT_DATASET = "alpha158_qlib_dataset.parquet"
DEFAULT_LABEL = "fwd_5d_excess"
DEFAULT_LOOKAHEAD_DAYS = 5
_REQUIRED_REPO_PATHS = [Path("data")]
_SUBREPO_NAMES = [
    "renquant-orchestrator",
    "renquant-common",
    "renquant-base-data",
    "renquant-artifacts",
    "renquant-model",
    "renquant-pipeline",
    "renquant-execution",
    "renquant-strategy-104",
    "renquant-backtesting",
]


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


def _subrepo_srcs(repo_dir: Path) -> list[Path]:
    subrepo_root = resolve_subrepo_root(repo_dir)
    return [subrepo_root / name / "src" for name in _SUBREPO_NAMES]


def _subrepo_pythonpath(repo_dir: Path, env: dict[str, str] | None = None) -> dict[str, str]:
    out = dict(os.environ if env is None else env)
    srcs = _subrepo_srcs(repo_dir)
    missing = [src for src in srcs if not src.is_dir()]
    if out.get("RENQUANT_STRICT_SUBREPO_PATHS") == "1" and missing:
        joined = ", ".join(str(src) for src in missing)
        raise FileNotFoundError(f"missing multirepo source paths: {joined}")
    existing = out.get("PYTHONPATH", "")
    out["PYTHONPATH"] = os.pathsep.join([*(str(src) for src in srcs), existing])
    out.setdefault("RENQUANT_REPO_ROOT", str(repo_dir))
    out.setdefault("RENQUANT_DATA_ROOT", str(repo_dir))
    out.setdefault("RENQUANT_STRATEGY_DIR", str(repo_dir / "backtesting" / "renquant_104"))
    return out


def _run(ctx: RetrainLinearContext, cmd: list[str], *, cwd: Path | None = None) -> None:
    ctx.commands.append(cmd)
    if ctx.dry_run:
        return
    result = subprocess.run(cmd, cwd=str(cwd or ctx.repo_dir), env=_subrepo_pythonpath(ctx.repo_dir))
    if result.returncode != 0:
        raise RuntimeError(f"command failed rc={result.returncode}: {' '.join(cmd)}")


def _read_json_object(path: Path, label: str) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"{label} did not produce {path}")
    if path.stat().st_size <= 2:
        raise ValueError(f"{label} artifact is too small: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} artifact is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} artifact must be a JSON object: {path}")
    return payload


def _validate_scorer_artifact(path: Path) -> None:
    payload = _read_json_object(path, "alpha158 linear training")
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
    payload = _read_json_object(path, "alpha158 linear calibrator refit")
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


def _resolve(repo_dir: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else repo_dir / path


def _default_scorer_artifact(repo_dir: Path) -> Path:
    return repo_dir / "backtesting" / "renquant_104" / "artifacts" / "panel-ltr.alpha158_linear.json"


def _default_calibrator_artifact(repo_dir: Path) -> Path:
    return repo_dir / "backtesting" / "renquant_104" / "artifacts" / "panel-rank-calibration.alpha158_linear.json"


def _staging_path(path: Path) -> Path:
    return path.with_suffix(".staging.json")


def _validate_repo_dir(repo_dir: Path) -> None:
    missing = [rel for rel in _REQUIRED_REPO_PATHS if not (repo_dir / rel).exists()]
    if missing:
        joined = ", ".join(str(rel) for rel in missing)
        raise FileNotFoundError(f"repo-dir is not a usable RenQuant checkout; missing: {joined}")


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
    _validate_repo_dir(repo_dir)
    scorer_out = _resolve(repo_dir, args.scorer_out) if args.scorer_out else _default_scorer_artifact(repo_dir)
    calibrator_out = (
        _resolve(repo_dir, args.calibrator_out)
        if args.calibrator_out
        else _default_calibrator_artifact(repo_dir)
    )
    if args.staged:
        if not args.scorer_out:
            scorer_out = _staging_path(scorer_out)
        if not args.calibrator_out:
            calibrator_out = _staging_path(calibrator_out)
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
