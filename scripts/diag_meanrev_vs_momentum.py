"""Is the model mean-reverting or trend-following?
corr(recent trailing return, mu) across the universe. Negative => fades winners
(mean-reversion); positive => rides winners (momentum)."""
from __future__ import annotations
import json, os
import numpy as np, pandas as pd
os.environ.setdefault("RENQUANT_REPO_ROOT", os.path.abspath("RenQuant"))
OHLCV="RenQuant/data/ohlcv"
MODEL=("RenQuant/artifacts/patchtst_shadow/pt07_strict_trainfit_embargo60_20260522/seed_44/hf_patchtst_all_seed44_model.pt")
CAL=("RenQuant/backtesting/renquant_104/artifacts/shadow/panel-rank-calibration.hf_patchtst_seed44_trainfit_20230103_20240409.json")
CFG="renquant-strategy-104/configs/strategy_config.json"
ASOF=pd.Timestamp("2026-06-10")
from renquant_pipeline.kernel.panel_pipeline import job_panel_scoring as J
from renquant_pipeline.kernel.panel_pipeline.hf_patchtst_scorer import HFPatchTSTPanelScorer
from renquant_pipeline.kernel.panel_pipeline.global_calibrator import GlobalPanelCalibration
class C: pass
def trail(df,d):
    c=df["close"];
    return float(c.iloc[-1]/c.iloc[-1-d]-1) if len(c)>d else None
def main():
    cfg=json.load(open(CFG)); cfg["ranking"]["panel_scoring"]["csranknorm_context_mode"]="stable"
    sc=HFPatchTSTPanelScorer.load(MODEL)
    oh={}
    for t in cfg["watchlist"]:
        p=f"{OHLCV}/{t}/1d.parquet"
        if os.path.exists(p):
            df=pd.read_parquet(p); df=df[df.index<=ASOF]
            if len(df)>260: oh[t]=df
    ctx=C(); ctx.ohlcv=oh; ctx.config=cfg; ctx.holdings={}; ctx.models={}; ctx.today=ASOF
    ph=J._build_live_panel_history(ctx,sc,list(oh.keys()),ASOF)
    s=sc.score_with_history(ph,list(oh.keys())).dropna()
    cal=GlobalPanelCalibration.load(CAL)
    mu={t:cal.expected_return(float(s[t])) for t in s.index}
    df=pd.DataFrame({"mu":mu})
    for d,nm in ((20,"ret20"),(60,"ret60"),(120,"ret120"),(252,"ret252")):
        df[nm]={t:trail(oh[t],d) for t in s.index}
    df=df.dropna()
    print(f"n={len(df)} names, asof {ASOF.date()}\n")
    print("=== Spearman corr( trailing return , model mu ) ===")
    for nm,lbl in (("ret20","20d"),("ret60","60d"),("ret120","120d"),("ret252","12mo")):
        r=df["mu"].corr(df[nm],method="spearman")
        tag = "MEAN-REVERSION (fades winners)" if r<-0.15 else ("MOMENTUM (rides winners)" if r>0.15 else "~neutral")
        print(f"  vs {lbl:4s} momentum:  rho = {r:+.3f}   {tag}")
    print("\n=== the 8 strongest recent winners (by 60d return): does the model fade them? ===")
    top=df.sort_values("ret60",ascending=False).head(8)
    for t,row in top.iterrows():
        print(f"  {t:6s} 60d_ret={row['ret60']*100:+6.1f}%  mu={row['mu']:+.4f}  {'FADED (mu<0)' if row['mu']<0 else 'kept'}")
    print("\n=== the 8 worst recent laggards (by 60d return): does the model buy them? ===")
    bot=df.sort_values("ret60").head(8)
    for t,row in bot.iterrows():
        print(f"  {t:6s} 60d_ret={row['ret60']*100:+6.1f}%  mu={row['mu']:+.4f}  {'BOUGHT (mu>0)' if row['mu']>0 else 'avoided'}")
if __name__=="__main__": main()
