"""Buy-book under sizing scenarios — fix the Kelly sigma-horizon + retune fractional.

Scores once (real data asof 2026-06-10, calibrated-mu gate ON), then shows the
top-slot buy book under:
  (A) current:  sigma_horizon=252 (annual), fractional=0.5   [the bug]
  (B) sigma=60 matched, fractional=0.5
  (C) sigma=60 matched, fractional=0.3
  (D) sigma=60 matched, fractional=0.2
so we can pick a config that lifts the chips the model favors without pinning
every name at the 12% cap.
"""
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
from renquant_pipeline.kernel.pipeline.signal_direction import long_signal_ok
from renquant_pipeline.kernel.kelly import kelly_target_pct
SEMIS={"NVDA","AMD","SMCI","QCOM","MU","AVGO","DELL","INTC","LRCX","AMAT","ASML","ARM","MRVL","ON","NXPI","ADI","TXN","MCHP"}
class C: pass
def annvol(df,w=60):
    r=df["close"].pct_change().dropna().tail(w)
    return min(max(float(r.std()*np.sqrt(252)),0.05),1.5) if len(r)>=5 else None
def main():
    cfg=json.load(open(CFG))
    cfg["ranking"]["panel_scoring"]["csranknorm_context_mode"]="stable"
    cfg["ranking"]["panel_scoring"]["signal_gate_prefer_calibrated_mu"]=True
    slots=int(cfg.get("max_concurrent_positions",8)); cash=float(cfg.get("initial_cash",100000))
    max_conc=0.12; max_pct=0.15
    held=list((json.load(open(LIVE)).get("entry_dates") or {}).keys())
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
    v={t:annvol(oh[t]) for t in s.index}
    # admitted by gate, ranked by mu, top open slots (exclude held)
    adm=[t for t in s.index if long_signal_ok(float(s[t]),cfg,expected_return=mu[t])[0]]
    adm.sort(key=lambda t:mu[t],reverse=True)
    open_slots=max(0,slots-len(held))
    newb=[t for t in adm if t not in held][:open_slots]
    print(f"held={held}  open_slots={open_slots}  new buys (top by mu): {newb}\n")
    def book(horizon,frac):
        rows=[]
        for t in newb:
            sig=v[t]
            if sig is None: rows.append((t,0.0)); continue
            sig_h=sig*np.sqrt(horizon/252.0)
            kt=kelly_target_pct(mu[t],sig_h,max_pct=max_pct,max_concentration=max_conc,fractional=frac)
            rows.append((t,kt))
        return rows
    scenarios=[("A sigma=252 f=0.5 [CURRENT/BUG]",252,0.5),("B sigma=60  f=0.5",60,0.5),
               ("C sigma=60  f=0.3",60,0.3),("D sigma=60  f=0.2",60,0.2)]
    for name,h,f in scenarios:
        rows=book(h,f); tot=sum(k for _,k in rows)
        semi_w=sum(k for t,k in rows if t in SEMIS); soft_w=tot-semi_w
        print(f"--- {name} ---  deploy={tot*100:4.0f}%  chips={semi_w*100:4.0f}%  other={soft_w*100:4.0f}%")
        print("    "+"  ".join(f"{t}{'*' if t in SEMIS else ''}={k*100:.0f}%" for t,k in rows))
    print("\n(* = semiconductor)  caps: max_pct=15%, concentration=12%")
if __name__=="__main__": main()
