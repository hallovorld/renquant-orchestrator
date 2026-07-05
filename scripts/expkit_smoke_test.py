#!/usr/bin/env python3
"""expkit end-to-end smoke test with synthetic data.

Exercises the full prereg → evaluate → stats → evidence flow against
synthetic panel data (no WF-gate corpus or real model needed). Verifies
the framework is wired up and produces mechanically correct outputs.

Usage:
    python scripts/expkit_smoke_test.py [--out-dir /tmp/expkit_smoke]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from renquant_orchestrator.expkit import (
    Criterion,
    FrozenSpec,
    block_bootstrap_conditional_mean,
    bootstrap_or_exact,
    build_manifest,
    exact_sign_test,
    fwd_excess,
    multi_seed_unanimity,
    paired_deltas,
    per_date_ic,
    sha256_bytes,
    spearman,
    summarize_boot,
    verify_manifest,
    write_evidence,
    write_frozen_spec,
)


def _synthetic_panel(n_dates: int = 200, n_names: int = 50, seed: int = 42) -> tuple:
    """Generate synthetic wide-format panels: (score, label, placebo).

    Returns three date×name DataFrames matching expkit's per_date_ic API:
    score and label share mild positive IC; placebo is a shifted copy.
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2024-01-02", periods=n_dates, freq="B")
    tickers = [f"SYN{i:03d}" for i in range(n_names)]

    score_data = {}
    label_data = {}
    for dt in dates:
        signal = rng.standard_normal(n_names)
        noise = rng.standard_normal(n_names) * 3
        fwd = signal * 0.3 + noise
        score_data[dt] = dict(zip(tickers, signal))
        label_data[dt] = dict(zip(tickers, fwd))

    score_df = pd.DataFrame(score_data).T
    score_df.index.name = "date"
    label_df = pd.DataFrame(label_data).T
    label_df.index.name = "date"

    # Placebo: shift labels by ~60 sessions (approximate shifted_label_placebo)
    shift = min(60, n_dates // 3)
    placebo_df = label_df.shift(shift)

    return score_df, label_df, placebo_df


def _run(out_dir: Path) -> dict:
    results = {}
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 1: freeze a prereg spec ──────────────────────────────
    print("[1/6] Writing frozen prereg spec...")
    spec = FrozenSpec(
        experiment_id="SMOKE-001",
        hypothesis="Synthetic score has positive IC with fwd_60d",
        criteria=(
            Criterion(name="genuine_ic", threshold=0.02, direction="gt",
                      units="Spearman IC", description="placebo-clean IC bar"),
            Criterion(name="paired_delta_p", threshold=0.05, direction="lt",
                      units="p-value", description="paired delta significance"),
        ),
        family_size_k=1,
        seeds=(42,),
        evidence_boundary={
            "window": "2024-01 to 2024-10 (synthetic)",
            "cells": "200 dates × 50 names",
            "outcome_era": "synthetic (no real fwd_60d)",
            "cost_model": "n/a (no cost in smoke test)",
            "substrate": "iid synthetic panel",
            "multiplicity": "k=1 (single experiment)",
            "not_covered": "all real-world features (synthetic data only)",
        },
        reopening_conditions=(
            "This is a smoke test — no reopening conditions apply",
        ),
        horizon=60,
        block=20,
        n_boot=500,
    )
    spec_path = out_dir / "frozen_spec.json"
    spec_sha = write_frozen_spec(spec, spec_path)
    results["spec_sha"] = spec_sha
    results["spec_alpha"] = spec.alpha_one_sided
    print(f"  spec sha256: {spec_sha[:16]}...")
    print(f"  alpha_one_sided: {spec.alpha_one_sided}")

    # ── Step 2: generate synthetic data ───────────────────────────
    print("[2/6] Generating synthetic panel...")
    score_df, label_df, placebo_df = _synthetic_panel(n_dates=200, n_names=50, seed=42)
    results["panel_shape"] = list(score_df.shape)
    print(f"  score: {score_df.shape} (dates × names)")

    # ── Step 3: evaluate IC (genuine + placebo) ───────────────────
    print("[3/6] Computing per-date IC (genuine + placebo)...")
    ic_df = per_date_ic(score_df, label_df, placebo_df)
    clean_ic = ic_df["clean_ic"].dropna()
    real_ic = ic_df["real_ic"].dropna()
    placebo_ic = ic_df["placebo_ic"].dropna()
    mean_ic = float(real_ic.mean())
    mean_ic_placebo = float(placebo_ic.mean())
    mean_clean = float(clean_ic.mean())
    results["mean_ic_genuine"] = round(mean_ic, 4)
    results["mean_ic_placebo"] = round(mean_ic_placebo, 4)
    results["mean_ic_clean"] = round(mean_clean, 4)

    deltas = paired_deltas(real_ic, placebo_ic)
    mean_delta = float(deltas.mean())
    results["mean_paired_delta"] = round(mean_delta, 4)
    print(f"  genuine IC: {mean_ic:.4f}")
    print(f"  placebo IC: {mean_ic_placebo:.4f}")
    print(f"  clean IC: {mean_clean:.4f}")
    print(f"  paired delta: {mean_delta:.4f}")

    # ── Step 4: bootstrap inference ───────────────────────────────
    print("[4/6] Running block bootstrap...")
    in_cell = np.ones(len(deltas), dtype=bool)  # all-True = unconditional
    boot = block_bootstrap_conditional_mean(
        deltas.values, in_cell, block=20, n_boot=500, seed=42,
    )
    boot_summary = summarize_boot(boot, alpha_one_sided=spec.alpha_one_sided)
    ci95 = boot_summary["ci95_two_sided"]
    results["bootstrap_se"] = round(float(boot_summary["boot_se"]), 4)
    results["bootstrap_ci_lo"] = round(float(ci95[0]), 4)
    results["bootstrap_ci_hi"] = round(float(ci95[1]), 4)
    results["bootstrap_lb_one_sided"] = round(float(boot_summary["lb_one_sided"]), 4)
    # One-sided bootstrap percentile p-value for H0: mean paired delta <= 0,
    # from the SAME resample distribution used for the CI/lb above (standard
    # bootstrap-percentile p-value; the tail-mass equivalent of
    # exact_block_tail_masses' p_le_threshold, via resampling instead of full
    # enumeration — n_dates=200/block=20 puts exact enumeration (200**10
    # tuples) far past EXACT_ENUM_LIMIT, so the bootstrap estimate is the
    # correct available method here, not exact_sign_test's coarser
    # binomial approximation).
    paired_delta_p_value = float(np.mean(boot <= 0.0))
    results["paired_delta_p_value"] = round(paired_delta_p_value, 4)
    print(f"  SE: {boot_summary['boot_se']:.4f}, "
          f"CI95: [{ci95[0]:.4f}, {ci95[1]:.4f}], "
          f"lb_one_sided: {boot_summary['lb_one_sided']:.4f}, "
          f"paired_delta_p: {paired_delta_p_value:.4f}")

    # Also test the bootstrap_or_exact branch (small-n path)
    small_vals = deltas.values[:8]
    small_cell = np.ones(len(small_vals), dtype=bool)
    boe = bootstrap_or_exact(
        small_vals, block=2, n_boot=200, seeds=(42,),
        alpha_one_sided=spec.alpha_one_sided, in_cell=small_cell,
    )
    results["small_n_method"] = boe.get("method", "unknown")
    print(f"  small-n method ({len(small_vals)} vals): {boe.get('method', '?')}")

    # Multi-seed unanimity: run bootstrap per seed, then check unanimity
    by_seed = {}
    for s in (42, 7, 2026):
        b = block_bootstrap_conditional_mean(
            deltas.values, in_cell, block=20, n_boot=200, seed=s,
        )
        by_seed[str(s)] = summarize_boot(b, alpha_one_sided=spec.alpha_one_sided)
    unanimity = multi_seed_unanimity(
        by_seed, predicate=lambda s: s["lb_one_sided"] > 0,
    )
    results["unanimity_unanimous_true"] = unanimity["unanimous_true"]
    results["unanimity_n_seeds"] = len(by_seed)
    print(f"  multi-seed unanimity: {unanimity['unanimous_true']} "
          f"({len(by_seed)} seeds)")

    # ── Step 5: check criteria ────────────────────────────────────
    print("[5/6] Checking frozen criteria...")
    ic_criterion = spec.criterion("genuine_ic")
    ic_met = ic_criterion.met(mean_delta)
    p_criterion = spec.criterion("paired_delta_p")
    p_met = p_criterion.met(paired_delta_p_value)
    results["criterion_ic_met"] = ic_met
    results["criterion_paired_delta_p_met"] = p_met
    verdict = "GO" if (ic_met and p_met) else "FAIL"
    results["verdict"] = verdict
    print(f"  genuine_ic {ic_criterion.direction} {ic_criterion.threshold}: {ic_met} (value={mean_delta:.4f})")
    print(f"  paired_delta_p {p_criterion.direction} {p_criterion.threshold}: {p_met} (p={paired_delta_p_value:.4f})")
    print(f"  verdict: {verdict}")

    # ── Step 6: write evidence manifest ───────────────────────────
    print("[6/6] Writing evidence manifest...")
    evidence_payload = {
        "spec_sha256": spec_sha,
        "panel_shape": list(score_df.shape),
        "mean_ic_genuine": mean_ic,
        "mean_ic_placebo": mean_ic_placebo,
        "mean_paired_delta": mean_delta,
        "bootstrap": {k: (list(v) if isinstance(v, list) else v) for k, v in boot_summary.items()},
        "unanimity": unanimity,
        "criteria": {
            "genuine_ic": {"met": ic_met, "value": mean_delta},
            "paired_delta_p": {"met": p_met, "value": paired_delta_p_value},
        },
        "verdict": verdict,
    }
    ev_path = write_evidence(out_dir / "evidence", "smoke_results", evidence_payload)
    results["evidence_path"] = str(ev_path)

    # Build and verify manifest
    repo_root = Path(__file__).resolve().parent.parent
    manifest = build_manifest(
        repo_root=str(repo_root),
        script="scripts/expkit_smoke_test.py",
        inputs={"frozen_spec": str(spec_path)},
        spec_sha256=spec_sha,
        seeds=(42,),
    )
    manifest_path = out_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, default=str) + "\n")

    verification = verify_manifest(manifest, base=repo_root)
    results["manifest_ok"] = verification.ok
    if not verification.ok:
        results["manifest_problems"] = verification.problems
    print(f"  evidence: {ev_path}")
    print(f"  manifest ok: {verification.ok}")

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="expkit end-to-end smoke test")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="output directory (default: tempdir)")
    args = parser.parse_args()

    out_dir = args.out_dir or Path(tempfile.mkdtemp(prefix="expkit_smoke_"))
    print(f"expkit smoke test → {out_dir}\n")

    try:
        results = _run(out_dir)
    except Exception as exc:
        print(f"\n❌ SMOKE TEST FAILED: {exc}")
        import traceback
        traceback.print_exc()
        return 1

    print(f"\n{'='*60}")
    print("SMOKE TEST RESULTS")
    print(f"{'='*60}")
    for k, v in sorted(results.items()):
        print(f"  {k}: {v}")

    all_ok = (
        results.get("mean_ic_genuine", 0) > 0
        and results.get("criterion_ic_met") is True
        and results.get("criterion_paired_delta_p_met") is True
        and results.get("manifest_ok", False)
    )
    status = "✅ PASS" if all_ok else "❌ FAIL"
    print(f"\n{status} — expkit framework exercised end-to-end.")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
