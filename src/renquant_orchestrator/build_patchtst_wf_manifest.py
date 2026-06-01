"""Build a walk-forward manifest for PatchTST using ``hf_trainer --train-cutoff``.

Mirrors :mod:`renquant_orchestrator.build_wf_manifest` (which does this for GBDT)
but for the PatchTST family. Produces a manifest the gate can consume to recipe-match
a candidate PatchTST artifact and to score §5.2 sanity placebos at each cutoff.

The candidate artifact's recipe is verified BEFORE running expensive training. If a
training run completes but produces a recipe-fingerprint mismatch (e.g. accidental
hyperparameter drift), the entry is treated as failed and excluded from the manifest.

Per-cutoff cost (rough): ~15 min on MPS at 4 epochs. Default 6 cutoffs (semi-annual
over the WF window). Override with ``--cadence-days`` for a denser manifest.

Usage::

  python -m renquant_orchestrator.build_patchtst_wf_manifest \\
      --source-manifest /.../sim/walkforward_manifest_dropsenti_v3.json \\
      --output-dir /.../sim/walkforward_retrains_patchtst_v1 \\
      --output-manifest /.../sim/walkforward_manifest_patchtst_v1.json \\
      --cadence-days 180 \\
      --epochs 4 --device mps --seed 42 --cross-stock-attn \\
      --exclude-features mean_sentiment,n_articles_log,sentiment_pos_share

Architecture (R2 refactor 2026-05-30, per §1c Task/Job/Pipeline):
  Pipeline ``BuildPatchtstWfManifestPipeline``
    PrepareJob
      LoadCutoffsTask           — parse source manifest + cadence subsample
      ResolveDataRootTask       — explicit data/config paths for the trainer
      EnsureOutputDirTask       — mkdir ``ctx.output_dir``
    RetrainJob
      RetrainAllCutoffsTask     — per-cutoff hf_trainer subprocess
    EmitJob
      AssembleManifestPayloadTask + WriteManifestTask
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os as _os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from renquant_common import Job, Pipeline, Task


# DOE-tuned baseline (matches A's deployable). See renquant-model/docs/training_pipelines.md.
_TUNED = ["--lr", "1e-4", "--weight-decay", "0.3", "--seq-len", "24",
          "--early-stopping-patience", "2"]
GITHUB = Path(__file__).resolve().parents[3]
DEFAULT_DATA_ROOT = GITHUB / "RenQuant"
DEFAULT_DATASET_REL = Path("data/transformer_v4_wl200_clean.parquet")
DEFAULT_SPY_REL = Path("data/ohlcv/SPY/1d.parquet")
DEFAULT_STRATEGY_CONFIG = GITHUB / "renquant-strategy-104" / "configs" / "strategy_config.json"
LEGACY_STRATEGY_CONFIG = (
    GITHUB / "RenQuant" / "backtesting" / "renquant_104" / "strategy_config.json"
)


# ────────────────────────────────────────────────────────────────────────────────
# Pure helpers (preserved as Task building blocks).
# ────────────────────────────────────────────────────────────────────────────────


def extract_cutoffs(source_manifest_path: Path, cadence_days: int | None) -> list[str]:
    """Subsample the source manifest's cutoffs by minimum spacing.

    Source manifests carry many cutoffs (weekly cadence); PatchTST is expensive,
    so we keep a sparse schedule. ``cadence_days=None`` or ``<=0`` returns all.
    Always preserves the first and last cutoff.
    """
    payload = json.loads(source_manifest_path.read_text())
    rows = payload.get("retrains", payload) if isinstance(payload, dict) else payload
    all_cutoffs = sorted(
        str(r["cutoff_date"]).split("T", 1)[0]
        for r in rows if r.get("cutoff_date")
    )
    if cadence_days is None or cadence_days <= 0:
        return all_cutoffs
    selected: list[str] = []
    last = None
    for c in all_cutoffs:
        d = _dt.date.fromisoformat(c)
        if last is None or (d - last).days >= cadence_days:
            selected.append(c)
            last = d
    if all_cutoffs and all_cutoffs[-1] not in selected:
        selected.append(all_cutoffs[-1])
    return selected


def build_train_cmd(
    *,
    cutoff: str,
    out_path: Path,
    epochs: int,
    device: str,
    seed: int,
    cross_stock_attn: bool,
    film_regime_cond: bool,
    exclude_features: str | None,
    strategy_config: str | None,
    dataset_path: Path | str | None = None,
    spy_path: Path | str | None = None,
) -> list[str]:
    """Construct the ``hf_trainer`` subprocess argv for one cutoff (pure)."""
    cmd: list[str] = [
        sys.executable, "-m", "renquant_model_patchtst.hf_trainer",
        "--cut", "all",
        "--train-cutoff", cutoff,
        "--epochs", str(epochs),
        "--device", device,
        "--seed", str(seed),
        *_TUNED,
        "--save-model",
        "--output-dir", str(out_path),
    ]
    if dataset_path:
        cmd.extend(["--dataset", str(dataset_path)])
    if spy_path:
        cmd.extend(["--spy-path", str(spy_path)])
    if cross_stock_attn:
        cmd.append("--cross-stock-attn")
    if film_regime_cond:
        cmd.append("--film-regime-cond")
    if exclude_features:
        cmd.extend(["--exclude-features", exclude_features])
    if strategy_config:
        cmd.extend(["--strategy-config", strategy_config])
    return cmd


def resolve_data_root(data_root: str | None = None) -> Path | None:
    """Find the runtime data root that contains the PatchTST dataset."""
    raw = data_root or _os.environ.get("RENQUANT_DATA_ROOT")
    if raw:
        return Path(raw).expanduser().resolve()
    legacy_strategy_dir = _os.environ.get("RENQUANT_STRATEGY_DIR")
    if legacy_strategy_dir:
        legacy_root = Path(legacy_strategy_dir).expanduser().resolve().parent.parent
        if (legacy_root / DEFAULT_DATASET_REL).exists():
            return legacy_root
    if (DEFAULT_DATA_ROOT / DEFAULT_DATASET_REL).exists():
        return DEFAULT_DATA_ROOT.resolve()
    here = Path(__file__).resolve()
    for cand in here.parents:
        if (cand / DEFAULT_DATASET_REL).exists():
            return cand.resolve()
    return None


def resolve_umbrella_cwd() -> str | None:
    """Backward-compatible alias for older tests/callers."""
    root = resolve_data_root()
    return str(root) if root else None


def default_strategy_config() -> str | None:
    """Resolve the strategy config stamped into PatchTST artifacts."""
    raw = _os.environ.get("RENQUANT_STRATEGY_CONFIG")
    if raw:
        return str(Path(raw).expanduser().resolve())
    if DEFAULT_STRATEGY_CONFIG.exists():
        return str(DEFAULT_STRATEGY_CONFIG.resolve())
    if LEGACY_STRATEGY_CONFIG.exists():
        return str(LEGACY_STRATEGY_CONFIG.resolve())
    return None


def default_input_paths(data_root: Path | None) -> tuple[str | None, str | None]:
    """Resolve explicit dataset/SPY paths for the trainer subprocess."""
    if data_root is None:
        return None, None
    return str(data_root / DEFAULT_DATASET_REL), str(data_root / DEFAULT_SPY_REL)


def manifest_row(*, artifact: Path, cutoff: str, lookahead_days: int = 60) -> dict:
    """Assemble one PatchTST manifest row (pure)."""
    return {
        "artifact_uri": str(artifact.resolve()),
        "cutoff_date": cutoff,
        "lookahead_days": int(lookahead_days),
        "trained_date": _dt.date.today().isoformat(),
    }


def build_manifest_payload(
    *,
    rows: Sequence[dict],
    source_manifest_path: Path,
    options: dict,
    failed_cutoffs: Sequence[str],
) -> dict:
    """Compose the PatchTST v2 manifest JSON payload (pure)."""
    return {
        "retrains": list(rows),
        "schema_version": 2,
        "built_at": _dt.datetime.utcnow().isoformat() + "Z",
        "built_by": "renquant_orchestrator.build_patchtst_wf_manifest",
        "trainer": "renquant_model_patchtst.hf_trainer",
        "options": dict(options),
        "source_manifest": str(source_manifest_path.resolve()),
        "failed_cutoffs": list(failed_cutoffs),
    }


# ────────────────────────────────────────────────────────────────────────────────
# T/J/P architecture (§1c).
# ────────────────────────────────────────────────────────────────────────────────


@dataclass
class BuildPatchtstWfManifestContext:
    """State threaded through ``BuildPatchtstWfManifestPipeline``."""
    source_manifest_path: Path
    output_dir: Path
    output_manifest_path: Path
    cadence_days: int
    epochs: int
    device: str
    seed: int
    cross_stock_attn: bool
    film_regime_cond: bool
    exclude_features: str | None
    strategy_config: str | None
    data_root: Path | None = None
    dataset_path: str | None = None
    spy_path: str | None = None
    # populated through the pipeline
    cutoffs: list[str] = field(default_factory=list)
    cwd: str | None = None
    new_rows: list[dict] = field(default_factory=list)
    failed_cutoffs: list[str] = field(default_factory=list)
    payload: dict | None = None


class LoadCutoffsTask(Task):
    """Parse + cadence-subsample the source manifest's cutoffs into ``ctx.cutoffs``."""

    def run(self, ctx: BuildPatchtstWfManifestContext) -> bool | None:
        ctx.cutoffs = extract_cutoffs(ctx.source_manifest_path, ctx.cadence_days)
        print(
            f"build_patchtst_wf_manifest: {len(ctx.cutoffs)} cutoffs "
            f"(cadence={ctx.cadence_days}d, {ctx.cutoffs[0]} → {ctx.cutoffs[-1]})",
            flush=True,
        )
        return True


class ResolveDataRootTask(Task):
    """Resolve explicit data/config paths so ``hf_trainer`` avoids umbrella cwd magic."""

    def run(self, ctx: BuildPatchtstWfManifestContext) -> bool | None:
        ctx.data_root = resolve_data_root(str(ctx.data_root) if ctx.data_root else None)
        ctx.dataset_path, ctx.spy_path = default_input_paths(ctx.data_root)
        if ctx.strategy_config is None:
            ctx.strategy_config = default_strategy_config()
        # Keep cwd at the data root for back-compat with any relative output paths,
        # but the trainer receives explicit input/config paths above.
        ctx.cwd = str(ctx.data_root) if ctx.data_root else None
        return True


class EnsureOutputDirTask(Task):
    """Create the per-cutoff output directory (parents as needed)."""

    def run(self, ctx: BuildPatchtstWfManifestContext) -> bool | None:
        ctx.output_dir.mkdir(parents=True, exist_ok=True)
        return True


class PrepareJob(Job):
    """Stage 1: cutoff schedule + data/config path resolution + output-dir."""

    @property
    def tasks(self) -> list[Task]:
        return [LoadCutoffsTask(), ResolveDataRootTask(), EnsureOutputDirTask()]


class RetrainAllCutoffsTask(Task):
    """Invoke ``hf_trainer`` per cutoff with ``cwd=ctx.cwd``."""

    def run(self, ctx: BuildPatchtstWfManifestContext) -> bool | None:
        for i, cutoff in enumerate(ctx.cutoffs, 1):
            out_path = ctx.output_dir / cutoff
            out_path.mkdir(parents=True, exist_ok=True)
            cmd = build_train_cmd(
                cutoff=cutoff,
                out_path=out_path,
                epochs=ctx.epochs,
                device=ctx.device,
                seed=ctx.seed,
                cross_stock_attn=ctx.cross_stock_attn,
                film_regime_cond=ctx.film_regime_cond,
                exclude_features=ctx.exclude_features,
                strategy_config=ctx.strategy_config,
                dataset_path=ctx.dataset_path,
                spy_path=ctx.spy_path,
            )
            print(f"  [{i}/{len(ctx.cutoffs)}] training cutoff={cutoff} …", flush=True)
            rc = subprocess.run(cmd, cwd=ctx.cwd).returncode
            artifact = out_path / f"hf_patchtst_all_seed{ctx.seed}_model.pt"
            if rc != 0 or not artifact.exists():
                print(
                    f"    FAIL [{i}/{len(ctx.cutoffs)}] {cutoff} rc={rc} "
                    f"artifact_exists={artifact.exists()}",
                    flush=True,
                )
                ctx.failed_cutoffs.append(cutoff)
                continue
            ctx.new_rows.append(manifest_row(artifact=artifact, cutoff=cutoff))
            print(f"    ok   [{i}/{len(ctx.cutoffs)}] {cutoff}", flush=True)
        return True


class RetrainJob(Job):
    """Stage 2: retrain one PatchTST model per cutoff."""

    @property
    def tasks(self) -> list[Task]:
        return [RetrainAllCutoffsTask()]


class AssembleManifestPayloadTask(Task):
    """Compose the v2 manifest payload dict into ``ctx.payload``."""

    def run(self, ctx: BuildPatchtstWfManifestContext) -> bool | None:
        ctx.payload = build_manifest_payload(
            rows=ctx.new_rows,
            source_manifest_path=ctx.source_manifest_path,
            options={
                "cadence_days": ctx.cadence_days,
                "epochs": ctx.epochs,
                "device": ctx.device,
                "seed": ctx.seed,
                "cross_stock_attn": bool(ctx.cross_stock_attn),
                "film_regime_cond": bool(ctx.film_regime_cond),
                "exclude_features": ctx.exclude_features,
                "strategy_config": ctx.strategy_config,
                "data_root": str(ctx.data_root) if ctx.data_root else None,
                "dataset_path": ctx.dataset_path,
                "spy_path": ctx.spy_path,
            },
            failed_cutoffs=ctx.failed_cutoffs,
        )
        return True


class WriteManifestTask(Task):
    """Write the assembled payload to ``ctx.output_manifest_path``."""

    def run(self, ctx: BuildPatchtstWfManifestContext) -> bool | None:
        assert ctx.payload is not None, "AssembleManifestPayloadTask must run first"
        ctx.output_manifest_path.write_text(json.dumps(ctx.payload, indent=2))
        print(
            f"manifest written: {ctx.output_manifest_path} "
            f"({len(ctx.new_rows)} rows, {len(ctx.failed_cutoffs)} failed)"
        )
        return True


class EmitJob(Job):
    """Stage 3: build + write the manifest payload."""

    @property
    def tasks(self) -> list[Task]:
        return [AssembleManifestPayloadTask(), WriteManifestTask()]


def build_pipeline() -> Pipeline:
    """Factory: the canonical ``BuildPatchtstWfManifestPipeline`` instance."""
    return Pipeline(
        [PrepareJob(), RetrainJob(), EmitJob()],
        name="BuildPatchtstWfManifest",
    )


# Backward-compatible task name for existing callers.
ResolveUmbrellaCwdTask = ResolveDataRootTask


# ────────────────────────────────────────────────────────────────────────────────
# CLI entrypoint.
# ────────────────────────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source-manifest", required=True, type=Path,
                    help="GBDT manifest to inherit the cutoff schedule from.")
    ap.add_argument("--output-dir", required=True, type=Path)
    ap.add_argument("--output-manifest", required=True, type=Path)
    ap.add_argument("--cadence-days", type=int, default=180)
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--cross-stock-attn", action="store_true")
    ap.add_argument("--film-regime-cond", action="store_true")
    ap.add_argument("--exclude-features", default=None)
    ap.add_argument("--strategy-config", default=None)
    ap.add_argument("--data-root", type=Path, default=None)
    args = ap.parse_args(argv)

    ctx = BuildPatchtstWfManifestContext(
        source_manifest_path=args.source_manifest,
        output_dir=args.output_dir,
        output_manifest_path=args.output_manifest,
        cadence_days=args.cadence_days,
        epochs=args.epochs,
        device=args.device,
        seed=args.seed,
        cross_stock_attn=args.cross_stock_attn,
        film_regime_cond=args.film_regime_cond,
        exclude_features=args.exclude_features,
        strategy_config=args.strategy_config,
        data_root=args.data_root,
    )
    build_pipeline().run(ctx)
    return 0 if not ctx.failed_cutoffs else 1


if __name__ == "__main__":
    raise SystemExit(main())
