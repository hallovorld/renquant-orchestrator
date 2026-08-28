"""Stage I-0 census (merged design orch#1072). Frozen declarations FIRST:

- Regime for the KILL census: the K5 approx-regime computed on DAILY SPY
  (200d trend x trailing-20d vol vs rolling-252d median), assigned to every
  bar of that session (pure upsample). The intraday vol overlay named in the
  design is RESERVED for Stage I-1 conditioning and is NOT used by the kill
  census (fewer degrees of freedom at the gate).
- Drift rule (calibrated on development data only): a name-day is excluded
  when |IEX last-bar close / official daily close - 1| > 0.01; a name is
  excluded entirely when >5% of its eligible days breach.
- Eligibility: trailing rule from the design (>=60 sessions history and
  >=80% coverage over trailing 60 sessions, re-evaluated per session).
- s0 = -(trailing 13-bar return); primary h=13; blocks within-session,
  gap>=h; n_eff_adj = n_blocks*(1-rho1)/(1+rho1), rho1 floored at 0,
  estimated on episode-internal consecutive block-mean-IC pairs; <8 pairs
  => FAIL CLOSED (unestablished).
KILL: BEAR n_eff_adj < 30 at h=13 => route dead.
"""
import json, pathlib, numpy as np, pandas as pd
from scipy.stats import spearmanr
SP=pathlib.Path(__file__).parent
BARS=SP/"g2v3_bars"
H=13
# ---- SPY daily regime (frozen K5 formula) ----
spy=pd.read_parquet("/Users/renhao/git/github/RenQuant/data/ohlcv/SPY/1d.parquet",columns=["close"])["close"]
spy.index=pd.to_datetime(spy.index)
trend=spy>spy.rolling(200).mean()
vol=spy.pct_change().rolling(20).std()
volhi=vol>vol.rolling(252,min_periods=60).median()
regime=pd.Series("BEAR",index=spy.index,dtype=object)
regime[trend&~volhi]="BULL_CALM"; regime[trend&volhi]="BULL_VOLATILE"; regime[~trend&~volhi]="CHOPPY"
# ---- load bars into per-name session frames ----
names=[p.stem for p in BARS.glob("*.parquet")]
print("names with bars:",len(names))
frames={}
for t in names:
    df=pd.read_parquet(BARS/f"{t}.parquet")
    ts=pd.to_datetime(df["ts"])
    et=ts.dt.tz_convert("America/New_York")
    df=df.assign(session=et.dt.date, bar_et=et)
    # RTH only
    df=df[(et.dt.time>=pd.Timestamp("09:30").time())&(et.dt.time<pd.Timestamp("16:00").time())]
    df=df.sort_values("bar_et")
    frames[t]={"df":df,
               "by_sess":{k:v["close"].values for k,v in df.groupby("session")},
               "last_by_sess":df.groupby("session")["close"].last()}
# ---- coverage matrix (sessions x names): bars per session ----
all_sessions=sorted(set().union(*[set(f["by_sess"].keys()) for f in frames.values()]))
all_sessions=[s for s in all_sessions if str(s)>="2020-08-01" and str(s)<="2024-06-30"]
sess_idx={s:i for i,s in enumerate(all_sessions)}
cov=pd.DataFrame(0,index=all_sessions,columns=names,dtype=int)
for t,f in frames.items():
    c=pd.Series({k:len(v) for k,v in f["by_sess"].items()})
    cov.loc[c.index.intersection(cov.index),t]=c.reindex(cov.index).fillna(0).astype(int).loc[c.index.intersection(cov.index)]
present=(cov>=20)  # a session "covered" when >=20 of 39 bars exist
# trailing eligibility
elig=pd.DataFrame(False,index=all_sessions,columns=names)
roll=present.rolling(60,min_periods=60).mean()
hist=present.cumsum()
elig=(roll>=0.80)&(hist>=60)
print("median eligible names/session:", int(elig.sum(axis=1).median()))
# ---- drift validation (dev-only rule) ----
excluded_names=[]
drift_stats={}
for t in names:
    p=pathlib.Path(f"/Users/renhao/git/github/RenQuant/data/ohlcv/{t}/1d.parquet")
    if not p.exists(): continue
    dly=pd.read_parquet(p,columns=["close"])["close"]; dly.index=pd.to_datetime(dly.index).date
    last=frames[t]["last_by_sess"]
    m=pd.DataFrame({"iex":last}).join(pd.Series(dly,name="ofc"),how="inner").dropna()
    if len(m)<50: continue
    drift=(m["iex"]/m["ofc"]-1).abs()
    breach=(drift>0.01).mean()
    drift_stats[t]=float(breach)
    if breach>0.05: excluded_names.append(t)
print("drift-excluded names:",len(excluded_names))
# ---- s0 ICs at h=13, per session/regime ----
# build panel of s0 and fwd returns per bar index
ics={}  # (session)-> ic ; regime via session date
for si,s in enumerate(all_sessions):
    rows_s=[]; rows_f=[]
    tickers_today=[t for t in names if elig.at[s,t] and t not in excluded_names]
    if len(tickers_today)<100: continue
    for t in tickers_today:
        c=frames[t]["by_sess"].get(s)
        if c is None or len(c)<H*2+1: continue
        # one obs per session at bar H: s0 uses bars [0..H], fwd = [H..2H]
        s0=-(c[H]/c[0]-1.0)
        fwd=c[2*H]/c[H]-1.0
        rows_s.append(s0); rows_f.append(fwd)
    if len(rows_s)>=100:
        ics[s]=spearmanr(rows_s,rows_f).statistic
ic=pd.Series(ics); ic.index=pd.to_datetime(ic.index); ic=ic.sort_index()
reg=regime.reindex(ic.index).ffill()
# ---- episodes + blocks + AR(1) ESS ----
out={"h":H,"n_ic_days":len(ic),"drift_excluded":len(excluded_names),
     "median_eligible":int(elig.sum(axis=1).median()),"by_regime":{}}
# regime episodes = contiguous runs
runs=[]; cur=None; start=None; prev=None
for d,r in reg.items():
    if r!=cur:
        if cur is not None: runs.append((cur,start,prev))
        cur=r; start=d
    prev=d
runs.append((cur,start,prev))
for rname in ("BEAR","BULL_CALM","BULL_VOLATILE","CHOPPY"):
    # one IC obs per session (labels are within-session; sessions are the block units at h=13 intra-session)
    # blocks: consecutive sessions within an episode, block=1 session (each session's obs are within-session,
    # independent across sessions at bar-level h; the session IS the h=13 block since 39 bars/day => obs at bar 13 only)
    ep_blocks=[]
    pairs=[]
    for (r0,d0,d1) in runs:
        if r0!=rname: continue
        seg=ic[(ic.index>=d0)&(ic.index<=d1)].dropna()
        if len(seg)==0: continue
        ep_blocks.append(seg)
    n_blocks=sum(len(s) for s in ep_blocks)
    for seg in ep_blocks:
        v=seg.values
        pairs.extend(zip(v[:-1],v[1:]))
    if len(pairs)>=8:
        a=np.array(pairs)
        rho=float(np.corrcoef(a[:,0],a[:,1])[0,1]); rho=max(rho,0.0)
        n_eff=n_blocks*(1-rho)/(1+rho)
        est="ok"
    else:
        rho=None; n_eff=None; est="FAIL_CLOSED(<8 pairs)"
    out["by_regime"][rname]={"n_blocks":int(n_blocks),"n_episodes":len(ep_blocks),
        "pairs":len(pairs),"rho1":round(rho,4) if rho is not None else None,
        "n_eff_adj":round(n_eff,1) if n_eff is not None else None,
        "estimator":est,
        "mean_ic_s0":round(float(pd.concat(ep_blocks).mean()),5) if ep_blocks else None}
b=out["by_regime"]["BEAR"]
out["KILL_GATE"]={"bar":"BEAR n_eff_adj >= 30 @ h=13",
    "value":b["n_eff_adj"],"verdict":("PASS" if (b["n_eff_adj"] or 0)>=30 else "KILL")}
json.dump(out,open(SP/"g2v3_stage_i0_report.json","w"),indent=1)
print(json.dumps(out,indent=1))
