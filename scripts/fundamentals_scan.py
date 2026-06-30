#!/usr/bin/env python3
"""Cross-sectional fundamental factor scan (renquant-105 research lane).

Same cheap screen used by the prior orthogonal-lane scans: per-day cross-sectional
rank-IC of a factor vs forward returns, compared against a within-date label-shuffle
floor. NO CPCV / FWER / DSR -- this is a first-look triage, not a promotion gate.

WHAT THIS IS (and is NOT)
-------------------------
This is a CURRENT-VINTAGE RETROSPECTIVE DIAGNOSTIC, not a point-in-time backtest.
The fundamentals come from a single one-shot FMP `/stable` annual harvest taken on
the harvest date recorded in the per-endpoint manifest (see the harvest *.manifest
files). We attach each row's `acceptedDate` / `filingDate` and lag it, but we DO
NOT retain the as-filed snapshot: a historical annual row in a current harvest can
already reflect later restatements / revisions, and we cannot verify each value
equals what was visible on its original acceptance date. So the time-alignment here
is a best-effort *vintage* alignment, NOT proven as-filed PIT. Treat every result
as a directional probe on a biased current-watchlist panel, nothing stronger.

Timing discipline (best-effort vintage alignment, annual cadence)
-----------------------------------------------------------------
  * Every factor is keyed to `acceptedDate` (the wall-clock the filing was accepted)
    when present on the source statement, falling back to `filingDate` when
    acceptedDate is missing. A value only becomes "known" on the NEXT trading
    session at/after acceptance, plus `LAG_DAYS` extra trading-day(s) of slack.
  * income_statement / balance_sheet / cash_flow carry acceptedDate natively.
    key_metrics / financial_growth do NOT; we attach (acceptedDate, filingDate) from
    income_statement on (symbol, fiscalYear) and apply the same next-session rule.
  * Price-based value factors (earnings yield, book/price, FCF yield) use the
    *harvested per-share fundamental* in the numerator and the *current daily price*
    from the bars panel in the denominator. The fundamental is stale (annual,
    current-vintage); the price is live.
  * Each value is held constant from its effective session until the next filing --
    a step function refreshed roughly once a year. Turnover is therefore tiny.

Dependence / significance
--------------------------
Forward returns overlap up to the horizon (252 trading days), so the daily-IC
series is heavily autocorrelated (lag-1 ~0.98 at 252d). A short fixed block
bootstrap badly understates uncertainty. We therefore report, per factor/horizon:
  * `nonover_t`: a t-stat on NON-OVERLAPPING IC samples (one IC every `h` sessions)
    -- independent windows, the most honest (smallest-n) significance read.
  * `sb_t_<L>`: stationary-bootstrap (Politis-Romano, geometric blocks) t-stats at
    several mean block lengths L, as a SENSITIVITY sweep. We do NOT cherry-pick one.
None of these makes the panel PIT or unbiased; they only stop the t from being
inflated by overlap. Read them as soft, biased-panel diagnostics.

Survivorship caveat (framing fixed)
-----------------------------------
The 134-name universe is today's surviving large-cap watchlist projected backward.
Failed / delisted / distressed names that a real historical value screen would have
held are absent. This does NOT cleanly "harden" any conclusion: it removes names
and shifts both ranks and realized returns in directionally AMBIGUOUS ways for a
value test. All conclusions are limited to THIS biased current-watchlist panel.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

HARVEST = Path("/Users/renhao/git/github/RenQuant/data/fmp_harvest")
BARS = Path("/tmp/sighunt/bars.parquet")
HARVEST_TAG = "291"  # harvest file suffix, e.g. income_statement_291.parquet

LAG_DAYS = 1               # extra trading-day slack ON TOP OF the next-session rule
HORIZONS = [20, 60, 120, 252]
N_SHUFFLE = 200            # within-date label shuffles for the (deflated) null floor
SB_BLOCKS = [21, 63, 126, 252]   # mean block lengths for the stationary-bootstrap sweep
N_BOOT = 1000             # stationary-bootstrap resamples per block length
MIN_NAMES = 20            # require this many ranked names on a date to score it
SEED = 13


# ---------------------------------------------------------------- reproducibility
def sha256_file(path) -> str | None:
    if not path or not os.path.exists(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def git_commit() -> str | None:
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        return subprocess.check_output(
            ["git", "-C", here, "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
    except Exception:
        return None


def read_harvest_manifest(name: str) -> dict | None:
    p = HARVEST / f"{name}_{HARVEST_TAG}.manifest.json"
    if not p.exists():
        return None
    try:
        m = json.loads(p.read_text())
        return {k: m.get(k) for k in ("endpoint", "path_template", "url_base",
                                      "sha256", "started_at", "finished_at", "status")}
    except Exception:
        return None


# --------------------------------------------------------------------------- IO
def _load(name: str) -> pd.DataFrame:
    return pd.read_parquet(HARVEST / f"{name}_{HARVEST_TAG}.parquet")


def load_inputs(as_of: pd.Timestamp):
    bars = pd.read_parquet(BARS)
    bars.index = pd.to_datetime(bars.index)
    bars = bars.sort_index()
    # Respect the pinned as-of: never use bars after it (reproducible window).
    bars = bars[bars.index <= as_of]
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
def _known_ts(df: pd.DataFrame) -> pd.Series:
    """Earliest usable timestamp: acceptedDate when present, else filingDate.

    acceptedDate is the wall-clock the filing was accepted (often after-hours, and
    in ~16% of rows the calendar day BEFORE filingDate). It is the earliest a
    cross-sectional ranker could have used the numbers. We floor to next session
    later via searchsorted, so the intraday time only decides which session counts.
    """
    accepted = pd.to_datetime(df["acceptedDate"])
    filing = pd.to_datetime(df["filingDate"])
    return accepted.where(accepted.notna(), filing)


def _filing_key(inc: pd.DataFrame) -> pd.DataFrame:
    """One row per (symbol, fiscalYear) -> (acceptedDate, filingDate)."""
    k = inc[["symbol", "fiscalYear", "filingDate", "acceptedDate"]].copy()
    k = k.dropna(subset=["filingDate"]).sort_values("acceptedDate")
    k = k.drop_duplicates(["symbol", "fiscalYear"], keep="last")
    return k


def build_factor_frames(inc, bs, cf, km, fg):
    """Return {factor_name: long DataFrame[symbol, known_ts, value, price_based]}.

    `known_ts` is the acceptedDate-or-filingDate timestamp the value becomes usable;
    the next-session + lag rule is applied later in `asof_panel`. `price_based`
    flags factors whose numerator is a filed per-share quantity divided by the live
    price.
    """
    fkey = _filing_key(inc)

    def attach_known(df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()
        if "acceptedDate" in out.columns:
            # native acceptedDate (income / balance / cash_flow)
            out["known_ts"] = _known_ts(out)
        else:
            # key_metrics / financial_growth: attach acceptedDate+filingDate from income
            out = out.merge(
                fkey[["symbol", "fiscalYear", "acceptedDate", "filingDate"]],
                on=["symbol", "fiscalYear"], how="left",
            )
            out["known_ts"] = _known_ts(out)
        return out.dropna(subset=["known_ts"])

    inc_f = attach_known(inc)
    bs_f = attach_known(bs)
    cf_f = attach_known(cf)
    km_f = attach_known(km)
    fg_f = attach_known(fg)

    frames: dict[str, pd.DataFrame] = {}

    def emit(name, df, valuecol, price_based=False):
        sub = df[["symbol", "known_ts", valuecol]].rename(columns={valuecol: "value"})
        sub = sub.replace([np.inf, -np.inf], np.nan).dropna(subset=["value"])
        sub["price_based"] = price_based
        frames[name] = sub.sort_values("known_ts")

    # ---- VALUE (price-based: per-share numerator / live price) ----------------
    inc_f = inc_f.copy()
    inc_f["eps_use"] = inc_f["epsDiluted"].where(inc_f["epsDiluted"].notna(), inc_f["eps"])
    emit("value_earnings_yield", inc_f, "eps_use", price_based=True)

    bvps = bs_f.merge(
        inc_f[["symbol", "fiscalYear", "weightedAverageShsOut"]],
        on=["symbol", "fiscalYear"], how="left",
    )
    bvps["bvps"] = bvps["totalStockholdersEquity"] / bvps["weightedAverageShsOut"]
    emit("value_book_to_price", bvps, "bvps", price_based=True)

    fcfps = cf_f.merge(
        inc_f[["symbol", "fiscalYear", "weightedAverageShsOut"]],
        on=["symbol", "fiscalYear"], how="left",
    )
    fcfps["fcfps"] = fcfps["freeCashFlow"] / fcfps["weightedAverageShsOut"]
    emit("value_fcf_yield", fcfps, "fcfps", price_based=True)

    # EV/EBIT inverted = EBIT / period-end EnterpriseValue (frozen at fiscal year-end,
    # NOT recomputed on the live price) -- a stale multiple, weakest vintage-wise.
    eb = km_f.merge(inc_f[["symbol", "fiscalYear", "ebit"]],
                    on=["symbol", "fiscalYear"], how="left")
    eb["ebit_to_ev"] = eb["ebit"] / eb["enterpriseValue"]
    emit("value_ebit_to_ev", eb, "ebit_to_ev", price_based=False)

    # ---- QUALITY -------------------------------------------------------------
    emit("quality_roe", km_f, "returnOnEquity")
    inc_f["gross_margin"] = inc_f["grossProfit"] / inc_f["revenue"]
    emit("quality_gross_margin", inc_f, "gross_margin")
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

    For each symbol: sort filings by known_ts, map each known_ts to the FIRST bar
    session >= known_ts (the next usable session), add `lag_days` trading-day slack,
    then forward-fill so a value only appears on/after it was usable.
    """
    dates = pd.DatetimeIndex(sorted(dates))
    out = {}
    for sym, g in frame.groupby("symbol"):
        g = g.sort_values("known_ts")
        # next session at/after acceptance (side="left" => first bar >= known_ts),
        # then +lag_days extra slack.
        idx = dates.searchsorted(g["known_ts"].values, side="left") + lag_days
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


def lag1_autocorr(ic: pd.Series) -> float:
    x = ic.dropna().values
    if len(x) < 3:
        return np.nan
    return float(np.corrcoef(x[:-1], x[1:])[0, 1])


def nonoverlap_t(ic: pd.Series, h: int) -> tuple[float, int]:
    """t-stat on NON-OVERLAPPING IC samples (one IC every `h` sessions).

    Forward windows separated by >= h sessions do not overlap, so these samples are
    (approximately) independent and an ordinary t-stat is honest. Returns (t, n).
    """
    x = ic.dropna()
    if x.empty:
        return np.nan, 0
    sub = x.iloc[::h].values
    n = len(sub)
    if n < 3:
        return np.nan, n
    sd = sub.std(ddof=1)
    if not (sd > 0):
        return np.nan, n
    return float(sub.mean() / (sd / np.sqrt(n))), n


def stationary_bootstrap_t(ic: pd.Series, mean_block: int,
                           rng: np.random.Generator, n_boot: int) -> float:
    """Politis-Romano stationary-bootstrap t-stat of the daily-IC mean.

    Geometric block lengths with mean `mean_block` wrap-resample the IC series so
    long-range dependence (overlapping forward windows) is preserved on average.
    SE = std of the bootstrap means; t = mean / SE. Larger mean_block => more
    dependence retained => wider SE => smaller (more honest) t.

    Vectorised: build an (n_boot x n) wrapped-index matrix. At each column a new
    block starts with prob p (fresh uniform start), else the index advances by 1
    (mod n) -- exactly the Politis-Romano stationary bootstrap.
    """
    x = ic.dropna().values
    n = len(x)
    if n < max(3 * mean_block, 30):
        return np.nan
    mean = x.mean()
    p = 1.0 / max(1, mean_block)
    idx = np.empty((n_boot, n), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n, size=n_boot)
    new_block = rng.random((n_boot, n)) < p          # restart mask
    fresh = rng.integers(0, n, size=(n_boot, n))     # fresh starts when restarting
    for j in range(1, n):
        cont = (idx[:, j - 1] + 1) % n
        idx[:, j] = np.where(new_block[:, j], fresh[:, j], cont)
    means = x[idx].mean(axis=1)
    se = means.std(ddof=1)
    return float(mean / se) if se > 0 else np.nan


def shuffle_floor(fac: pd.DataFrame, fwd: pd.DataFrame, min_names: int,
                  rng: np.random.Generator, n_shuffle: int) -> float:
    """Mean |IC| achievable by shuffling the forward-return labels WITHIN each date.

    NOTE: this floor is DEFLATED by overlapping forward windows -- it is the
    cross-sectional null with date structure intact but per-date independence
    assumed, which the overlap violates. Reported for transparency, NOT used for the
    verdict; the dependence-aware t-stats above are load-bearing.
    """
    base_ic = daily_rank_ic(fac, fwd, min_names)
    valid = base_ic.dropna().index
    if len(valid) == 0:
        return np.nan
    fac_v = fac.loc[valid]
    fwd_v = fwd.loc[valid]
    fr = _rank(fac_v)
    means = np.empty(n_shuffle)
    fwd_vals = fwd_v.where(fac_v.notna()).values
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
    """Top-decile minus bottom-decile mean forward return, in bps, per period."""
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
def scan(bars, frames, lag_days, horizons, sb_blocks, n_boot, n_shuffle):
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
            ac1 = lag1_autocorr(ic)
            no_t, no_n = nonoverlap_t(ic, h)
            sb_t = {L: stationary_bootstrap_t(ic, L, rng, n_boot) for L in sb_blocks}
            hit = float((ic_valid > 0).mean())
            floor = shuffle_floor(f, w, MIN_NAMES, rng, n_shuffle)
            ls = ls_decile_bps(f, w, MIN_NAMES)
            row = {
                "factor": name,
                "horizon_d": h,
                "n_dates": int(len(ic_valid)),
                "mean_ic": round(mean_ic, 4),
                "ic_lag1_autocorr": round(ac1, 3) if ac1 == ac1 else np.nan,
                "nonover_t": round(no_t, 2) if no_t == no_t else np.nan,
                "nonover_n": no_n,
                "hit_rate": round(hit, 3),
                "shuffle_floor": round(floor, 4),
                "ls_decile_bps": round(ls, 1) if ls == ls else np.nan,
            }
            for L in sb_blocks:
                v = sb_t[L]
                row[f"sb_t_{L}"] = round(v, 2) if v == v else np.nan
            rows.append(row)
            sb_str = " ".join(
                f"sb{L}={sb_t[L]:+.2f}" if sb_t[L] == sb_t[L] else f"sb{L}=  nan"
                for L in sb_blocks
            )
            print(f"  {name:26s} h={h:3d}  IC={mean_ic:+.4f}  ac1={ac1:.2f}  "
                  f"nonover_t={no_t:+.2f}(n={no_n})  {sb_str}  "
                  f"hit={hit:.2f}  L/S={ls:+7.1f}bps  n={len(ic_valid)}", file=sys.stderr)
    return pd.DataFrame(rows)


def build_manifest(args, bars, frames, sb_blocks):
    symbols = list(bars.columns)
    harvest_manifests = {
        n: read_harvest_manifest(n)
        for n in ("income_statement", "balance_sheet", "cash_flow",
                  "key_metrics", "financial_growth")
    }
    inputs = {
        f"{n}_{HARVEST_TAG}.parquet": sha256_file(HARVEST / f"{n}_{HARVEST_TAG}.parquet")
        for n in ("income_statement", "balance_sheet", "cash_flow",
                  "key_metrics", "financial_growth")
    }
    return dict(
        script="scripts/fundamentals_scan.py",
        kind=("current-vintage retrospective diagnostic on a biased current-watchlist "
              "panel -- NOT proven as-filed PIT, NOT survivorship-corrected"),
        as_of=str(pd.Timestamp(args.as_of).date()),
        code_commit=git_commit(),
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        bars_cache=str(BARS),
        bars_cache_sha256=sha256_file(BARS),
        harvest_dir=str(HARVEST),
        harvest_tag=HARVEST_TAG,
        harvest_inputs_sha256=inputs,
        harvest_endpoint_manifests=harvest_manifests,
        parameters=dict(
            lag_days=args.lag_days, horizons=HORIZONS, min_names=MIN_NAMES,
            sb_blocks=sb_blocks, n_boot=args.n_boot, n_shuffle=args.n_shuffle,
            seed=SEED, timing="acceptedDate-or-filingDate, next-session + lag_days",
        ),
        panel=dict(
            days=int(bars.shape[0]), names=int(bars.shape[1]),
            start=str(bars.index.min().date()), end=str(bars.index.max().date()),
        ),
        factors=list(frames),
        kept_symbols=symbols,
        kept_symbols_sha256=sha256_text(",".join(symbols)),
    )


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--as-of", required=True,
                    help="Pinned end date YYYY-MM-DD (no datetime.now). Bars end here.")
    ap.add_argument("--out", default="/tmp/fund_scan",
                    help="Output directory for results.csv + manifest.json.")
    ap.add_argument("--lag-days", type=int, default=LAG_DAYS,
                    help="Extra trading-day slack on top of the next-session rule.")
    ap.add_argument("--n-boot", type=int, default=N_BOOT,
                    help="Stationary-bootstrap resamples per block length.")
    ap.add_argument("--n-shuffle", type=int, default=N_SHUFFLE,
                    help="Within-date label shuffles for the (deflated) floor.")
    args = ap.parse_args()

    as_of = pd.Timestamp(args.as_of).normalize()
    os.makedirs(args.out, exist_ok=True)

    bars, inc, bs, cf, km, fg = load_inputs(as_of)
    print(f"universe={len(bars.columns)} dates={len(bars)} "
          f"({bars.index.min().date()}..{bars.index.max().date()}) "
          f"as_of={as_of.date()} lag={args.lag_days}d "
          f"sb_blocks={SB_BLOCKS}", file=sys.stderr)
    frames = build_factor_frames(inc, bs, cf, km, fg)
    print(f"factors: {list(frames)}", file=sys.stderr)
    res = scan(bars, frames, args.lag_days, HORIZONS, SB_BLOCKS, args.n_boot, args.n_shuffle)
    res = res.sort_values(["factor", "horizon_d"]).reset_index(drop=True)

    print("\n=== RESULT TABLE ===")
    print(res.to_string(index=False))

    csv_path = os.path.join(args.out, "results.csv")
    res.to_csv(csv_path, index=False)
    manifest = build_manifest(args, bars, frames, SB_BLOCKS)
    man_path = os.path.join(args.out, "manifest.json")
    with open(man_path, "w") as f:
        json.dump(manifest, f, indent=2)
    print(f"\nwrote {csv_path}", file=sys.stderr)
    print(f"wrote {man_path}", file=sys.stderr)
    print(f"kept_symbols_sha256={manifest['kept_symbols_sha256'][:12]} "
          f"code_commit={manifest['code_commit']}", file=sys.stderr)
    return res


if __name__ == "__main__":
    main()
