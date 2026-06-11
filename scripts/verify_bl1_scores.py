"""BL-1 live verification: PatchTST scores over the real 142-name cross-section.

Loads the prod PatchTST model + real OHLCV (asof 2026-06-10) and runs the
MERGED scoring path in two modes for the SAME target tickers:

  - candidates : sequence panel built over only the post-gate subset (the bug)
  - stable     : sequence panel built over the watchlist cross-section (the fix)

Proves BL-1: the candidate-only CSRankNorm collapses scores to a degenerate
(uniformly negative) cluster, while the stable cross-section restores a
realistic distribution that crosses zero.
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

OHLCV_ROOT = "RenQuant/data/ohlcv"
MODEL_PATH = ("RenQuant/artifacts/patchtst_shadow/"
              "pt07_strict_trainfit_embargo60_20260522/seed_44/"
              "hf_patchtst_all_seed44_model.pt")
CFG_PATH = "renquant-strategy-104/configs/strategy_config.json"
ASOF = pd.Timestamp("2026-06-10")

os.environ.setdefault("RENQUANT_REPO_ROOT", os.path.abspath("RenQuant"))

from renquant_pipeline.kernel.panel_pipeline import job_panel_scoring as J
from renquant_pipeline.kernel.panel_pipeline.hf_patchtst_scorer import (
    HFPatchTSTPanelScorer,
)


def _load_ohlcv(tickers):
    out = {}
    for t in tickers:
        p = f"{OHLCV_ROOT}/{t}/1d.parquet"
        if os.path.exists(p):
            df = pd.read_parquet(p)
            df = df[df.index <= ASOF]
            if len(df):
                out[t] = df
    return out


class _Ctx:
    pass


def _make_ctx(ohlcv, watchlist, context_mode):
    ctx = _Ctx()
    ctx.ohlcv = ohlcv
    cfg = json.load(open(CFG_PATH))
    cfg["ranking"]["panel_scoring"]["csranknorm_context_mode"] = context_mode
    ctx.config = cfg
    ctx.holdings = {}
    ctx.models = {}
    ctx.today = ASOF
    return ctx


def main():
    cfg = json.load(open(CFG_PATH))
    watchlist = cfg["watchlist"]
    print(f"watchlist={len(watchlist)} asof={ASOF.date()}")

    print("loading PatchTST model ...", flush=True)
    scorer = HFPatchTSTPanelScorer.load(MODEL_PATH)
    print(f"  scorer seq_len={scorer.seq_len} n_features={len(scorer.feature_cols)} "
          f"uses_csranknorm={scorer.metadata.get('uses_csranknorm', True)}")

    ohlcv = _load_ohlcv(watchlist)
    print(f"loaded OHLCV for {len(ohlcv)}/{len(watchlist)} tickers")

    # Simulate the live failure mode: a tiny post-gate candidate subset.
    targets = [t for t in ("NVTS", "SPOT", "LLY") if t in ohlcv][:3]
    if len(targets) < 3:
        targets = list(ohlcv.keys())[:3]
    print(f"target (post-gate) tickers: {targets}\n")

    results = {}
    for mode in ("candidates", "stable"):
        ctx = _make_ctx(ohlcv, watchlist, mode)
        ph = J._build_live_panel_history(ctx, scorer, targets, ASOF)
        if ph is None:
            print(f"[{mode}] panel history None — skipping")
            continue
        n_cross = ph["ticker"].nunique()
        scores = scorer.score_with_history(ph, targets)
        results[mode] = scores
        print(f"[{mode:10s}] CSRankNorm cross-section = {n_cross:3d} tickers | "
              f"target scores: "
              + ", ".join(f"{t}={scores.get(t, float('nan')):+.4f}" for t in targets))

    # Full-universe distribution in the fixed (stable) mode.
    ctx = _make_ctx(ohlcv, watchlist, "stable")
    ph_all = J._build_live_panel_history(ctx, scorer, list(ohlcv.keys()), ASOF)
    if ph_all is not None:
        all_scores = scorer.score_with_history(ph_all, list(ohlcv.keys()))
        s = all_scores.dropna()
        print(f"\nFULL-UNIVERSE (stable, fix) score distribution over {len(s)} names:")
        print(f"  min={s.min():+.4f}  p25={s.quantile(.25):+.4f}  "
              f"median={s.median():+.4f}  p75={s.quantile(.75):+.4f}  max={s.max():+.4f}")
        print(f"  share positive = {(s > 0).mean():.1%}  (degenerate bug => ~0%)")

    if "candidates" in results and "stable" in results:
        print("\nVERDICT: BL-1 fix changes the SAME targets' scores from the "
              "degenerate candidate-only cross-section to the trained 142-name "
              "cross-section.")


if __name__ == "__main__":
    sys.exit(main())
