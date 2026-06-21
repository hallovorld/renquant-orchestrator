"""Build a walk-forward manifest for PatchTST using ``hf_trainer --train-cutoff``.

Mirrors :mod:`renquant_orchestrator.build_wf_manifest` (which does this for GBDT)
but for the PatchTST family. Produces a manifest the gate can consume to recipe-match
a candidate PatchTST artifact and to score §5.2 sanity placebos at each cutoff.

The candidate artifact's recipe is verified BEFORE running expensive training. If a
training run completes but produces a recipe-fingerprint mismatch (e.g. accidental
hyperparameter drift), the entry is treated as failed and excluded from the manifest.

Per-cutoff cost (rough): ~15 min on MPS at 4 epochs. Default cadence is quarterly-ish
(``--cadence-days 90``) so the WF gate has more than a handful of retrains to judge.
Override with ``--cadence-days`` for even denser manifests.

Usage::

  python -m renquant_orchestrator.build_patchtst_wf_manifest \\
      --source-manifest /.../sim/walkforward_manifest_dropsenti_v3.json \\
      --output-dir /.../sim/walkforward_retrains_patchtst_v1 \\
      --output-manifest /.../sim/walkforward_manifest_patchtst_v1.json \\
      --cadence-days 90 \\
      --epochs 4 --device mps --seed 42 --cross-stock-attn \\
      --exclude-features mean_sentiment,n_articles_log,sentiment_pos_share

Architecture (R2 refactor 2026-05-30, per §1c Task/Job/Pipeline):
  Pipeline ``BuildPatchtstWfManifestPipeline``
    PrepareJob
      LoadCutoffsTask           — parse source manifest + cadence subsample
      ResolveDataRootTask       — explicit data/config paths for the trainer
      EnsureOutputDirTask       — mkdir ``ctx.output_dir``
    RetrainJob
      RetrainAllCutoffsTask     — per-cutoff hf_trainer + calibrator subprocesses
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

import pandas as pd
from renquant_common import Job, Pipeline, Task

from .artifact_resolver import resolve_artifact
from .runtime_paths import (
    default_github_root,
    default_repo_root,
    default_strategy_config_candidates,
)

# DOE-tuned baseline (matches A's deployable). See renquant-model/docs/training_pipelines.md.
_TUNED = ["--lr", "1e-4", "--weight-decay", "0.3", "--seq-len", "24",
          "--early-stopping-patience", "2"]
GITHUB = default_github_root()
DEFAULT_DATA_ROOT = default_repo_root()
DEFAULT_DATASET_REL = Path("data/transformer_v4_wl200_clean.parquet")
DEFAULT_SPY_REL = Path("data/ohlcv/SPY/1d.parquet")
DEFAULT_RAW_LABEL_PANEL_REL = Path("data/alpha158_291_fundamental_dataset_rawlabel.parquet")
DEFAULT_STRATEGY_CONFIG, LEGACY_STRATEGY_CONFIG = default_strategy_config_candidates(
    repo_root=DEFAULT_DATA_ROOT,
    github_root=GITHUB,
)
DEFAULT_LABEL = "fwd_60d_excess"


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
    label: str = DEFAULT_LABEL,
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
        "--label", label,
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


def infer_label_lookahead_days(label: str | None) -> int:
    import re

    match = re.search(r"fwd_(\d+)d", str(label or DEFAULT_LABEL))
    return int(match.group(1)) if match else 60


def data_end_for_cutoff(cutoff: str, label: str | None) -> str:
    lookahead = infer_label_lookahead_days(label)
    return (pd.Timestamp(cutoff) - pd.offsets.BDay(lookahead)).date().isoformat()


def model_path_for(out_path: Path, seed: int) -> Path:
    return out_path / f"hf_patchtst_all_seed{seed}_model.pt"


def calibrator_path_for(model_path: Path) -> Path:
    return model_path.with_name("hf_patchtst-calibration.json")


def sidecar_path_for(model_path: Path) -> Path:
    return model_path.with_name(model_path.name + ".metadata.json")


def artifact_present(ref: Path, *, repo_root: Path | str | None = None) -> bool:
    """Return whether ``ref`` resolves to an existing artifact (fail-closed).

    Routes the bare ``Path.exists()`` existence check through the single
    ``resolve_artifact`` authority so the per-cutoff success gate uses the same
    resolution order as every other artifact lookup. ``ref`` is the trainer's
    absolute output path; ``repo_root`` only seeds the relative-ref fallback and
    defaults to the artifact's parent. Returns ``False`` (so the caller records
    the cutoff as failed) when nothing resolves, rather than raising.
    """
    root = Path(repo_root) if repo_root is not None else Path(ref).parent
    try:
        resolve_artifact(ref, strategy_dir=root, repo_root=root, verify_sha=False)
    except FileNotFoundError:
        return False
    return True


def read_training_contract(model_path: Path) -> dict:
    sidecar = sidecar_path_for(model_path)
    if not sidecar.exists():
        raise FileNotFoundError(f"missing PatchTST metadata sidecar: {sidecar}")
    payload = json.loads(sidecar.read_text())
    contract = payload.get("training_contract") or {}
    if not contract.get("trained_date") or not contract.get("effective_train_cutoff_date"):
        raise ValueError(f"incomplete PatchTST sidecar training_contract: {sidecar}")
    return contract


def build_calibrator_cmd(
    *,
    scorer_artifact: Path,
    out_path: Path,
    panel_path: Path | str | None,
    raw_label_panel_path: Path | str | None,
    label: str,
    data_end: str,
    batch_size: int,
    method: str,
    min_rows: int,
) -> list[str]:
    """Construct the PatchTST calibrator subprocess argv for one cutoff."""
    cmd: list[str] = [
        sys.executable, "-m", "renquant_model_patchtst.fit_calibrator",
        "--scorer-artifact", str(scorer_artifact),
        "--out", str(out_path),
        "--label-col", label,
        "--data-end", data_end,
        "--batch-size", str(batch_size),
        "--method", method,
        "--min-rows", str(min_rows),
    ]
    if panel_path:
        cmd.extend(["--panel", str(panel_path)])
    if raw_label_panel_path:
        cmd.extend(["--raw-label-panel", str(raw_label_panel_path)])
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


def default_raw_label_panel_path(data_root: Path | None) -> str | None:
    """Resolve the raw-label panel used by the calibrator subprocess."""
    if data_root is None:
        return None
    return str(data_root / DEFAULT_RAW_LABEL_PANEL_REL)


def manifest_row(
    *,
    artifact: Path,
    cutoff: str,
    calibrator: Path | None = None,
    label: str = DEFAULT_LABEL,
) -> dict:
    """Assemble one PatchTST manifest row (pure)."""
    contract = read_training_contract(artifact)
    row = {
        "artifact_uri": str(artifact.resolve()),
        "cutoff_date": cutoff,
        "lookahead_days": int(contract.get("lookahead_days") or infer_label_lookahead_days(label)),
        "trained_date": str(contract["trained_date"]),
    }
    if calibrator is not None:
        row["calibrator_uri"] = str(calibrator.resolve())
    if contract.get("effective_train_cutoff_date"):
        row["effective_train_cutoff_date"] = str(contract["effective_train_cutoff_date"])
    return row


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
    raw_label_panel_path: str | None = None
    label: str = DEFAULT_LABEL
    skip_calibrators: bool = False
    calibrator_batch_size: int = 512
    calibrator_method: str = "platt"
    calibrator_min_rows: int = 1000
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
        ctx.raw_label_panel_path = default_raw_label_panel_path(ctx.data_root)
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
                label=ctx.label,
                dataset_path=ctx.dataset_path,
                spy_path=ctx.spy_path,
            )
            print(f"  [{i}/{len(ctx.cutoffs)}] training cutoff={cutoff} …", flush=True)
            rc = subprocess.run(cmd, cwd=ctx.cwd).returncode
            artifact = model_path_for(out_path, ctx.seed)
            artifact_ok = artifact_present(artifact, repo_root=ctx.output_dir)
            if rc != 0 or not artifact_ok:
                print(
                    f"    FAIL [{i}/{len(ctx.cutoffs)}] {cutoff} rc={rc} "
                    f"artifact_exists={artifact_ok}",
                    flush=True,
                )
                ctx.failed_cutoffs.append(cutoff)
                continue
            calibrator: Path | None = None
            if not ctx.skip_calibrators:
                calibrator = calibrator_path_for(artifact)
                cal_cmd = build_calibrator_cmd(
                    scorer_artifact=artifact,
                    out_path=calibrator,
                    panel_path=ctx.dataset_path,
                    raw_label_panel_path=ctx.raw_label_panel_path,
                    label=ctx.label,
                    data_end=data_end_for_cutoff(cutoff, ctx.label),
                    batch_size=ctx.calibrator_batch_size,
                    method=ctx.calibrator_method,
                    min_rows=ctx.calibrator_min_rows,
                )
                print(f"    calibrating cutoff={cutoff} …", flush=True)
                cal_rc = subprocess.run(cal_cmd, cwd=ctx.cwd).returncode
                calibrator_ok = artifact_present(calibrator, repo_root=ctx.output_dir)
                if cal_rc != 0 or not calibrator_ok:
                    print(
                        f"    FAIL [{i}/{len(ctx.cutoffs)}] {cutoff} calibrator_rc={cal_rc} "
                        f"calibrator_exists={calibrator_ok}",
                        flush=True,
                    )
                    ctx.failed_cutoffs.append(cutoff)
                    continue
            ctx.new_rows.append(
                manifest_row(
                    artifact=artifact,
                    cutoff=cutoff,
                    calibrator=calibrator,
                    label=ctx.label,
                )
            )
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
                "raw_label_panel_path": ctx.raw_label_panel_path,
                "label": ctx.label,
                "skip_calibrators": bool(ctx.skip_calibrators),
                "calibrator": None if ctx.skip_calibrators else "renquant_model_patchtst.fit_calibrator",
                "calibrator_batch_size": int(ctx.calibrator_batch_size),
                "calibrator_method": ctx.calibrator_method,
                "calibrator_min_rows": int(ctx.calibrator_min_rows),
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
    ap.add_argument("--cadence-days", type=int, default=90)
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--cross-stock-attn", action="store_true")
    ap.add_argument("--film-regime-cond", action="store_true")
    ap.add_argument("--exclude-features", default=None)
    ap.add_argument("--strategy-config", default=None)
    ap.add_argument("--data-root", type=Path, default=None)
    ap.add_argument("--label", default=DEFAULT_LABEL)
    ap.add_argument("--skip-calibrators", action="store_true")
    ap.add_argument("--calibrator-batch-size", type=int, default=512)
    ap.add_argument("--calibrator-method", default="platt", choices=["platt", "isotonic"])
    ap.add_argument("--calibrator-min-rows", type=int, default=1000)
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
        label=args.label,
        skip_calibrators=args.skip_calibrators,
        calibrator_batch_size=args.calibrator_batch_size,
        calibrator_method=args.calibrator_method,
        calibrator_min_rows=args.calibrator_min_rows,
    )
    build_pipeline().run(ctx)
    return 0 if not ctx.failed_cutoffs else 1


if __name__ == "__main__":
    raise SystemExit(main())
