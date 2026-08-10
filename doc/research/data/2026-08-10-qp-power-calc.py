"""Power computation for the qp re-enable prereg s5 (issue orch#954).

Variance of a held-5-name equal-weight book's daily excess return vs SPY,
estimated on PRE-2026 data ONLY (2023-01-01..2025-12-31, no peeking at
any candidate confirmatory window). Random books, 5-session holds, 400
seeded draws. MDE at 80% power, alpha=0.05 two-sided, with effective
sample size deflated by the measured lag-1 autocorrelation
(N_eff = N * (1-rho1)/(1+rho1), the AR(1) approximation).
Read-only; prints the s5 table.
"""
import numpy as np, pandas as pd, glob, os
ROOT='/Users/renhao/git/github/RenQuant/data/ohlcv'
rng=np.random.default_rng(20260810)
spy=pd.read_parquet(f'{ROOT}/SPY/1d.parquet')['close']
spy.index=pd.to_datetime(spy.index)
spy=spy.sort_index().loc['2023-01-01':'2025-12-31']
spy_ret=spy.pct_change()
corpus=pd.read_parquet('/Users/renhao/git/github/RenQuant/data/alpha158_291_fundamental_dataset.parquet',columns=['ticker'])
tickers=sorted(set(corpus.ticker.unique()))  # the corpus universe, not the whole ohlcv dir
tickers=[t for t in tickers if t!='SPY']
rets={}
for t in tickers:
    try:
        c=pd.read_parquet(f'{ROOT}/{t}/1d.parquet')['close']
        c.index=pd.to_datetime(c.index)
        c=c.sort_index().loc['2023-01-01':'2025-12-31']
        if len(c)>700: rets[t]=c.pct_change()
    except Exception: pass
R=pd.DataFrame(rets).reindex(spy_ret.index)
print(f'universe {R.shape[1]} names x {R.shape[0]} days (2023-2025)')
days=R.index
series=[]
for draw in range(400):
    picks=None; out=[]; kept=[]
    for i,d in enumerate(days):
        if i%5==0 or picks is None:
            avail=R.loc[d].dropna().index
            if len(avail)<5: continue
            picks=rng.choice(avail,5,replace=False)
        out.append(R.loc[d,picks].mean()-spy_ret.loc[d]); kept.append(d)
    series.append(pd.Series(out,index=kept).dropna())
allx=pd.concat(series)
sigma_d=float(allx.std())
rho1=float(np.mean([s.autocorr(1) for s in series]))
infl=(1+rho1)/(1-rho1)
z=1.959964+0.841621
print(f'sigma_d {sigma_d:.5f}/day | rho1 {rho1:+.4f} | N_eff inflation {infl:.3f}')
for N in (63,126,252):
    neff=N/infl
    mde_d=z*sigma_d/np.sqrt(neff)
    print(f'N={N:3d}d: MDE {mde_d*1e4:6.1f} bps/day = {mde_d*252*100:6.1f} %/yr annualized')
