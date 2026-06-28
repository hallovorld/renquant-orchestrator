#!/usr/bin/env python
"""
MONETIZATION under FAITHFUL turnover costs + NEXT-SESSION entry for the short-horizon
minute candidate from scripts/minute_feature_scan.py (#206).

NOTE (corrected, 2026-06-28): after the review fixes (DST-correct RTH, NEXT-SESSION
entry, proper FWL marginal IC), the minute features carry NO marginal IC over the
daily price factors at 1d/3d -- the old +0.02-0.03 "marginal IC" was an artifact of
(a) DST-contaminated pre/after-hours bars and (b) an optimistic same-close entry.
This cost test now exists to CONFIRM the negative economically: with a tradable
next-session entry and realistic cost, the market-neutral L/S does NOT monetize.

WHAT IT DOES:
  1. SIGNAL: standardized minute features, PIT as-of day D's RTH close (DST-correct),
     ENTERED at the OPEN of the next session D+1. vwap_dev (primary) AND an
     equal-weight cross-sectional combo of {vwap_dev, intraday_mom_last, close_loc}.
  2. PORTFOLIOS: cross-sectional, rebalanced at 1-DAY and 3-DAY frequency:
       - top-decile / top-quintile LONG-ONLY (equal-weight),
       - top-minus-bottom decile market-neutral L/S (the clean read).
  3. NEXT-SESSION ENTRY: a position formed from D's signal is ENTERED at open[D+1]
     and exited at close[D+step]; per-period return = close[D+step]/open[D+1] - 1.
     No same-close execution.
  4. FAITHFUL COSTS: turnover from ACTUAL weight changes (sum|w_t-w_{t-1}|/2 = one-way
     fraction traded); round-trip cost SENSITIVITY 5 / 11 / 20 bps; net = gross-cost.
  5. REPORT: gross + NET annualized return, NET Sharpe, realized turnover, BREAKEVEN
     round-trip cost, ACTIVE-DAY exposure, and a chronological OOS split (same 70/30
     as the scan) so the economics are reported in-sample AND out-of-sample.

PIT / NO LOOK-AHEAD: feature for day D uses only minute bars < D's RTH close
(identical to #206's build_features). Entry is the NEXT session's open; the realized
return is strictly future of the signal. The pinned --as-of caps minute pull + labels.

READ-ONLY. Reuses #206's cached minute panel (--min-cache) and sighunt's daily close
panel (--daily-bars). No Alpaca credentials needed when the cache is present. No
orders, no canonical writes, no live-tree git. Output/cache under --out.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

from minute_rth import rth_filter

DEFAULT_CFG = "/Users/renhao/git/github/RenQuant/backtesting/renquant_104/strategy_config.golden.json"
ETFS = {"SPY", "GLD", "TLT", "XLE", "XLF", "XLI", "XLK", "XLU", "XLY", "XLV"}
STEPS = [1, 3]                  # rebalance frequencies tested
ROUND_TRIP_BPS = [5.0, 11.0, 20.0]  # round-trip cost sensitivity band (base 11)
TRADING_DAYS = 252.0
OOS_FRAC = 0.70
COMBO_FEATURES = ["vwap_dev", "intraday_mom_last", "close_loc"]


# ----------------------------------------------------------------------------- #
# repro helpers (mirror minute_feature_scan.py)
# ----------------------------------------------------------------------------- #
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
            ["git", "-C", here, "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return None


def load_universe(cfg_path):
    wl = json.load(open(cfg_path))["watchlist"]
    universe = [t for t in wl if t not in ETFS]
    print(f"[universe] {len(universe)} single names "
          f"(dropped {len(set(wl) & ETFS)} ETFs from {len(wl)}) <- {cfg_path}", flush=True)
    return universe


def build_features(minbars, daily_close, kept):
    """IDENTICAL feature construction to minute_feature_scan.py (#206): PIT
    cross-sectional features as-of each day's close, plus the per-(symbol,session)
    day OPEN (first RTH bar open) so entry is the tradable NEXT-session open. We
    compute the three short-horizon candidates + the combo from the same code path so
    the signal here is byte-for-byte the #206 signal."""
    feats = {name: {} for name in (
        "intraday_mom_last", "vwap_dev", "close_loc",
    )}
    day_open = {}
    grouped = minbars.groupby([minbars.index.get_level_values("symbol"), "session"])
    for (sym, sess), g in grouped:
        if sym not in kept:
            continue
        g = g.sort_index()
        c = g["close"].values
        o = g["open"].values
        hi = g["high"].values
        lo = g["low"].values
        vol = g["volume"].values
        vwap_bar = g["vwap"].values
        n = len(c)
        if n < 4:
            continue
        day_c = c[-1]
        day_hi = float(np.max(hi))
        day_lo = float(np.min(lo))
        k = min(2, n - 1)
        mom_last = float(c[-1] / c[-1 - k] - 1.0) if k >= 1 else np.nan
        tv = np.nansum(vol)
        if tv > 0 and np.isfinite(vwap_bar).any():
            day_vwap = float(np.nansum(np.where(np.isfinite(vwap_bar), vwap_bar, (hi + lo + c) / 3) * vol) / tv)
        else:
            day_vwap = float(np.nanmean(c))
        vwap_dev = float(day_c / day_vwap - 1.0) if day_vwap > 0 else np.nan
        close_loc = float((day_c - day_lo) / (day_hi - day_lo)) if day_hi > day_lo else 0.5

        feats["intraday_mom_last"].setdefault(sess, {})[sym] = mom_last
        feats["vwap_dev"].setdefault(sess, {})[sym] = vwap_dev
        feats["close_loc"].setdefault(sess, {})[sym] = close_loc
        day_open.setdefault(sess, {})[sym] = float(o[0])

    idx = daily_close.index
    out = {}
    for name, dd in feats.items():
        frame = pd.DataFrame.from_dict(dd, orient="index")
        frame = frame.reindex(index=idx, columns=daily_close.columns)
        out[name] = frame.sort_index()
    dofr = pd.DataFrame.from_dict(day_open, orient="index").reindex(
        index=idx, columns=daily_close.columns).sort_index()
    return out, dofr


def zscore_rows(df):
    """Cross-sectional rank-standardize each row (date): rank -> z. NaNs preserved."""
    r = df.rank(axis=1)
    mu = r.mean(axis=1)
    sd = r.std(axis=1, ddof=0)
    return r.sub(mu, axis=0).div(sd.replace(0, np.nan) + 1e-12, axis=0)


# ----------------------------------------------------------------------------- #
# portfolio + faithful cost engine
# ----------------------------------------------------------------------------- #
def target_weights(signal_row, leg, frac):
    """Equal-weight target weights for a single rebalance from a cross-sectional
    signal row. leg='long' -> top `frac` quantile (long-only, sums to +1);
    leg='ls' -> long top decile / short bottom decile, dollar-neutral (gross 2,
    net 0; each side sums to +/-1)."""
    s = signal_row.dropna()
    w = pd.Series(0.0, index=signal_row.index)
    nn = len(s)
    if nn < 10:
        return w
    k = max(1, int(round(nn * frac)))
    order = s.sort_values()
    if leg == "long":
        top = order.index[-k:]
        w.loc[top] = 1.0 / k
    elif leg == "ls":
        top = order.index[-k:]
        bot = order.index[:k]
        w.loc[top] = 0.5 / k
        w.loc[bot] = -0.5 / k
    return w


def run_portfolio(signal, fwd_step, px_index, leg, frac, step, round_trip_bps_list,
                  date_pool=None):
    """Walk forward over non-overlapping rebalance dates spaced `step` apart. At each
    rebalance date D (on which a minute signal exists), form target weights from D's
    signal and hold for `step` sessions ENTERED at the next-session open; the
    per-period gross return is the equal-weight (or L/S) portfolio return
    close[D+step]/open[D+1] - 1 (supplied via `fwd_step`). Turnover at D =
    sum|w_D - w_prev|/2 (one-way fraction traded). Costs charged per rebalance.

    `date_pool`: optional set restricting rebalance dates (for an OOS split).
    Returns a per-period DataFrame with date, gross_ret, one_way_turnover, n_long,
    n_short, and net_ret for each round-trip cost in the list."""
    # rebalance dates: dates that HAVE a signal AND a realized next-session return.
    sig_dates = signal.dropna(how="all").index
    valid = [d for d in sig_dates if d in fwd_step.index and fwd_step.loc[d].notna().any()]
    if date_pool is not None:
        valid = [d for d in valid if d in date_pool]
    valid = sorted(valid)
    if not valid:
        return pd.DataFrame()
    # space them `step` apart (non-overlapping holding periods)
    reb = valid[::step]

    rows = []
    prev_w = pd.Series(0.0, index=signal.columns)
    for d in reb:
        w = target_weights(signal.loc[d], leg, frac)
        # gross per-period return: weight . forward step-return, over names with both
        r = fwd_step.loc[d]
        m = (w != 0) & r.notna()
        gross = float((w[m] * r[m]).sum())
        # turnover vs previous held book (one-way fraction of gross traded)
        one_way = float((w - prev_w).abs().sum() / 2.0)
        n_long = int((w > 0).sum())
        n_short = int((w < 0).sum())
        row = dict(date=d, gross_ret=gross, one_way_turnover=one_way,
                   n_long=n_long, n_short=n_short)
        for rt in round_trip_bps_list:
            row[f"net_ret_{rt:g}"] = gross - one_way * (rt / 1e4)
        rows.append(row)
        prev_w = w
    return pd.DataFrame(rows)


def annualize(per_period_mean, step):
    """Geometric-ish annualization of a per-period simple mean return held `step`
    trading days. periods/yr = 252/step."""
    periods_per_yr = TRADING_DAYS / step
    return (1.0 + per_period_mean) ** periods_per_yr - 1.0


def sharpe(per_period_returns, step):
    """Annualized Sharpe of a per-period return series (rf=0)."""
    x = np.asarray(per_period_returns, dtype=float)
    if len(x) < 3 or x.std(ddof=1) == 0:
        return np.nan
    periods_per_yr = TRADING_DAYS / step
    return float(x.mean() / x.std(ddof=1) * np.sqrt(periods_per_yr))


def summarize(pp, step, round_trip_bps_list):
    """Collapse a per-period DataFrame to the headline economics."""
    if pp.empty:
        return None
    n = len(pp)
    gross_mean = float(pp["gross_ret"].mean())
    turn_mean = float(pp["one_way_turnover"].mean())
    # turnover as NAMES traded per DAY-equivalent: one_way * avg book names / step
    avg_book = float((pp["n_long"] + pp["n_short"]).mean())
    names_per_day = turn_mean * avg_book / step
    # active-day exposure: fraction of available rebalance periods actually held
    active_frac = float((pp["n_long"] + pp["n_short"] > 0).mean())
    out = dict(
        leg_periods=n, step=step,
        gross_per_period=gross_mean,
        gross_ann=annualize(gross_mean, step),
        gross_sharpe=sharpe(pp["gross_ret"].values, step),
        one_way_turnover=turn_mean,
        avg_book_names=avg_book,
        names_traded_per_day=names_per_day,
        active_day_frac=active_frac,
        # breakeven ROUND-TRIP cost (bps) at which net edge = 0
        breakeven_rt_bps=(gross_mean / turn_mean * 1e4) if turn_mean > 1e-9 else np.nan,
    )
    for rt in round_trip_bps_list:
        col = f"net_ret_{rt:g}"
        nm = float(pp[col].mean())
        out[f"net_per_period_{rt:g}"] = nm
        out[f"net_ann_{rt:g}"] = annualize(nm, step)
        out[f"net_sharpe_{rt:g}"] = sharpe(pp[col].values, step)
    return out


def by_year_net(pp, step, base_rt):
    """Net annualized return BY YEAR at the base round-trip cost (stability check)."""
    if pp.empty:
        return {}
    col = f"net_ret_{base_rt:g}"
    g = {}
    yrs = pd.DatetimeIndex(pp["date"]).year
    for y in sorted(set(yrs)):
        sel = pp[yrs == y]
        if len(sel) < 3:
            g[int(y)] = dict(n=len(sel), net_ann=float("nan"), net_sharpe=float("nan"),
                             gross_ann=float("nan"))
            continue
        g[int(y)] = dict(
            n=len(sel),
            gross_ann=annualize(float(sel["gross_ret"].mean()), step),
            net_ann=annualize(float(sel[col].mean()), step),
            net_sharpe=sharpe(sel[col].values, step),
        )
    return g


# ----------------------------------------------------------------------------- #
def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--as-of", required=True,
                    help="Pinned end date YYYY-MM-DD (no datetime.now). Bars + labels end here.")
    ap.add_argument("--out", default="/tmp/minfeat2_out", help="Output directory.")
    ap.add_argument("--min-cache", default="/tmp/minfeat_out/minbars.parquet",
                    help="Cached intraday bar parquet from #206 (read WITHOUT creds).")
    ap.add_argument("--daily-bars", default="/tmp/sighunt/bars.parquet",
                    help="Daily close-panel parquet (reused from sighunt) for fwd returns.")
    ap.add_argument("--coverage", type=float, default=0.55,
                    help="Min full-period DAILY coverage to keep a name (shared w/ #206).")
    ap.add_argument("--decile", type=float, default=0.10,
                    help="Top/bottom fraction for the decile portfolios (0.10).")
    ap.add_argument("--quintile", type=float, default=0.20,
                    help="Top fraction for the long-only quintile portfolio (0.20).")
    ap.add_argument("--config", default=DEFAULT_CFG,
                    help="renquant-104 golden watchlist json (universe source).")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    as_of = pd.Timestamp(args.as_of).normalize()

    universe = load_universe(args.config)

    # ---- daily close panel (reused) for forward returns + coverage ----
    px = pd.read_parquet(args.daily_bars).sort_index()
    px = px[px.index <= as_of]
    cov = px.notna().mean()
    kept = sorted(cov[cov > args.coverage].index.tolist())
    px = px[[c for c in kept if c in px.columns]]
    print(f"[daily] panel {px.shape[0]}d x {px.shape[1]}n "
          f"{px.index.min().date()}->{px.index.max().date()}", flush=True)

    # ---- minute bars: cache-first (read WITHOUT credentials) ----
    cache = args.min_cache
    if not os.path.exists(cache):
        sys.exit(f"[fatal] minute cache {cache} not found; this cost-test REUSES the "
                 f"#206 cache and never re-pulls. Run minute_feature_scan.py first.")
    mb = pd.read_parquet(cache)
    print(f"[data] loaded cached intraday panel {mb.shape} from {cache} "
          f"(no credentials used)", flush=True)
    ts = mb.index.get_level_values("timestamp")
    mb = mb[ts.tz_convert("UTC").normalize().tz_localize(None) <= as_of]
    mb = rth_filter(mb)  # DST-correct XNYS calendar filter (half-days included)
    n_sess = mb["session"].nunique()
    print(f"[data] RTH intraday rows={len(mb)} sessions={n_sess} "
          f"{mb['session'].min().date()}->{mb['session'].max().date()} "
          f"(DST-correct XNYS calendar filter)", flush=True)

    # ---- features (identical #206 path) + tradable next-session open ----
    feats, day_open = build_features(mb, px, set(px.columns))
    for name, fr in feats.items():
        print(f"[feat] {name:18s} non-null cells={int(fr.notna().sum().sum())}", flush=True)

    # signals: vwap_dev (primary) + equal-weight combo of the 3 short-horizon features
    z = {name: zscore_rows(fr) for name, fr in feats.items()}
    combo = sum(z[name] for name in COMBO_FEATURES) / float(len(COMBO_FEATURES))
    # re-standardize the combo so its scale matches a single z-feature (cosmetic; rank
    # portfolios are scale-invariant, but keep it clean)
    combo = zscore_rows(combo)
    signals = {"vwap_dev": z["vwap_dev"], "combo": combo}

    # NEXT-SESSION ENTRY forward returns: signal for D known after D's close -> ENTER
    # at open[D+1], exit at close[D+step]. ret = close[D+step]/open[D+1] - 1, future.
    next_open = day_open.shift(-1)  # open of session D+1, indexed at D

    def fwd_step_ret(step):
        return px.shift(-step) / next_open - 1.0

    # chronological OOS split over signal-sessions (same 70/30 as the scan)
    min_days = feats["vwap_dev"].dropna(how="all").index
    sessions = sorted([d for d in px.index if d in set(min_days)])
    cut = int(len(sessions) * OOS_FRAC)
    disc_pool = set(sessions[:cut])
    oos_pool = set(sessions[cut:])
    split_date = sessions[cut] if cut < len(sessions) else None
    print(f"[oos] {len(sessions)} signal-sessions -> DISCOVERY {len(disc_pool)} | "
          f"OOS {len(oos_pool)} (>= {split_date.date() if split_date is not None else 'NA'})",
          flush=True)

    # ---- run the full grid (full window + OOS holdout) ----
    portfolios = {
        "longdecile": ("long", args.decile),
        "longquintile": ("long", args.quintile),
        "lsdecile": ("ls", args.decile),
    }
    windows = {"full": None, "oos": oos_pool}
    grid = []           # flat summary rows
    per_period_store = {}  # (window,sig,port,step) -> per-period DataFrame
    for wname, pool in windows.items():
        for sig_name, sig in signals.items():
            for step in STEPS:
                fwd = fwd_step_ret(step)
                for port_name, (leg, frac) in portfolios.items():
                    pp = run_portfolio(sig, fwd, px.index, leg, frac, step,
                                       ROUND_TRIP_BPS, date_pool=pool)
                    s = summarize(pp, step, ROUND_TRIP_BPS)
                    if s is None:
                        continue
                    s.update(dict(window=wname, signal=sig_name, portfolio=port_name,
                                  leg=leg, frac=frac))
                    s["by_year"] = by_year_net(pp, step, 11.0)
                    grid.append(s)
                    per_period_store[(wname, sig_name, port_name, step)] = pp

    # ---- persist per-period series + summary csv + manifest ----
    flat_rows = []
    for s in grid:
        row = {k: v for k, v in s.items() if k != "by_year"}
        flat_rows.append(row)
    summary = pd.DataFrame(flat_rows)
    summary.to_csv(os.path.join(args.out, "costtest_summary.csv"), index=False)

    # tidy per-period dump (long format) for audit
    pp_frames = []
    for (wname, sig_name, port_name, step), pp in per_period_store.items():
        t = pp.copy()
        t.insert(0, "window", wname)
        t.insert(1, "signal", sig_name)
        t.insert(2, "portfolio", port_name)
        t.insert(3, "step", step)
        pp_frames.append(t)
    if pp_frames:
        pd.concat(pp_frames, ignore_index=True).to_csv(
            os.path.join(args.out, "costtest_perperiod.csv"), index=False)

    by_year_out = {f"{s['window']}|{s['signal']}|{s['portfolio']}|{s['step']}d": s["by_year"]
                   for s in grid}
    with open(os.path.join(args.out, "costtest_by_year.json"), "w") as f:
        json.dump(by_year_out, f, indent=2)

    symbols = list(px.columns)
    manifest = dict(
        script="scripts/minute_signal_costtest.py",
        kind="renquant-105 minute short-horizon signal MONETIZATION under faithful turnover costs",
        extends="scripts/minute_feature_scan.py (#206)",
        as_of=args.as_of,
        code_commit=git_commit(),
        generated_at_utc=datetime.now(timezone.utc).isoformat(),
        universe_config=args.config,
        universe_config_sha256=sha256_file(args.config),
        min_cache=cache,
        min_cache_sha256=sha256_file(cache),
        daily_bars=args.daily_bars,
        daily_bars_sha256=sha256_file(args.daily_bars),
        used_cache_without_credentials=True,
        rth_filter="XNYS exchange_calendars [session_open, session_close) UTC (half-days included)",
        entry_timing="next-session OPEN (signal known after close[D]; enter open[D+1]); "
                     "ret = close[D+step]/open[D+1] - 1",
        oos="chronological %.0f/%.0f split; economics reported full window AND OOS holdout"
            % (OOS_FRAC * 100, (1 - OOS_FRAC) * 100),
        oos_split_date=str(split_date.date()) if split_date is not None else None,
        parameters=dict(
            steps=STEPS, round_trip_bps=ROUND_TRIP_BPS, base_rt_bps=11.0,
            decile=args.decile, quintile=args.quintile, coverage=args.coverage,
            combo_features=COMBO_FEATURES, trading_days=TRADING_DAYS, oos_frac=OOS_FRAC,
        ),
        intraday_panel=dict(
            sessions=int(n_sess), rth_rows=int(len(mb)),
            start=str(mb["session"].min().date()), end=str(mb["session"].max().date()),
        ),
        daily_panel=dict(days=int(px.shape[0]), names=int(px.shape[1])),
        kept_symbols=symbols,
        kept_symbols_sha256=sha256_text(",".join(symbols)),
    )
    with open(os.path.join(args.out, "costtest_manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)

    # ---- print the decision tables ----
    pd.set_option("display.width", 240)
    pd.set_option("display.max_columns", 40)
    pd.set_option("display.float_format", lambda x: f"{x:.4f}")

    print("\n========= NET ECONOMICS (next-session entry, base round-trip 11 bps) =========")
    cols = ["window", "signal", "portfolio", "step", "leg_periods", "gross_ann",
            "net_ann_11", "net_sharpe_11", "one_way_turnover",
            "names_traded_per_day", "active_day_frac", "breakeven_rt_bps"]
    print(summary.sort_values(["window", "signal", "portfolio", "step"])[cols].to_string(index=False))

    print("\n========= COST SENSITIVITY (net annualized return) =========")
    cols2 = ["window", "signal", "portfolio", "step",
             "net_ann_5", "net_ann_11", "net_ann_20",
             "net_sharpe_5", "net_sharpe_11", "net_sharpe_20"]
    print(summary.sort_values(["window", "signal", "portfolio", "step"])[cols2].to_string(index=False))

    print("\n========= FULL-WINDOW NET RETURN BY YEAR (base 11 bps) =========")
    for s in grid:
        if s["window"] != "full":
            continue
        tag = f"{s['signal']:9s} {s['portfolio']:13s} {s['step']}d"
        parts = []
        for y, d in s["by_year"].items():
            na = d["net_ann"]
            parts.append(f"{y}:{'' if na != na else f'{na*100:+.1f}%'}(n{d['n']})")
        print(f"{tag} | " + "  ".join(parts))

    print(f"\nBase round-trip = 11 bps; sensitivity {ROUND_TRIP_BPS} bps.")
    print(f"breakeven_rt_bps = round-trip cost at which NET = 0 (higher = more headroom).")
    print(f"Kept-symbols sha256={manifest['kept_symbols_sha256'][:12]} (coverage={args.coverage})")
    print(f"Wrote: {args.out}/costtest_summary.csv, costtest_perperiod.csv, "
          f"costtest_by_year.json, costtest_manifest.json")


if __name__ == "__main__":
    main()
