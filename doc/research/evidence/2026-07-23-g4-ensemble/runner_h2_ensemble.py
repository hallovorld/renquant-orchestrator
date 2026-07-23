"""GOAL-4 H2 — directly test the ENSEMBLE (the gap codex flagged): does an
equal-weight XGB+PatchTST ensemble clear the placebo floor where neither expert
does? Score BOTH experts on the same test dates, per-date z-score, average,
run the SAME existence screen on XGB / PatchTST / ENSEMBLE. Persists score frames.
"""
from __future__ import annotations
import sys, glob, numpy as np, pandas as pd
sys.path.insert(0, "/Users/renhao/git/github/renquant-orchestrator/src")
for r in ("renquant-pipeline","renquant-common","renquant-base-data","renquant-model"):
    sys.path.insert(0, f"/Users/renhao/git/github/{r}/src")
sys.path.insert(0, "/Users/renhao/git/github/RenQuant/.subrepo_runtime/repos/renquant-pipeline/src")
from renquant_orchestrator.expkit.evaluation import per_date_ic, shifted_label_placebo, gate_shift_sessions
from renquant_orchestrator.expkit.stats import block_bootstrap_conditional_mean, summarize_boot, usable_blocks
from renquant_pipeline.kernel.panel_pipeline.hf_patchtst_scorer import HFPatchTSTPanelScorer
import xgboost as xgb

SP="/private/tmp/claude-502/-Users-renhao-git-github-renquant-orchestrator/428feb92-8ee7-4b4f-afed-1e4fa82ef367/scratchpad"
A158="/Users/renhao/git/github/RenQuant/data/alpha158_291_fundamental_dataset_rawlabel.parquet"
TV4="/Users/renhao/git/github/RenQuant/data/transformer_v4_wl200_clean.parquet"
LAB={"5d":"fwd_5d_excess","20d":"fwd_20d_excess","60d":"fwd_60d_excess"}; HZ={"5d":5,"20d":20,"60d":60}
SPLIT=pd.Timestamp("2023-01-01"); ALPHA=0.05/6; NBOOT=2000

def mde(K,sd,f=2.4865): return float("inf") if (K<=0 or sd<=0) else f*sd/(K**0.5)
def zc(w):  # per-date cross-sectional z-score
    return w.sub(w.mean(axis=1),axis=0).div(w.std(axis=1).replace(0,np.nan),axis=0)

def existence(score, label, h):
    placebo=shifted_label_placebo(label, gate_shift_sessions(h))
    ic=per_date_ic(score, label, placebo, min_names=30)
    clean=ic["clean_ic"].dropna() if "clean_ic" in ic else pd.Series(dtype=float)
    real=ic["real_ic"].dropna(); plc=ic["placebo_ic"].dropna()
    n=len(clean); K=usable_blocks(n,h)
    boot=block_bootstrap_conditional_mean(clean.to_numpy(), np.ones(n,bool), block=h, n_boot=NBOOT, seed=44)
    sbf=summarize_boot(boot, alpha_one_sided=ALPHA); s95=summarize_boot(boot, alpha_one_sided=0.025)
    sd=clean.std(ddof=1)
    return dict(n=n,K=K,mde=mde(K,sd),real=real.mean(),floor=plc.mean(),clean=clean.mean(),
                lb95=s95["lb_one_sided"],lb_bonf=sbf["lb_one_sided"],exists=sbf["lb_one_sided"]>0)

print("loading panels ...", flush=True)
a=pd.read_parquet(A158); a["date"]=pd.to_datetime(a["date"])
drop=lambda c:("fwd" in c.lower() or "excess" in c.lower() or "label" in c.lower() or c in ("ticker","date"))
feat=[c for c in a.columns if not drop(c) and pd.api.types.is_numeric_dtype(a[c])]
tv=pd.read_parquet(TV4); tv["date"]=pd.to_datetime(tv["date"]); tv=tv.sort_values(["date","ticker"])

def xgb_scores(h,lbl):
    sub=a[["date","ticker",lbl]+feat].dropna(subset=[lbl])
    emb=pd.Timedelta(days=int(h*1.6)+5)
    tr=sub[sub.date<=SPLIT-emb]; te=sub[sub.date>=SPLIT]
    m=xgb.XGBRegressor(n_estimators=300,max_depth=5,learning_rate=0.03,subsample=0.8,
                       colsample_bytree=0.6,min_child_weight=10,reg_lambda=5.0,n_jobs=8,tree_method="hist")
    m.fit(tr[feat].to_numpy("float32"), tr[lbl].to_numpy("float32"))
    te=te.copy(); te["s"]=m.predict(te[feat].to_numpy("float32"))
    return te.pivot_table(index="date",columns="ticker",values="s",aggfunc="first"), \
           te.pivot_table(index="date",columns="ticker",values=lbl,aggfunc="first")

def pt_scores(name):
    mp=sorted(glob.glob(f"{SP}/patchtst_ss_fixed/pt_{name}/*.pt"))[0]
    sc=HFPatchTSTPanelScorer.load(mp); fc=sc.feature_cols
    keep=["ticker","date"]+[c for c in fc if c in tv.columns]; p=tv[keep]
    td=np.array(sorted(tv.loc[tv["date"]>=SPLIT,"date"].unique())); rows=[]
    for t in td:
        hist=p[(p["date"]>t-pd.Timedelta(days=int(sc.seq_len*2.2)+15))&(p["date"]<=t)]
        tk=hist.loc[hist["date"]==t,"ticker"].unique().tolist()
        if not tk: continue
        try: s=sc.score_with_history(hist,tk)
        except Exception: continue
        for k,v in s.items(): rows.append((t,k,float(v)))
    return pd.DataFrame(rows,columns=["date","ticker","s"]).pivot_table(index="date",columns="ticker",values="s",aggfunc="first")

print(f"{'h':>4} {'expert':>9} {'K':>4} {'clean':>8} {'lb_bonf':>9} {'exists':>7}")
out={}
for name,lbl in LAB.items():
    h=HZ[name]
    xs,label=xgb_scores(h,lbl); ps=pt_scores(name)
    # align on common (date,ticker); build equal-weight z-score ensemble
    ens_z=(zc(xs).add(zc(ps),fill_value=np.nan))/2.0
    ens_z=ens_z.dropna(how="all")
    res={}
    for tag,sc in (("XGB",xs),("PatchTST",ps),("ENSEMBLE",ens_z)):
        r=existence(sc, label, h); res[tag]=r
        print(f"{name:>4} {tag:>9} {r['K']:>4} {r['clean']:>8.3f} {r['lb_bonf']:>9.3f} {str(r['exists']):>7}", flush=True)
    out[name]=res
    xs.to_parquet(f"{SP}/h2_xgb_score_{name}.parquet"); ps.to_parquet(f"{SP}/h2_pt_score_{name}.parquet")

any_ens=any(out[n]["ENSEMBLE"]["exists"] for n in out)
print(f"\n[H2 VERDICT] does the ENSEMBLE exist at any horizon where neither expert does? -> {any_ens}")
import json; json.dump(out, open(f"{SP}/g4_h2_ensemble_FIXED_results.json","w"), indent=2, default=str)
print("saved g4_h2_ensemble_FIXED_results.json")
