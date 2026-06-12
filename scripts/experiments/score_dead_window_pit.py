"""Score the dead window (2025-10..2026-01) with PIT model #1 (cutoff 2023-10)."""
import sys, json, torch, numpy as np, pandas as pd
sys.path.insert(0, "scripts")
from scipy import stats as st
import patchtst_hf as P

ART="artifacts/patchtst_shadow/pit_cutoff_2023-10-01_seed44"
panel=pd.read_parquet("data/transformer_v4_wl200_clean.parquet")
panel["date"]=pd.to_datetime(panel["date"])
meta=json.load(open(f"{ART}/hf_patchtst_all_seed44_model.pt.metadata.json")) if False else None
# feature cols = panel cols minus meta/labels (same 172 as training)
drop={"ticker","date","split_label","fwd_5d_excess","fwd_20d_excess","fwd_60d_excess"}
feat=[c for c in panel.columns if c not in drop]
win=panel[(panel["date"]>="2025-08-15")&(panel["date"]<="2026-01-31")].copy()  # extra lead for seq_len=24
win=P.csrank_norm_per_day(win, feat)
from safetensors.torch import load_file
import glob
ckpt=sorted(glob.glob(f"{ART}/_hf_trainer/checkpoint-*/model.safetensors"))[-1]
sd=load_file(ckpt)
from transformers import PatchTSTConfig
cfg=PatchTSTConfig(num_input_channels=len(feat), context_length=24, patch_length=4,
                   patch_stride=4, d_model=64, num_attention_heads=4,
                   num_hidden_layers=2, ffn_dim=128)
model=P.HFPatchTSTRanker(cfg, use_distributional_head=True)
missing,unexpected=model.load_state_dict(sd, strict=False)
print("missing:",len(missing),"unexpected:",len(unexpected))
print("loaded", ckpt)
model.eval()
dates=sorted(win["date"].unique())
ics=[]
with torch.no_grad():
    for dt in [d for d in dates if d>=pd.Timestamp("2025-10-01")][::2]:   # every 2nd day
        rows=[]
        idx=dates.index(dt)
        if idx<23: continue
        seq_dates=dates[idx-23:idx+1]
        sub=win[win["date"].isin(seq_dates)]
        piv={}
        for t,g in sub.groupby("ticker"):
            if len(g)==24:
                piv[t]=g.sort_values("date")[feat].values
        if len(piv)<30: continue
        X=torch.tensor(np.stack(list(piv.values())),dtype=torch.float32)
        out=model(X)
        sc=out["score"] if isinstance(out,dict) else (out[0] if isinstance(out,tuple) else out)
        sc=sc.squeeze(-1) if sc.dim()>1 else sc
        s=pd.Series(sc.numpy().ravel()[:len(piv)], index=list(piv.keys()))
        lab=win[win["date"]==dt].set_index("ticker")["fwd_60d_excess"]
        j=pd.concat([s.rename("p"),lab.rename("y")],axis=1).dropna()
        if len(j)>=10: ics.append(st.spearmanr(j["p"],j["y"]).statistic)
print(f"model#1 (cutoff 2023-10, 24-27mo stale) DEAD-WINDOW IC: mean={np.mean(ics):+.4f} over {len(ics)} sampled days")
print(f"vs prod (cutoff 2024-11, 11-15mo stale) same window:    -0.0915")

# ── RESULTS (2026-06-11/12, same hand-rolled pipeline, 42 sampled days) ──
# dead window 2025-10-01..2026-01-31, IC vs fwd_60d_excess:
#   PROD   (cutoff 2024-11, 11-15mo stale): -0.0054
#   PIT #1 (cutoff 2023-10, 24-27mo stale): -0.0701
# → staleness effect REAL (~6-7 IC pts for 13 months extra distance)
# → regime effect ALSO real: even the fresher model only reaches ~0 in calm
#   tape (vs +0.19 in dispersive windows) — freshness rescues from negative
#   to zero, not to positive. Quarterly retrains: necessary, NOT sufficient.
# caveat: hand pipeline != native (native scored prod at -0.0915 in the same
# window); within-pipeline A/B is fair, cross-pipeline levels are not.

# ── THIRD POINT (2026-06-12, model #2 cutoff 2024-04 done 23:23) ──
# Same hand-rolled pipeline, same 42 sampled dead-window days:
#   prod  (cutoff 2024-11, 11-15mo stale): -0.0054
#   PIT#2 (cutoff 2024-04, 18-21mo stale): -0.0584
#   PIT#1 (cutoff 2023-10, 24-27mo stale): -0.0701
# → decay curve is MONOTONE across three cutoffs in the same calendar
#   window: staleness effect confirmed with three points (~6.5 IC pts per
#   ~year of cutoff distance in this window). Regime effect still present:
#   even the freshest model is ~0, not positive, in calm tape.
# CAVEAT: hand pipeline levels != native pipeline levels; within-pipeline
# comparisons only. Next: per-cutoff calibrators -> manifest extension ->
# WF gate retake (the 3-cut exam).
