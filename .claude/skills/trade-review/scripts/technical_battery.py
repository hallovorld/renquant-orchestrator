#!/usr/bin/env python3
"""Technical battery for a list of tickers vs a benchmark, from Alpaca daily bars.

Scale-invariant indicators (trend / RSI / relative-strength / vol / 52w position) —
robust to absolute-price data quirks, which is exactly what a price-feed sanity check
needs. Read-only (market-data only).

Usage:
    technical_battery.py CRWD PANW CSCO [--benchmark SPY] [--json]

Env: ALPACA_API_KEY / ALPACA_SECRET_KEY (source the strategy .env first).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta


def _client():
    from alpaca.data.historical import StockHistoricalDataClient  # noqa: PLC0415

    key, sec = os.environ.get("ALPACA_API_KEY"), os.environ.get("ALPACA_SECRET_KEY")
    if not key or not sec:
        sys.exit("ALPACA_API_KEY / ALPACA_SECRET_KEY not set — source the strategy .env first.")
    return StockHistoricalDataClient(key, sec)


def battery(tickers: list[str], benchmark: str = "SPY", lookback_days: int = 400) -> dict:
    import numpy as np  # noqa: PLC0415
    from alpaca.data.requests import StockBarsRequest  # noqa: PLC0415
    from alpaca.data.timeframe import TimeFrame  # noqa: PLC0415

    d = _client()
    syms = sorted(set(tickers) | {benchmark})
    start = (datetime.utcnow() - timedelta(days=lookback_days)).strftime("%Y-%m-%d")
    bars = d.get_stock_bars(
        StockBarsRequest(symbol_or_symbols=syms, timeframe=TimeFrame.Day, start=start)
    ).df

    def close(sym):
        return bars.loc[sym]["close"]

    def rsi(x, n=14):
        dl = x.diff()
        up = dl.clip(lower=0).rolling(n).mean()
        dn = (-dl.clip(upper=0)).rolling(n).mean()
        return float((100 - 100 / (1 + up / dn)).iloc[-1])

    def ret(x, n):
        return float((x.iloc[-1] / x.iloc[-n] - 1) * 100) if len(x) > n else float("nan")

    bench = close(benchmark)
    bench6 = ret(bench, 126)
    out = {"benchmark": benchmark, "benchmark_3m_pct": round(ret(bench, 63), 1),
           "benchmark_6m_pct": round(bench6, 1), "names": {}}
    for s in tickers:
        if s not in bars.index.get_level_values(0):
            out["names"][s] = {"error": "no bars"}
            continue
        x = close(s)
        px = float(x.iloc[-1])
        sma50 = float(x.rolling(50).mean().iloc[-1])
        sma200 = float(x.rolling(200).mean().iloc[-1])
        hi, lo = float(x.iloc[-252:].max()), float(x.iloc[-252:].min())
        r6 = ret(x, 126)
        vol60 = float(x.pct_change().iloc[-60:].std() * np.sqrt(252) * 100)
        trend = "UP" if px > sma50 > sma200 else ("DOWN" if px < sma50 < sma200 else "mixed")
        out["names"][s] = {
            "price": round(px, 2),
            "vs_sma50_pct": round((px / sma50 - 1) * 100, 1),
            "vs_sma200_pct": round((px / sma200 - 1) * 100, 1),
            "rsi14": round(rsi(x), 0),
            "ret_3m_pct": round(ret(x, 63), 1),
            "ret_6m_pct": round(r6, 1),
            "rel_strength_6m_vs_bench_pct": round(r6 - bench6, 1),
            "realized_vol_60d_pct": round(vol60, 0),
            "pos_in_52w_range_pct": round((px - lo) / (hi - lo) * 100, 0) if hi > lo else None,
            "trend": trend,
        }
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("tickers", nargs="+")
    ap.add_argument("--benchmark", default="SPY")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    res = battery([t.upper() for t in a.tickers], a.benchmark.upper())
    if a.json:
        print(json.dumps(res, indent=2))
        return
    b = res
    print(f"benchmark {b['benchmark']}: 3m {b['benchmark_3m_pct']:+.1f}%  6m {b['benchmark_6m_pct']:+.1f}%")
    hdr = f"{'sym':6}{'px':>9}{'vs50':>7}{'vs200':>7}{'RSI':>5}{'3m%':>7}{'6m%':>7}{'RS6m':>7}{'vol%':>6}{'52w':>5}  trend"
    print(hdr)
    for s, m in b["names"].items():
        if "error" in m:
            print(f"{s:6}  {m['error']}")
            continue
        print(f"{s:6}{m['price']:>9.1f}{m['vs_sma50_pct']:>+6.1f}%{m['vs_sma200_pct']:>+6.1f}%"
              f"{m['rsi14']:>5.0f}{m['ret_3m_pct']:>+6.1f}%{m['ret_6m_pct']:>+6.1f}%"
              f"{m['rel_strength_6m_vs_bench_pct']:>+6.1f}%{m['realized_vol_60d_pct']:>5.0f}%"
              f"{m['pos_in_52w_range_pct']:>4.0f}%  {m['trend']}")


if __name__ == "__main__":
    main()
