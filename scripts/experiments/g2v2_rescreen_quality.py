"""G2v2 development-window re-screen: the QUALITY base at the widened
cross-section (current 246-name universe + r2k dev names), under the
development-selection protocol (2016-2019 = declared development window;
2020-2023 untouched).

Features: roe, gross_profitability, asset_growth — PIT via filed_date
overwrite-forward (production semantics), T-1 shifted at use.
Labels: exact 20d forward returns; r2k names via the verified global
affine inversion of ROC20 (beta=2.288396, alpha=-2.326484, machine-precision
on 4 ground-truth tickers); legacy names via ohlcv closes.
Method: forward-chaining expanding-window OOF daily rank-IC, block-t on
~quarterly non-overlapping blocks (gap>=h=20), matching the K5 screen shape.
"""
import json, pathlib, numpy as np, pandas as pd
from scipy.stats import spearmanr
SP=pathlib.Path(__file__).parent
BETA, ALPHA = 2.288396, -2.326484
DEV_START, DEV_END = "2016-01-01", "2019-12-31"
H=20

# ---- 1. r2k labels from ROC20 inversion ----
r2k=pd.read_parquet("/Users/renhao/git/github/RenQuant/data/alpha158_r2k_dataset.parquet",
                    columns=["ticker","date","ROC20"])
r2k["date"]=pd.to_datetime(r2k["date"])
r2k=r2k.sort_values(["ticker","date"])
def fwd20(g):
    roc=g["ROC20"]
    return BETA/(roc.shift(-H)-ALPHA)-1.0
r2k["fwd"]=r2k.groupby("ticker",group_keys=False).apply(fwd20, include_groups=False).values
labels_r2k=r2k[["ticker","date","fwd"]]

# ---- 2. quality features for r2k names from the harvest ----
FIELD_MAP={"net_income":"NetIncomeLoss","total_assets":"Assets",
           "stockholders_equity":"StockholdersEquity","gross_profit":"GrossProfit"}
rows=[]
for fn in ("g2v2_r2k_companyfacts.jsonl","g2v2_r2k_equity_shares.jsonl"):
    for l in open(SP/fn):
        r=json.loads(l); f=r.get("field")
        if f not in FIELD_MAP or not r.get("filed_date") or r.get("value") is None: continue
        rows.append((r["ticker"],FIELD_MAP[f],r["filed_date"],r.get("period_end") or "",float(r["value"])))
facts=pd.DataFrame(rows,columns=["ticker","concept","filed","end","value"])
facts["filed"]=pd.to_datetime(facts["filed"])
spy=pd.read_parquet("/Users/renhao/git/github/RenQuant/data/ohlcv/SPY/1d.parquet")
idx=pd.DatetimeIndex(pd.to_datetime(spy.index))
idx=idx[(idx>="2015-01-02")&(idx<=DEV_END)]
def _safe(num,den,eps=1.0): return num/den.where(den.abs()>eps)
feat_rows=[]
for t,g in facts.groupby("ticker"):
    daily=pd.DataFrame(index=idx)
    for c,gc in g.groupby("concept"):
        gc=gc.sort_values(["filed","end"]).drop_duplicates("filed",keep="last")
        daily[c]=gc.set_index("filed")["value"].reindex(idx,method="ffill")
    ni=daily.get("NetIncomeLoss"); eq=daily.get("StockholdersEquity")
    gp=daily.get("GrossProfit"); ast=daily.get("Assets")
    if ni is None or eq is None: continue
    r=pd.DataFrame(index=idx); r["ticker"]=t
    with np.errstate(all="ignore"):
        r["roe"]=_safe(ni,eq)
        r["gross_profitability"]=_safe(gp,ast) if gp is not None and ast is not None else np.nan
        r["asset_growth"]=ast.pct_change(periods=252,fill_method=None).clip(-0.99,5.0) if ast is not None else np.nan
    feat_rows.append(r.reset_index().rename(columns={"index":"date"}))
qual_r2k=pd.concat(feat_rows,ignore_index=True)

# ---- 3. legacy universe: features from sec_fundamentals_daily + labels from ohlcv ----
legacy=pd.read_parquet("/Users/renhao/git/github/RenQuant/data/sec_fundamentals_daily.parquet",
                       columns=["date","ticker","roe","gross_profitability","asset_growth"])
legacy["date"]=pd.to_datetime(legacy["date"])
legacy=legacy[(legacy["date"]>=DEV_START)&(legacy["date"]<=DEV_END)]
leg_t=sorted(legacy["ticker"].unique())
lab_rows=[]
for t in leg_t:
    p=pathlib.Path(f"/Users/renhao/git/github/RenQuant/data/ohlcv/{t}/1d.parquet")
    if not p.exists(): continue
    px=pd.read_parquet(p,columns=["close"])["close"]; px.index=pd.to_datetime(px.index)
    f=px.shift(-H)/px-1.0
    lab_rows.append(pd.DataFrame({"ticker":t,"date":f.index,"fwd":f.values}))
labels_leg=pd.concat(lab_rows,ignore_index=True)

# ---- 4. combined dev panel, T-1 feature shift ----
def prep(feat,lab):
    m=feat.merge(lab,on=["ticker","date"],how="inner")
    return m
qual_r2k=qual_r2k[(qual_r2k["date"]>=DEV_START)]
comb=pd.concat([prep(qual_r2k,labels_r2k), prep(legacy,labels_leg)],ignore_index=True)
comb=comb[(comb["date"]>=DEV_START)&(comb["date"]<=DEV_END)].dropna(subset=["fwd"])
# T-1 shift: features computed through filed-date ffill are available same day;
# shift by one day within ticker for caution (K5 convention)
comb=comb.sort_values(["ticker","date"])
for c in ("roe","gross_profitability","asset_growth"):
    comb[c]=comb.groupby("ticker")[c].shift(1)
# composite quality score: mean of cross-sectional z-scores (K5 base def)
def xz(s):
    return (s-s.mean())/(s.std() or 1)
def day_score(g):
    zs=[xz(g[c]) for c in ("roe","gross_profitability","asset_growth") if g[c].notna().sum()>=30]
    if not zs: return pd.Series(np.nan,index=g.index)
    return pd.concat(zs,axis=1).mean(axis=1)
comb["score"]=comb.groupby("date",group_keys=False).apply(day_score, include_groups=False).values
d=comb.dropna(subset=["score"])
# ---- 5. daily rank-IC + quarterly block t (gap>=h) ----
ics={}
for dt,g in d.groupby("date"):
    if len(g)>=100:
        ics[dt]=spearmanr(g["score"],g["fwd"]).statistic
ic=pd.Series(ics).sort_index()
blocks=[]
i=0
vals=ic.values
while i < len(vals):
    chunk=vals[i:i+63]
    if len(chunk)>=40: blocks.append(np.nanmean(chunk))
    i+=63+H  # gap >= h between blocks
blocks=np.array(blocks)
tstat=blocks.mean()/(blocks.std(ddof=1)/np.sqrt(len(blocks))) if len(blocks)>1 else float("nan")
rep={"dev_window":[DEV_START,DEV_END],"h":H,
     "n_days":len(ic),"mean_daily_ic":round(float(ic.mean()),5),
     "median_names_per_day":int(d.groupby("date").size().median()),
     "n_blocks":len(blocks),"block_means":[round(float(b),5) for b in blocks],
     "block_t":round(float(tstat),3),
     "by_year":{str(y):round(float(g.mean()),5) for y,g in ic.groupby(ic.index.year)}}
json.dump(rep,open(SP/"g2v2_rescreen_quality_report.json","w"),indent=1)
print(json.dumps(rep,indent=1))
