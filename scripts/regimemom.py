#!/usr/bin/env python
"""
renquant105 forward lead #1: Does conditioning mom_12_1 on a POINT-IN-TIME (PIT)
market regime rescue it into a stable, net-positive multi-day cross-sectional edge?

LEAN: ONE script. Conditional IC + within-date shuffle floor + honest per-regime
sample sizes + run-length/frequency actionability. NO CPCV / nested-CV / FWER /
PBO / DSR / pre-registration. Cheap directional probe.

READ-ONLY: reuses the prior hunt's cached 134-name 8y panel
(/tmp/sighunt/bars.parquet) and pulls SPY daily bars from Alpaca (read-only).
No orders. No git on the live tree. Output only to /tmp/regimemom/.

Regime label (PIT, no look-ahead, SPY-only, as-of each date):
  trend = sign(SPY_close - SPY_trailing_200d_SMA)  -> UP / DOWN   (PRIMARY 2-state)
  vol   = PIT tercile of SPY trailing-20d realized vol, computed on an EXPANDING
          basis using only data up to (and including) each date -> CALM/NORMAL/VOLATILE
  secondary = trend x vol (2x3)

Signal: mom_12_1 = px.shift(21)/px.shift(252) - 1  (252d return skipping last 21d).
IC: daily cross-sectional Spearman rank-IC of mom_12_1 vs fwd_20d (primary) and
    fwd_5d, every day (overlapping for power); t-stats are NEWEY-WEST adjusted for
    the overlap (lag = horizon-1). Group daily ICs by the day's PIT regime label.
Per regime: n_days, mean IC, NW t, hit-rate, IC vs within-date shuffle floor,
    net top-decile-minus-bottom-decile L/S bps (gross minus ~11bps cost),
    % of history, mean run-length.
"""
import os
import sys
import json
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta
from scipy.stats import spearmanr

OUT = "/tmp/regimemom"
os.makedirs(OUT, exist_ok=True)
COST_BPS = 11.0
rng = np.random.default_rng(42)

# ---------------------------------------------------------------------------
# 1) Load cached single-name panel (reuse prior hunt)
# ---------------------------------------------------------------------------
CACHE = "/tmp/sighunt/bars.parquet"
if not os.path.exists(CACHE):
    print("[fatal] cached panel missing; re-pull path not exercised here.", file=sys.stderr)
    sys.exit(1)
px = pd.read_parquet(CACHE).sort_index()
print(f"[data] single-name panel {px.shape}  {px.index.min().date()}->{px.index.max().date()}", flush=True)

# ---------------------------------------------------------------------------
# 2) Pull SPY daily bars (READ-ONLY) for the regime label; cache it
# ---------------------------------------------------------------------------
SPY_CACHE = os.path.join(OUT, "spy.parquet")
if os.path.exists(SPY_CACHE):
    spy = pd.read_parquet(SPY_CACHE)["SPY"]
    print(f"[data] loaded cached SPY {spy.shape}", flush=True)
else:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.enums import Adjustment
    client = StockHistoricalDataClient(
        api_key=os.environ["ALPACA_API_KEY"],
        secret_key=os.environ["ALPACA_SECRET_KEY"],
    )
    end = datetime.now(timezone.utc) - timedelta(days=1)
    start = end - timedelta(days=365 * 8 + 60)
    req = StockBarsRequest(symbol_or_symbols=["SPY"], timeframe=TimeFrame.Day,
                           start=start, end=end, adjustment=Adjustment.ALL)
    bars = client.get_stock_bars(req).df
    close = bars["close"].reset_index()
    close["date"] = pd.to_datetime(close["timestamp"]).dt.tz_localize(None).dt.normalize()
    spy = close.set_index("date")["close"].sort_index()
    spy.to_frame("SPY").to_parquet(SPY_CACHE)
    print(f"[data] pulled SPY {spy.shape} -> {SPY_CACHE}", flush=True)

# align SPY to the single-name panel's trading calendar
spy = spy.reindex(px.index).ffill(limit=3)
print(f"[data] SPY aligned coverage on panel dates: {spy.notna().mean():.3f}", flush=True)

# ---------------------------------------------------------------------------
# 3) PIT regime label from SPY only (no look-ahead)
# ---------------------------------------------------------------------------
# trend: close vs trailing 200d SMA (uses only past+current closes)
sma200 = spy.rolling(200, min_periods=150).mean()
trend = pd.Series(np.where(spy > sma200, "UP", "DOWN"), index=spy.index)
trend[sma200.isna()] = np.nan

# vol: trailing-20d realized vol (annualized), then EXPANDING PIT terciles.
ret1 = spy.pct_change()
rv20 = ret1.rolling(20, min_periods=20).std() * np.sqrt(252)

# PIT terciles: at each date t, rank rv20[t] against the *expanding* history rv20[:t]
# (only data up to and including t). Use expanding 33/66 percentiles. Require a
# burn-in so the terciles are meaningful (>=250 prior obs before labeling vol).
VOL_BURNIN = 250
vol_label = pd.Series(index=spy.index, dtype=object)
rv_valid = rv20.dropna()
hist_vals = []
# build cumulative percentile membership without look-ahead
for d, v in rv20.items():
    if np.isnan(v):
        continue
    if len(hist_vals) >= VOL_BURNIN:
        arr = np.asarray(hist_vals)
        q33 = np.quantile(arr, 1/3)
        q66 = np.quantile(arr, 2/3)
        if v <= q33:
            vol_label[d] = "CALM"
        elif v <= q66:
            vol_label[d] = "NORMAL"
        else:
            vol_label[d] = "VOLATILE"
    # append AFTER labeling so the current obs isn't used to set its own cutoff
    hist_vals.append(v)

regime2 = trend  # primary 2-state
regime6 = pd.Series(index=spy.index, dtype=object)
both = trend.notna() & vol_label.notna()
regime6[both] = trend[both].astype(str) + "_" + vol_label[both].astype(str)

# sanity: confirm no look-ahead — labels at date d use only data <= d.
# (trend uses rolling SMA up to d; vol uses expanding history strictly < d for cutoffs.)

# ---------------------------------------------------------------------------
# 4) Signal + forward returns
# ---------------------------------------------------------------------------
mom = px.shift(21) / px.shift(252) - 1.0  # mom_12_1

def fwd_ret(h):
    return px.shift(-h) / px - 1.0

HORIZONS = [20, 5]

def daily_ic_series(sig, fwd, dates):
    out = {}
    for d in dates:
        s = sig.loc[d]; f = fwd.loc[d]
        m = s.notna() & f.notna()
        if m.sum() < 10:
            continue
        rho = spearmanr(s[m].values, f[m].values).correlation
        if rho is not None and not np.isnan(rho):
            out[d] = rho
    return pd.Series(out)

def daily_ls_series(sig, fwd, dates):
    """top-decile minus bottom-decile fwd return per date (gross, fraction)."""
    out = {}
    for d in dates:
        s = sig.loc[d].dropna(); f = fwd.loc[d]
        common = s.index.intersection(f.dropna().index)
        if len(common) < 20:
            continue
        s = s.loc[common]; f = f.loc[common]
        q = s.rank(pct=True)
        top = f[q >= 0.9].mean(); bot = f[q <= 0.1].mean()
        if np.isnan(top) or np.isnan(bot):
            continue
        out[d] = top - bot
    return pd.Series(out)

def nw_tstat(x, lag):
    """Newey-West t-stat of the mean of x (overlapping series), Bartlett kernel."""
    x = np.asarray(x, float)
    n = len(x)
    if n < 3:
        return np.nan
    mu = x.mean()
    e = x - mu
    gamma0 = (e @ e) / n
    var = gamma0
    L = min(lag, n - 1)
    for k in range(1, L + 1):
        w = 1.0 - k / (L + 1)
        cov = (e[k:] @ e[:-k]) / n
        var += 2.0 * w * cov
    if var <= 0:
        return np.nan
    se = np.sqrt(var / n)
    return mu / se

def run_lengths(labels_on_dates):
    """mean consecutive-run length of a boolean membership over the ordered dates."""
    runs = []
    cur = 0
    for v in labels_on_dates:
        if v:
            cur += 1
        else:
            if cur > 0:
                runs.append(cur)
            cur = 0
    if cur > 0:
        runs.append(cur)
    return (np.mean(runs) if runs else 0.0), len(runs)

# within-date shuffle floor: permute fwd across names within each date, recompute
# mean IC over the *regime's* dates. Gives a per-regime noise floor that respects
# that regime's coverage/cross-section sizes.
def shuffle_floor(sig, fwd, dates, n_perm=200):
    perm_means = []
    # pre-extract aligned arrays per date once
    cache = []
    for d in dates:
        s = sig.loc[d]; f = fwd.loc[d]
        m = (s.notna() & f.notna()).values
        if m.sum() < 10:
            continue
        cache.append((s.values[m], f.values[m]))
    if not cache:
        return dict(p95_abs=np.nan, mean=np.nan, std=np.nan)
    for _ in range(n_perm):
        ics = []
        for sv, fv in cache:
            fp = fv.copy()
            rng.shuffle(fp)
            rho = spearmanr(sv, fp).correlation
            if rho is not None and not np.isnan(rho):
                ics.append(rho)
        if ics:
            perm_means.append(np.mean(ics))
    perm_means = np.array(perm_means)
    return dict(
        p95_abs=float(np.percentile(np.abs(perm_means), 95)),
        mean=float(perm_means.mean()),
        std=float(perm_means.std(ddof=1)),
    )

# valid date range: need signal history (>=252) and future (<=h)
report = {}
for h in HORIZONS:
    fwd = fwd_ret(h)
    valid = px.index[252:-h]
    ic = daily_ic_series(mom, fwd, valid)
    ls = daily_ls_series(mom, fwd, valid)
    # align regimes to IC dates
    r2 = regime2.reindex(ic.index)
    r6 = regime6.reindex(ic.index)

    rows = []
    # overall (ALL) row
    def summarize(label, mask_index, regime_series, regime_name):
        idx = ic.index[mask_index]
        sub = ic.loc[idx]
        if len(sub) < 5:
            return None
        sub_ls = ls.reindex(idx).dropna()
        floor = shuffle_floor(mom, fwd, idx, n_perm=150)
        # run-length: over the FULL ic.index, membership in this regime
        if regime_series is None:
            mean_run, n_runs = np.nan, np.nan
        else:
            member = (regime_series.reindex(ic.index) == regime_name).fillna(False).values
            mean_run, n_runs = run_lengths(member)
        gross_bps = sub_ls.mean() * 1e4 if len(sub_ls) else np.nan
        net_bps = gross_bps - COST_BPS if not np.isnan(gross_bps) else np.nan
        mean_ic = sub.mean()
        nwt = nw_tstat(sub.values, lag=h - 1)
        hit = (sub > 0).mean()
        pct_hist = len(sub) / len(ic)
        ic_over_floor = abs(mean_ic) / floor["p95_abs"] if floor["p95_abs"] and not np.isnan(floor["p95_abs"]) else np.nan
        return dict(
            regime=label, n_days=int(len(sub)), mean_ic=float(mean_ic),
            nw_t=float(nwt) if not np.isnan(nwt) else np.nan, hit_rate=float(hit),
            floor_p95_abs=floor["p95_abs"], ic_over_floor=ic_over_floor,
            gross_ls_bps=gross_bps, net_ls_bps=net_bps,
            pct_history=pct_hist, mean_run_len=mean_run, n_runs=n_runs,
        )

    # ALL
    rows.append(summarize("ALL", np.ones(len(ic), bool), None, None))
    # 2-state trend
    for lab in ["UP", "DOWN"]:
        rows.append(summarize(lab, (r2 == lab).values, regime2, lab))
    # 2x3 trend x vol
    for t in ["UP", "DOWN"]:
        for v in ["CALM", "NORMAL", "VOLATILE"]:
            lab = f"{t}_{v}"
            rows.append(summarize(lab, (r6 == lab).values, regime6, lab))
    rows = [r for r in rows if r is not None]
    report[h] = pd.DataFrame(rows)

# ---------------------------------------------------------------------------
# Per-year IC (to expose whether "UP momentum" is just the 2021-26 re-slice)
# ---------------------------------------------------------------------------
fwd20 = fwd_ret(20)
valid20 = px.index[252:-20]
ic20 = daily_ic_series(mom, fwd20, valid20)
yr_rows = []
for y, g in ic20.groupby(ic20.index.year):
    up_frac = (regime2.reindex(g.index) == "UP").mean()
    yr_rows.append(dict(year=int(y), n_days=len(g), mean_ic=float(g.mean()),
                        hit=float((g > 0).mean()), pct_UP=float(up_frac)))
yr_df = pd.DataFrame(yr_rows)

# UP-only per-year (is the UP edge consistent across years or one-year-driven?)
ic20_up = ic20[(regime2.reindex(ic20.index) == "UP").values]
yr_up_rows = []
for y, g in ic20_up.groupby(ic20_up.index.year):
    yr_up_rows.append(dict(year=int(y), n_up_days=len(g), mean_ic_UP=float(g.mean()),
                           hit_UP=float((g > 0).mean())))
yr_up_df = pd.DataFrame(yr_up_rows)

# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------
pd.set_option("display.width", 220)
pd.set_option("display.max_columns", 30)
pd.set_option("display.float_format", lambda x: f"{x:.4f}")

with open(os.path.join(OUT, "regime_ic.txt"), "w") as fh:
    for h in HORIZONS:
        hdr = f"\n================ mom_12_1 conditional IC | fwd_{h}d ================"
        print(hdr); fh.write(hdr + "\n")
        cols = ["regime", "n_days", "mean_ic", "nw_t", "hit_rate", "floor_p95_abs",
                "ic_over_floor", "gross_ls_bps", "net_ls_bps", "pct_history",
                "mean_run_len", "n_runs"]
        body = report[h][cols].to_string(index=False)
        print(body); fh.write(body + "\n")
    print("\n================ per-YEAR fwd_20d IC (overall) ================")
    fh.write("\n================ per-YEAR fwd_20d IC (overall) ================\n")
    print(yr_df.to_string(index=False)); fh.write(yr_df.to_string(index=False) + "\n")
    print("\n================ per-YEAR fwd_20d IC (UP-trend days only) ================")
    fh.write("\n================ per-YEAR fwd_20d IC (UP-trend days only) ================\n")
    print(yr_up_df.to_string(index=False)); fh.write(yr_up_df.to_string(index=False) + "\n")

report[20].to_csv(os.path.join(OUT, "regime_ic_fwd20.csv"), index=False)
report[5].to_csv(os.path.join(OUT, "regime_ic_fwd5.csv"), index=False)
yr_df.to_csv(os.path.join(OUT, "per_year_ic.csv"), index=False)
yr_up_df.to_csv(os.path.join(OUT, "per_year_ic_up.csv"), index=False)
print(f"\nWrote: {OUT}/regime_ic.txt + CSVs")
