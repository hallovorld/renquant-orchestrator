"""PEAD %-surprise follow-up: LONG-SIDE-ONLY economics + ORTHOGONALITY.

The cheap screen (see scripts/pead_test.py) already passed for %-surprise:
fwd_20d IC +0.0313, NW t=3.12, 14.5x shuffle floor, placebo-clean, low-turnover.
The short leg is unmonetizable under our shorting mandate, so this script decides
USABILITY by quantifying:

  (1) LONG-SIDE-ONLY economics: top-quintile AND top-decile of recent positive
      %-surprise names, LONG-ONLY, excess return vs the equal-weight universe mean
      over [t+1,t+20] and [t+1,t+60], NET of ~11 bps one-way cost. Hit-rate and a
      long-only IC restricted to the monetizable long side.

  (2) ORTHOGONALITY: cross-sectional rank correlation of the PEAD %-surprise signal
      vs the canonical price factors (mom_12_1, mom_6_1, ma200_dist) recomputed on the
      same bars panel. Low correlation => a genuinely different (Fundamental-Law) bet.

LEAN, candidate-signal style. READ-ONLY. No orders, no git, no canonical writes.
Output to /tmp/pead/.

Caveat carried forward: correlation vs the LIVE model scores is PENDING faithful
decision-ledger data (the ledger is too thin/impaired; see prior audit). NOT computed
here; flagged as a follow-up rather than fabricated.
"""
import numpy as np
import pandas as pd

EARN = '/Users/renhao/git/github/RenQuant/data/fmp_harvest/earnings_291.parquet'
BARS = '/tmp/sighunt/bars.parquet'
OUT = '/tmp/pead/'

FWD = [20, 60]
TRAIL = 63          # signal validity window after an earnings date (~1 quarter)
LAG = 1             # enter signal first trading day AFTER earnings date
COST_BPS = 11.0     # one-way cost (low-turnover quarterly cadence)

# ---------------------------------------------------------------- load
bars = pd.read_parquet(BARS)
bars.index = pd.to_datetime(bars.index)
bars = bars.sort_index()
uni = list(bars.columns)
trading_days = bars.index
px = bars.copy()

e = pd.read_parquet(EARN)
e['date'] = pd.to_datetime(e['date'])
e = e[e['symbol'].isin(uni)].copy()
e = e.dropna(subset=['epsActual', 'epsEstimated'])
e = e[(e['date'] >= bars.index.min()) & (e['date'] <= bars.index.max())]
e = e.sort_values(['symbol', 'date']).reset_index(drop=True)

e['surp'] = e['epsActual'] - e['epsEstimated']
denom = e['epsEstimated'].abs().replace(0, np.nan)
e['pct_surp'] = e['surp'] / denom

# ---------------------------------------------------------------- as-of %-surprise panel
def first_td_on_or_after(ts):
    idx = trading_days.searchsorted(ts, side='left')
    if idx >= len(trading_days):
        return None
    return idx

pct_panel = pd.DataFrame(index=trading_days, columns=uni, dtype=float)
for sym, g in e.groupby('symbol'):
    g = g.sort_values('date')
    for _, row in g.iterrows():
        i0 = first_td_on_or_after(row['date'] + pd.Timedelta(days=LAG))
        if i0 is None:
            continue
        i1 = min(i0 + TRAIL, len(trading_days))
        pct_panel.iloc[i0:i1, pct_panel.columns.get_loc(sym)] = row['pct_surp']

# forward return panels
fwd_panels = {h: px.shift(-h) / px - 1.0 for h in FWD}

# ================================================================
# (1) LONG-SIDE-ONLY ECONOMICS
# ================================================================
# On each rebalance date, take names whose CURRENT as-of %-surprise is POSITIVE
# (a real recent positive surprise -> the monetizable side), rank them, take the
# top-quintile and top-decile, and measure equal-weight excess return vs the
# universe (equal-weight) mean over the horizon. We rebalance on a ~quarterly
# cadence (every TRAIL=63 trading days, non-overlapping) so cost is one-way per
# rebalance (turnover ~1x/quarter).
print("=== (1) LONG-SIDE-ONLY economics ===")
rebal_dates = trading_days[252::TRAIL]   # quarterly, after warmup

def long_only_economics(top_frac, label):
    rows = []
    for h in FWD:
        fwd = fwd_panels[h]
        excesses, hits, n_names = [], [], []
        for d in rebal_dates:
            if d not in fwd.index:
                continue
            sig = pct_panel.loc[d]
            r = fwd.loc[d]
            # universe equal-weight mean return (names with valid fwd)
            ru = r[r.notna()]
            if len(ru) < 10:
                continue
            uni_mean = ru.mean()
            # monetizable long side: POSITIVE recent %-surprise only
            pos = sig[(sig.notna()) & (sig > 0)]
            common = pos.index.intersection(ru.index)
            if len(common) < 5:
                continue
            pos = pos.loc[common]
            q = pos.rank(pct=True)
            cut = 1.0 - top_frac
            sel = pos[q >= cut].index
            if len(sel) == 0:
                continue
            sel_ret = r.loc[sel]
            sel_ret = sel_ret[sel_ret.notna()]
            if len(sel_ret) == 0:
                continue
            excesses.append(sel_ret.mean() - uni_mean)
            # hit-rate = fraction of selected names that BEAT the universe mean
            hits.append((sel_ret > uni_mean).mean())
            n_names.append(len(sel_ret))
        excesses = np.array(excesses)
        gross_bps = np.nanmean(excesses) * 1e4
        net_bps = gross_bps - COST_BPS   # one-way cost per quarterly rebalance
        rows.append({
            'leg': label, 'horizon': h, 'n_rebal': len(excesses),
            'avg_names': np.nanmean(n_names) if n_names else np.nan,
            'gross_excess_bps': gross_bps,
            'net_excess_bps': net_bps,
            'hit_rate_vs_uni': np.nanmean(hits) if hits else np.nan,
            'rebal_pos_frac': (excesses > 0).mean() if len(excesses) else np.nan,
        })
    return rows

lo_rows = []
lo_rows += long_only_economics(0.20, 'top_quintile')
lo_rows += long_only_economics(0.10, 'top_decile')
lo_df = pd.DataFrame(lo_rows)
pd.set_option('display.width', 200)
print(lo_df.to_string(index=False))

# ---- long-only IC: IC restricted to the monetizable (positive-surprise) long side
print("\n=== (1b) long-only IC (restricted to POSITIVE %-surprise names) ===")
def spearman_ic(sig_row, ret_row):
    m = sig_row.notna() & ret_row.notna()
    if m.sum() < 5:
        return np.nan, m.sum()
    a = sig_row[m].rank()
    bb = ret_row[m].rank()
    if a.std() == 0 or bb.std() == 0:
        return np.nan, m.sum()
    return np.corrcoef(a, bb)[0, 1], m.sum()

loic_rows = []
for h in FWD:
    fwd = fwd_panels[h]
    common = pct_panel.index.intersection(fwd.index)
    ics = []
    for dt in common:
        sig = pct_panel.loc[dt]
        pos = sig[(sig.notna()) & (sig > 0)]   # long side only
        if len(pos) < 5:
            continue
        r = fwd.loc[dt].reindex(pos.index)
        ic, n = spearman_ic(pos, r)
        if not np.isnan(ic):
            ics.append(ic)
    ics = np.array(ics)
    loic_rows.append({
        'horizon': h, 'n_dates': len(ics),
        'long_only_mean_IC': np.nanmean(ics),
        'hit_rate': (ics > 0).mean() if len(ics) else np.nan,
    })
loic_df = pd.DataFrame(loic_rows)
print(loic_df.to_string(index=False))

# ================================================================
# (2) ORTHOGONALITY vs canonical price factors
# ================================================================
print("\n=== (2) ORTHOGONALITY: rank-corr of %-surprise vs price factors ===")
factors = {}
factors['mom_12_1'] = px.shift(21) / px.shift(252) - 1.0
factors['mom_6_1'] = px.shift(21) / px.shift(126) - 1.0
sma200 = px.rolling(200, min_periods=150).mean()
factors['ma200_dist'] = px / sma200 - 1.0

# Per-date cross-sectional Spearman rank corr of the PEAD %-surprise signal vs
# each factor; report the mean (and abs-mean) over dates where >=10 names overlap.
orth_rows = []
common = pct_panel.index
for fname, fpanel in factors.items():
    rhos = []
    for dt in common:
        sig = pct_panel.loc[dt]
        fac = fpanel.loc[dt] if dt in fpanel.index else None
        if fac is None:
            continue
        m = sig.notna() & fac.notna()
        if m.sum() < 10:
            continue
        a = sig[m].rank()
        b = fac[m].rank()
        if a.std() == 0 or b.std() == 0:
            continue
        rhos.append(np.corrcoef(a, b)[0, 1])
    rhos = np.array(rhos)
    orth_rows.append({
        'factor': fname, 'n_dates': len(rhos),
        'mean_rank_corr': np.nanmean(rhos),
        'abs_mean_rank_corr': np.nanmean(np.abs(rhos)),
        'p05': np.nanpercentile(rhos, 5) if len(rhos) else np.nan,
        'p95': np.nanpercentile(rhos, 95) if len(rhos) else np.nan,
    })
orth_df = pd.DataFrame(orth_rows)
print(orth_df.to_string(index=False))
print("\nNOTE: correlation vs the LIVE model scores is PENDING faithful decision-ledger")
print("data (ledger too thin/impaired; see prior audit). Flagged as follow-up; NOT fabricated.")

# ---- save
lo_df.to_csv(OUT + 'pead_longonly_economics.csv', index=False)
loic_df.to_csv(OUT + 'pead_longonly_ic.csv', index=False)
orth_df.to_csv(OUT + 'pead_orthogonality.csv', index=False)
print("\n[saved] pead_longonly_economics.csv, pead_longonly_ic.csv, pead_orthogonality.csv ->", OUT)
