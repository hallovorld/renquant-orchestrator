#!/usr/bin/env python
"""PEAD / earnings-surprise drift as a cross-sectional signal on the renquant-104 universe.

LEAN cheap screen: SUE / %-surprise / raw cross-sectional rank-IC vs forward 20/60d
returns + a within-date shuffle placebo floor, plus a classic post-announcement-drift
quintile event study. READ-ONLY. No orders, no git, no canonical writes.

PIT / look-ahead honesty (see review on PR #203, downgraded 2026-06-28):
  The earnings parquet is a SINGLE CURRENT one-shot harvest. `epsEstimated` on a
  historical row is the value in TODAY'S harvest, NOT a captured pre-announcement
  consensus snapshot. The +1-trading-day entry convention (LAG) controls ENTRY TIMING
  only; it does NOT prove the estimate value was the consensus that existed pre-event or
  was not later revised. The harvested `lastUpdated` is a generic floor before 2024-09
  and so cannot establish per-event vintage. THEREFORE: pre-2024 results are
  NON-POINT-IN-TIME EXPLORATORY EVIDENCE, not a clean PIT backtest. Do not call this
  "PIT-clean in principle." Treat all numbers as a directional probe.

Reproducibility (same standard as scripts/sighunt.py, PR #202): pass `--as-of` (pinned,
NO datetime.now), `--bars-cache`, `--earnings`, `--out`. Input hashes + all parameters +
code commit are written to a `manifest.json` next to the outputs. The output dir is
created.
"""
import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone

import numpy as np
import pandas as pd

DEFAULT_EARN = "/Users/renhao/git/github/RenQuant/data/fmp_harvest/earnings_291.parquet"
DEFAULT_BARS = "/tmp/sighunt/bars.parquet"
DEFAULT_OUT = "/tmp/pead/"

FWD = [20, 60]
TRAIL = 63          # signal validity window after an earnings date (~1 quarter)
LAG = 1             # enter signal first trading day AFTER earnings date (timing only)
COST_BPS = 11.0     # round-trip-ish L/S cost assumption from mandate
N_SHUFFLE = 200
WINSOR_Q = 0.05     # floor |epsEstimated| at this quantile so tiny denominators can't dominate
SEED = 20260627


# ---------------------------------------------------------------- repro helpers
def sha256_file(path):
    if not path or not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git_commit():
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.check_output(
            ["git", "-C", here, "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--as-of", required=True,
                    help="Pinned end date YYYY-MM-DD (no datetime.now). Bars/events end here.")
    ap.add_argument("--bars-cache", default=DEFAULT_BARS,
                    help="Cached close-panel parquet (read-only).")
    ap.add_argument("--earnings", default=DEFAULT_EARN,
                    help="FMP earnings harvest parquet (read-only, current one-shot harvest).")
    ap.add_argument("--out", default=DEFAULT_OUT, help="Output directory (created if missing).")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    out = args.out if args.out.endswith("/") else args.out + "/"
    as_of = pd.Timestamp(args.as_of).normalize()
    rng = np.random.default_rng(SEED)

    # ---------------------------------------------------------------- load
    bars = pd.read_parquet(args.bars_cache)
    bars.index = pd.to_datetime(bars.index)
    bars = bars.sort_index()
    bars = bars[bars.index <= as_of]   # respect the pinned as-of
    uni = list(bars.columns)
    trading_days = bars.index
    px = bars.copy()

    e = pd.read_parquet(args.earnings)
    e['date'] = pd.to_datetime(e['date'])
    e = e[e['symbol'].isin(uni)].copy()
    e = e.dropna(subset=['epsActual', 'epsEstimated'])
    e = e[(e['date'] >= bars.index.min()) & (e['date'] <= as_of)]
    e = e.sort_values(['symbol', 'date']).reset_index(drop=True)

    # ---------------------------------------------------------------- eps cleanliness check
    exact_eq = (e['epsActual'] == e['epsEstimated']).mean()
    zero_est = (e['epsEstimated'].abs() < 1e-9).mean()
    print(f"[cleanliness] n events on universe in window = {len(e)}  tickers = {e['symbol'].nunique()}")
    print(f"[cleanliness] frac epsActual==epsEstimated EXACTLY = {exact_eq:.4f}")
    print(f"[cleanliness] frac |epsEstimated|~0 = {zero_est:.4f}")
    surp = e['epsActual'] - e['epsEstimated']
    print(f"[cleanliness] raw surprise mean={surp.mean():.4f} median={surp.median():.4f} std={surp.std():.4f}")

    # ---------------------------------------------------------------- surprise measures
    e['surp'] = e['epsActual'] - e['epsEstimated']
    # WINSORIZED %-surprise denominator: floor |epsEstimated| at the WINSOR_Q quantile so
    # tiny estimates near zero cannot dominate the top-positive selection (review note).
    denom_floor = float(e['epsEstimated'].abs().quantile(WINSOR_Q))
    denom = e['epsEstimated'].abs().clip(lower=denom_floor)
    e['pct_surp'] = e['surp'] / denom
    print(f"[winsor] %-surprise denominator floored at |epsEstimated| p{int(WINSOR_Q*100)} = {denom_floor:.4f}")

    def roll_sue(g):
        s = g['surp']
        past_std = s.shift(1).rolling(8, min_periods=4).std()
        return s / past_std
    e['sue'] = e.groupby('symbol', group_keys=False).apply(roll_sue)

    # ---------------------------------------------------------------- forward returns from bars
    fwd_panels = {h: px.shift(-h) / px - 1.0 for h in FWD}

    # ---------------------------------------------------------------- build daily as-of signal panel
    def first_td_on_or_after(ts):
        idx = trading_days.searchsorted(ts, side='left')
        return idx if idx < len(trading_days) else None

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
        var = (xd @ xd) / n
        for k in range(1, lag + 1):
            if k >= n:
                break
            w = 1 - k / (lag + 1)
            var += 2 * w * (xd[k:] @ xd[:-k]) / n
        se = np.sqrt(var / n)
        return mu / se if se > 0 else np.nan

    def shuffle_floor(sig_panel, ret_panel, n_shuffle):
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
                sh = pd.Series(rng.permutation(s.values), index=s.index)
                ic, _ = spearman_ic(sh, r)
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
            daily_ic, daily_n, dates = [], [], []
            for dt in common:
                ic, n = spearman_ic(sig_panel.loc[dt], ret_panel.loc[dt])
                if not np.isnan(ic):
                    daily_ic.append(ic); daily_n.append(n); dates.append(dt)
            daily_ic = np.array(daily_ic)
            mean_ic = np.nanmean(daily_ic)
            hit = (daily_ic > 0).mean()
            t = nw_tstat(daily_ic, lag=h)
            fstd, _ = shuffle_floor(sig_panel, ret_panel, N_SHUFFLE)
            rows.append({
                'signal': name, 'horizon': h, 'n_dates': len(daily_ic),
                'avg_names': np.nanmean(daily_n), 'mean_IC': mean_ic,
                'NW_t': t, 'hit_rate': hit, 'shuffle_IC_std': fstd,
                'IC_over_floor': mean_ic / fstd if fstd > 0 else np.nan,
                'dates': dates, 'ics': daily_ic,
            })
        return rows

    print("\n=== Cross-sectional IC (NON-PIT exploratory; winsorized %-surprise) ===")
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
    yr_tab = pd.DataFrame({'mean_IC': yr.mean(), 'n_dates': yr.size(),
                           'pos_frac': yr.apply(lambda s: (s > 0).mean())})
    print(yr_tab.to_string())

    # ---------------------------------------------------------------- classic PEAD event study (quintiles)
    print("\n=== Classic PEAD event study (SUE quintiles) ===")
    ev = e.dropna(subset=['sue']).copy()

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
        p0u = px.iloc[i0]
        pHu = px.iloc[i0 + H]
        ru = (pHu / p0u - 1.0)
        ru = ru[np.isfinite(ru)]
        if len(ru) < 10:
            return np.nan
        return r_name - ru.mean()

    for H in FWD:
        ev[f'car{H}'] = ev.apply(lambda r: event_car(r, H), axis=1)

    ev['q'] = pd.qcut(ev['sue'], 5, labels=False, duplicates='drop')
    qtab_rows = []
    from scipy import stats as _st
    for H in FWD:
        col = f'car{H}'
        sub = ev.dropna(subset=[col, 'q'])
        g = sub.groupby('q')[col]
        means = g.mean()
        counts = g.size()
        top = means.get(4, np.nan)
        bot = means.get(0, np.nan)
        spread = top - bot
        tvals = sub[sub['q'] == 4][col].values
        bvals = sub[sub['q'] == 0][col].values
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
        print(f"  Q5-Q1 spread = {spread*1e4:.1f} bps  (Welch t={tt.statistic:.2f})  "
              f"net of {COST_BPS}bps = {spread*1e4-COST_BPS:.1f} bps")

    qtab = pd.DataFrame(qtab_rows)
    print("\n=== PEAD quintile summary ===")
    print(qtab.to_string(index=False))

    # ---------------------------------------------------------------- turnover note
    ev_per_yr = e.groupby(e['date'].dt.year).size()
    print(f"\n=== events/year on {len(uni)} universe ===")
    print(ev_per_yr.to_string())

    # ---------------------------------------------------------------- save tables + manifest
    ic_df.to_csv(out + 'ic_table.csv', index=False)
    qtab.to_csv(out + 'pead_quintile_table.csv', index=False)
    yr_tab.to_csv(out + 'sue_stability_by_year.csv')

    manifest = dict(
        script="scripts/pead_test.py",
        kind="NON-PIT exploratory earnings-surprise cross-sectional screen "
             "(single current one-shot FMP harvest; not a captured pre-announcement consensus)",
        pit_status="NON-POINT-IN-TIME: +1d convention controls entry timing only; "
                   "estimate values are from today's harvest, lastUpdated is a generic floor "
                   "pre-2024-09. Pre-2024 results are exploratory, not PIT-clean.",
        as_of=args.as_of,
        code_commit=git_commit(),
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        bars_cache=args.bars_cache,
        bars_cache_sha256=sha256_file(args.bars_cache),
        earnings=args.earnings,
        earnings_sha256=sha256_file(args.earnings),
        parameters=dict(
            fwd=FWD, trail=TRAIL, lag=LAG, cost_bps=COST_BPS,
            n_shuffle=N_SHUFFLE, winsor_q=WINSOR_Q, denom_floor=denom_floor, seed=SEED,
        ),
        panel=dict(
            days=int(px.shape[0]), names=int(px.shape[1]),
            start=str(px.index.min().date()), end=str(px.index.max().date()),
        ),
        n_events=int(len(e)),
        kept_symbols=uni,
        kept_symbols_sha256=sha256_text(",".join(sorted(uni))),
    )
    with open(out + 'manifest_pead_test.json', 'w') as f:
        json.dump(manifest, f, indent=2)
    print("\n[saved] ic_table.csv, pead_quintile_table.csv, sue_stability_by_year.csv, "
          "manifest_pead_test.json ->", out)
    print("[note] NON-PIT exploratory evidence; single current harvest, +1d = entry timing only.")


if __name__ == "__main__":
    main()
