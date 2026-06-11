"""Validate the model-protection state machine on REAL μ trajectories.

For each of the last few trading days, score the real universe and read each
target name's calibrated μ; then run kernel.model_protection.evaluate over the
day-by-day μ sequence to show when the N-of-N thesis-breach exit would fire vs
hold. Demonstrates: held names the model still likes are kept; a name the model
turns sustainedly bearish on is exited after N consecutive breaches; a single
noisy dip does not exit.
"""
from __future__ import annotations
import json, os
import pandas as pd
os.environ.setdefault("RENQUANT_REPO_ROOT", os.path.abspath("RenQuant"))
OHLCV="RenQuant/data/ohlcv"
MODEL=("RenQuant/artifacts/patchtst_shadow/pt07_strict_trainfit_embargo60_20260522/seed_44/hf_patchtst_all_seed44_model.pt")
CAL=("RenQuant/backtesting/renquant_104/artifacts/shadow/panel-rank-calibration.hf_patchtst_seed44_trainfit_20230103_20240409.json")
CFG="renquant-strategy-104/configs/strategy_config.json"
ASOFS=[pd.Timestamp(d) for d in ("2026-06-04","2026-06-05","2026-06-08","2026-06-09","2026-06-10")]
TARGETS=["MU","EQIX","DDOG","NVDA","AMZN","TSLA"]
from renquant_pipeline.kernel.panel_pipeline import job_panel_scoring as J
from renquant_pipeline.kernel.panel_pipeline.hf_patchtst_scorer import HFPatchTSTPanelScorer
from renquant_pipeline.kernel.panel_pipeline.global_calibrator import GlobalPanelCalibration
from renquant_pipeline.kernel.model_protection import (
    ProtectionConfig, ProtectionState, evaluate, ACTION_EXIT, ACTION_BREACH)
class C: pass
def main():
    cfg=json.load(open(CFG)); cfg["ranking"]["panel_scoring"]["csranknorm_context_mode"]="stable"
    sc=HFPatchTSTPanelScorer.load(MODEL); cal=GlobalPanelCalibration.load(CAL)
    wl=cfg["watchlist"]
    series={t:[] for t in TARGETS}
    for asof in ASOFS:
        oh={}
        for t in wl:
            p=f"{OHLCV}/{t}/1d.parquet"
            if os.path.exists(p):
                df=pd.read_parquet(p); df=df[df.index<=asof]
                if len(df): oh[t]=df
        ctx=C(); ctx.ohlcv=oh; ctx.config=cfg; ctx.holdings={}; ctx.models={}; ctx.today=asof
        ph=J._build_live_panel_history(ctx,sc,list(oh.keys()),asof)
        s=sc.score_with_history(ph,list(oh.keys())).dropna()
        for t in TARGETS:
            mu=cal.expected_return(float(s[t])) if t in s.index else None
            series[t].append(mu)
    print(f"protection cfg: threshold=0.0, n_strikes=3 (exit after 3 consecutive mu<=0)\n")
    print("asof:        " + "  ".join(d.strftime("%m-%d") for d in ASOFS))
    pcfg=ProtectionConfig(enabled=True, exit_mu_threshold=0.0, n_strikes=3)
    for t in TARGETS:
        st=ProtectionState(0); marks=[]; exited=None
        row=series[t]
        for i,mu in enumerate(row):
            action,st,_=evaluate(mu,pcfg,st)
            if action==ACTION_EXIT and exited is None: exited=ASOFS[i].strftime("%m-%d")
            marks.append("EXIT" if action==ACTION_EXIT else ("brch%d"%st.consecutive_breaches if action==ACTION_BREACH else "hold"))
        mus="  ".join(("%+.3f"%m if m is not None else " n/a ") for m in row)
        verdict = f"EXITS {exited}" if exited else "HELD (thesis intact)"
        print(f"  {t:5s} mu: {mus}   -> {verdict}")
        print(f"  {'':5s}     " + "  ".join(f"{m:>5s}" for m in marks))
if __name__=="__main__": main()
