#!/usr/bin/env python3
"""How much does the ±0.5 label clip actually move a per-date Spearman IC?

WHY (orch#817, 2026-08-05): I raised a P0 on the strength of two correct
numbers — 53 % of `fwd_60d_excess` rows exceed |0.5|, and clipping collapses
726,100 distinct values to 340,527 — and did NOT measure the consequence before
setting the severity. Measured afterwards on three fixed panel predictors, the
mean per-date IC moves by at most ~0.005.

The property to reason from is that **`clip` is MONOTONE and Spearman is
invariant to monotone transforms**, except through the ties one creates. A large
*fraction of rows* is not automatically a large *rank* perturbation.

NO CEILING IS CLAIMED [codex on orch#822]: if a distribution's values all land
on one side of the bound they collapse into a SINGLE tie group and the whole
correlation is lost. The cost depends on how the values sit against the bound,
and 0.866-on-two-groups is calibration, not a worst case.

Read-only. It answers a question about the INSTRUMENT, not about any model:
it uses fixed predictors taken from the panel itself, not a scorer's output.

    python scripts/goal4_label_clip_sensitivity.py [--predictors KMID KLEN ROC60]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

DEFAULT_PANEL = pathlib.Path(
    "/Users/renhao/git/github/RenQuant/data/"
    "alpha158_291_fundamental_dataset_rawlabel.parquet")
DEFAULT_LABEL = "fwd_60d_excess"
DEFAULT_SINCE = "2024-04-10"        # the helper's own default validation slice
CLIP = 0.5
MIN_NAMES = 20                      # summarize_ic's floor, mirrored


def sensitivity(panel_path: pathlib.Path = DEFAULT_PANEL,
                predictors: tuple[str, ...] = ("KMID", "KLEN", "ROC60"),
                label: str = DEFAULT_LABEL, since: str = DEFAULT_SINCE) -> dict:
    import numpy as np
    import pandas as pd
    from scipy import stats

    have = [c for c in predictors]
    df = pd.read_parquet(panel_path, columns=["date", label, *have])
    df = df.dropna(subset=[label])
    df["date"] = pd.to_datetime(df["date"])
    val = df[df["date"] > pd.Timestamp(since)]

    out: dict = {"panel": str(panel_path), "label": label, "since": since,
                 "clip": CLIP, "n_rows": int(len(val)),
                 "n_dates": int(val["date"].nunique()), "predictors": {}}
    for pred in have:
        rows = []
        for date, g in val.groupby("date"):
            sub = g[[pred, label]].dropna()
            if len(sub) < MIN_NAMES:
                continue
            y = sub[label]
            rows.append((
                float(stats.spearmanr(sub[pred], y).statistic),
                float(stats.spearmanr(sub[pred], y.clip(-CLIP, CLIP)).statistic),
            ))
        if not rows:
            out["predictors"][pred] = {"n_dates": 0, "note": "no eligible dates"}
            continue
        unc = np.array([r[0] for r in rows])
        clp = np.array([r[1] for r in rows])
        d = clp - unc
        out["predictors"][pred] = {
            "n_dates": len(rows),
            "mean_ic_unclipped": float(unc.mean()),
            "mean_ic_clipped": float(clp.mean()),
            "mean_delta": float(d.mean()),
            "max_abs_delta": float(np.abs(d).max()),
        }
    return out


def render(r: dict) -> str:
    lines = [f"label-clip sensitivity — {r['label']} clipped at ±{r['clip']}",
             f"  panel {pathlib.Path(r['panel']).name}, since {r['since']}: "
             f"{r['n_rows']:,} rows / {r['n_dates']:,} dates", ""]
    lines.append(f"  {'predictor':>10}  {'unclipped':>10} {'clipped':>10} "
                 f"{'mean Δ':>10} {'max |Δ|':>9}  n_dates")
    for pred, c in r["predictors"].items():
        if not c.get("n_dates"):
            lines.append(f"  {pred:>10}  (no eligible dates)")
            continue
        lines.append(f"  {pred:>10}  {c['mean_ic_unclipped']:>+10.5f} "
                     f"{c['mean_ic_clipped']:>+10.5f} {c['mean_delta']:>+10.5f} "
                     f"{c['max_abs_delta']:>9.5f}  {c['n_dates']}")
    lines += [
        "",
        "  `clip` is MONOTONE and Spearman is invariant to monotone transforms",
        "  except through the ties they create — so a large fraction of clipped",
        "  ROWS is not automatically a large RANK perturbation.",
        "",
        "  NO CEILING IS CLAIMED [codex on orch#822]. A distribution whose values",
        "  all land on ONE side of the clip collapses to a single tie group and",
        "  loses the whole correlation — the worst case is 1.0, not 0.134. How",
        "  much is lost depends entirely on how the values sit against the bound.",
        "",
        "  SCOPE: fixed panel predictors, NOT a served scorer's mu. A model whose",
        "  scores concentrate differently against the clipped tails could move",
        "  more. These numbers cannot settle a severity question about",
        "  scorer-based IC evidence; they describe three named probes.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--panel", type=pathlib.Path, default=DEFAULT_PANEL)
    ap.add_argument("--predictors", nargs="+", default=["KMID", "KLEN", "ROC60"])
    ap.add_argument("--since", default=DEFAULT_SINCE)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    r = sensitivity(args.panel, tuple(args.predictors), since=args.since)
    print(json.dumps(r, indent=2) if args.json else render(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
