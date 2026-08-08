"""Cube v1: sector x regime x style-proxy, daily return space. DESCRIPTIVE ONLY.
Style proxies are trailing-price constructions, NOT the registry experts —
labelled *_proxy to keep the registry honest. Regime = production HMM argmax.

Inputs (re-runnable): regime posteriors are the committed snapshot
`2026-08-08-regime-posteriors.csv` next to this script (production HMM
posteriors, 2016-11-02..2026-05-05, written %.17g / read round_trip so the
float64 values are bit-exact); OHLCV + sector_map are read-only from the
machine-local production stores. Output: `2026-08-08-cube-v1.csv` alongside."""
import json, sys
from pathlib import Path
sys.path.insert(0,"/Users/renhao/git/github/renquant-model/src")
import numpy as np, pandas as pd
from renquant_model_common.total_return import total_return_close
HERE=Path(__file__).resolve().parent
sec=json.load(open('/Users/renhao/git/github/renquant-strategy-104/configs/strategy_config.json'))['sector_map']
names=[t for t,s in sec.items() if s not in ('benchmark','defensive_bonds')]
rets={}
for t in names:
    try:
        df=pd.read_parquet(f'/Users/renhao/git/github/RenQuant/data/ohlcv/{t}/1d.parquet')
        div=df['dividend'] if 'dividend' in df.columns else pd.Series(0.0,index=df.index)
        rets[t]=total_return_close(df['close'],div).pct_change()
    except FileNotFoundError: pass
R=pd.DataFrame(rets).loc['2017-01-01':]
reg=pd.read_csv(HERE/'2026-08-08-regime-posteriors.csv',index_col='date',float_precision='round_trip')
lab=reg[['regime_p_bull_calm','regime_p_bear','regime_p_bull_volatile']].idxmax(axis=1).str.replace('regime_p_','')
lab.index=pd.to_datetime(lab.index)
common=R.index.intersection(lab.index)
R=R.loc[common]; lab=lab.loc[common]
print(f'{len(common)} joint days {common.min().date()}..{common.max().date()}, names {R.shape[1]}')
def trail(sub,w): return sub.rolling(w).apply(lambda x:(1+x).prod()-1,raw=True).shift(1)
STYLES={'mom63_proxy':('mom',63),'mom252_proxy':('mom',252),'rev21_proxy':('rev',21),'lowvol63_proxy':('lv',63)}
rows=[]
for g in sorted({sec[t] for t in R.columns}):
    cols=[t for t in R.columns if sec[t]==g]
    if len(cols)<6: continue
    sub=R[cols]
    ew=sub.mean(axis=1)
    for sid,(kind,w) in STYLES.items():
        if kind=='mom': sig=trail(sub,w)
        elif kind=='rev': sig=-trail(sub,w)
        else: sig=-sub.rolling(w).std().shift(1)
        pick=sig.rank(axis=1,ascending=False)<=3
        strat=sub[pick].mean(axis=1)
        sp=(strat-ew).dropna()
        for rg in ('bull_calm','bull_volatile','bear'):
            m=sp[lab.reindex(sp.index)==rg]
            if len(m)<40: rows.append((g,rg,sid,len(m),np.nan,np.nan)); continue
            ne=len(m)/21
            t=m.mean()/(m.std(ddof=1)/np.sqrt(ne))
            rows.append((g,rg,sid,len(m),m.mean()*252*100,t))
df=pd.DataFrame(rows,columns=['sector','regime','style','n_days','ann_spread_pct','adj_t'])
df.to_csv(HERE/'2026-08-08-cube-v1.csv',index=False)
sig=df[df['adj_t'].abs()>=2.0]
print(f'cells: {len(df)}  with n>=40: {df["adj_t"].notna().sum()}  |adj_t|>=2.0: {len(sig)}')
print(sig.to_string(index=False) if len(sig) else '(no cell clears |t|>=2)')
print('\ntop |t| cells (descriptive only):')
print(df.dropna().reindex(df.dropna()['adj_t'].abs().sort_values(ascending=False).index).head(8).to_string(index=False))
