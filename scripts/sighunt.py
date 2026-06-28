#!/usr/bin/env python
"""
MVP cross-sectional multi-day TREND signal scan.
READ-ONLY: pulls Alpaca daily bars, computes ~5 canonical price factors,
measures raw cross-sectional Spearman rank-IC vs forward multi-day returns,
with ONE shuffle-placebo noise-floor guard. No orders. No git. No canonical writes.

Honest overlap handling: IC t-stat is computed on NON-OVERLAPPING forward windows
(step == horizon) so the daily-IC samples are independent. We also report the
naive overlapping t-stat for transparency, but the headline t-stat is the
non-overlapping one.
"""
import os
import sys
import json
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from scipy.stats import spearmanr

OUT = "/tmp/sighunt"
os.makedirs(OUT, exist_ok=True)

# ---- universe (canonical renquant_104 golden watchlist, 142 names) ----
CFG = "/Users/renhao/git/github/RenQuant/backtesting/renquant_104/strategy_config.golden.json"
wl = json.load(open(CFG))["watchlist"]
# drop the ETFs / non-single-name members so the cross-section is comparable stocks.
ETFS = {"SPY", "GLD", "TLT", "XLE", "XLF", "XLI", "XLK", "XLU", "XLY", "XLV"}
UNIVERSE = [t for t in wl if t not in ETFS]
print(f"[universe] {len(UNIVERSE)} single names (dropped {len(set(wl)&ETFS)} ETFs from {len(wl)})", flush=True)

# ---- fetch ~5y daily bars from Alpaca (READ-ONLY) ----
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.data.enums import Adjustment

client = StockHistoricalDataClient(
    api_key=os.environ["ALPACA_API_KEY"],
    secret_key=os.environ["ALPACA_SECRET_KEY"],
)
end = datetime.now(timezone.utc) - timedelta(days=1)
# extend to ~8y: more independent non-overlapping windows + a pre-2021 regime.
# (Alpaca serves pre-2021 history; recent-IPO names just have shorter coverage and
#  are coverage-filtered below.)
start = end - timedelta(days=365 * 8 + 30)

CACHE = os.path.join(OUT, "bars.parquet")
if os.path.exists(CACHE):
    px = pd.read_parquet(CACHE)
    print(f"[data] loaded cached close panel {px.shape}", flush=True)
else:
    req = StockBarsRequest(
        symbol_or_symbols=UNIVERSE,
        timeframe=TimeFrame.Day,
        start=start,
        end=end,
        adjustment=Adjustment.ALL,  # split + dividend adjusted
    )
    bars = client.get_stock_bars(req).df
    print(f"[data] raw bars rows={len(bars)}", flush=True)
    close = bars["close"].reset_index()
    close["date"] = pd.to_datetime(close["timestamp"]).dt.tz_localize(None).dt.normalize()
    px = close.pivot(index="date", columns="symbol", values="close").sort_index()
    px.to_parquet(CACHE)
    print(f"[data] close panel {px.shape} -> {CACHE}", flush=True)

# require reasonable coverage
cov = px.notna().mean()
# 0.55 over an 8y window keeps names listed >= ~4.4y (incl. 2021-era IPOs);
# the per-date notna mask means each name only enters the cross-section where it has data.
keep = cov[cov > 0.55].index.tolist()
dropped = sorted(set(px.columns) - set(keep))
if dropped:
    print(f"[data] dropping {len(dropped)} names with <80% coverage: {dropped}", flush=True)
px = px[keep]
print(f"[data] final panel: {px.shape[0]} days x {px.shape[1]} names; "
      f"{px.index.min().date()} -> {px.index.max().date()}", flush=True)

logpx = np.log(px)

# ---- candidate signals (per day, cross-sectional) ----
def ret(n):
    return px / px.shift(n) - 1.0

signals = {}
# 1) Momentum 12-1: 252d return skipping last ~21d
signals["mom_12_1"] = (px.shift(21) / px.shift(252) - 1.0)
# 2) Momentum 6-1: 126d return skipping last ~21d
signals["mom_6_1"] = (px.shift(21) / px.shift(126) - 1.0)
# 3) Short-term reversal: -1 * trailing 21d return
signals["st_rev_21"] = -1.0 * (px / px.shift(21) - 1.0)
# 4) Trend / MA distance: price / 200d SMA - 1
sma200 = px.rolling(200, min_periods=150).mean()
signals["ma200_dist"] = px / sma200 - 1.0
# 5) 52-week-high proximity: price / trailing-252d high
hi252 = px.rolling(252, min_periods=200).max()
signals["pct_52w_high"] = px / hi252

HORIZONS = [5, 20, 60]
PRIMARY = 20
COST_BPS = 11.0  # round-trip cost to subtract from L/S decile spread

rng = np.random.default_rng(42)

def fwd_ret(h):
    return px.shift(-h) / px - 1.0

def daily_ic(sig, fwd, dates):
    """Spearman rank-IC per date over the cross-section."""
    ics = []
    for d in dates:
        s = sig.loc[d]
        f = fwd.loc[d]
        m = s.notna() & f.notna()
        if m.sum() < 10:
            continue
        rho = spearmanr(s[m].values, f[m].values).correlation
        if rho is not None and not np.isnan(rho):
            ics.append((d, rho))
    return pd.Series({d: v for d, v in ics})

def ls_decile_spread(sig, fwd, dates):
    """Top-decile minus bottom-decile mean forward return, averaged over dates,
    annualization-free (per-period). Returns per-rebalance gross bps."""
    spreads = []
    for d in dates:
        s = sig.loc[d].dropna()
        f = fwd.loc[d]
        common = s.index.intersection(f.dropna().index)
        if len(common) < 20:
            continue
        s = s.loc[common]
        f = f.loc[common]
        q = s.rank(pct=True)
        top = f[q >= 0.9].mean()
        bot = f[q <= 0.1].mean()
        if np.isnan(top) or np.isnan(bot):
            continue
        spreads.append(top - bot)
    return np.array(spreads)

results = []
placebo_floor = {}

for h in HORIZONS:
    fwd = fwd_ret(h)
    # NON-OVERLAPPING rebalance dates: every h trading days
    all_dates = px.index
    # valid range: need history for signals (>=252) and future (<=h)
    valid = px.index[252:-h] if h > 0 else px.index[252:]
    nonover_dates = valid[::h]
    for name, sig in signals.items():
        ic = daily_ic(sig, fwd, nonover_dates)
        if len(ic) < 5:
            continue
        mean_ic = ic.mean()
        std_ic = ic.std(ddof=1)
        n = len(ic)
        tstat = mean_ic / (std_ic / np.sqrt(n)) if std_ic > 0 else np.nan
        hit = (ic > 0).mean()
        # net L/S decile spread (gross per-rebalance), then subtract cost
        spreads = ls_decile_spread(sig, fwd, nonover_dates)
        gross_bps = np.nanmean(spreads) * 1e4 if len(spreads) else np.nan
        net_bps = gross_bps - COST_BPS if not np.isnan(gross_bps) else np.nan
        # overlapping (daily) IC for reference
        ic_daily = daily_ic(sig, fwd, valid)
        mean_ic_daily = ic_daily.mean()
        results.append(dict(
            signal=name, horizon=h, n_obs=n,
            mean_ic=mean_ic, ic_std=std_ic, t_stat=tstat, hit_rate=hit,
            gross_ls_bps=gross_bps, net_ls_bps=net_bps,
            mean_ic_overlap=mean_ic_daily,
        ))

# ---- ONE placebo guard: shuffle forward returns across names within each date ----
# Build noise floor per horizon (signal-agnostic; permuting fwd breaks any real link).
N_PERM = 200
print("[placebo] building shuffle noise floor...", flush=True)
for h in HORIZONS:
    fwd = fwd_ret(h)
    valid = px.index[252:-h]
    nonover_dates = valid[::h]
    # use one representative signal (mom_12_1) for the permutation geometry;
    # under the null the IC distribution is signal-agnostic given same coverage.
    sig = signals["mom_12_1"]
    perm_mean_ics = []
    for _ in range(N_PERM):
        ics = []
        for d in nonover_dates:
            s = sig.loc[d]
            f = fwd.loc[d]
            m = s.notna() & f.notna()
            if m.sum() < 10:
                continue
            fv = f[m].values.copy()
            rng.shuffle(fv)
            rho = spearmanr(s[m].values, fv).correlation
            if rho is not None and not np.isnan(rho):
                ics.append(rho)
        if ics:
            perm_mean_ics.append(np.mean(ics))
    perm_mean_ics = np.array(perm_mean_ics)
    placebo_floor[h] = dict(
        mean=float(perm_mean_ics.mean()),
        std=float(perm_mean_ics.std(ddof=1)),
        p95_abs=float(np.percentile(np.abs(perm_mean_ics), 95)),
        p05=float(np.percentile(perm_mean_ics, 5)),
        p95=float(np.percentile(perm_mean_ics, 95)),
    )
    print(f"[placebo] h={h}: floor |mean_ic| p95={placebo_floor[h]['p95_abs']:.4f} "
          f"(perm mean={placebo_floor[h]['mean']:.4f} std={placebo_floor[h]['std']:.4f})", flush=True)

df = pd.DataFrame(results)
# clearance vs placebo: |mean_ic| beyond the 95th-pct of permuted |mean_ic|
df["floor_p95_abs"] = df["horizon"].map(lambda h: placebo_floor[h]["p95_abs"])
df["clears_floor"] = df["mean_ic"].abs() > df["floor_p95_abs"]
df["ic_over_floor"] = df["mean_ic"].abs() / df["floor_p95_abs"]

df = df.sort_values(["horizon", "mean_ic"], ascending=[True, False]).reset_index(drop=True)
df.to_csv(os.path.join(OUT, "results.csv"), index=False)
with open(os.path.join(OUT, "placebo_floor.json"), "w") as f:
    json.dump(placebo_floor, f, indent=2)

pd.set_option("display.width", 200)
pd.set_option("display.max_columns", 30)
pd.set_option("display.float_format", lambda x: f"{x:.4f}")
print("\n================ RANKED RESULTS ================")
cols = ["signal", "horizon", "n_obs", "mean_ic", "t_stat", "hit_rate",
        "gross_ls_bps", "net_ls_bps", "floor_p95_abs", "ic_over_floor", "clears_floor"]
print(df[cols].to_string(index=False))
print("\n================ PLACEBO NOISE FLOOR ================")
for h in HORIZONS:
    pf = placebo_floor[h]
    print(f"h={h:>3}: perm mean_ic={pf['mean']:+.4f}  std={pf['std']:.4f}  "
          f"|mean_ic| 95th-pct={pf['p95_abs']:.4f}  [5%,95%]=[{pf['p05']:+.4f},{pf['p95']:+.4f}]")
print(f"\nWrote: {OUT}/results.csv, {OUT}/placebo_floor.json")
