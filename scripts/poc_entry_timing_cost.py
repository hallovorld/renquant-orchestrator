#!/usr/bin/env python3
"""POC-C: measure (1) what our next-open entries actually cost vs same-day
references, from REAL broker fills; (2) the overnight-vs-intraday return
decomposition on OUR watchlist — the two data legs under the 105 Stage-1/2
economic thesis (roadmap #230 §5 increment 1; #208 A4.1 reframe).

Claims under test:
  (a) our buy fills land at/near the open auction print;
  (b) the open is a systematically expensive reference vs the rest of the day
      on the days we buy;
  (c) on our watchlist, multi-day returns accrue predominantly OVERNIGHT
      (close->open), intraday (open->close) ~ 0 — the deep-research claim,
      re-measured on our own names.

Method:
  Leg 1: GET /v2/orders (closed, side=buy, filled) from the live Alpaca
  account -> per fill: (fill - open)/open, (fill - ohlc4)/ohlc4,
  (fill - close)/close in bps, where ohlc4 = (O+H+L+C)/4 is a coarse VWAP
  proxy (stated limitation: no true VWAP without minute data).
  Leg 2: for the 142 panel tickers over the last ~756 trading days: mean
  daily overnight return (prev_close->open) vs intraday return (open->close),
  equal-weight, plus the same split within the top-quartile 12-1 momentum
  names (the ones the book actually buys).

Reproduce:
  cd /Users/renhao/git/github/RenQuant && set -a && source .env && set +a && \
    .venv/bin/python <orchestrator>/scripts/poc_entry_timing_cost.py
Inputs (read-only): Alpaca /v2/orders API; data/ohlcv/<T>/1d.parquet;
  data/transformer_v4_wl200_clean.parquet (ticker list).
Output: doc/research/evidence/2026-07-02-roadmap-pocs/poc_c_entry_timing_cost.json
"""
import json
import os
import urllib.request

import numpy as np
import pandas as pd

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
OUT = os.environ.get(
    "POC_OUT_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "doc/research/evidence/2026-07-02-roadmap-pocs"),
)
BASE = os.environ.get("ALPACA_BASE_URL", "https://api.alpaca.markets")
LOOKBACK_D = 756


def _bars(t):
    p = os.path.join(RQ, "data/ohlcv", t, "1d.parquet")
    if not os.path.exists(p):
        return None
    df = pd.read_parquet(p)
    df.columns = [c.lower() for c in df.columns]
    if "date" in df.columns:
        df = df.set_index("date")
    return df.sort_index()


def leg1_fills():
    req = urllib.request.Request(
        f"{BASE}/v2/orders?status=closed&side=buy&limit=500&direction=desc",
        headers={"APCA-API-KEY-ID": os.environ["ALPACA_API_KEY"],
                 "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET_KEY"]})
    orders = json.load(urllib.request.urlopen(req))
    rows = []
    for o in orders:
        if o.get("filled_avg_price") is None or float(o.get("filled_qty") or 0) == 0:
            continue
        ts = pd.Timestamp(o["filled_at"]).tz_convert("America/New_York")
        b = _bars(o["symbol"])
        if b is None:
            continue
        day = ts.normalize().tz_localize(None)
        if day not in b.index:
            continue
        bar = b.loc[day]
        fill = float(o["filled_avg_price"])
        o4 = (bar.open + bar.high + bar.low + bar.close) / 4
        rows.append({
            "symbol": o["symbol"], "date": str(day.date()),
            "fill_time_et": str(ts.time())[:8],
            "fill_vs_open_bps": (fill / bar.open - 1) * 1e4,
            "fill_vs_ohlc4_bps": (fill / o4 - 1) * 1e4,
            "fill_vs_close_bps": (fill / bar.close - 1) * 1e4,
            "open_vs_close_bps": (bar.open / bar.close - 1) * 1e4,
        })
    df = pd.DataFrame(rows)
    stats = {}
    if len(df):
        for c in ["fill_vs_open_bps", "fill_vs_ohlc4_bps",
                  "fill_vs_close_bps", "open_vs_close_bps"]:
            stats[c] = {"mean": round(float(df[c].mean()), 1),
                        "median": round(float(df[c].median()), 1),
                        "se_mean": round(float(df[c].std() / np.sqrt(len(df))), 1)}
    return {"n_fills": int(len(df)), "stats": stats,
            "fills_sample": df.head(20).to_dict("records")}


def leg2_overnight():
    tickers = pd.read_parquet(
        os.path.join(RQ, "data/transformer_v4_wl200_clean.parquet"),
        columns=["ticker"])["ticker"].unique().tolist()
    ov, iv, mom_ov, mom_iv = [], [], [], []
    per_name = {}
    for t in tickers:
        b = _bars(t)
        if b is None or len(b) < 300:
            continue
        b = b.iloc[-LOOKBACK_D:]
        overnight = (b.open / b.close.shift(1) - 1).dropna()
        intraday = (b.close / b.open - 1).dropna()
        per_name[t] = {"ov": float(overnight.mean()), "iv": float(intraday.mean())}
        ov.append(overnight.mean()); iv.append(intraday.mean())
        # momentum 12-1 at the midpoint of the window: crude but sufficient
        if len(b) >= 300:
            m = b.close.iloc[-21] / b.close.iloc[-252] - 1 if len(b) >= 252 else np.nan
            if np.isfinite(m):
                per_name[t]["mom_12_1_now"] = float(m)
    dfm = pd.DataFrame(per_name).T
    q = dfm["mom_12_1_now"].quantile(0.75) if "mom_12_1_now" in dfm else np.nan
    top = dfm[dfm.get("mom_12_1_now", pd.Series(dtype=float)) >= q] if np.isfinite(q) else dfm.iloc[0:0]
    ann = 252
    return {
        "n_names": int(len(dfm)),
        "lookback_days": LOOKBACK_D,
        "avg_overnight_bps_per_day": round(float(np.mean(ov)) * 1e4, 2),
        "avg_intraday_bps_per_day": round(float(np.mean(iv)) * 1e4, 2),
        "annualized_overnight_pct": round(float(np.mean(ov)) * ann * 100, 1),
        "annualized_intraday_pct": round(float(np.mean(iv)) * ann * 100, 1),
        "top_quartile_mom_overnight_bps": round(float(top["ov"].mean()) * 1e4, 2) if len(top) else None,
        "top_quartile_mom_intraday_bps": round(float(top["iv"].mean()) * 1e4, 2) if len(top) else None,
        "caveat": ("momentum quartile uses CURRENT 12-1, not point-in-time "
                   "membership — indicative only; the PIT version is the S10 "
                   "deliverable"),
    }


def main() -> None:
    out = {"leg1_real_fills_vs_references": leg1_fills(),
           "leg2_overnight_vs_intraday": leg2_overnight()}
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "poc_c_entry_timing_cost.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({k: (v if k != "leg1_real_fills_vs_references" else
                          {kk: vv for kk, vv in v.items() if kk != "fills_sample"})
                      for k, v in out.items()}, indent=2))


if __name__ == "__main__":
    main()
