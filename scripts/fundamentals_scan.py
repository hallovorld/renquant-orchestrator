#!/usr/bin/env python3
"""Cross-sectional fundamental factor scan (renquant-105 research lane).

Same cheap screen used by the prior orthogonal-lane scans: per-day cross-sectional
rank-IC of a factor vs forward returns, compared against a within-date label-shuffle
floor. NO CPCV / FWER / DSR -- this is a first-look triage, not a promotion gate.

The lane under test here is the last untested cheap PIT-clean orthogonal lane:
canonical fundamental value / quality / growth factors.

PIT discipline (fundamentals are slow / annual):
  * Every factor is keyed to the FILING date (`filingDate` in income_statement /
    balance_sheet / cash_flow), not the fiscal period-end. A factor value only
    becomes "known" `LAG_DAYS` trading days AFTER the filing was accepted.
  * key_metrics / ratios / financial_growth do NOT carry filingDate; we attach it
    from income_statement on (symbol, fiscalYear) and apply the same lag.
  * Price-based value factors (earnings yield, book/price, FCF yield) use the
    *filed per-share fundamental* in the numerator and the *current daily price*
    from the bars panel in the denominator. This is the correct PIT construction:
    the fundamental is stale (annual), the price is live.
  * Each filed value is held constant from (filingDate + lag) until the next filing
    -- a step function refreshed roughly once a year. Turnover is therefore tiny.

Survivorship caveat: the 134-name universe is today's large-cap watchlist projected
backwards. Names that were small/distressed and never made the list are absent, so a
value/quality "works" reading would be optimistic. We report this, we do not correct it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HARVEST = Path("/Users/renhao/git/github/RenQuant/data/fmp_harvest")
BARS = Path("/tmp/sighunt/bars.parquet")

LAG_DAYS = 2            # trading days after acceptedDate before a filing is "known"
HORIZONS = [20, 60, 120, 252]
N_SHUFFLE = 200         # within-date label shuffles for the null floor
BLOCK = 21              # ~1 month block for the block-bootstrap t-stat
MIN_NAMES = 20          # require this many ranked names on a date to score it
SEED = 13


# --------------------------------------------------------------------------- IO
def _load(name: str) -> pd.DataFrame:
    return pd.read_parquet(HARVEST / f"{name}_291.parquet")


def load_inputs():
    bars = pd.read_parquet(BARS)
    bars.index = pd.to_datetime(bars.index)
    bars = bars.sort_index()
    universe = list(bars.columns)

    inc = _load("income_statement")
    bs = _load("balance_sheet")
    cf = _load("cash_flow")
    km = _load("key_metrics")
    fg = _load("financial_growth")

    for df in (inc, bs, cf):
        df["filingDate"] = pd.to_datetime(df["filingDate"])
        df["acceptedDate"] = pd.to_datetime(df["acceptedDate"])
        df["date"] = pd.to_datetime(df["date"])
    for df in (km, fg):
        df["date"] = pd.to_datetime(df["date"])

    # restrict to bars universe everywhere
    inc = inc[inc.symbol.isin(universe)].copy()
    bs = bs[bs.symbol.isin(universe)].copy()
    cf = cf[cf.symbol.isin(universe)].copy()
    km = km[km.symbol.isin(universe)].copy()
    fg = fg[fg.symbol.isin(universe)].copy()
    return bars, inc, bs, cf, km, fg


# ----------------------------------------------------------------- factor build
def _filing_key(inc: pd.DataFrame) -> pd.DataFrame:
    """One row per (symbol, fiscalYear) -> the accepted/filing timestamp.

    acceptedDate is the wall-clock the 10-K hit EDGAR; that is the earliest a
    cross-sectional ranker could have used the numbers.
    """
    k = (
        inc[["symbol", "fiscalYear", "filingDate", "acceptedDate"]]
        .dropna(subset=["filingDate"])
        .sort_values("acceptedDate")
        .drop_duplicates(["symbol", "fiscalYear"], keep="last")
    )
    return k


def build_factor_frames(inc, bs, cf, km, fg):
    """Return a dict {factor_name: long DataFrame[symbol, known_date, value, price_based]}.

    `known_date` is the calendar date the value becomes usable (filingDate; the
    extra trading-day lag is applied later when we as-of merge onto the bar grid).
    `price_based` flags factors whose numerator is a filed per-share quantity that
    we later divide by the live price.
    """
    fkey = _filing_key(inc)

    def attach_filing(df: pd.DataFrame) -> pd.DataFrame:
        if "filingDate" in df.columns:
            # native filingDate (income / balance / cash_flow) -- trust it directly
            out = df.copy()
            out["known_date"] = pd.to_datetime(out["filingDate"])
        else:
            # key_metrics / financial_growth carry no filingDate; attach from income
            out = df.merge(fkey[["symbol", "fiscalYear", "filingDate"]],
                           on=["symbol", "fiscalYear"], how="left")
            out["known_date"] = pd.to_datetime(out["filingDate"])
        return out.dropna(subset=["known_date"])

    inc_f = attach_filing(inc)
    bs_f = attach_filing(bs)
    cf_f = attach_filing(cf)
    km_f = attach_filing(km)
    fg_f = attach_filing(fg)

    frames: dict[str, pd.DataFrame] = {}

    def emit(name, df, valuecol, price_based=False):
        sub = df[["symbol", "known_date", valuecol]].rename(columns={valuecol: "value"})
        sub = sub.replace([np.inf, -np.inf], np.nan).dropna(subset=["value"])
        sub["price_based"] = price_based
        frames[name] = sub.sort_values("known_date")

    # ---- VALUE (price-based: filed per-share numerator / live price) ----------
    # earnings yield = diluted EPS (TTM annual) / price
    inc_f = inc_f.copy()
    inc_f["eps_use"] = inc_f["epsDiluted"].where(inc_f["epsDiluted"].notna(), inc_f["eps"])
    emit("value_earnings_yield", inc_f, "eps_use", price_based=True)

    # book / price = book value per share / price  (BVPS from equity / shares)
    bvps = bs_f.merge(
        inc_f[["symbol", "fiscalYear", "weightedAverageShsOut"]],
        on=["symbol", "fiscalYear"], how="left",
    )
    bvps["bvps"] = bvps["totalStockholdersEquity"] / bvps["weightedAverageShsOut"]
    emit("value_book_to_price", bvps, "bvps", price_based=True)

    # FCF yield = FCF per share / price
    fcfps = cf_f.merge(
        inc_f[["symbol", "fiscalYear", "weightedAverageShsOut"]],
        on=["symbol", "fiscalYear"], how="left",
    )
    fcfps["fcfps"] = fcfps["freeCashFlow"] / fcfps["weightedAverageShsOut"]
    emit("value_fcf_yield", fcfps, "fcfps", price_based=True)

    # EV/EBIT inverted = EBIT / EnterpriseValue. EV here uses the period-end EV from
    # key_metrics (frozen at fiscal year-end) -- NOT recomputed on the live price, so
    # this one is a *stale* multiple, weaker PIT-wise than the live-price value trio.
    eb = km_f.merge(inc_f[["symbol", "fiscalYear", "ebit"]],
                    on=["symbol", "fiscalYear"], how="left")
    eb["ebit_to_ev"] = eb["ebit"] / eb["enterpriseValue"]
    emit("value_ebit_to_ev", eb, "ebit_to_ev", price_based=False)

    # ---- QUALITY -------------------------------------------------------------
    emit("quality_roe", km_f, "returnOnEquity")
    # gross margin = grossProfit / revenue (recomputed; robust to vendor field gaps)
    inc_f["gross_margin"] = inc_f["grossProfit"] / inc_f["revenue"]
    emit("quality_gross_margin", inc_f, "gross_margin")
    # accruals (Sloan), signed so HIGHER = better quality: -(NI - CFO)/TotalAssets
    acc = cf_f.merge(bs_f[["symbol", "fiscalYear", "totalAssets"]],
                     on=["symbol", "fiscalYear"], how="left")
    acc["neg_accruals"] = -((acc["netIncome"] - acc["operatingCashFlow"]) / acc["totalAssets"])
    emit("quality_low_accruals", acc, "neg_accruals")

    # ---- GROWTH --------------------------------------------------------------
    emit("growth_revenue", fg_f, "revenueGrowth")
    emit("growth_eps", fg_f, "epsgrowth")

    return frames


# ------------------------------------------------------------ as-of to bar grid
def asof_panel(frame: pd.DataFrame, dates: pd.DatetimeIndex, lag_days: int) -> pd.DataFrame:
    """Forward-fill the step-function factor onto the daily bar grid.

    For each symbol: sort filings by known_date, shift the effective date forward
    by `lag_days` trading days, then as-of (backward) merge onto the bar dates so a
    value only appears on/after it was usable. Returns wide [date x symbol].
    """
    dates = pd.DatetimeIndex(sorted(dates))
    pos = pd.Series(np.arange(len(dates)), index=dates)
    out = {}
    for sym, g in frame.groupby("symbol"):
        g = g.sort_values("known_date")
        # map each filing's known_date to the bar index >= known_date, then + lag
        idx = dates.searchsorted(g["known_date"].values, side="left") + lag_days
        idx = np.clip(idx, 0, len(dates) - 1)
        eff_dates = dates[idx]
        s = pd.Series(g["value"].values, index=eff_dates)
        s = s[~s.index.duplicated(keep="last")]
        out[sym] = s.reindex(dates).ffill()
    return pd.DataFrame(out, index=dates)


def fwd_returns(bars: pd.DataFrame, h: int) -> pd.DataFrame:
    return bars.shift(-h) / bars - 1.0


# ----------------------------------------------------------------------- rank-IC
def _rank(df: pd.DataFrame) -> pd.DataFrame:
    return df.rank(axis=1)


def daily_rank_ic(fac: pd.DataFrame, fwd: pd.DataFrame, min_names: int) -> pd.Series:
    """Spearman (rank-rank Pearson) IC per date."""
    fr = _rank(fac)
    rr = _rank(fwd.where(fac.notna()))
    fr = fr.where(rr.notna())
    rr = rr.where(fr.notna())
    n = fr.notna().sum(axis=1)
    fr = fr.sub(fr.mean(axis=1), axis=0)
    rr = rr.sub(rr.mean(axis=1), axis=0)
    num = (fr * rr).sum(axis=1)
    den = np.sqrt((fr ** 2).sum(axis=1) * (rr ** 2).sum(axis=1))
    ic = num / den.replace(0, np.nan)
    return ic.where(n >= min_names)


def block_t(ic: pd.Series, block: int, rng: np.random.Generator, n_boot: int = 1000) -> float:
    x = ic.dropna().values
    if len(x) < block * 3:
        return np.nan
    mean = x.mean()
    n = len(x)
    n_blocks = int(np.ceil(n / block))
    means = np.empty(n_boot)
    starts_max = n - block
    for b in range(n_boot):
        starts = rng.integers(0, starts_max + 1, size=n_blocks)
        samp = np.concatenate([x[s:s + block] for s in starts])[:n]
        means[b] = samp.mean()
    se = means.std(ddof=1)
    return mean / se if se > 0 else np.nan


def shuffle_floor(fac: pd.DataFrame, fwd: pd.DataFrame, min_names: int,
                  rng: np.random.Generator, n_shuffle: int) -> float:
    """Mean |IC| achievable by shuffling the forward-return labels WITHIN each date.

    This is the cross-sectional null: same date structure, same coverage, the
    factor-return link destroyed. A real factor's mean IC must clear this floor.
    """
    base_ic = daily_rank_ic(fac, fwd, min_names)
    valid = base_ic.dropna().index
    if len(valid) == 0:
        return np.nan
    fac_v = fac.loc[valid]
    fwd_v = fwd.loc[valid]
    fr = _rank(fac_v)
    means = np.empty(n_shuffle)
    fwd_vals = fwd_v.where(fac_v.notna()).values  # date x sym
    fr_vals = fr.where(fwd_v.notna()).values
    for s in range(n_shuffle):
        shuffled = np.full_like(fwd_vals, np.nan, dtype=float)
        for i in range(fwd_vals.shape[0]):
            row = fwd_vals[i]
            mask = ~np.isnan(row)
            vals = row[mask]
            perm = rng.permutation(vals)
            shuffled[i, mask] = perm
        rr = pd.DataFrame(shuffled, index=fwd_v.index, columns=fwd_v.columns).rank(axis=1)
        frd = pd.DataFrame(fr_vals, index=fr.index, columns=fr.columns)
        a = frd.sub(frd.mean(axis=1), axis=0)
        b = rr.sub(rr.mean(axis=1), axis=0)
        num = (a * b).sum(axis=1)
        den = np.sqrt((a ** 2).sum(axis=1) * (b ** 2).sum(axis=1))
        ic = (num / den.replace(0, np.nan))
        means[s] = ic.mean()
    return float(np.nanmean(np.abs(means)))


def ls_decile_bps(fac: pd.DataFrame, fwd: pd.DataFrame, min_names: int) -> float:
    """Mean forward return of top decile minus bottom decile, in bps, per period.

    Not annualized, not turnover-netted -- a raw spread readout.
    """
    spreads = []
    for dt, row in fac.iterrows():
        r = row.dropna()
        f = fwd.loc[dt, r.index].dropna()
        r = r.loc[f.index]
        if len(r) < min_names:
            continue
        k = max(1, int(round(len(r) * 0.1)))
        order = r.sort_values()
        bot = f.loc[order.index[:k]].mean()
        top = f.loc[order.index[-k:]].mean()
        spreads.append(top - bot)
    if not spreads:
        return np.nan
    return float(np.nanmean(spreads) * 1e4)


# --------------------------------------------------------------------------- run
def scan(bars, frames, lag_days, horizons):
    rng = np.random.default_rng(SEED)
    dates = bars.index
    rows = []
    for name, frame in frames.items():
        fac = asof_panel(frame, dates, lag_days)
        cov = fac.notna().sum(axis=1)
        active = fac.loc[cov >= MIN_NAMES]
        if active.empty:
            print(f"[skip] {name}: never reaches {MIN_NAMES} ranked names", file=sys.stderr)
            continue
        first_active = active.index.min()
        for h in horizons:
            fwd = fwd_returns(bars, h)
            f = fac.loc[fac.index >= first_active]
            w = fwd.loc[f.index]
            ic = daily_rank_ic(f, w, MIN_NAMES)
            ic_valid = ic.dropna()
            if ic_valid.empty:
                continue
            mean_ic = ic_valid.mean()
            t = block_t(ic, BLOCK, rng)
            hit = float((ic_valid > 0).mean())
            floor = shuffle_floor(f, w, MIN_NAMES, rng, N_SHUFFLE)
            ratio = abs(mean_ic) / floor if floor and floor > 0 else np.nan
            ls = ls_decile_bps(f, w, MIN_NAMES)
            rows.append({
                "factor": name,
                "horizon_d": h,
                "n_dates": int(len(ic_valid)),
                "mean_ic": round(mean_ic, 4),
                "block_t": round(t, 2) if t == t else np.nan,
                "hit_rate": round(hit, 3),
                "shuffle_floor": round(floor, 4),
                "ic_over_floor": round(ratio, 2) if ratio == ratio else np.nan,
                "ls_decile_bps": round(ls, 1) if ls == ls else np.nan,
            })
            print(f"  {name:26s} h={h:3d}  IC={mean_ic:+.4f}  t={t:5.2f}  "
                  f"hit={hit:.2f}  floor={floor:.4f}  IC/floor={ratio:4.2f}  "
                  f"L/S={ls:+7.1f}bps  n={len(ic_valid)}", file=sys.stderr)
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=None, help="optional CSV output path")
    ap.add_argument("--lag-days", type=int, default=LAG_DAYS)
    args = ap.parse_args()

    bars, inc, bs, cf, km, fg = load_inputs()
    print(f"universe={len(bars.columns)} dates={len(bars)} "
          f"({bars.index.min().date()}..{bars.index.max().date()}) lag={args.lag_days}d",
          file=sys.stderr)
    frames = build_factor_frames(inc, bs, cf, km, fg)
    print(f"factors: {list(frames)}", file=sys.stderr)
    res = scan(bars, frames, args.lag_days, HORIZONS)
    res = res.sort_values(["factor", "horizon_d"]).reset_index(drop=True)
    print("\n=== RESULT TABLE ===")
    print(res.to_string(index=False))
    if args.out:
        res.to_csv(args.out, index=False)
        print(f"\nwrote {args.out}", file=sys.stderr)
    return res


if __name__ == "__main__":
    main()
