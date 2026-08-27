"""G2v2 re-screen r2: K5-METHOD-FAITHFUL quality base at the widened
cross-section. Per-fold XGB (K5 hyperparams + folds verbatim), OOF daily
rank-IC, K5 block_means/block_t (H=20, spacing=40). Development window only."""
import json, pathlib, numpy as np, pandas as pd
from scipy.stats import spearmanr
import xgboost as xgb
SP=pathlib.Path(__file__).parent
H=20
FOLDS=[("2017-06-30","2017-08-01","2018-01-31"),
       ("2018-01-31","2018-03-01","2018-07-31"),
       ("2018-07-31","2018-09-01","2019-01-31"),
       ("2019-01-31","2019-03-01","2019-07-31"),
       ("2019-07-31","2019-09-01","2019-12-31")]
XGBP=dict(max_depth=3,n_estimators=300,learning_rate=0.05,subsample=0.8,
          colsample_bytree=0.8,min_child_weight=20,n_jobs=8,verbosity=0)
COLS=["roe","gross_profitability","asset_growth"]

# reuse the r1 combined panel construction (features T-1-shifted + fwd labels)
import importlib.util
BETA,ALPHA=2.288396,-2.326484
r2k=pd.read_parquet("/Users/renhao/git/github/RenQuant/data/alpha158_r2k_dataset.parquet",
                    columns=["ticker","date","ROC20"])
r2k["date"]=pd.to_datetime(r2k["date"]); r2k=r2k.sort_values(["ticker","date"])
r2k["fwd"]=r2k.groupby("ticker",group_keys=False)["ROC20"].apply(
    lambda s: BETA/(s.shift(-H)-ALPHA)-1.0).values
labels_r2k=r2k[["ticker","date","fwd"]]
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
idx=pd.DatetimeIndex(pd.to_datetime(spy.index)); idx=idx[(idx>="2015-01-02")&(idx<="2019-12-31")]
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
legacy=pd.read_parquet("/Users/renhao/git/github/RenQuant/data/sec_fundamentals_daily.parquet",
                       columns=["date","ticker","roe","gross_profitability","asset_growth"])
legacy["date"]=pd.to_datetime(legacy["date"])
legacy=legacy[(legacy["date"]>="2016-01-01")&(legacy["date"]<="2019-12-31")]
lab_rows=[]
for t in sorted(legacy["ticker"].unique()):
    p=pathlib.Path(f"/Users/renhao/git/github/RenQuant/data/ohlcv/{t}/1d.parquet")
    if not p.exists(): continue
    px=pd.read_parquet(p,columns=["close"])["close"]; px.index=pd.to_datetime(px.index)
    f=px.shift(-H)/px-1.0
    lab_rows.append(pd.DataFrame({"ticker":t,"date":f.index,"fwd":f.values}))
labels_leg=pd.concat(lab_rows,ignore_index=True)
comb=pd.concat([qual_r2k.merge(labels_r2k,on=["ticker","date"]),
                legacy.merge(labels_leg,on=["ticker","date"])],ignore_index=True)
comb=comb[(comb["date"]>="2016-01-01")&(comb["date"]<="2019-12-31")].dropna(subset=["fwd"])
comb=comb.sort_values(["ticker","date"])
for c in COLS: comb[c]=comb.groupby("ticker")[c].shift(1)
comb=comb.dropna(thresh=len(COLS)-1, subset=COLS).set_index(["date","ticker"])

preds=[]; ys=[]
for tr_end,oof_s,oof_e in FOLDS:
    tr=comb[comb.index.get_level_values(0)<=tr_end]
    te=comb[(comb.index.get_level_values(0)>=oof_s)&(comb.index.get_level_values(0)<=oof_e)]
    b=xgb.XGBRegressor(**XGBP)
    b.fit(tr[COLS],tr["fwd"])
    preds.append(pd.Series(b.predict(te[COLS]),index=te.index))
    ys.append(te["fwd"])
pred=pd.concat(preds); y=pd.concat(ys)
df=pd.DataFrame({"p":pred,"y":y}).dropna()
ics={}
for d,g in df.groupby(level=0):
    if len(g)>=30: ics[d]=spearmanr(g["p"],g["y"]).statistic
ic=pd.Series(ics).sort_index()
blocks=[]; i=0
while i<len(ic):
    chunk=ic.iloc[i:i+H]
    if len(chunk)>=10: blocks.append(chunk.mean())
    i+=40
blocks=np.array(blocks)
t=blocks.mean()/(blocks.std(ddof=1)/np.sqrt(len(blocks)))
rep={"estimand":"K5 per-fold XGB quality base, widened universe",
     "oof_days":len(ic),"median_names_per_day":int(df.groupby(level=0).size().median()),
     "oof_ic":round(float(ic.mean()),5),"n_blocks":len(blocks),
     "block_t":round(float(t),3),
     "by_year":{str(yy):round(float(g.mean()),5) for yy,g in ic.groupby(ic.index.year)},
     "k5_narrow_reference":{"oof_ic":0.0096,"block_t":0.73}}
json.dump(rep,open(SP/"g2v2_rescreen_quality_xgb_report.json","w"),indent=1)
print(json.dumps(rep,indent=1))
