"""Weekly alpha158+fund retrain pipeline owned by renquant-orchestrator.

This is a transitional multirepo workflow: alpha158 materialization and
fund-panel merge run through ``renquant-base-data``. Calibrator refit still
calls the existing umbrella script, while the GBDT scorer is trained through
``renquant_orchestrator.train_gbdt`` plus the pinned ``renquant-model`` engine.
It preserves the weekly trust boundary: callers provide staging output paths,
and this module never promotes production artifacts.
"""
from __future__ import annotations

import argparse
import datetime as dt
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import subprocess
import sys

from renquant_common import Job, Pipeline, Task


GITHUB = Path(__file__).resolve().parents[3]
DEFAULT_REPO_DIR = GITHUB / "RenQuant"
_REQUIRED_REPO_PATHS = [
    Path("scripts/fit_calibrator_alpha158_fund.py"),
    Path("backtesting/renquant_104"),
]


@dataclass
class RetrainContext:
    repo_dir: Path
    xgb_artifact_out: Path
    calibrator_out: Path
    python: str = sys.executable
    truncate_to_sec_max: bool = True
    dry_run: bool = False
    commands: list[list[str]] = field(default_factory=list)

    @property
    def data_dir(self) -> Path:
        return self.repo_dir / "data"

    @property
    def strategy_config(self) -> Path:
        return self.repo_dir / "backtesting" / "renquant_104" / "strategy_config.json"


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


def _subrepo_srcs(repo_dir: Path) -> list[Path]:
    github = repo_dir.parent
    return [github / name / "src" for name in _SUBREPO_NAMES]


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
    out.setdefault("RENQUANT_STRATEGY_DIR", str(repo_dir / "backtesting" / "renquant_104"))
    return out


def _run(ctx: RetrainContext, cmd: list[str], *, cwd: Path | None = None) -> None:
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
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} artifact is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} artifact must be a JSON object: {path}")
    return payload


def _validate_scorer_artifact(path: Path) -> None:
    payload = _read_json_object(path, "GBDT training")
    if not payload.get("config_fingerprint"):
        raise ValueError(f"GBDT artifact missing config_fingerprint: {path}")
    expected = dt.datetime.utcnow().strftime("%Y-%m-%d")
    if payload.get("trained_date") != expected:
        raise ValueError(
            f"GBDT artifact trained_date={payload.get('trained_date')!r}; expected {expected}: {path}"
        )


def _validate_calibrator_artifact(path: Path) -> None:
    payload = _read_json_object(path, "calibrator refit")
    if not payload:
        raise ValueError(f"calibrator artifact is empty: {path}")


class BuildAlpha158PanelTask(Task):
    def run(self, ctx: RetrainContext) -> bool | None:
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


class MergeFundFeaturesTask(Task):
    def run(self, ctx: RetrainContext) -> bool | None:
        cmd = [
            ctx.python,
            "-m",
            "renquant_base_data.alpha158_fund_panel",
            "--data-dir",
            str(ctx.data_dir),
        ]
        if ctx.truncate_to_sec_max:
            cmd.append("--truncate-to-sec-max")
        _run(ctx, cmd)
        return True


class TrainGbdtScorerTask(Task):
    def run(self, ctx: RetrainContext) -> bool | None:
        cmd = [
            ctx.python,
            "-m",
            "renquant_orchestrator.train_gbdt",
            "--data-dir",
            str(ctx.data_dir),
            "--strategy-config",
            str(ctx.strategy_config),
            "--output-path",
            str(ctx.xgb_artifact_out),
        ]
        _run(ctx, cmd, cwd=ctx.repo_dir)
        if ctx.dry_run:
            return True
        _validate_scorer_artifact(ctx.xgb_artifact_out)
        return True


class RefitCalibratorTask(Task):
    def run(self, ctx: RetrainContext) -> bool | None:
        cmd = [
            ctx.python,
            str(ctx.repo_dir / "scripts" / "fit_calibrator_alpha158_fund.py"),
            "--scorer-artifact",
            str(ctx.xgb_artifact_out),
            "--out",
            str(ctx.calibrator_out),
        ]
        _run(ctx, cmd)
        if ctx.dry_run:
            return True
        _validate_calibrator_artifact(ctx.calibrator_out)
        return True


class RetrainJob(Job):
    @property
    def tasks(self) -> list[Task]:
        return [
            BuildAlpha158PanelTask(),
            MergeFundFeaturesTask(),
            TrainGbdtScorerTask(),
            RefitCalibratorTask(),
        ]


def build_pipeline() -> Pipeline:
    return Pipeline([RetrainJob()], name="weekly-alpha158-fund-retrain")


def _resolve(repo_dir: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else repo_dir / path


def _validate_repo_dir(repo_dir: Path) -> None:
    missing = [rel for rel in _REQUIRED_REPO_PATHS if not (repo_dir / rel).exists()]
    if missing:
        joined = ", ".join(str(rel) for rel in missing)
        raise FileNotFoundError(f"repo-dir is not a usable RenQuant checkout; missing: {joined}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-dir", type=Path, default=DEFAULT_REPO_DIR)
    parser.add_argument("--xgb-artifact-out", required=True)
    parser.add_argument("--calibrator-out", required=True)
    parser.add_argument("--truncate-to-sec-max", default=True, action=argparse.BooleanOptionalAction)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_dir = args.repo_dir.expanduser().resolve()
    _validate_repo_dir(repo_dir)
    ctx = RetrainContext(
        repo_dir=repo_dir,
        xgb_artifact_out=_resolve(repo_dir, args.xgb_artifact_out),
        calibrator_out=_resolve(repo_dir, args.calibrator_out),
        truncate_to_sec_max=args.truncate_to_sec_max,
        dry_run=args.dry_run,
    )
    build_pipeline().run(ctx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
