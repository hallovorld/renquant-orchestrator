"""Decisive diagnostic: PatchTST raw scores -> calibrator -> admission gates.

Runs the merged scoring path over the real 142-name universe (asof 2026-06-10),
then pushes the raw scores through the PROD calibrator and asks: under each
admission gate, how many names are tradeable as a NEW long?

This answers whether "every score negative" is a model/feature artifact, and
which gate the system actually needs to open longs.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

os.environ.setdefault("RENQUANT_REPO_ROOT", os.path.abspath("RenQuant"))

OHLCV_ROOT = "RenQuant/data/ohlcv"
MODEL_PATH = ("RenQuant/artifacts/patchtst_shadow/"
              "pt07_strict_trainfit_embargo60_20260522/seed_44/"
              "hf_patchtst_all_seed44_model.pt")
CAL_PATH = ("RenQuant/backtesting/renquant_104/artifacts/shadow/"
            "panel-rank-calibration.hf_patchtst_seed44_trainfit_20230103_20240409.json")
CFG_PATH = "renquant-strategy-104/configs/strategy_config.json"
ASOF = pd.Timestamp("2026-06-10")

from renquant_pipeline.kernel.panel_pipeline import job_panel_scoring as J
from renquant_pipeline.kernel.panel_pipeline.hf_patchtst_scorer import (
    HFPatchTSTPanelScorer,
)
from renquant_pipeline.kernel.panel_pipeline.global_calibrator import (
    GlobalPanelCalibration,
)


class _Ctx:
    pass


def main():
    cfg = json.load(open(CFG_PATH))
    watchlist = cfg["watchlist"]
    scorer = HFPatchTSTPanelScorer.load(MODEL_PATH)

    ohlcv = {}
    for t in watchlist:
        p = f"{OHLCV_ROOT}/{t}/1d.parquet"
        if os.path.exists(p):
            df = pd.read_parquet(p)
            df = df[df.index <= ASOF]
            if len(df):
                ohlcv[t] = df

    ctx = _Ctx()
    ctx.ohlcv = ohlcv
    cfg["ranking"]["panel_scoring"]["csranknorm_context_mode"] = "stable"
    ctx.config = cfg
    ctx.holdings = {}
    ctx.models = {}
    ctx.today = ASOF

    ph = J._build_live_panel_history(ctx, scorer, list(ohlcv.keys()), ASOF)

    # Extra-feature health: are the 14 non-alpha158 features real, or all 0?
    from renquant_pipeline.kernel.panel_pipeline.alpha158_features import (
        alpha158_feature_names,
    )
    a158 = set(alpha158_feature_names())
    extra = [c for c in scorer.feature_cols if c not in a158 and c in ph.columns]
    print("=== extra-feature health (non-zero share at asof bar) ===")
    last = ph[ph["date"] == ph["date"].max()]
    for c in extra:
        nz = (last[c].astype(float).abs() > 1e-9).mean()
        print(f"  {c:28s} non-zero={nz:5.1%}  mean={last[c].astype(float).mean():+.4f}")

    scores = scorer.score_with_history(ph, list(ohlcv.keys())).dropna()
    print(f"\n=== raw PatchTST scores over {len(scores)} names ===")
    print(f"  min={scores.min():+.4f} median={scores.median():+.4f} "
          f"max={scores.max():+.4f} | share>0 = {(scores>0).mean():.1%}")

    cal = GlobalPanelCalibration.load(CAL_PATH)
    print(f"\n=== prod calibrator ===")
    print(f"  neutral_raw (ER=0 crossing) = {cal.neutral_raw}")
    print(f"  prob_neutral_raw (P=0.5)    = {cal.prob_neutral_raw}")
    mu = scores.map(lambda s: cal.expected_return(float(s)))
    prob = scores.map(lambda s: cal.calibrate_probability(float(s)))
    print(f"  calibrated mu:  min={mu.min():+.4f} median={mu.median():+.4f} max={mu.max():+.4f} | share>0 = {(mu>0).mean():.1%}")
    print(f"  calibrated P:   min={prob.min():.3f} median={prob.median():.3f} max={prob.max():.3f}")

    nr = cal.neutral_raw if cal.neutral_raw is not None else 0.0
    print(f"\n=== how many of {len(scores)} names are tradeable as a NEW long? ===")
    print(f"  gate 'raw > 0'            : {(scores>0).sum():3d}  <- the PR #81 / long_signal_ok raw gate")
    print(f"  gate 'mu > 0' (calibr.)   : {(mu>0).sum():3d}")
    print(f"  gate 'raw > neutral_raw'  : {(scores>nr).sum():3d}  (neutral_raw={nr:+.4f})")

    top = scores.sort_values(ascending=False).head(8)
    print(f"\n=== top-8 names by raw score (the would-be longs) ===")
    for t, s in top.items():
        print(f"  {t:6s} raw={s:+.4f}  mu={cal.expected_return(float(s)):+.4f}  P={cal.calibrate_probability(float(s)):.3f}")


if __name__ == "__main__":
    main()
