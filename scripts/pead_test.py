"""PEAD / earnings-surprise drift as a cross-sectional signal on the renquant-104 universe.

LEAN: one script. SUE/surprise cross-sectional rank-IC vs fwd 20/60d + within-date
shuffle placebo floor, plus a classic post-announcement-drift quintile event study.
READ-ONLY. Output to /tmp/pead/. No orders, no git, no canonical writes.
"""
import sys
import numpy as np
import pandas as pd

EARN = '/Users/renhao/git/github/RenQuant/data/fmp_harvest/earnings_291.parquet'
BARS = '/tmp/sighunt/bars.parquet'
OUT = '/tmp/pead/'
RNG = np.random.default_rng(20260627)

FWD = [20, 60]
TRAIL = 63          # signal validity window after an earnings date (~1 quarter)
LAG = 1             # enter signal first trading day AFTER earnings date
COST_BPS = 11.0     # round-trip-ish L/S cost assumption from mandate
N_SHUFFLE = 200

# ---------------------------------------------------------------- load
bars = pd.read_parquet(BARS)
bars.index = pd.to_datetime(bars.index)
bars = bars.sort_index()
uni = list(bars.columns)
trading_days = bars.index

e = pd.read_parquet(EARN)
e['date'] = pd.to_datetime(e['date'])
e = e[e['symbol'].isin(uni)].copy()
e = e.dropna(subset=['epsActual', 'epsEstimated'])
e = e[(e['date'] >= bars.index.min()) & (e['date'] <= bars.index.max())]
e = e.sort_values(['symbol', 'date']).reset_index(drop=True)

# ---------------------------------------------------------------- eps cleanliness check
exact_eq = (e['epsActual'] == e['epsEstimated']).mean()
# zero-estimate (would blow up % surprise)
zero_est = (e['epsEstimated'].abs() < 1e-9).mean()
print(f"[cleanliness] n events on universe in window = {len(e)}  tickers = {e['symbol'].nunique()}")
print(f"[cleanliness] frac epsActual==epsEstimated EXACTLY = {exact_eq:.4f}")
print(f"[cleanliness] frac |epsEstimated|~0 = {zero_est:.4f}")
surp = e['epsActual'] - e['epsEstimated']
print(f"[cleanliness] raw surprise mean={surp.mean():.4f} median={surp.median():.4f} std={surp.std():.4f}")

# ---------------------------------------------------------------- surprise measures
# rolling per-ticker std of PAST surprises -> SUE (drift-style standardization, PIT)
e['surp'] = e['epsActual'] - e['epsEstimated']
# % surprise
denom = e['epsEstimated'].abs().replace(0, np.nan)
e['pct_surp'] = e['surp'] / denom
# SUE = surp / rolling std of past (shifted) surprises, min 4 priors
def roll_sue(g):
    s = g['surp']
    past_std = s.shift(1).rolling(8, min_periods=4).std()
    return s / past_std
e['sue'] = e.groupby('symbol', group_keys=False).apply(roll_sue)

# ---------------------------------------------------------------- forward returns from bars
# fwd_h return at date d for ticker t = price[d+h]/price[d]-1 using trading-day offset
px = bars.copy()
pos = {d: i for i, d in enumerate(trading_days)}
fwd_panels = {}
for h in FWD:
    fp = px.shift(-h) / px - 1.0
    fwd_panels[h] = fp

# ---------------------------------------------------------------- build daily as-of signal panel
# For each ticker, each earnings event activates on first trading day >= date+LAG
# and stays the "current SUE" until next event or TRAIL trading days elapse.
def first_td_on_or_after(ts):
    idx = trading_days.searchsorted(ts, side='left')
    if idx >= len(trading_days):
        return None
    return idx

# panels: index = trading_days, columns = uni
sue_panel = pd.DataFrame(index=trading_days, columns=uni, dtype=float)
pct_panel = pd.DataFrame(index=trading_days, columns=uni, dtype=float)
raw_panel = pd.DataFrame(index=trading_days, columns=uni, dtype=float)

for sym, g in e.groupby('symbol'):
    g = g.sort_values('date')
    for _, row in g.iterrows():
        entry_ts = row['date'] + pd.Timedelta(days=LAG)
        i0 = first_td_on_or_after(entry_ts)
        if i0 is None:
            continue
        i1 = min(i0 + TRAIL, len(trading_days))
        sl = slice(i0, i1)
        # later events overwrite earlier within their own window (sorted asc -> ok)
        sue_panel.iloc[sl, sue_panel.columns.get_loc(sym)] = row['sue']
        pct_panel.iloc[sl, pct_panel.columns.get_loc(sym)] = row['pct_surp']
        raw_panel.iloc[sl, raw_panel.columns.get_loc(sym)] = row['surp']

# ---------------------------------------------------------------- cross-sectional IC framing
def spearman_ic(sig_row, ret_row):
    m = sig_row.notna() & ret_row.notna()
    if m.sum() < 5:
        return np.nan, m.sum()
    a = sig_row[m].rank()
    bb = ret_row[m].rank()
    if a.std() == 0 or bb.std() == 0:
        return np.nan, m.sum()
    return np.corrcoef(a, bb)[0, 1], m.sum()

def nw_tstat(x, lag):
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 10:
        return np.nan
    mu = x.mean()
    xd = x - mu
    gamma0 = (xd @ xd) / n
    var = gamma0
    for k in range(1, lag + 1):
        if k >= n:
            break
        w = 1 - k / (lag + 1)
        cov = (xd[k:] @ xd[:-k]) / n
        var += 2 * w * cov
    se = np.sqrt(var / n)
    return mu / se if se > 0 else np.nan

def shuffle_floor(sig_panel, ret_panel, n_shuffle):
    """Within-date shuffle: permute signal across names each date, recompute mean IC."""
    floors = []
    common = sig_panel.index.intersection(ret_panel.index)
    sigv = sig_panel.loc[common]
    retv = ret_panel.loc[common]
    for _ in range(n_shuffle):
        ics = []
        for dt in common:
            s = sigv.loc[dt].dropna()
            if len(s) < 5:
                continue
            r = retv.loc[dt].reindex(s.index)
            sh = pd.Series(RNG.permutation(s.values), index=s.index)
            ic, n = spearman_ic(sh, r)
            if not np.isnan(ic):
                ics.append(ic)
        if ics:
            floors.append(np.nanmean(ics))
    return np.nanstd(floors), np.nanmean(np.abs(floors))

def run_ic(sig_panel, name):
    rows = []
    for h in FWD:
        ret_panel = fwd_panels[h]
        common = sig_panel.index.intersection(ret_panel.index)
        daily_ic, daily_n = [], []
        dates = []
        for dt in common:
            s = sig_panel.loc[dt]
            r = ret_panel.loc[dt]
            ic, n = spearman_ic(s, r)
            if not np.isnan(ic):
                daily_ic.append(ic); daily_n.append(n); dates.append(dt)
        daily_ic = np.array(daily_ic)
        mean_ic = np.nanmean(daily_ic)
        hit = (daily_ic > 0).mean()
        # NW t-stat with lag ~ horizon (overlap)
        t = nw_tstat(daily_ic, lag=h)
        fstd, fabs = shuffle_floor(sig_panel, ret_panel, N_SHUFFLE)
        rows.append({
            'signal': name, 'horizon': h, 'n_dates': len(daily_ic),
            'avg_names': np.nanmean(daily_n), 'mean_IC': mean_ic,
            'NW_t': t, 'hit_rate': hit, 'shuffle_IC_std': fstd,
            'IC_over_floor': mean_ic / fstd if fstd > 0 else np.nan,
            'dates': dates, 'ics': daily_ic,
        })
    return rows

print("\n=== Cross-sectional IC (SUE) ===")
ic_rows = []
ic_rows += run_ic(sue_panel, 'SUE')
ic_rows += run_ic(pct_panel, 'pct_surprise')
ic_rows += run_ic(raw_panel, 'raw_surprise')

ic_df = pd.DataFrame([{k: v for k, v in r.items() if k not in ('dates', 'ics')} for r in ic_rows])
pd.set_option('display.width', 200)
print(ic_df.to_string(index=False))

# ---------------------------------------------------------------- stability by year (SUE, 60d)
print("\n=== Stability by year (SUE vs fwd60) ===")
sue60 = [r for r in ic_rows if r['signal'] == 'SUE' and r['horizon'] == 60][0]
yr = pd.Series(sue60['ics'], index=pd.DatetimeIndex(sue60['dates'])).groupby(lambda d: d.year)
yr_tab = pd.DataFrame({'mean_IC': yr.mean(), 'n_dates': yr.size(), 'pos_frac': yr.apply(lambda s: (s > 0).mean())})
print(yr_tab.to_string())

# ---------------------------------------------------------------- classic PEAD event study (quintiles)
# For each earnings event, rank its surprise (SUE) cross-sectionally WITHIN a +/-window
# of similar dates? Simpler & standard: rank within calendar quarter buckets is noisy on
# 134 names; instead rank each event vs the trailing distribution -> use the same SUE,
# then bucket events into quintiles by SUE, and measure CAR over [t+1, t+H] minus the
# universe mean over the same window.
print("\n=== Classic PEAD event study (SUE quintiles) ===")
ev = e.dropna(subset=['sue']).copy()
# entry index & forward CAR vs universe mean
def event_car(row, H):
    i0 = first_td_on_or_after(row['date'] + pd.Timedelta(days=LAG))
    if i0 is None or i0 + H >= len(trading_days):
        return np.nan
    sym = row['symbol']
    p0 = px.iloc[i0][sym]
    pH = px.iloc[i0 + H][sym]
    if not np.isfinite(p0) or not np.isfinite(pH) or p0 <= 0:
        return np.nan
    r_name = pH / p0 - 1.0
    # universe mean return over same window (equal weight, names with valid prices)
    p0u = px.iloc[i0]
    pHu = px.iloc[i0 + H]
    ru = (pHu / p0u - 1.0)
    ru = ru[np.isfinite(ru)]
    if len(ru) < 10:
        return np.nan
    return r_name - ru.mean()

for H in FWD:
    ev[f'car{H}'] = ev.apply(lambda r: event_car(r, H), axis=1)

# quintile by SUE (global quintile of all usable events)
ev['q'] = pd.qcut(ev['sue'], 5, labels=False, duplicates='drop')
qtab_rows = []
for H in FWD:
    col = f'car{H}'
    sub = ev.dropna(subset=[col, 'q'])
    g = sub.groupby('q')[col]
    means = g.mean()
    counts = g.size()
    top = means.get(4, np.nan)
    bot = means.get(0, np.nan)
    spread = top - bot
    # t-stat of top-minus-bottom (independent groups, but events overlap -> rough)
    tvals = sub[sub['q'] == 4][col].values
    bvals = sub[sub['q'] == 0][col].values
    from scipy import stats as _st
    tt = _st.ttest_ind(tvals, bvals, equal_var=False, nan_policy='omit')
    qtab_rows.append({
        'horizon': H, 'n_events': len(sub),
        'Q1(low)_CAR': bot, 'Q5(high)_CAR': top,
        'Q5-Q1_spread': spread, 'spread_bps': spread * 1e4,
        'net_bps(-cost)': spread * 1e4 - COST_BPS, 'Welch_t': tt.statistic,
    })
    print(f"\n-- horizon {H}d -- (n={len(sub)})")
    print("  quintile mean CAR vs universe:")
    for q in sorted(means.index):
        print(f"    Q{int(q)+1}: CAR={means[q]*1e4:8.1f} bps  n={counts[q]}")
    print(f"  Q5-Q1 spread = {spread*1e4:.1f} bps  (Welch t={tt.statistic:.2f})  net of {COST_BPS}bps = {spread*1e4-COST_BPS:.1f} bps")

qtab = pd.DataFrame(qtab_rows)
print("\n=== PEAD quintile summary ===")
print(qtab.to_string(index=False))

# ---------------------------------------------------------------- turnover note
# events per year on universe -> rebalance cadence
ev_per_yr = e.groupby(e['date'].dt.year).size()
print("\n=== events/year on 134 universe ===")
print(ev_per_yr.to_string())

# save tables
ic_df.to_csv(OUT + 'ic_table.csv', index=False)
qtab.to_csv(OUT + 'pead_quintile_table.csv', index=False)
yr_tab.to_csv(OUT + 'sue_stability_by_year.csv')
print("\n[saved] ic_table.csv, pead_quintile_table.csv, sue_stability_by_year.csv ->", OUT)
