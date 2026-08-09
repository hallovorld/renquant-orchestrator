"""Verifier: recompute the L2-S backtest from the COMMITTED artifacts alone.
Re-runs every Hedge recursion (global floored, local unfloored) and the
mixture arithmetic from the daily CSV's book columns; re-derives every
book's cost from the committed holdings paths (10bps x names-only |dh|,
no half); recomputes all four legs and the verdict. Exits 1 on any drift."""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd

HERE = Path(__file__).parent
ETA, C, FLOOR, COST1W = 0.21, 0.05, 0.5, 0.0010
ELIGIBLE = {'software': (26, 3, 0.50), 'industrial': (21, 3, 0.50),
            'finance': (20, 3, 0.50), 'ai_chip': (19, 2, 0.67),
            'consumer': (16, 2, 0.67), 'datacenter_hw': (14, 2, 0.67)}
TOTAL, ARM_ORDER = 159, ['panel', 'mom_slow', 'mom_fast']
S = json.load(open(HERE / '2026-08-09-l2s-summary.json'))
D = pd.read_csv(HERE / '2026-08-09-l2s-daily.csv', index_col='date')
H = pd.read_csv(HERE / '2026-08-09-l2s-holdings.csv')
P = pd.read_csv(HERE / '2026-08-09-l2s-placebo.csv')['placebo_delta_sharpe']
bad = []

# 1 cost re-derivation from holdings paths, every book
for (lab, arm), g in H.groupby(['sector', 'arm']):
    by_date = {d: dict(zip(gg['ticker'], gg['weight'])) for d, gg in g.groupby('date')}
    h_prev, cost = {}, {}
    for d in D.index:
        h = by_date.get(d, {})
        names = set(h_prev) | set(h)
        cost[d] = COST1W * sum(abs(h.get(t, 0) - h_prev.get(t, 0)) for t in names)
        h_prev = h
    col = f'{lab}__{arm}_cost'
    if col in D.columns and not np.allclose(D[col], pd.Series(cost), atol=1e-9):
        bad.append(f'cost {lab}/{arm}')

# 2 recursions + mixture from book columns
g_arms = D[[f'globalarm_{a}_net' for a in ARM_ORDER]].values
wg = np.array([0.5, 0.25, 0.25]); local = {s: np.array([0.5, 0.25, 0.25]) for s in ELIGIBLE}
cap = {s: n / TOTAL for s, (n, _, _) in ELIGIBLE.items()}; cap_g = 1 - sum(cap.values())
comp, gonly, plocal = [], [], []
for i, d in enumerate(D.index):
    rg = g_arms[i]
    gonly.append(float(wg @ rg)); day = cap_g * float(wg @ rg); day_pl = cap_g * float(wg @ rg)
    for s in ELIGIBLE:
        m = ELIGIBLE[s][2]
        rs = np.array([D.at[d, f'{s}__{a}_net'] for a in ARM_ORDER])
        ws = (1 - m) * local[s] + m * wg
        if not np.allclose(ws, [D.at[d, f'wmix_{s}_{a}'] for a in ARM_ORDER], atol=1e-9):
            bad.append(f'wmix {s}@{d}'); break
        day += cap[s] * float(ws @ rs); day_pl += cap[s] * float(local[s] @ rs)
        w2 = local[s] * np.exp(ETA * np.clip(rs, -C, C)); local[s] = w2 / w2.sum()
    w2 = wg * np.exp(ETA * np.clip(rg, -C, C)); w2 = w2 / w2.sum()
    if w2[0] < FLOOR: w2[1:] *= (1 - FLOOR) / (1 - w2[0]); w2[0] = FLOOR
    wg = w2; comp.append(day); plocal.append(day_pl)
for name, mine, col in (('composite', comp, 'composite_net'),
                        ('global', gonly, 'global_only_net'),
                        ('pure_local', plocal, 'pure_local_net')):
    if not np.allclose(mine, D[col], atol=1e-9): bad.append(f'series {name}')

# 3 stats + legs + verdict
def sharpe(x):
    x = pd.Series(x); a = (1 + x).prod() ** (252 / len(x)) - 1
    v = x.std() * np.sqrt(252); return a / v if v > 0 else 0.0
def maxdd(x):
    c = (1 + pd.Series(x)).cumprod(); return float((c / c.cummax() - 1).min())
sc, sg = sharpe(comp), sharpe(gonly)
if abs(sc - S['composite']['sharpe']) > 1e-9: bad.append('sharpe comp')
if abs(sg - S['global_only']['sharpe']) > 1e-9: bad.append('sharpe glob')
p95 = float(np.quantile(P, 0.95))
if abs(p95 - S['placebo_p95']) > 1e-12: bad.append('p95')
legs = {'leg_sharpe_floor': sc >= sg - 0.05,
        'leg_maxdd': maxdd(comp) <= maxdd(gonly) + 0.05,
        'leg_sector_tilt': any(max(D[f'wlocal_{s}_{a}'].iloc[-1] for a in ARM_ORDER[1:]) >= 0.40 for s in ELIGIBLE),
        'leg_placebo': (sc - sg) > p95}
for k, v in legs.items():
    if bool(v) != S[k]: bad.append(k)
verdict = 'ADOPT-for-shadow' if all(legs.values()) else 'RECORD-ONLY'
if verdict != S['verdict']: bad.append('verdict')
if bad: print('DRIFT:', bad); sys.exit(1)
print(f'VERIFIED — recursions, mixtures, holdings-derived costs, legs and '
      f'verdict all reproduce: {verdict} (comp {sc:.3f} vs glob {sg:.3f}, '
      f'delta {sc-sg:.3f} vs p95 {p95:.3f})')
