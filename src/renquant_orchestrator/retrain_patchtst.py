"""Weekly PatchTST retrain pipeline owned by renquant-orchestrator.

The production scorer is the HF PatchTST checkpoint
(``artifacts/patchtst_shadow/pt07_strict_trainfit_embargo60_20260522/seed_44``),
but until now only GBDT and the linear shadow/legacy models had a scheduled
retrain. This module mirrors :mod:`renquant_orchestrator.retrain_alpha158_fund`:
it is a ``renquant_common`` Pipeline of Tasks that subprocess into the pinned
``renquant-model`` PatchTST trainer + calibrator, validate the resulting
artifacts (fingerprint / trained_date / non-empty), and write everything to a
STAGING directory. Like the GBDT retrain it preserves the weekly trust
boundary: this module NEVER promotes a production artifact — the WF gate /
operator promotion path is responsible for that.

HARD BOUNDARY: training internals live in ``renquant-model``. The orchestrator
only constructs the subprocess argv (reusing the canonical command builders from
:mod:`renquant_orchestrator.build_patchtst_wf_manifest`) and runs it with the
multirepo ``PYTHONPATH``.
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

from .artifact_resolver import resolve_artifact
from .build_patchtst_wf_manifest import (
    DEFAULT_LABEL,
    build_calibrator_cmd,
    build_train_cmd,
    calibrator_path_for,
    data_end_for_cutoff,
    default_input_paths,
    default_raw_label_panel_path,
    default_strategy_config,
    model_path_for,
    resolve_data_root,
)
from .runtime_paths import (
    default_github_root,
    default_repo_root,
)


GITHUB = default_github_root()
DEFAULT_REPO_DIR = default_repo_root()
_REQUIRED_REPO_PATHS = [
    Path("data"),
]

# Production PatchTST scorer + calibrator (NEVER overwritten by this job; see
# RenQuant/backtesting/renquant_104/strategy_config.golden.json). Defaults below
# stage NEXT to these prod artifacts so promotion is an explicit operator step.
_PROD_MODEL_REL = Path(
    "backtesting/renquant_104/artifacts/patchtst_shadow/"
    "pt07_strict_trainfit_embargo60_20260522/seed_44"
)
_STAGING_DIR_REL = Path("backtesting/renquant_104/artifacts/patchtst_staging")

# DOE-tuned production recipe (matches the deployed pt07 strict seed44 checkpoint
# + the build_patchtst_wf_manifest defaults). Keep these in sync with the WF
# manifest builder so a staged candidate recipe-matches the manifest cuts.
DEFAULT_SEED = 44
DEFAULT_EPOCHS = 4
DEFAULT_DEVICE = "cpu"
DEFAULT_CROSS_STOCK_ATTN = True
DEFAULT_FILM_REGIME_COND = False
DEFAULT_EXCLUDE_FEATURES = "mean_sentiment,n_articles_log,sentiment_pos_share"


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
class PatchtstRetrainContext:
    repo_dir: Path
    output_dir: Path
    train_cutoff: str | None = None
    seed: int = DEFAULT_SEED
    epochs: int = DEFAULT_EPOCHS
    device: str = DEFAULT_DEVICE
    cross_stock_attn: bool = DEFAULT_CROSS_STOCK_ATTN
    film_regime_cond: bool = DEFAULT_FILM_REGIME_COND
    exclude_features: str | None = DEFAULT_EXCLUDE_FEATURES
    label: str = DEFAULT_LABEL
    strategy_config_path: Path | None = None
    calibrator_method: str = "platt"
    calibrator_batch_size: int = 512
    calibrator_min_rows: int = 1000
    python: str = sys.executable
    dry_run: bool = False
    # resolved during the pipeline
    data_root: Path | None = None
    dataset_path: str | None = None
    spy_path: str | None = None
    raw_label_panel_path: str | None = None
    strategy_config: str | None = None
    model_artifact: Path | None = None
    calibrator_artifact: Path | None = None
    commands: list[list[str]] = field(default_factory=list)

    @property
    def data_dir(self) -> Path:
        return self.repo_dir / "data"

    @property
    def effective_cutoff(self) -> str:
        """The train cutoff the trainer/calibrator pin to.

        Defaults to today (UTC) so a scheduled weekly run trains on all data up
        to the run date, matching the GBDT weekly retrain semantics.
        """
        return self.train_cutoff or dt.datetime.utcnow().strftime("%Y-%m-%d")


def _subrepo_srcs(repo_dir: Path) -> list[Path]:
    from .runtime_paths import resolve_subrepo_root

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


def _run(ctx: PatchtstRetrainContext, cmd: list[str], *, cwd: Path | None = None) -> None:
    ctx.commands.append(cmd)
    if ctx.dry_run:
        return
    result = subprocess.run(
        cmd,
        cwd=str(cwd if cwd is not None else (ctx.data_root or ctx.repo_dir)),
        env=_subrepo_pythonpath(ctx.repo_dir),
    )
    if result.returncode != 0:
        raise RuntimeError(f"command failed rc={result.returncode}: {' '.join(cmd)}")


def _resolve_present(path: Path) -> Path:
    """Existence-check ``path`` through the single ``resolve_artifact`` authority.

    Replaces the ad-hoc ``Path.exists()`` guards on the produced staging
    artifacts so a missing file fails closed with the resolver's message (which
    lists every tried path) instead of a bespoke string. ``path`` is the
    absolute staging output, so the resolver uses it as-is; the parent only
    seeds the (unused for absolute refs) relative-ref fallback.
    """
    return resolve_artifact(
        path, strategy_dir=path.parent, repo_root=path.parent, verify_sha=False
    ).path


def _read_json_object(path: Path, label: str) -> dict:
    try:
        _resolve_present(path)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"{label} did not produce {path}: {exc}") from exc
    if path.stat().st_size <= 2:
        raise ValueError(f"{label} artifact is too small: {path}")
    try:
        payload = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} artifact is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{label} artifact must be a JSON object: {path}")
    return payload


def _validate_scorer_artifact(model_path: Path) -> None:
    """Validate the trained PatchTST checkpoint + its metadata sidecar.

    The trainer writes ``<model>.pt`` plus a ``<model>.pt.metadata.json`` sidecar
    carrying the ``training_contract`` (trained_date / effective_train_cutoff_date
    / fingerprint). We assert the checkpoint is non-empty and the sidecar's
    contract was stamped today, mirroring the GBDT ``trained_date`` guard.
    """
    try:
        _resolve_present(model_path)
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"PatchTST training did not produce {model_path}: {exc}"
        ) from exc
    if model_path.stat().st_size <= 2:
        raise ValueError(f"PatchTST checkpoint is too small: {model_path}")
    sidecar = model_path.with_name(model_path.name + ".metadata.json")
    payload = _read_json_object(sidecar, "PatchTST training")
    contract = payload.get("training_contract") or {}
    if not contract.get("trained_date"):
        raise ValueError(f"PatchTST sidecar missing trained_date: {sidecar}")
    if not contract.get("effective_train_cutoff_date"):
        raise ValueError(
            f"PatchTST sidecar missing effective_train_cutoff_date: {sidecar}"
        )
    expected = dt.datetime.utcnow().strftime("%Y-%m-%d")
    if str(contract.get("trained_date")) != expected:
        raise ValueError(
            f"PatchTST artifact trained_date={contract.get('trained_date')!r}; "
            f"expected {expected}: {sidecar}"
        )


def _validate_calibrator_artifact(path: Path) -> None:
    payload = _read_json_object(path, "PatchTST calibrator refit")
    if not payload:
        raise ValueError(f"calibrator artifact is empty: {path}")


class ResolveDataRootTask(Task):
    """Resolve explicit dataset / SPY / panel / strategy-config paths.

    Mirrors ``build_patchtst_wf_manifest.ResolveDataRootTask`` so the trainer
    subprocess never relies on umbrella-cwd magic.
    """

    def run(self, ctx: PatchtstRetrainContext) -> bool | None:
        ctx.data_root = resolve_data_root(str(ctx.data_root) if ctx.data_root else None)
        if ctx.data_root is None:
            ctx.data_root = ctx.repo_dir
        ctx.dataset_path, ctx.spy_path = default_input_paths(ctx.data_root)
        ctx.raw_label_panel_path = default_raw_label_panel_path(ctx.data_root)
        if ctx.strategy_config is None:
            ctx.strategy_config = (
                str(ctx.strategy_config_path)
                if ctx.strategy_config_path is not None
                else default_strategy_config()
            )
        return True


class EnsureStagingDirTask(Task):
    """Create the staging output directory (parents as needed)."""

    def run(self, ctx: PatchtstRetrainContext) -> bool | None:
        if ctx.dry_run:
            return True
        ctx.output_dir.mkdir(parents=True, exist_ok=True)
        return True


class TrainPatchtstScorerTask(Task):
    """Subprocess into ``renquant_model_patchtst.hf_trainer`` for one cutoff."""

    def run(self, ctx: PatchtstRetrainContext) -> bool | None:
        cmd = build_train_cmd(
            cutoff=ctx.effective_cutoff,
            out_path=ctx.output_dir,
            epochs=ctx.epochs,
            device=ctx.device,
            seed=ctx.seed,
            cross_stock_attn=ctx.cross_stock_attn,
            film_regime_cond=ctx.film_regime_cond,
            exclude_features=ctx.exclude_features,
            strategy_config=ctx.strategy_config,
            label=ctx.label,
            dataset_path=ctx.dataset_path,
            spy_path=ctx.spy_path,
        )
        # build_train_cmd hardcodes sys.executable; pin it to ctx.python so tests
        # and operators can override the interpreter deterministically.
        cmd[0] = ctx.python
        ctx.model_artifact = model_path_for(ctx.output_dir, ctx.seed)
        _run(ctx, cmd)
        if ctx.dry_run:
            return True
        _validate_scorer_artifact(ctx.model_artifact)
        return True


class RefitCalibratorTask(Task):
    """Subprocess into ``renquant_model_patchtst.fit_calibrator``."""

    def run(self, ctx: PatchtstRetrainContext) -> bool | None:
        assert ctx.model_artifact is not None, "TrainPatchtstScorerTask must run first"
        ctx.calibrator_artifact = calibrator_path_for(ctx.model_artifact)
        cmd = build_calibrator_cmd(
            scorer_artifact=ctx.model_artifact,
            out_path=ctx.calibrator_artifact,
            panel_path=ctx.dataset_path,
            raw_label_panel_path=ctx.raw_label_panel_path,
            label=ctx.label,
            data_end=data_end_for_cutoff(ctx.effective_cutoff, ctx.label),
            batch_size=ctx.calibrator_batch_size,
            method=ctx.calibrator_method,
            min_rows=ctx.calibrator_min_rows,
        )
        cmd[0] = ctx.python
        _run(ctx, cmd)
        if ctx.dry_run:
            return True
        _validate_calibrator_artifact(ctx.calibrator_artifact)
        return True


class RetrainJob(Job):
    @property
    def tasks(self) -> list[Task]:
        return [
            ResolveDataRootTask(),
            EnsureStagingDirTask(),
            TrainPatchtstScorerTask(),
            RefitCalibratorTask(),
        ]


def build_pipeline() -> Pipeline:
    return Pipeline([RetrainJob()], name="weekly-patchtst-retrain")


def _resolve(repo_dir: Path, raw: str) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else repo_dir / path


def _default_staging_dir(repo_dir: Path) -> Path:
    """Default STAGING output dir (timestamped, never the prod artifact dir)."""
    stamp = dt.datetime.utcnow().strftime("weekly_%Y%m%dT%H%M%SZ")
    return repo_dir / _STAGING_DIR_REL / stamp


def _validate_repo_dir(repo_dir: Path) -> None:
    missing = [rel for rel in _REQUIRED_REPO_PATHS if not (repo_dir / rel).exists()]
    if missing:
        joined = ", ".join(str(rel) for rel in missing)
        raise FileNotFoundError(
            f"repo-dir is not a usable RenQuant checkout; missing: {joined}"
        )


def _assert_not_prod_dir(repo_dir: Path, output_dir: Path) -> None:
    """Refuse to write into the live production PatchTST artifact directory."""
    prod = (repo_dir / _PROD_MODEL_REL).resolve()
    out = output_dir.resolve()
    if out == prod or prod in out.parents or out in prod.parents:
        raise SystemExit(
            f"refusing to stage into / over the production PatchTST artifact dir: "
            f"{out} overlaps {prod}. Choose a staging --output-dir."
        )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-dir", type=Path, default=DEFAULT_REPO_DIR)
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Staging directory for the trained checkpoint + calibrator. "
        "When omitted with --staged, a timestamped staging dir under "
        "artifacts/patchtst_staging/ is used. NEVER the prod artifact dir.",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Use a default timestamped staging output dir when --output-dir is omitted.",
    )
    parser.add_argument(
        "--train-cutoff",
        default=None,
        help="Train cutoff date (YYYY-MM-DD). Defaults to today (UTC).",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    parser.add_argument("--device", default=DEFAULT_DEVICE, choices=["cpu", "mps", "cuda"])
    parser.add_argument(
        "--cross-stock-attn",
        default=DEFAULT_CROSS_STOCK_ATTN,
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "--film-regime-cond",
        default=DEFAULT_FILM_REGIME_COND,
        action=argparse.BooleanOptionalAction,
    )
    parser.add_argument(
        "--exclude-features",
        default=DEFAULT_EXCLUDE_FEATURES,
        help="Comma-separated features to drop (default mirrors the prod pt07 recipe).",
    )
    parser.add_argument("--label", default=DEFAULT_LABEL)
    parser.add_argument("--strategy-config", type=Path, default=None)
    parser.add_argument("--calibrator-method", default="platt", choices=["platt", "isotonic"])
    parser.add_argument("--calibrator-batch-size", type=int, default=512)
    parser.add_argument("--calibrator-min-rows", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    repo_dir = args.repo_dir.expanduser().resolve()
    _validate_repo_dir(repo_dir)
    if args.output_dir:
        output_dir = _resolve(repo_dir, args.output_dir)
    elif args.staged:
        output_dir = _default_staging_dir(repo_dir)
    else:
        output_dir = _default_staging_dir(repo_dir)
    _assert_not_prod_dir(repo_dir, output_dir)
    ctx = PatchtstRetrainContext(
        repo_dir=repo_dir,
        output_dir=output_dir,
        train_cutoff=args.train_cutoff,
        seed=args.seed,
        epochs=args.epochs,
        device=args.device,
        cross_stock_attn=args.cross_stock_attn,
        film_regime_cond=args.film_regime_cond,
        exclude_features=args.exclude_features,
        label=args.label,
        strategy_config_path=(
            args.strategy_config.expanduser().resolve() if args.strategy_config else None
        ),
        calibrator_method=args.calibrator_method,
        calibrator_batch_size=args.calibrator_batch_size,
        calibrator_min_rows=args.calibrator_min_rows,
        dry_run=args.dry_run,
    )
    build_pipeline().run(ctx)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
