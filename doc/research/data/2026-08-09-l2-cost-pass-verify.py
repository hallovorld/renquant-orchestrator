"""Verifier: recompute every cost-pass statistic from the committed CSV alone,
including the hedge recursion over the NET arm returns."""
from pathlib import Path
import numpy as np, pandas as pd
ETA, C, FLOOR = 0.21, 0.05, 0.5
df = pd.read_csv(Path(__file__).with_name('2026-08-09-l2-cost-pass-daily.csv'),
                 index_col=0, parse_dates=True)
arms = ['panel', 'mom_slow', 'mom_fast']

# r1 P1: the cost identities are ASSERTED from the committed columns before
# any statistic is trusted: net == gross - cost and cost == churn/3 * 2 * 10bps.
for a in arms:
    cost_expected = df[a + '_churn'] / 3 * 2 * 0.0010
    assert np.allclose(df[a + '_cost'], cost_expected, atol=1e-12), f'{a}: cost != churn/3*2*10bps'
    assert np.allclose(df[a + '_net'], df[a + '_gross'] - df[a + '_cost'], atol=1e-12), f'{a}: net != gross - cost'
print('cost identities verified: net == gross - cost, cost == churn/3*2*0.001 (all arms, all days)')
def stats(s, name):
    a=(1+s).prod()**(252/len(s))-1; vol=s.std()*np.sqrt(252)
    cum=(1+s).cumprod(); dd=(cum/cum.cummax()-1).min()
    print(f'{name:24s} ann {a*100:+7.1f}%  sharpe {a/vol:5.2f}  maxDD {dd*100:6.1f}%')
print(f'days={len(df)}; mean churn: ' + ', '.join(
    f'{a}={df[a+"_churn"].mean():.2f}' for a in arms))
print('drag pp/yr: ' + ', '.join(
    f'{a}={df[a+"_churn"].mean()*2/3*0.0010*252*100:.1f}' for a in arms))
for a in arms: stats(df[a+'_net'], a+'_net')
stats(df['hedge_net'], 'hedge_net (committed)')
stats(df[[a+'_net' for a in arms]].mean(axis=1), 'uniform net')
w = np.array([FLOOR, 0.25, 0.25]); err = 0.0
for _, row in df.iterrows():
    r = row[[a+'_net' for a in arms]].to_numpy(dtype=float)
    err = max(err, abs(float(w@r) - float(row['hedge_net'])))
    w = w*np.exp(ETA*np.clip(r, -C, C)); w = w/w.sum()
    if w[0] < FLOOR: w[1:] *= (1-FLOOR)/(1-w[0]); w[0] = FLOOR
print(f'recursion max err {err:.2e}')
