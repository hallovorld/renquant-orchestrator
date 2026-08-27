"""Attempt 3: regime-conditioned IC of the wide quality base (K5 approx-regime)."""
import json, pathlib, numpy as np, pandas as pd
from scipy.stats import spearmanr
import xgboost as xgb
SP=pathlib.Path(__file__).parent
exec(open(SP/"g2v2_rescreen_quality_xgb.py").read().split("preds=[]; ys=[]")[0])  # reuse panel build
preds=[]; ys=[]
for tr_end,oof_s,oof_e in FOLDS:
    tr=comb[comb.index.get_level_values(0)<=tr_end]
    te=comb[(comb.index.get_level_values(0)>=oof_s)&(comb.index.get_level_values(0)<=oof_e)]
    b=xgb.XGBRegressor(**XGBP)
    b.fit(tr[COLS],tr["fwd"])
    preds.append(pd.Series(b.predict(te[COLS]),index=te.index))
    ys.append(te["fwd"])
pred=pd.concat(preds); yy=pd.concat(ys)
df=pd.DataFrame({"p":pred,"y":yy}).dropna()
# approx regime from SPY: 200d trend x 20d vol median split (K5 convention)
spx=pd.read_parquet("/Users/renhao/git/github/RenQuant/data/ohlcv/SPY/1d.parquet",columns=["close"])["close"]
spx.index=pd.to_datetime(spx.index)
trend=spx>spx.rolling(200).mean()
vol=spx.pct_change().rolling(20).std()
volhi=vol>vol.rolling(252,min_periods=60).median()
regime=pd.Series("BEAR",index=spx.index)
regime[trend&~volhi]="BULL_CALM"; regime[trend&volhi]="BULL_VOLATILE"; regime[~trend&~volhi]="CHOPPY"
ics={}
for d,g in df.groupby(level=0):
    if len(g)>=30: ics[d]=spearmanr(g["p"],g["y"]).statistic
ic=pd.Series(ics).sort_index()
out={"overall_ic":round(float(ic.mean()),5),"n_days":len(ic),"by_regime":{}}
r=regime.reindex(ic.index)
for name,g in ic.groupby(r):
    blocks=[]; i=0
    while i<len(g):
        ch=g.iloc[i:i+20]
        if len(ch)>=8: blocks.append(ch.mean())
        i+=40
    blocks=np.array(blocks)
    t=blocks.mean()/(blocks.std(ddof=1)/np.sqrt(len(blocks))) if len(blocks)>1 else float("nan")
    out["by_regime"][name]={"ic":round(float(g.mean()),5),"n_days":int(len(g)),
                            "n_blocks":len(blocks),"block_t":round(float(t),3)}
json.dump(out,open(SP/"g2v2_rescreen_regime_report.json","w"),indent=1)
print(json.dumps(out,indent=1))
