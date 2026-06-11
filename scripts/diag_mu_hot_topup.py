"""Answer: are candidate raws still negative? how's their mu? hot names? top-up?"""
from __future__ import annotations
import json, os
import numpy as np, pandas as pd
os.environ.setdefault("RENQUANT_REPO_ROOT", os.path.abspath("RenQuant"))
OHLCV="RenQuant/data/ohlcv"
MODEL=("RenQuant/artifacts/patchtst_shadow/pt07_strict_trainfit_embargo60_20260522/seed_44/hf_patchtst_all_seed44_model.pt")
CAL=("RenQuant/backtesting/renquant_104/artifacts/shadow/panel-rank-calibration.hf_patchtst_seed44_trainfit_20230103_20240409.json")
CFG="renquant-strategy-104/configs/strategy_config.json"
LIVE="RenQuant/backtesting/renquant_104/live_state.alpaca.json"
ASOF=pd.Timestamp("2026-06-10")
from renquant_pipeline.kernel.panel_pipeline import job_panel_scoring as J
from renquant_pipeline.kernel.panel_pipeline.hf_patchtst_scorer import HFPatchTSTPanelScorer
from renquant_pipeline.kernel.panel_pipeline.global_calibrator import GlobalPanelCalibration
from renquant_pipeline.kernel.kelly import kelly_target_pct
HOT=["NVDA","AAPL","MSFT","GOOGL","META","AMZN","TSLA","AVGO","AMD","PLTR","NFLX","ORCL","CRWD","SMCI"]
class C: pass
def annvol(df,w=60):
    r=df["close"].pct_change().dropna().tail(w)
    return min(max(float(r.std()*np.sqrt(252)),0.05),1.5) if len(r)>=5 else None
def main():
    cfg=json.load(open(CFG))
    cfg["ranking"]["panel_scoring"]["csranknorm_context_mode"]="stable"
    sc=HFPatchTSTPanelScorer.load(MODEL)
    oh={}
    for t in cfg["watchlist"]:
        p=f"{OHLCV}/{t}/1d.parquet"
        if os.path.exists(p):
            df=pd.read_parquet(p); df=df[df.index<=ASOF]
            if len(df): oh[t]=df
    ctx=C(); ctx.ohlcv=oh; ctx.config=cfg; ctx.holdings={}; ctx.models={}; ctx.today=ASOF
    ph=J._build_live_panel_history(ctx,sc,list(oh.keys()),ASOF)
    s=sc.score_with_history(ph,list(oh.keys())).dropna()
    cal=GlobalPanelCalibration.load(CAL)
    mu={t:cal.expected_return(float(s[t])) for t in s.index}
    P={t:cal.calibrate_probability(float(s[t])) for t in s.index}
    rank=sorted(s.index,key=lambda t:mu[t],reverse=True); pos={t:i+1 for i,t in enumerate(rank)}
    def line(t):
        v=annvol(oh[t]); sig60=v*np.sqrt(60/252) if v else None
        kt=kelly_target_pct(mu[t],sig60,max_pct=0.15,max_concentration=0.12,fractional=0.3) if sig60 else 0
        return f"  {t:6s} rank {pos[t]:3d}/{len(s)}  raw={s[t]:+.4f}  mu={mu[t]:+.4f}  P={P[t]:.3f}  kelly={kt*100:.1f}%"
    print(f"neutral_raw={cal.neutral_raw:+.3f}  (raw>neutral => mu>0 => bullish)\n")
    print("=== TOP 12 the model favors (by mu) ===")
    for t in rank[:12]: print(line(t))
    print("\n=== the 'hot' names — where the model actually puts them ===")
    for t in HOT:
        if t in s.index: print(line(t)+("  <- BEARISH" if mu[t]<=0 else ""))
    held=list((json.load(open(LIVE)).get("entry_dates") or {}).keys())
    print(f"\n=== held positions (top-up check; top_up_threshold=0.05) ===")
    for t in held:
        if t in s.index: print(line(t))
        else: print(f"  {t}: not scored")
    print("  top-up fires when held kelly_target − current_weight > 0.05 (current weight from broker, not in offline state)")

if __name__=="__main__": main()
