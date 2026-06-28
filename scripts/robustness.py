#!/usr/bin/env python
"""
Robustness follow-up for the two candidates that cleared the floor at usable N:
  - mom_12_1 @ h=5  (t=1.84, 3.5x floor)
  - mom_12_1 @ h=20 (t=0.98, 1.24x floor, only 51 obs)
Checks:
  (A) Overlapping daily IC with Newey-West HAC t-stat (lag=h) -> uses all days, honest overlap correction.
  (B) Two-half sub-sample stability (is the IC present in both halves?).
  (C) Yearly IC breakdown (is it one lucky year?).
Same data panel from the cached parquet. READ-ONLY.
"""
import os, json
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

OUT="/tmp/sighunt"
px=pd.read_parquet(os.path.join(OUT,"bars.parquet"))
cov=px.notna().mean(); px=px[cov[cov>0.80].index]
print(f"[panel] {px.shape[0]} days x {px.shape[1]} names; {px.index.min().date()}->{px.index.max().date()}")

sig = px.shift(21)/px.shift(252)-1.0   # mom_12_1
def fwd(h): return px.shift(-h)/px-1.0

def daily_ic_series(sig, f, dates):
    out={}
    for d in dates:
        s=sig.loc[d]; fr=f.loc[d]; m=s.notna()&fr.notna()
        if m.sum()<10: continue
        rho=spearmanr(s[m].values, fr[m].values).correlation
        if rho is not None and not np.isnan(rho): out[d]=rho
    return pd.Series(out)

def nw_tstat(x, lag):
    x=np.asarray(x); n=len(x); mu=x.mean(); e=x-mu
    g0=np.dot(e,e)/n
    var=g0
    for k in range(1,lag+1):
        if k>=n: break
        w=1-k/(lag+1)
        gk=np.dot(e[k:],e[:-k])/n
        var+=2*w*gk
    se=np.sqrt(var/n)
    return mu, mu/se if se>0 else np.nan, n

for h in (5,20):
    f=fwd(h)
    valid=px.index[252:-h]
    ic=daily_ic_series(sig,f,valid)
    mu,t_nw,n = nw_tstat(ic.values, lag=h)
    print(f"\n=== mom_12_1 @ h={h} (overlapping daily IC, Newey-West lag={h}) ===")
    hit=(ic>0).mean()
    print(f"  n_days={n}  mean_ic={mu:+.4f}  NW t-stat={t_nw:+.2f}  hit={hit:.3f}")
    # two-half stability
    half=len(ic)//2
    a,b=ic.iloc[:half],ic.iloc[half:]
    print(f"  half-1 ({a.index.min().date()}..{a.index.max().date()}) mean_ic={a.mean():+.4f}")
    print(f"  half-2 ({b.index.min().date()}..{b.index.max().date()}) mean_ic={b.mean():+.4f}")
    # yearly
    yr=ic.groupby(ic.index.year).mean()
    print("  yearly mean_ic:", {int(k):round(v,4) for k,v in yr.items()})
