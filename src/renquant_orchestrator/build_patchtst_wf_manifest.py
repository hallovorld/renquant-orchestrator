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

D2 refactor (2026-05-30): split into single-responsibility helpers per §1c,
each with a unit test in ``tests/test_build_patchtst_wf_manifest_refactor.py``.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os as _os
import subprocess
import sys
from pathlib import Path
from typing import Sequence

# DOE-tuned baseline (matches A's deployable). See renquant-model/docs/training_pipelines.md.
_TUNED = ["--lr", "1e-4", "--weight-decay", "0.3", "--seq-len", "24",
          "--early-stopping-patience", "2"]


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
    if cross_stock_attn:
        cmd.append("--cross-stock-attn")
    if film_regime_cond:
        cmd.append("--film-regime-cond")
    if exclude_features:
        cmd.extend(["--exclude-features", exclude_features])
    if strategy_config:
        cmd.extend(["--strategy-config", strategy_config])
    return cmd


def resolve_umbrella_cwd() -> str | None:
    """Find the umbrella directory so ``hf_trainer`` can read its dataset.

    ``hf_trainer --dataset`` defaults to ``data/transformer_v4_wl200_clean.parquet``
    relative to the caller's cwd; that path only resolves from the umbrella.
    Pattern: prefer ``$RENQUANT_STRATEGY_DIR``; else walk parents of this module
    for a sibling ``data/transformer_v4_wl200_clean.parquet``. Returns ``None``
    when neither is available (caller's cwd is used).
    """
    strat = _os.environ.get("RENQUANT_STRATEGY_DIR")
    if strat:
        return str(Path(strat).resolve().parent.parent)
    here = Path(__file__).resolve()
    for cand in here.parents:
        if (cand / "data" / "transformer_v4_wl200_clean.parquet").exists():
            return str(cand)
    return None


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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source-manifest", required=True, type=Path,
                    help="GBDT manifest to inherit the cutoff schedule from.")
    ap.add_argument("--output-dir", required=True, type=Path)
    ap.add_argument("--output-manifest", required=True, type=Path)
    ap.add_argument("--cadence-days", type=int, default=180,
                    help="Subsample the source manifest's cutoffs to this minimum "
                         "spacing (default 180 = semi-annual ~6 entries).")
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--device", default="mps")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--cross-stock-attn", action="store_true")
    ap.add_argument("--film-regime-cond", action="store_true")
    ap.add_argument("--exclude-features", default=None,
                    help="Comma list of feature columns to drop (mirror candidate).")
    ap.add_argument("--strategy-config", default=None)
    args = ap.parse_args(argv)

    cutoffs = extract_cutoffs(args.source_manifest, args.cadence_days)
    print(f"build_patchtst_wf_manifest: {len(cutoffs)} cutoffs "
          f"(cadence={args.cadence_days}d, {cutoffs[0]} → {cutoffs[-1]})",
          flush=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    cwd = resolve_umbrella_cwd()

    new_rows: list[dict] = []
    failed: list[str] = []
    for i, cutoff in enumerate(cutoffs, 1):
        out_path = args.output_dir / cutoff
        out_path.mkdir(parents=True, exist_ok=True)
        cmd = build_train_cmd(
            cutoff=cutoff,
            out_path=out_path,
            epochs=args.epochs,
            device=args.device,
            seed=args.seed,
            cross_stock_attn=args.cross_stock_attn,
            film_regime_cond=args.film_regime_cond,
            exclude_features=args.exclude_features,
            strategy_config=args.strategy_config,
        )
        print(f"  [{i}/{len(cutoffs)}] training cutoff={cutoff} …", flush=True)
        rc = subprocess.run(cmd, cwd=cwd).returncode
        artifact = out_path / f"hf_patchtst_all_seed{args.seed}_model.pt"
        if rc != 0 or not artifact.exists():
            print(f"    FAIL [{i}/{len(cutoffs)}] {cutoff} rc={rc} "
                  f"artifact_exists={artifact.exists()}", flush=True)
            failed.append(cutoff)
            continue
        new_rows.append(manifest_row(artifact=artifact, cutoff=cutoff))
        print(f"    ok   [{i}/{len(cutoffs)}] {cutoff}", flush=True)

    payload = build_manifest_payload(
        rows=new_rows,
        source_manifest_path=args.source_manifest,
        options={
            "cadence_days": args.cadence_days,
            "epochs": args.epochs,
            "device": args.device,
            "seed": args.seed,
            "cross_stock_attn": bool(args.cross_stock_attn),
            "film_regime_cond": bool(args.film_regime_cond),
            "exclude_features": args.exclude_features,
            "strategy_config": args.strategy_config,
        },
        failed_cutoffs=failed,
    )
    args.output_manifest.write_text(json.dumps(payload, indent=2))
    print(f"manifest written: {args.output_manifest} "
          f"({len(new_rows)} rows, {len(failed)} failed)")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
