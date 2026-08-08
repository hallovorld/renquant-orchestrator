import json, sqlite3, sys
sys.path.insert(0,"/Users/renhao/git/github/renquant-model/src")
import numpy as np, pandas as pd
from renquant_model_common.total_return import total_return_close

sec=json.load(open('/Users/renhao/git/github/renquant-strategy-104/configs/strategy_config.json'))['sector_map']
names=[t for t,s in sec.items() if s not in ('benchmark','defensive_bonds')]
rets={}
for t in names:
    try:
        df=pd.read_parquet(f'/Users/renhao/git/github/RenQuant/data/ohlcv/{t}/1d.parquet')
        tr=total_return_close(df['close'], df['dividend'])
        rets[t]=tr.pct_change()
    except Exception:
        pass
R=pd.DataFrame(rets).loc['2019-01-01':]
print(f'names loaded: {R.shape[1]}, days: {len(R)}, span {R.index[0].date()}..{R.index[-1].date()}')
sectors=sorted({sec[t] for t in R.columns})
S=pd.DataFrame({g: R[[t for t in R.columns if sec[t]==g]].mean(axis=1) for g in sectors}).dropna(how='all')
S=S[[g for g in S.columns if S[g].notna().mean()>0.9]]
uni=R.mean(axis=1)

def stats(ser, name, to_py=0.0, cost_bps=20):
    # to_py = one-way turnover per year, in units of full-book turns; 20 bps per full turn.
    ser=ser.dropna()
    ann=(1+ser).prod()**(252/len(ser))-1
    vol=ser.std()*np.sqrt(252)
    cum=(1+ser).cumprod(); dd=(cum/cum.cummax()-1).min()
    net=ann - to_py*cost_bps/1e4
    print(f'{name:44s} ann {ann*100:+7.1f}%  net {net*100:+7.1f}%  vol {vol*100:5.1f}%  sharpe {ann/vol:5.2f}  maxDD {dd*100:6.1f}%')
    return ser

for span,label in [('2024-01-01','2024-01..now'),('2019-01-01','2019-01..now')]:
    Ss=S.loc[span:]; unis=uni.loc[span:]
    print(f'\n== SECTOR ROTATION, {label} (signal: trailing 63d, rebalance daily, cost 20bps per full-book one-way turn)')
    stats(unis,'universe EW')
    stats(Ss.mean(axis=1),'equal-sector')
    for K in (1,2):
        sig=Ss.rolling(63).apply(lambda x:(1+x).prod()-1, raw=True).shift(1)
        top=sig.rank(axis=1, ascending=False)<=K
        strat=(Ss[top].mean(axis=1))
        # Cost from FULL-BASKET one-way turnover (entry/exit weights included), not
        # first-pick switches: W is the equal-weight top-K basket; second-slot
        # changes and partial membership changes are charged at their weight.
        W=top.div(top.sum(axis=1), axis=0).fillna(0.0)
        to=(W-W.shift(1, fill_value=0.0)).clip(lower=0).sum(axis=1)
        live=top.any(axis=1)
        to_py=to.sum()/(int(live.sum())/252)
        n_chg=int(((W!=W.shift(1)).any(axis=1)&live).sum())
        stats(strat,f'rotation top-{K} ({to_py:.0f} turns/yr, {n_chg} basket changes)', to_py=to_py)

print('\n== LIVE-CASH WINDOW: cash series + universe EW on exactly the snapshot dates')
conn=sqlite3.connect('file:/Users/renhao/git/github/RenQuant/data/runs.alpaca.db?mode=ro', uri=True)
snap=pd.read_sql('SELECT run_date, cash, portfolio_value FROM live_state_snapshots ORDER BY run_date, portfolio_value', conn)
snap['run_date']=pd.to_datetime(snap['run_date'])
best=snap.groupby('run_date').last().tail(63)   # best row per date = max portfolio_value, last 63 snapshot dates
frac=best['cash']/best['portfolio_value']
print(f'cash: {len(best)} dates {best.index[0].date()}..{best.index[-1].date()}  '
      f'mean {frac.mean()*100:.1f}%  median {frac.median()*100:.1f}%  min {frac.min()*100:.1f}%  '
      f'max {frac.max()*100:.1f}%  book ${best["portfolio_value"].iloc[-1]:,.0f}')
stats(uni.reindex(best.index).dropna(),'universe EW, cash dates only')
print('\n== POCKET-STYLE HYPOTHESES, 2024-01..now (within-pocket, daily rebalance, vs own pocket EW)')
for g,style in [('giant_tech','REVERSAL'),('ai_chip','REVERSAL'),('giant_tech','MOMENTUM'),('ai_chip','MOMENTUM')]:
    cols=[t for t in R.columns if sec[t]==g]
    sub=R[cols].loc['2024-01-01':]
    trail=sub.rolling(21).apply(lambda x:(1+x).prod()-1, raw=True).shift(1)
    pick = trail.rank(axis=1, ascending=(style=='REVERSAL'))<=3
    strat=sub[pick].mean(axis=1)
    ew=sub.mean(axis=1)
    sp=(strat-ew).dropna()
    ann_s=(1+strat.dropna()).prod()**(252/len(strat.dropna()))-1
    ann_e=(1+ew).prod()**(252/len(ew))-1
    ne=len(sp)/21
    t=sp.mean()/(sp.std(ddof=1)/np.sqrt(ne))
    print(f'{g:12s} {style:9s} bottom/top-3: ann {ann_s*100:+7.1f}%  vs EW {ann_e*100:+7.1f}%  spread t(adj) {t:+.2f}')
