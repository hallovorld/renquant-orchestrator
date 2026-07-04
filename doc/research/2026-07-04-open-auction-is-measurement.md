# S10: Open-auction implementation shortfall — measurement memo

**Date:** 2026-05-22 (study as of)
**Period:** 2026-04-23 to 2026-05-22
**Sample:** 37 unique live buys, $70,115 total invested

## Summary

Average implementation shortfall vs VWAP: **-168.8 bps** (95% CI [-459.0, +0.2]), n=37. We underpaid relative to same-day VWAP on average.
Dollar-weighted IS vs VWAP: **-119.9 bps** (weights larger orders more heavily).

Fill vs same-day open: **-149.7 bps** (95% CI [-429.8, +5.6]). Fills deviate meaningfully from the open. 
Fill vs same-day close: **-206.2 bps** (95% CI [-512.8, -13.4]). 
Fill vs next-day close: **-55.1 bps** (95% CI [-391.3, +195.5]). 

## Interpretation for 105 §9.4 prereg

The IS vs VWAP is negative or zero — we are NOT systematically overpaying relative to VWAP. This suggests the current execution is already competitive with or better than intraday average. For the §9.4 prereg: the execution-leak rationale for 105 is **not supported** by this data. The prize from entry-timing optimization may be smaller than the ~40bps previously assumed.

## Data and method

- Source: `runs.alpaca.db` live buys joined to FMP `historical-price-eod/full`
- Deduplication: `DISTINCT (run_date, ticker, shares, price, invest)`
- OHLCV source: FMP Starter (includes true volume-weighted VWAP)
- Bootstrap: 10000 resamples, 95% CI (seed=42)
- IS convention: positive = overpaid = leak

## Per-ticker detail

| Ticker | Buys | Invested | IS vs Open (bps) | IS vs VWAP (bps) |
|--------|------|----------|-------------------|-------------------|
| NVDA | 4 | $8,961 | -69.7 | -88.6 |
| NVTS | 2 | $8,899 | +29.0 | -139.8 |
| SMCI | 2 | $8,898 | +86.7 | +236.7 |
| NET | 2 | $8,697 | +14.0 | -122.4 |
| MU | 2 | $8,444 | -271.1 | -431.6 |
| FTNT | 3 | $8,268 | +20.0 | -21.6 |
| TSM | 1 | $2,296 | -41.4 | -5.5 |
| MCD | 2 | $1,653 | -54.4 | -87.0 |
| DOCU | 1 | $1,046 | -85.0 | -22.5 |
| ABBV | 1 | $1,014 | +39.1 | +61.4 |
| SOFI | 1 | $1,008 | -18.7 | +102.6 |
| ON | 1 | $1,006 | -135.3 | -165.9 |
| GS | 1 | $926 | -108.2 | -96.9 |
| TXN | 1 | $919 | -10.8 | -26.6 |
| BA | 2 | $903 | -11.5 | -71.8 |
| GE | 1 | $892 | +50.0 | +79.7 |
| SPOT | 1 | $855 | +29.8 | +130.3 |
| VRT | 1 | $736 | +182.7 | +165.4 |
| DUK | 1 | $732 | +13.6 | -19.0 |
| BAC | 1 | $673 | +21.3 | -4.3 |
| HD | 1 | $645 | -1.2 | +75.2 |
| META | 1 | $618 | +72.3 | +61.0 |
| D | 1 | $541 | -79.2 | -44.5 |
| WFC | 1 | $535 | +5.2 | -4.2 |
| LMT | 1 | $512 | +75.1 | +88.8 |
| HON | 1 | $435 | -4916.2 | -4969.1 |
