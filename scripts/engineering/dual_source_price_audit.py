#!/usr/bin/env python3
"""Dual-source price audit (#108 III.6; self-discovered gap #4).

Production prices come from yfinance — an unofficial scraper API that can
silently rate-limit, rename fields, or drift. This audit cross-checks one
source against another per (ticker, day): relative close divergence beyond
tolerance → audit verdict (L6 catalog item).

Offline proof here: yfinance parquet vs the LEAN zip exports (independently
written pipeline) for the same days. Production wiring swaps source B for
the Alpaca market-data API (already paid for via the broker).
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pandas as pd

R = Path("/Users/renhao/git/github/RenQuant")
TOL = 0.005   # 50 bps close divergence → WARN; 5x TOL → CRITICAL


def lean_closes(ticker: str) -> pd.Series:
    z = R / f"backtesting/data/equity/usa/daily/{ticker.lower()}.zip"
    if not z.exists():
        raise FileNotFoundError(z)
    with zipfile.ZipFile(z) as f:
        name = f.namelist()[0]
        df = pd.read_csv(io.BytesIO(f.read(name)), header=None,
                         names=["dt", "open", "high", "low", "close", "vol"])
    df["date"] = pd.to_datetime(df["dt"].astype(str).str.slice(0, 8))
    return df.set_index("date")["close"] / 10_000.0   # LEAN deci-cent scaling


def audit(ticker: str, days: int = 30) -> dict:
    yf = pd.read_parquet(R / f"data/ohlcv/{ticker}/1d.parquet")["close"]
    ln = lean_closes(ticker)
    j = pd.concat([yf.rename("a"), ln.rename("b")], axis=1).dropna().tail(days)
    if j.empty:
        return {"ticker": ticker, "verdict": "NO_OVERLAP"}
    div = (j["a"] / j["b"] - 1).abs()
    worst = float(div.max())
    verdict = ("CRITICAL" if worst > 5 * TOL else
               "WARN" if worst > TOL else "OK")
    return {"ticker": ticker, "days": len(j), "worst_div": round(worst, 5),
            "worst_day": str(div.idxmax().date()), "verdict": verdict}


if __name__ == "__main__":
    results = [audit(t) for t in ("AAPL", "SPY", "GOOG", "IBM", "BAC")]
    for r in results:
        print(r)
    crit = [r for r in results if r.get("verdict") == "CRITICAL"]
    print(f"\n{len(results)} tickers cross-checked, {len(crit)} CRITICAL")
    print("note: LEAN zips are adjusted differently around dividends — a "
          "WARN day adjacent to an ex-date is expected behavior, which is "
          "exactly why the audit reports the worst DAY, not just a flag. "
          "Production: source B = Alpaca market data; verdicts → L6 sidecar.")
