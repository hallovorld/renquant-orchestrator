"""Build a walk-forward manifest using the orchestrator's ``train_gbdt`` recipe.

The umbrella's ``train_walkforward_panel.py`` predates the multi-repo split; its
per-cutoff artifacts don't carry ``feature_norm_kind`` / ``feature_source_contract``,
so any candidate trained by ``renquant_orchestrator.train_gbdt`` fails
``run_wf_gate.py``'s recipe-parity check against that older manifest. This driver
loops the existing date schedule and re-runs ``train_gbdt`` per cutoff, producing a
manifest of artifacts whose recipe fingerprint matches a candidate trained by the
same orchestrator driver.

Usage::

  python -m renquant_orchestrator.build_wf_manifest \\
      --source-manifest /.../sim/walkforward_manifest_merged.json \\
      --output-dir /.../sim/walkforward_retrains_dropsenti_v3 \\
      --output-manifest /.../sim/walkforward_manifest_dropsenti_v3.json \\
      --drop-sentiment

``--skip-cv`` is on by default — manifest rows do not need CV stamps; the candidate
artifact already carries them, and the manifest is consumed only for recipe parity +
sanity scoring.

D1 refactor (2026-05-30): split into single-responsibility helpers per §1c,
each with a unit test in ``tests/test_build_wf_manifest_refactor.py``.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Sequence


def extract_cutoffs(source_manifest_path: Path) -> list[str]:
    """Extract sorted ``YYYY-MM-DD`` cutoffs from a WF manifest's ``retrains`` rows.

    Source manifests store cutoffs as ISO datetimes (``2022-01-01T00:00:00``);
    train_gbdt's ``--train-cutoff`` expects ``YYYY-MM-DD``, so we trim the time.
    """
    payload = json.loads(source_manifest_path.read_text())
    rows = payload.get("retrains", payload) if isinstance(payload, dict) else payload
    out: list[str] = []
    for r in rows:
        c = r.get("cutoff_date")
        if not c:
            continue
        out.append(str(c).split("T", 1)[0])
    return out


def build_train_cmd(
    *,
    cutoff: str,
    out_path: Path,
    side_label: str,
    cv_embargo_days: int,
    cv_n_splits: int,
    drop_sentiment: bool,
    skip_cv: bool,
) -> list[str]:
    """Construct the ``train_gbdt`` subprocess argv for one cutoff.

    Pure function: returns the argv list without side effects. Caller invokes
    subprocess + records the result. Makes per-cutoff command introspectable
    in tests.
    """
    cmd: list[str] = [
        sys.executable, "-m", "renquant_orchestrator.train_gbdt",
        "--train-cutoff", cutoff,
        "--side-label", side_label,
        "--cv-embargo-days", str(cv_embargo_days),
        "--cv-n-splits", str(cv_n_splits),
        "--output-path", str(out_path),
    ]
    if drop_sentiment:
        cmd.append("--drop-sentiment")
    if skip_cv:
        cmd.append("--skip-cv")
    return cmd


def manifest_row(*, artifact_uri: Path, cutoff: str, lookahead_days: int = 60) -> dict:
    """Assemble one manifest row (pure)."""
    return {
        "artifact_uri": str(artifact_uri.resolve()),
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
    """Compose the v2 manifest JSON payload (pure)."""
    return {
        "retrains": list(rows),
        "schema_version": 2,
        "built_at": _dt.datetime.utcnow().isoformat() + "Z",
        "built_by": "renquant_orchestrator.build_wf_manifest",
        "trainer": "renquant_orchestrator.train_gbdt",
        "options": dict(options),
        "source_manifest": str(source_manifest_path.resolve()),
        "failed_cutoffs": list(failed_cutoffs),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--source-manifest", required=True, type=Path)
    ap.add_argument("--output-dir", required=True, type=Path)
    ap.add_argument("--output-manifest", required=True, type=Path)
    ap.add_argument("--drop-sentiment", action="store_true")
    ap.add_argument("--cv-embargo-days", type=int, default=60)
    ap.add_argument("--cv-n-splits", type=int, default=3)
    ap.add_argument("--no-skip-cv", action="store_true",
                    help="Force CV inside each per-cutoff train (default skips CV).")
    ap.add_argument("--side-label", default="wf_dropsenti_v3",
                    help="Side-label per §5.13.13 (train_gbdt requires it with --train-cutoff).")
    args = ap.parse_args(argv)

    cutoffs = extract_cutoffs(args.source_manifest)
    print(f"build_wf_manifest: {len(cutoffs)} cutoffs ({cutoffs[0]} → {cutoffs[-1]})",
          flush=True)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    skip_cv = not args.no_skip_cv

    new_rows: list[dict] = []
    failed: list[str] = []
    for i, cutoff in enumerate(cutoffs, 1):
        out_path = args.output_dir / cutoff / "panel-ltr.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = build_train_cmd(
            cutoff=cutoff,
            out_path=out_path,
            side_label=args.side_label,
            cv_embargo_days=args.cv_embargo_days,
            cv_n_splits=args.cv_n_splits,
            drop_sentiment=args.drop_sentiment,
            skip_cv=skip_cv,
        )
        rc = subprocess.run(cmd).returncode
        if rc != 0:
            print(f"  FAIL [{i}/{len(cutoffs)}] {cutoff} rc={rc}", flush=True)
            failed.append(cutoff)
            continue
        new_rows.append(manifest_row(artifact_uri=out_path, cutoff=cutoff))
        print(f"  ok   [{i}/{len(cutoffs)}] {cutoff}", flush=True)

    payload = build_manifest_payload(
        rows=new_rows,
        source_manifest_path=args.source_manifest,
        options={
            "drop_sentiment": bool(args.drop_sentiment),
            "cv_embargo_days": args.cv_embargo_days,
            "cv_n_splits": args.cv_n_splits,
            "skip_cv": skip_cv,
        },
        failed_cutoffs=failed,
    )
    args.output_manifest.write_text(json.dumps(payload, indent=2))
    print(f"manifest written: {args.output_manifest} ({len(new_rows)} rows, "
          f"{len(failed)} failed)")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
