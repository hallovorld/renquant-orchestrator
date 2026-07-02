#!/usr/bin/env python3
"""S10: the full open-auction implementation-shortfall study (#231 S10; upgrades
POC-C leg 1 from point estimate to CI-backed verdict on the available history).

Improvements over POC-C:
  1. TRUE daily VWAP where 10-minute bars exist (data/intraday/<T>/10min.parquet
     carries a per-bar `vwap`; day VWAP = Σ(vwap·vol)/Σvol over RTH bars),
     falling back to OHLC4 with an explicit `ref_kind` label (10min coverage
     ends 2026-05-01; later fills use the proxy).
  2. Date-clustered BLOCK BOOTSTRAP 95% CI on every reference delta (fills on
     the same day share the day's market move — i.i.d. bootstrap would
     overstate precision).
  3. An explicit decision readout for the #230 §8 S10 row: is the prize
     point-estimate materially >10bps AND is its CI separated from zero?

Estimand: per real filled buy order, (fill − reference)/reference in bps for
reference ∈ {open, day_vwap, close}. fill≈open is already established (POC-C:
fills stamped 09:30:00–01); the economic quantity is fill_vs_vwap / fill_vs_close
— what a delayed entry could have obtained on the same day.

Reproduce:
  cd /Users/renhao/git/github/RenQuant && set -a && source .env && set +a && \
    .venv/bin/python <orchestrator>/scripts/s10_open_auction_is_study.py
Inputs (read-only): Alpaca /v2/orders (closed, filled buys);
  data/ohlcv/<T>/1d.parquet; data/intraday/<T>/10min.parquet.
Output: doc/research/evidence/2026-07-02-roadmap-pocs/s10_open_auction_is.json
"""
import json
import os
import urllib.request

import numpy as np
import pandas as pd

RQ = os.environ.get("RQ_ROOT", "/Users/renhao/git/github/RenQuant")
BASE = os.environ.get("ALPACA_BASE_URL", "https://api.alpaca.markets")
OUT = os.environ.get(
    "POC_OUT_DIR",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "doc/research/evidence/2026-07-02-roadmap-pocs"),
)
N_BOOT = 5000
SEED = 20260702


def _daily(t):
    p = os.path.join(RQ, "data/ohlcv", t, "1d.parquet")
    if not os.path.exists(p):
        return None
    df = pd.read_parquet(p)
    df.columns = [c.lower() for c in df.columns]
    if "date" in df.columns:
        df = df.set_index("date")
    return df.sort_index()


def _true_vwap(t, day):
    p = os.path.join(RQ, "data/intraday", t, "10min.parquet")
    if not os.path.exists(p):
        return None
    df = pd.read_parquet(p)
    df.columns = [c.lower() for c in df.columns]
    idx = pd.to_datetime(df.index)
    # bars are UTC-stamped; RTH 09:30–16:00 ET = 13:30–20:00 UTC (EDT) or
    # 14:30–21:00 (EST). Select by ET wall clock to be DST-correct.
    et = idx.tz_localize("UTC").tz_convert("America/New_York") if idx.tz is None \
        else idx.tz_convert("America/New_York")
    day_mask = (et.date == day.date())
    rth = day_mask & (et.time >= pd.Timestamp("09:30").time()) & \
        (et.time < pd.Timestamp("16:00").time())
    g = df.loc[rth]
    if len(g) < 10 or g["volume"].sum() <= 0:
        return None
    return float((g["vwap"] * g["volume"]).sum() / g["volume"].sum())


def _fills():
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
        day = ts.normalize().tz_localize(None)
        b = _daily(o["symbol"])
        if b is None or day not in b.index:
            continue
        bar = b.loc[day]
        fill = float(o["filled_avg_price"])
        tv = _true_vwap(o["symbol"], day)
        ref_vwap = tv if tv is not None else (bar.open + bar.high + bar.low + bar.close) / 4
        rows.append({
            "symbol": o["symbol"], "date": str(day.date()),
            "ref_kind": "true_vwap_10min" if tv is not None else "ohlc4_proxy",
            "fill_vs_open_bps": (fill / bar.open - 1) * 1e4,
            "fill_vs_vwap_bps": (fill / ref_vwap - 1) * 1e4,
            "fill_vs_close_bps": (fill / bar.close - 1) * 1e4,
        })
    return pd.DataFrame(rows)


def _cluster_boot(df, col):
    """Date-clustered bootstrap of the mean (resample DAYS with replacement)."""
    rng = np.random.default_rng(SEED)
    days = df["date"].unique()
    groups = {d: g[col].to_numpy() for d, g in df.groupby("date")}
    means = []
    for _ in range(N_BOOT):
        pick = rng.choice(days, size=len(days), replace=True)
        vals = np.concatenate([groups[d] for d in pick])
        means.append(vals.mean())
    lo, hi = np.percentile(means, [2.5, 97.5])
    return {"mean": round(float(df[col].mean()), 1),
            "median": round(float(df[col].median()), 1),
            "ci95": [round(float(lo), 1), round(float(hi), 1)],
            "n_fills": int(len(df)), "n_days": int(df["date"].nunique())}


def main() -> None:
    df = _fills()
    stats = {c: _cluster_boot(df, c) for c in
             ["fill_vs_open_bps", "fill_vs_vwap_bps", "fill_vs_close_bps"]}
    v = stats["fill_vs_vwap_bps"]
    c = stats["fill_vs_close_bps"]
    verdict = {
        "prize_point_estimate_bps": {"vs_day_vwap": v["mean"], "vs_close": c["mean"]},
        "material_gt_10bps": bool(v["mean"] > 10 or c["mean"] > 10),
        "ci_separated_from_zero": {"vs_day_vwap": bool(v["ci95"][0] > 0),
                                   "vs_close": bool(c["ci95"][0] > 0)},
        "reading": ("S10 verdict per #230 §8: prize material if point>10bps; "
                    "SIGNIFICANT only if the date-clustered CI excludes 0 — "
                    "otherwise the verdict is 'material-but-unproven, collector "
                    "corpus accrues N'"),
    }
    out = {
        "estimand": "per real filled buy: (fill − ref)/ref bps; ref ∈ {open, day_vwap, close}",
        "ref_kind_counts": df["ref_kind"].value_counts().to_dict(),
        "stats_date_clustered_bootstrap": stats,
        "verdict": verdict,
        "fills": df.to_dict("records"),
    }
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "s10_open_auction_is.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(json.dumps({k: v for k, v in out.items() if k != "fills"}, indent=2))


if __name__ == "__main__":
    main()
