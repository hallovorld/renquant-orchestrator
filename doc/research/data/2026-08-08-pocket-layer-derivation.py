"""Pocket-layer return-space derivation — PROVENANCE ONLY (machine-local OHLCV).

r2 fixes (codex on orch#914):
1. The cash-drag benchmark is computed ON THE CASH WINDOW's own dates; the
   2024..now stats are labelled long-run proxy.
2. Rotation turnover counts FULL-BASKET membership changes (name-level entries
   and exits), not just the first pick: cost/yr = basket-change-equivalents
   x 20 bps, where one equivalent = a full K-name replacement.

r3 fix (codex MED on orch#914 head 6ea3bc2): the live cash statistics are
MEASURED here from live_state_snapshots (read-only), on exactly the benchmark
window's own trading dates — no longer hardcoded constants.
"""
import json, sqlite3, sys
sys.path.insert(0, "/Users/renhao/git/github/renquant-model/src")
import numpy as np, pandas as pd
from renquant_model_common.total_return import total_return_close

sec = json.load(open('/Users/renhao/git/github/renquant-strategy-104/configs/strategy_config.json'))['sector_map']
names = [t for t, s in sec.items() if s not in ('benchmark', 'defensive_bonds')]
rets = {}
for t in names:
    try:
        df = pd.read_parquet(f'/Users/renhao/git/github/RenQuant/data/ohlcv/{t}/1d.parquet')
        div = df['dividend'] if 'dividend' in df.columns else pd.Series(0.0, index=df.index)
        rets[t] = total_return_close(df['close'], div).pct_change()
    except FileNotFoundError:
        pass
R = pd.DataFrame(rets).loc['2019-01-01':]
print(f'names {R.shape[1]}, days {len(R)}, span {R.index[0].date()}..{R.index[-1].date()}')
sectors = sorted({sec[t] for t in R.columns})
S = pd.DataFrame({g: R[[t for t in R.columns if sec[t] == g]].mean(axis=1) for g in sectors})
S = S[[g for g in S.columns if S[g].notna().mean() > 0.9]]
uni = R.mean(axis=1)

def stats(ser, name, cost_py=0.0):
    ser = ser.dropna()
    ann = (1 + ser).prod() ** (252 / len(ser)) - 1
    vol = ser.std() * np.sqrt(252)
    cum = (1 + ser).cumprod()
    dd = (cum / cum.cummax() - 1).min()
    print(f'{name:36s} ann {ann*100:+7.1f}%  net {(ann-cost_py)*100:+7.1f}%  '
          f'vol {vol*100:5.1f}%  sharpe {ann/vol:5.2f}  maxDD {dd*100:6.1f}%')
    return ann

for span, label in [('2024-01-01', 'LONG-RUN PROXY 2024-01..now'), ('2019-01-01', 'LONG-RUN PROXY 2019-01..now')]:
    Ss, unis = S.loc[span:], uni.loc[span:]
    print(f'\n== SECTOR ROTATION, {label} (63d signal, daily rebalance, 20bps per full-basket switch)')
    stats(unis, 'universe EW')
    stats(Ss.mean(axis=1), 'equal-sector')
    sig = Ss.rolling(63).apply(lambda x: (1 + x).prod() - 1, raw=True).shift(1)
    for K in (1, 2):
        top = sig.rank(axis=1, ascending=False) <= K
        strat = Ss[top].mean(axis=1)
        # r2 fix: full-basket turnover — name-level membership changes, both slots
        prev = top.shift(1).fillna(False)
        changes = (top ^ prev).sum(axis=1) / 2          # pairs (one exit + one entry)
        eq_switch = changes.sum() / K                    # full-K-basket replacement units
        years = len(strat.dropna()) / 252
        cost_py = (eq_switch / years) * 20 / 1e4
        stats(strat, f'rotation top-{K} ({eq_switch/years:.0f} basket-eq/yr)', cost_py=cost_py)

# --- cash-drag benchmark ON THE CASH WINDOW ITSELF (r2 fix 1) -----------------
CASH_START, CASH_END = '2026-05-11', '2026-08-07'   # the live_state_snapshots window
w = uni.loc[CASH_START:CASH_END].dropna()
ann_w = (1 + w).prod() ** (252 / len(w)) - 1
cum = (1 + w).cumprod()
print(f'\n== CASH-WINDOW BENCHMARK {CASH_START}..{CASH_END}: {len(w)} days')
print(f'universe EW: ann {ann_w*100:+.1f}%  sharpe {ann_w/(w.std()*np.sqrt(252)):.2f}  '
      f'maxDD {(cum/cum.cummax()-1).min()*100:.2f}%  window return {(cum.iloc[-1]-1)*100:+.2f}%')
# r3 fix: cash stats measured from the snapshots DB (read-only), best row per
# run_date = max portfolio_value (ties -> the day's latest snapshot),
# restricted to the benchmark's own dates.
con = sqlite3.connect('file:/Users/renhao/git/github/RenQuant/data/runs.alpaca.db?mode=ro', uri=True)
snap = pd.read_sql_query(
    "SELECT run_date, cash, portfolio_value FROM live_state_snapshots s "
    "WHERE portfolio_value = (SELECT MAX(portfolio_value) "
    "FROM live_state_snapshots s2 WHERE s2.run_date = s.run_date) "
    "ORDER BY run_date, created_at",
    con, parse_dates=['run_date']).set_index('run_date')
snap = snap[~snap.index.duplicated(keep='last')]
snap = snap[snap.index.isin(w.index)]
cash_pct = snap['cash'] / snap['portfolio_value']
MEAN_CASH, BOOK = cash_pct.mean(), snap['portfolio_value'].iloc[-1]
print(f'live book ({len(snap)} snapshot days on the benchmark dates '
      f'{snap.index[0].date()}..{snap.index[-1].date()}): mean cash {MEAN_CASH*100:.1f}%  '
      f'median {cash_pct.median()*100:.1f}%  max {cash_pct.max()*100:.1f}%  book ${BOOK:,.2f}')
print(f'same-window drag: mean cash {MEAN_CASH*100:.1f}% x window return '
      f'-> ${MEAN_CASH*BOOK*(cum.iloc[-1]-1):,.0f} missed over the window; '
      f'annualized at the window rate: ${MEAN_CASH*BOOK*ann_w:,.0f}/yr')

print('\n== POCKET-STYLE, 2024-01..now (top/bottom-3 vs own pocket EW, daily rebalance)')
for g, style in [('giant_tech', 'REVERSAL'), ('ai_chip', 'REVERSAL'),
                 ('giant_tech', 'MOMENTUM'), ('ai_chip', 'MOMENTUM')]:
    cols = [t for t in R.columns if sec[t] == g]
    sub = R[cols].loc['2024-01-01':]
    trail = sub.rolling(21).apply(lambda x: (1 + x).prod() - 1, raw=True).shift(1)
    pick = trail.rank(axis=1, ascending=(style == 'REVERSAL')) <= 3
    strat, ew = sub[pick].mean(axis=1), sub.mean(axis=1)
    sp = (strat - ew).dropna()
    ann_s = (1 + strat.dropna()).prod() ** (252 / len(strat.dropna())) - 1
    ann_e = (1 + ew).prod() ** (252 / len(ew)) - 1
    t = sp.mean() / (sp.std(ddof=1) / np.sqrt(len(sp) / 21))
    print(f'{g:12s} {style:9s}: ann {ann_s*100:+7.1f}%  vs EW {ann_e*100:+7.1f}%  spread t(adj) {t:+.2f}')
