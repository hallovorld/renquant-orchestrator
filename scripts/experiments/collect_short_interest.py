"""Point-in-time short-interest collector (daily snapshot appender).

data/fundamentals/<T>.parquet holds ONE latest short_pct_float snapshot per
ticker (no history) — unusable for IC screens or training. Short interest
cannot be backfilled from yfinance, so we accumulate it point-in-time:
each run appends today's snapshot per watchlist ticker to
data/short_interest/history.parquet with a collection-date stamp.
Run daily (ride the daily data rail). FINRA bi-monthly backfill is a
separate follow-up.
"""
import datetime as dt
from pathlib import Path

import pandas as pd
import yfinance as yf

R = Path("/Users/renhao/git/github/RenQuant")
OUT = R / "data/short_interest/history.parquet"
OUT.parent.mkdir(parents=True, exist_ok=True)

watchlist = [p.name for p in (R / "data/ohlcv").iterdir() if p.is_dir()]
today = dt.date.today().isoformat()
rows = []
for t in sorted(watchlist):
    try:
        info = yf.Ticker(t).info
        rows.append({
            "collect_date": today,
            "ticker": t,
            "short_pct_float": info.get("shortPercentOfFloat"),
            "shares_short": info.get("sharesShort"),
            "short_ratio_dtc": info.get("shortRatio"),
            "shares_short_prior_month": info.get("sharesShortPriorMonth"),
        })
    except Exception:
        continue
new = pd.DataFrame(rows).dropna(subset=["short_pct_float"], how="all")
if OUT.exists():
    hist = pd.read_parquet(OUT)
    hist = hist[hist["collect_date"] != today]   # idempotent per day
    new = pd.concat([hist, new], ignore_index=True)
new.to_parquet(OUT, index=False)
print(f"short-interest snapshot {today}: {len(rows)} tickers, file now {len(new)} rows")
