"""Dependence calibration r2 -- PERSISTENT selections (review P1, corrected).

The estimand's top-5 is sticky across days (model scores persist), so the
daily statistic inherits the 5d label overlap. Calibrate with picks HELD
for H sessions (H=5 weekly-refresh, H=21 sticky), 400 seeded draws each,
pre-2026 only. Report ACF(1..10), Newey-West kappa (Bartlett L=10),
N_eff and MDE at N=1357 and the power floor at 700.
"""
import numpy as np, pandas as pd, math
rng=np.random.default_rng(20260810)
c=pd.read_parquet('/Users/renhao/git/github/RenQuant/data/alpha158_291_fundamental_dataset.parquet',columns=['date','ticker','fwd_5d_excess'])
c['date']=pd.to_datetime(c['date'])
pre=c[(c.date>='2023-01-01')&(c.date<='2025-12-31')].dropna()
days=sorted(pre.date.unique())
byday={d:g.set_index('ticker').fwd_5d_excess for d,g in pre.groupby('date')}
z=1.959964+0.841621
for H in (5,21):
    acfs=np.zeros(10); sigs=[]
    for _ in range(400):
        picks=None; xs=[]
        for i,d in enumerate(days):
            s=byday[d]
            if i%H==0 or picks is None:
                if len(s)<5: continue
                picks=rng.choice(s.index.values,5,replace=False)
            v=s.reindex(picks).dropna()
            if len(v)>=3: xs.append(v.mean())
        x=np.array(xs); x=x-x.mean(); var=np.mean(x*x); sigs.append(math.sqrt(var))
        for k in range(1,11): acfs[k-1]+=np.mean(x[:-k]*x[k:])/var
    acfs/=400; sig=float(np.mean(sigs))
    w=np.array([1-k/11 for k in range(1,11)])
    kappa=max(1.0, 1+2*float(np.sum(w*acfs)))
    print(f'H={H:2d}: sigma {sig:.4f} | ACF1-5 {np.round(acfs[:5],3).tolist()} | kappa {kappa:.3f} | '
          f'MDE@1357 {z*sig/math.sqrt(1357/kappa):.4f} | MDE@700 {z*sig/math.sqrt(700/kappa):.4f}')
