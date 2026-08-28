"""GOAL-2v3 Stage I-0 census — r2, faithful to the frozen #1072 design.

Frozen declarations implemented LITERALLY (review r1 of #1073):

- Bar-level IC observations: at bar-time t (0-indexed RTH 10-min bars,
  t = 13..25), score s0(t) = -(close[t]/close[t-13] - 1), label
  fwd(t) = close[t+13]/close[t] - 1. Times 26..38 would have close-truncated
  labels and are DROPPED per the frozen rule -- the drop IS the gap.
- Block = the mean of the 13 bar-time ICs {t=13..25} of one session:
  length h=13 in bar time, and consecutive blocks (adjacent sessions in an
  episode) are separated by the 13 dropped bar-times >= h. Within-session
  only; non-overlapping; gap >= h. One block per session BY CONSTRUCTION of
  the 39-bar RTH day, not by convenience.
- Drift rule, two layers, in declared order: (1) name-days with
  |IEX close/official close - 1| > 0.01 are excluded from ALL downstream
  use (including IC rows of retained names); (2) a name whose breach rate
  over its ELIGIBLE days exceeds 5% is excluded entirely.
- Trailing eligibility as frozen (>=60 sessions history, >=80% trailing-60
  coverage), evaluated on the coverage matrix BEFORE drift exclusions
  (coverage is about data presence; drift is about data quality).
- rho1: RAW estimate persisted alongside the floored value used by the
  conservative ESS formula; block-mean series persisted per regime in the
  audit artifact.
- Repo-relative paths: data dir defaults to doc/research/data/2026-08-27-
  g2v3-i0/ inside the repo; the bar store location comes from
  G2V3_BAR_STORE (mutable vendor data, not committed; content hashes of
  every consumed file go into the audit artifact).

KILL: BEAR n_eff_adj < 30 at h=13 => route dead.
"""
import hashlib, json, os, pathlib, sys
import numpy as np, pandas as pd
from scipy.stats import spearmanr

REPO=pathlib.Path(__file__).resolve().parents[2]
DATA=REPO/"doc/research/data/2026-08-27-g2v3-i0"
BARS=pathlib.Path(os.environ.get("G2V3_BAR_STORE",""))
if not BARS.exists():
    sys.exit("set G2V3_BAR_STORE to the fetched 10-min bar directory")
H=13

# ---- SPY daily regime (frozen K5 formula) ----
spy=pd.read_parquet("/Users/renhao/git/github/RenQuant/data/ohlcv/SPY/1d.parquet",columns=["close"])["close"]
spy.index=pd.to_datetime(spy.index)
trend=spy>spy.rolling(200).mean()
vol=spy.pct_change().rolling(20).std()
volhi=vol>vol.rolling(252,min_periods=60).median()
regime=pd.Series("BEAR",index=spy.index,dtype=object)
regime[trend&~volhi]="BULL_CALM"; regime[trend&volhi]="BULL_VOLATILE"; regime[~trend&~volhi]="CHOPPY"

# ---- load bars ----
hashes={}
frames={}
for p in sorted(BARS.glob("*.parquet")):
    t=p.stem
    hashes[t]=hashlib.sha256(p.read_bytes()).hexdigest()
    df=pd.read_parquet(p)
    ts=pd.to_datetime(df["ts"]); et=ts.dt.tz_convert("America/New_York")
    df=df.assign(session=et.dt.date, bar_et=et)
    df=df[(et.dt.time>=pd.Timestamp("09:30").time())&(et.dt.time<pd.Timestamp("16:00").time())].sort_values("bar_et")
    # Amendment A1: canonical 39-slot RTH grid; position IS time, NaN = missing
    df=df.assign(slot=((df["bar_et"].dt.hour*60+df["bar_et"].dt.minute)-570)//10)
    by={}
    for k,v in df.groupby("session"):
        arr=np.full(39,np.nan)
        sl=v["slot"].values.astype(int); cl=v["close"].values
        ok=(sl>=0)&(sl<39)
        arr[sl[ok]]=cl[ok]
        by[k]=arr
    frames[t]={"by_sess":by,
               "last_by_sess":df.groupby("session")["close"].last()}
print("names with bars:",len(frames),flush=True)

all_sessions=sorted(set().union(*[set(f["by_sess"].keys()) for f in frames.values()]))
all_sessions=[s for s in all_sessions if "2020-08-01"<=str(s)<="2024-06-30"]
names=list(frames)

# ---- coverage + trailing eligibility ----
cov=pd.DataFrame(0,index=all_sessions,columns=names,dtype=int)
for t,f in frames.items():
    c=pd.Series({k:int(np.isfinite(v).sum()) for k,v in f["by_sess"].items()})
    idx=c.index.intersection(cov.index)
    cov.loc[idx,t]=c.loc[idx].astype(int)
present=(cov>=20)
roll=present.rolling(60,min_periods=60).mean()
hist=present.cumsum()
elig=(roll>=0.80)&(hist>=60)

# ---- drift rule, two layers, declared order ----
bad_days={}     # t -> set of sessions excluded (layer 1)
excluded_names=[]
name_breach={}
for t in names:
    p=pathlib.Path(f"/Users/renhao/git/github/RenQuant/data/ohlcv/{t}/1d.parquet")
    if not p.exists():
        continue
    dly=pd.read_parquet(p,columns=["close"])["close"]; dly.index=pd.to_datetime(dly.index).date
    last=frames[t]["last_by_sess"]
    m=pd.DataFrame({"iex":last}).join(pd.Series(dly,name="ofc"),how="inner").dropna()
    if m.empty: continue
    drift=(m["iex"]/m["ofc"]-1).abs()
    breach_days=set(drift[drift>0.01].index)
    bad_days[t]=breach_days
    # layer 2: breach rate over ELIGIBLE days only
    el_days=[s for s in m.index if s in elig.index and bool(elig.at[s,t])]
    if el_days:
        rate=len([s for s in el_days if s in breach_days])/len(el_days)
        name_breach[t]=rate
        if rate>0.05: excluded_names.append(t)
print("drift: layer-2 excluded names:",len(excluded_names),flush=True)

# ---- bar-level ICs; block = mean of 13 bar-time ICs per session ----
block={}   # session -> block-mean IC
percell={} # audit: session -> n names used
bar_ics_audit={}  # A1: session -> 13 bar-time ICs
for s in all_sessions:
    cols=[t for t in names
          if bool(elig.at[s,t]) and t not in excluded_names
          and s not in bad_days.get(t,())]
    if len(cols)<100: continue
    mats=[]
    for t in cols:
        c=frames[t]["by_sess"].get(s)
        if c is None: continue
        mats.append((t,c))
    if len(mats)<100: continue
    ics=[]
    for tt in range(H,2*H):     # t = 13..25 on the canonical grid
        ss=[]; ff=[]
        for _,c in mats:
            a,b,d=c[tt-H],c[tt],c[tt+H]
            if np.isfinite(a) and np.isfinite(b) and np.isfinite(d):
                ss.append(-(b/a-1.0)); ff.append(d/b-1.0)
        if len(ss)>=100:
            ics.append(spearmanr(ss,ff).statistic)
    if len(ics)==H:            # all 13 bar-time ICs must exist (A1)
        block[s]=float(np.mean(ics)); percell[s]=len(mats)
        bar_ics_audit[str(s)]=[round(float(x),6) for x in ics]
ic=pd.Series(block); ic.index=pd.to_datetime(ic.index); ic=ic.sort_index()
reg=regime.reindex(ic.index).ffill()
print("block sessions:",len(ic),flush=True)

# ---- episodes + AR(1) ESS (raw + floored rho) ----
runs=[]; cur=None; start=None; prev=None
for d,r in reg.items():
    if r!=cur:
        if cur is not None: runs.append((cur,start,prev))
        cur=r; start=d
    prev=d
runs.append((cur,start,prev))
out={"h":H,"n_block_sessions":len(ic),
     "median_eligible":int(elig.sum(axis=1).median()),
     "drift_excluded_names":len(excluded_names),
     "by_regime":{}}
audit={"block_series":{},"per_session_names":{str(k):v for k,v in percell.items()},
       "bar_time_ics":bar_ics_audit,
       "layer1_excluded_name_days":{t:[str(d) for d in sorted(ds)] for t,ds in bad_days.items() if ds},
       "eligible_membership_post_drift":{
           str(s):[t for t in names
                   if bool(elig.at[s,t]) and t not in excluded_names
                   and s not in bad_days.get(t,())]
           for s in all_sessions},
       "eligibility_counts":{str(s):int(elig.loc[s].sum()) for s in all_sessions},
       "name_breach_rates":name_breach,
       "excluded_names":excluded_names,
       "bar_store_sha256":hashes}
for rname in ("BEAR","BULL_CALM","BULL_VOLATILE","CHOPPY"):
    segs=[]
    for (r0,d0,d1) in runs:
        if r0!=rname: continue
        seg=ic[(ic.index>=d0)&(ic.index<=d1)].dropna()
        if len(seg): segs.append(seg)
    n_blocks=sum(len(x) for x in segs)
    pairs=[]
    for seg in segs:
        v=seg.values; pairs.extend(zip(v[:-1],v[1:]))
    if len(pairs)>=8:
        a=np.array(pairs)
        rho_raw=float(np.corrcoef(a[:,0],a[:,1])[0,1])
        rho_used=max(rho_raw,0.0)
        n_eff=n_blocks*(1-rho_used)/(1+rho_used)
        est="ok"
    else:
        rho_raw=None; rho_used=None; n_eff=None; est="FAIL_CLOSED(<8 pairs)"
    out["by_regime"][rname]={"n_blocks":int(n_blocks),"n_episodes":len(segs),
        "pairs":len(pairs),
        "rho1_raw":round(rho_raw,4) if rho_raw is not None else None,
        "rho1_used":round(rho_used,4) if rho_used is not None else None,
        "n_eff_adj":round(n_eff,1) if n_eff is not None else None,
        "estimator":est,
        "mean_block_ic_s0":round(float(pd.concat(segs).mean()),5) if segs else None}
    audit["block_series"][rname]={str(k.date()):round(float(v),6)
        for seg in segs for k,v in seg.items()}
b=out["by_regime"]["BEAR"]
GATE_RUN = "--gate-run" in sys.argv  # only a run from the A1-acknowledged frozen commit passes this flag
out["gate_bar"]="BEAR n_eff_adj >= 30 @ h=13"
if GATE_RUN:
    out["run_status"]="GATE_RUN"
    out["gate_verdict"]=("PASS" if (b["n_eff_adj"] or 0)>=30 else "KILL")
else:
    out["run_status"]="DEVELOPMENT_ONLY"
    out["gate_verdict"]=None
    out["indicative_bear_n_eff_adj"]=b["n_eff_adj"]
DATA.mkdir(parents=True,exist_ok=True)
json.dump(out,open(DATA/"g2v3_stage_i0_report.json","w"),indent=1)
json.dump(audit,open(DATA/"g2v3_stage_i0_audit.json","w"))
print(json.dumps(out,indent=1))
