"""End-to-end proof: the calibrated-μ gate admits the bullish names on real data.

Scores the real 142-name universe (asof 2026-06-10), calibrates μ, then runs the
ACTUAL long_signal_ok predicate with signal_gate_prefer_calibrated_mu OFF (legacy)
vs ON (fix), and lists the candidates the fix would admit.
"""
from __future__ import annotations

import json
import os

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
from renquant_pipeline.kernel.panel_pipeline.hf_patchtst_scorer import HFPatchTSTPanelScorer
from renquant_pipeline.kernel.panel_pipeline.global_calibrator import GlobalPanelCalibration
from renquant_pipeline.kernel.pipeline.signal_direction import long_signal_ok


class _Ctx:
    pass


def main():
    cfg = json.load(open(CFG_PATH))
    cfg["ranking"]["panel_scoring"]["csranknorm_context_mode"] = "stable"
    scorer = HFPatchTSTPanelScorer.load(MODEL_PATH)
    ohlcv = {}
    for t in cfg["watchlist"]:
        p = f"{OHLCV_ROOT}/{t}/1d.parquet"
        if os.path.exists(p):
            df = pd.read_parquet(p)
            df = df[df.index <= ASOF]
            if len(df):
                ohlcv[t] = df
    ctx = _Ctx(); ctx.ohlcv = ohlcv; ctx.config = cfg; ctx.holdings = {}
    ctx.models = {}; ctx.today = ASOF
    ph = J._build_live_panel_history(ctx, scorer, list(ohlcv.keys()), ASOF)
    scores = scorer.score_with_history(ph, list(ohlcv.keys())).dropna()
    cal = GlobalPanelCalibration.load(CAL_PATH)
    mu = {t: cal.expected_return(float(s)) for t, s in scores.items()}

    cfg_legacy = json.loads(json.dumps(cfg))
    cfg_fix = json.loads(json.dumps(cfg))
    cfg_fix["ranking"]["panel_scoring"]["signal_gate_prefer_calibrated_mu"] = True

    legacy = [t for t in scores.index
              if long_signal_ok(float(scores[t]), cfg_legacy, expected_return=mu[t])[0]]
    fixed = [t for t in scores.index
             if long_signal_ok(float(scores[t]), cfg_fix, expected_return=mu[t])[0]]

    print(f"long_signal_ok over {len(scores)} names, asof {ASOF.date()}:")
    print(f"  legacy (raw>0)              admits: {len(legacy):3d}")
    print(f"  fix (signal_gate_prefer_calibrated_mu=true) admits: {len(fixed):3d}")
    top = sorted(fixed, key=lambda t: mu[t], reverse=True)[:15]
    print(f"\n  top-15 admitted candidates (by μ) the fix would open as new longs:")
    for t in top:
        print(f"    {t:6s} raw={scores[t]:+.4f}  mu={mu[t]:+.4f}  "
              f"P={cal.calibrate_probability(float(scores[t])):.3f}")


if __name__ == "__main__":
    main()
