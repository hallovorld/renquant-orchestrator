"""Selection-level power inputs for the qp prereg revision (orch#954 fork a).

Pre-2026 ONLY (2023-01-01..2025-12-31). Two quantities:
1. z->raw mapping: per-day cross-sectional std of RAW 5d excess return
   (reconstructed from OHLCV, ticker close vs SPY, 5-session horizon on
   each ticker's own calendar) -- median across days. A selection alpha of
   m sigma/day converts to m * this * (252/5) annualized (approx).
2. sigma of the daily statistic "mean label-z of k random picks" for
   k in (5, 10, 20): empirical, 400 seeded draws over corpus z-labels.
Then MDE tables at 80%/alpha=0.05 for N in (63, 126, 252) days.
Read-only.
"""
import numpy as np, pandas as pd
rng=np.random.default_rng(20260810)
corpus=pd.read_parquet('/Users/renhao/git/github/RenQuant/data/alpha158_291_fundamental_dataset.parquet',columns=['date','ticker','fwd_5d_excess'])
corpus['date']=pd.to_datetime(corpus['date'])
pre=corpus[(corpus.date>='2023-01-01')&(corpus.date<='2025-12-31')].dropna()
# 2. sigma of daily mean-z of k random picks
days=sorted(pre.date.unique()); byday={d:g.fwd_5d_excess.values for d,g in pre.groupby('date')}
for k in (5,10,20):
    stats=[]
    for _ in range(400):
        vals=[np.mean(rng.choice(byday[d],k,replace=False)) for d in days if len(byday[d])>=k]
        stats.append(np.std(vals))
    sig=float(np.mean(stats))
    z=1.959964+0.841621
    row=f'k={k:2d}: sigma_stat {sig:.4f}sigma/day | MDE(sigma/day):'
    for N in (63,126,252):
        row+=f'  {z*sig/np.sqrt(N):.4f}@{N}d'
    print(row)
# 1. raw dispersion for the z->raw mapping
import glob,os
ROOT='/Users/renhao/git/github/RenQuant/data/ohlcv'
tick=sorted(set(pre.ticker.unique()))
raw={}
spy=pd.read_parquet(f'{ROOT}/SPY/1d.parquet')['close']; spy.index=pd.to_datetime(spy.index); spy=spy.sort_index()
spy5=spy.shift(-5)/spy-1
disp=[]
sub=rng.choice(tick,80,replace=False)  # 80-name sample is enough for a median dispersion
frames=[]
for t in sub:
    try:
        c=pd.read_parquet(f'{ROOT}/{t}/1d.parquet')['close']; c.index=pd.to_datetime(c.index); c=c.sort_index()
        f5=(c.shift(-5)/c-1)-spy5.reindex(c.index,method='ffill')
        frames.append(f5.loc['2023-01-01':'2025-12-31'].rename(t))
    except Exception: pass
M=pd.concat(frames,axis=1)
per_day_std=M.std(axis=1).dropna()
print(f'raw 5d excess per-day cross-sectional std: median {per_day_std.median():.4f} (p25 {per_day_std.quantile(.25):.4f}, p75 {per_day_std.quantile(.75):.4f}) over {len(per_day_std)} days, 80-name sample')
print(f'=> 0.10 sigma/day selection alpha ~= {0.10*per_day_std.median()*252/5*100:.1f} %/yr (median-day mapping, approx)')
