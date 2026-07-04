"""Shared infrastructure for alpha158 retrain pipelines (campaign B8).

Extracted from the 7 functions duplicated between ``retrain_alpha158_fund``
and ``retrain_alpha158_linear``. The 3 validator functions that differ
between scorers remain in their respective modules.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
from typing import Protocol

from .runtime_paths import resolve_subrepo_root

SUBREPO_NAMES = [
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


class RetrainContextLike(Protocol):
    repo_dir: Path
    dry_run: bool
    commands: list[list[str]]


def subrepo_srcs(repo_dir: Path) -> list[Path]:
    subrepo_root = resolve_subrepo_root(repo_dir)
    return [subrepo_root / name / "src" for name in SUBREPO_NAMES]


def subrepo_pythonpath(
    repo_dir: Path,
    env: dict[str, str] | None = None,
    *,
    strategy_config: str | None = None,
) -> dict[str, str]:
    out = dict(os.environ if env is None else env)
    srcs = subrepo_srcs(repo_dir)
    missing = [src for src in srcs if not src.is_dir()]
    if out.get("RENQUANT_STRICT_SUBREPO_PATHS") == "1" and missing:
        joined = ", ".join(str(src) for src in missing)
        raise FileNotFoundError(f"missing multirepo source paths: {joined}")
    existing = out.get("PYTHONPATH", "")
    out["PYTHONPATH"] = os.pathsep.join([*(str(src) for src in srcs), existing])
    out.setdefault("RENQUANT_REPO_ROOT", str(repo_dir))
    out.setdefault("RENQUANT_DATA_ROOT", str(repo_dir))
    out.setdefault("RENQUANT_STRATEGY_DIR", str(repo_dir / "backtesting" / "renquant_104"))
    if strategy_config is not None:
        out.setdefault("RENQUANT_STRATEGY_CONFIG", strategy_config)
    return out


def run_subprocess(ctx: RetrainContextLike, cmd: list[str], *, cwd: Path | None = None,
                   env_strategy_config: str | None = None) -> None:
    ctx.commands.append(cmd)
    if ctx.dry_run:
        return
    result = subprocess.run(
        cmd, cwd=str(cwd or ctx.repo_dir),
        env=subrepo_pythonpath(ctx.repo_dir, strategy_config=env_strategy_config),
    )
    if result.returncode != 0:
        raise RuntimeError(f"command failed rc={result.returncode}: {' '.join(cmd)}")


def read_json_object(path: Path, label: str) -> dict:
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


def resolve_path(repo_dir: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else repo_dir / path


def staging_path(path: Path) -> Path:
    return path.with_suffix(".staging.json")


def validate_repo_dir(repo_dir: Path, required: list[Path] | None = None) -> None:
    required = required or [Path("data")]
    missing = [rel for rel in required if not (repo_dir / rel).exists()]
    if missing:
        joined = ", ".join(str(rel) for rel in missing)
        raise FileNotFoundError(f"repo-dir is not a usable RenQuant checkout; missing: {joined}")
