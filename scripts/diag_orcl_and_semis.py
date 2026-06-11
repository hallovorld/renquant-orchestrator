"""Diagnose two operator questions on real data (asof 2026-06-10):
1. ORCL was stop_loss'd on a pullback — does the model still rank it bullish?
2. Are semis under-weighted, and is the Kelly σ-horizon (252 vs 60) the cause?
"""
from __future__ import annotations
import json, os
import numpy as np, pandas as pd
os.environ.setdefault("RENQUANT_REPO_ROOT", os.path.abspath("RenQuant"))
OHLCV_ROOT="RenQuant/data/ohlcv"
MODEL=("RenQuant/artifacts/patchtst_shadow/pt07_strict_trainfit_embargo60_20260522/seed_44/hf_patchtst_all_seed44_model.pt")
CAL=("RenQuant/backtesting/renquant_104/artifacts/shadow/panel-rank-calibration.hf_patchtst_seed44_trainfit_20230103_20240409.json")
CFG="renquant-strategy-104/configs/strategy_config.json"
ASOF=pd.Timestamp("2026-06-10")
from renquant_pipeline.kernel.panel_pipeline import job_panel_scoring as J
from renquant_pipeline.kernel.panel_pipeline.hf_patchtst_scorer import HFPatchTSTPanelScorer
from renquant_pipeline.kernel.panel_pipeline.global_calibrator import GlobalPanelCalibration
from renquant_pipeline.kernel.kelly import kelly_target_pct

SEMIS=["NVDA","AMD","SMCI","QCOM","MU","AVGO","DELL","INTC","LRCX","AMAT","ASML","ARM","MRVL","ON","NXPI","ADI","TXN","MCHP"]
class C: pass
def vol(df,w=60):
    r=df["close"].pct_change().dropna().tail(w);
    return min(max(float(r.std()*np.sqrt(252)),0.05),1.5) if len(r)>=5 else None
def main():
    cfg=json.load(open(CFG)); wl=cfg["watchlist"]
    cfg["ranking"]["panel_scoring"]["csranknorm_context_mode"]="stable"
    cfg["ranking"]["panel_scoring"]["signal_gate_prefer_calibrated_mu"]=True
    sc=HFPatchTSTPanelScorer.load(MODEL)
    oh={}
    for t in wl:
        p=f"{OHLCV_ROOT}/{t}/1d.parquet"
        if os.path.exists(p):
            df=pd.read_parquet(p); df=df[df.index<=ASOF]
            if len(df): oh[t]=df
    ctx=C(); ctx.ohlcv=oh; ctx.config=cfg; ctx.holdings={}; ctx.models={}; ctx.today=ASOF
    ph=J._build_live_panel_history(ctx,sc,list(oh.keys()),ASOF)
    s=sc.score_with_history(ph,list(oh.keys())).dropna()
    cal=GlobalPanelCalibration.load(CAL)
    mu={t:cal.expected_return(float(s[t])) for t in s.index}
    rank=sorted(s.index,key=lambda t:mu[t],reverse=True)
    pos={t:i+1 for i,t in enumerate(rank)}
    print(f"universe scored: {len(s)} names. neutral_raw={cal.neutral_raw:+.3f}")
    print(f"\n=== ORCL (held; stop_loss'd 06-10/06-11) ===")
    if "ORCL" in s.index:
        print(f"  raw={s['ORCL']:+.4f}  mu={mu['ORCL']:+.4f}  P={cal.calibrate_probability(float(s['ORCL'])):.3f}  rank={pos['ORCL']}/{len(s)}  -> model {'BULLISH (mu>0)' if mu['ORCL']>0 else 'bearish'}")
    else:
        print("  ORCL not in scored set")
    print(f"\n=== semis in watchlist: weight under sigma_horizon 252 (prod) vs 60 (matched) ===")
    print(f"  {'tkr':6s}{'mu':>8s}{'rank':>6s}{'vol_ann':>8s}{'k@252':>7s}{'k@60':>7s}")
    insemi=[t for t in SEMIS if t in s.index]
    for t in sorted(insemi,key=lambda t:mu[t],reverse=True):
        v=vol(oh[t]);
        if v is None: continue
        k252=kelly_target_pct(mu[t],v,max_pct=0.15,max_concentration=0.12,fractional=0.5)
        v60=v*np.sqrt(60/252)
        k60=kelly_target_pct(mu[t],v60,max_pct=0.15,max_concentration=0.12,fractional=0.5)
        print(f"  {t:6s}{mu[t]:>+8.4f}{pos[t]:>6d}{v:>8.2f}{k252*100:>6.1f}%{k60*100:>6.1f}%")
    print(f"\n  semis in watchlist: {insemi}")
    print(f"  (k@252 = prod Kelly with annual sigma vs 60d mu = HORIZON MISMATCH; k@60 = sigma matched to mu horizon)")

if __name__=="__main__": main()
