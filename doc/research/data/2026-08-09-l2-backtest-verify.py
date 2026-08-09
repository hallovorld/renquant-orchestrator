"""Verifier: recompute every reported L2 statistic from the committed CSV
alone, INCLUDING re-running the Hedge recursion from the arm columns and
checking the committed weight path. No OHLCV, no scratch, no DB."""
from pathlib import Path
import numpy as np, pandas as pd

ETA, C, FLOOR = 0.21, 0.05, 0.5
df = pd.read_csv(Path(__file__).with_name('2026-08-09-l2-backtest-daily.csv'),
                 index_col=0, parse_dates=True)
arms = ['panel', 'mom_slow', 'mom_fast']

def stats(s, name):
    a = (1 + s).prod() ** (252 / len(s)) - 1
    vol = s.std() * np.sqrt(252)
    cum = (1 + s).cumprod(); dd = (cum / cum.cummax() - 1).min()
    print(f'{name:26s} ann {a*100:+7.1f}%  vol {vol*100:5.1f}%  '
          f'sharpe {a/vol:5.2f}  maxDD {dd*100:6.1f}%')

print(f'days={len(df)} span {df.index[0].date()}..{df.index[-1].date()}')
for a in arms: stats(df[a], a)
stats(df['hedge_book'], 'hedge_book (committed)')
stats(df[arms].mean(axis=1), 'uniform 1/3')

# re-run the recursion and check the committed weight path + book
w = np.array([FLOOR, (1-FLOOR)/2, (1-FLOOR)/2])
max_w_err, max_b_err = 0.0, 0.0
for _, row in df.iterrows():
    r = row[arms].to_numpy(dtype=float)
    max_w_err = max(max_w_err, float(np.abs(
        w - row[[f'w_{a}' for a in arms]].to_numpy(dtype=float)).max()))
    max_b_err = max(max_b_err, abs(float(w @ r) - float(row['hedge_book'])))
    w = w * np.exp(ETA * np.clip(r, -C, C)); w = w / w.sum()
    if w[0] < FLOOR:
        w[1:] *= (1 - FLOOR) / (1 - w[0]); w[0] = FLOOR
clipped = df[arms].clip(-C, C)
wpath = df[[f'w_{a}' for a in arms]].to_numpy(dtype=float)
hedge_cum = float((wpath * clipped.to_numpy()).sum())
cum = clipped.sum()
# r1 P0: the theorem's benchmark is the best comparator IN K (w_panel >= 0.5);
# no bound exists vs the unconstrained best arm (counterexample in the doc).
best_in_K = max(cum['panel'],
                FLOOR * cum['panel'] + (1 - FLOOR) * max(cum['mom_slow'], cum['mom_fast']))
T = len(df)
bound_K = np.log(2)/ETA + ETA*T*(2*C)**2/8
print(f'recursion check: max weight err {max_w_err:.2e}, max book err {max_b_err:.2e}')
print(f'regret vs best-in-K (valid benchmark) {best_in_K - hedge_cum:.4f}  vs bound {bound_K:.4f}  (T={T})')
print(f'regret vs best unconstrained arm (DESCRIPTIVE, no theorem) {cum.max() - hedge_cum:.4f}')
