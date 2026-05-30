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
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path

# DOE-tuned baseline (matches A's deployable). See renquant-model/docs/training_pipelines.md.
_TUNED = ["--lr", "1e-4", "--weight-decay", "0.3", "--seq-len", "24",
          "--early-stopping-patience", "2"]


def _cutoffs_from_source(path: Path, cadence_days: int | None) -> list[str]:
    payload = json.loads(path.read_text())
    rows = payload.get("retrains", payload) if isinstance(payload, dict) else payload
    all_cutoffs = sorted(
        str(r["cutoff_date"]).split("T", 1)[0]
        for r in rows if r.get("cutoff_date")
    )
    if cadence_days is None or cadence_days <= 0:
        return all_cutoffs
    # Subsample by date distance; always keep the first and last cutoff.
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source-manifest", required=True, type=Path,
                    help="GBDT manifest to inherit the cutoff schedule from.")
    ap.add_argument("--output-dir", required=True, type=Path)
    ap.add_argument("--output-manifest", required=True, type=Path)
    ap.add_argument("--cadence-days", type=int, default=180,
                    help="Subsample the source manifest's cutoffs to this minimum "
                         "spacing (default 180 = semi-annual ~6 entries).")
    ap.add_argument("--epochs", type=int, default=4,
                    help="Training epochs per cutoff (default 4 — shorter than the "
                         "8-epoch deployable since manifest entries only need a "
                         "recipe-matching model, not the production checkpoint).")
    ap.add_argument("--device", default="mps")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--cross-stock-attn", action="store_true")
    ap.add_argument("--film-regime-cond", action="store_true")
    ap.add_argument("--exclude-features", default=None,
                    help="Comma list of feature columns to drop (mirror candidate).")
    ap.add_argument("--strategy-config", default=None,
                    help="Strategy config JSON name (defaults to strategy_config.shadow.json).")
    args = ap.parse_args(argv)

    cutoffs = _cutoffs_from_source(args.source_manifest, args.cadence_days)
    print(f"build_patchtst_wf_manifest: {len(cutoffs)} cutoffs "
          f"(cadence={args.cadence_days}d, {cutoffs[0]} → {cutoffs[-1]})",
          flush=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    new_rows: list[dict] = []
    failed: list[str] = []
    for i, cutoff in enumerate(cutoffs, 1):
        out_path = args.output_dir / cutoff
        out_path.mkdir(parents=True, exist_ok=True)
        cmd: list[str] = [
            sys.executable, "-m", "renquant_model_patchtst.hf_trainer",
            "--cut", "all",         # full-history train within the cutoff
            "--train-cutoff", cutoff,
            "--epochs", str(args.epochs),
            "--device", args.device,
            "--seed", str(args.seed),
            *_TUNED,
            "--save-model",
            "--output-dir", str(out_path),
        ]
        if args.cross_stock_attn:
            cmd.append("--cross-stock-attn")
        if args.film_regime_cond:
            cmd.append("--film-regime-cond")
        if args.exclude_features:
            cmd.extend(["--exclude-features", args.exclude_features])
        if args.strategy_config:
            cmd.extend(["--strategy-config", args.strategy_config])

        print(f"  [{i}/{len(cutoffs)}] training cutoff={cutoff} …", flush=True)
        # hf_trainer's --dataset defaults to a path relative to the umbrella
        # (data/transformer_v4_wl200_clean.parquet), so cd to the umbrella when
        # the env var points at the strategy dir under it.
        import os as _os
        strat = _os.environ.get("RENQUANT_STRATEGY_DIR")
        cwd = str(Path(strat).resolve().parent.parent) if strat else None
        rc = subprocess.run(cmd, cwd=cwd).returncode
        artifact = out_path / f"hf_patchtst_all_seed{args.seed}_model.pt"
        if rc != 0 or not artifact.exists():
            print(f"    FAIL [{i}/{len(cutoffs)}] {cutoff} rc={rc} "
                  f"artifact_exists={artifact.exists()}", flush=True)
            failed.append(cutoff)
            continue
        new_rows.append({
            "artifact_uri": str(artifact.resolve()),
            "cutoff_date": cutoff,
            "lookahead_days": 60,
            "trained_date": _dt.date.today().isoformat(),
        })
        print(f"    ok   [{i}/{len(cutoffs)}] {cutoff}", flush=True)

    manifest_payload = {
        "retrains": new_rows,
        "schema_version": 2,
        "built_at": _dt.datetime.utcnow().isoformat() + "Z",
        "built_by": "renquant_orchestrator.build_patchtst_wf_manifest",
        "trainer": "renquant_model_patchtst.hf_trainer",
        "options": {
            "cadence_days": args.cadence_days,
            "epochs": args.epochs,
            "device": args.device,
            "seed": args.seed,
            "cross_stock_attn": bool(args.cross_stock_attn),
            "film_regime_cond": bool(args.film_regime_cond),
            "exclude_features": args.exclude_features,
            "strategy_config": args.strategy_config,
        },
        "source_manifest": str(args.source_manifest.resolve()),
        "failed_cutoffs": failed,
    }
    args.output_manifest.write_text(json.dumps(manifest_payload, indent=2))
    print(f"manifest written: {args.output_manifest} "
          f"({len(new_rows)} rows, {len(failed)} failed)")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
