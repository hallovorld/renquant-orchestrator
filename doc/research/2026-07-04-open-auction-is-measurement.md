# S10: Open-auction implementation shortfall — measurement memo

**Date:** 2026-07-04
**Period:** 2026-04-23 to 2026-05-22
**Sample:** 36 clean unique live buys, $69,679 total invested (1 excluded: HON 2:1 split-adjustment mismatch)

## Bottom line

**No measurable execution leak.** Current open-auction fills are competitive with
same-day VWAP. The execution-timing prize assumed by 105 §9.4 (~40 bps) is
**not supported** by this data.

## Summary (clean sample, n=36, HON excluded)

| Benchmark | Mean (bps) | Median (bps) | 95% CI | % overpaid |
|-----------|-----------|-------------|--------|------------|
| Fill vs open | -17.3 | +12.6 | [-49.6, +12.7] | 56% |
| Fill vs VWAP | -35.4 | -13.5 | [-85.9, +11.1] | 39% |
| Fill vs close | -73.4 | -3.9 | [-154.2, +5.4] | 42% |
| Fill vs next-day close | +81.9 | -47.9 | [-52.5, +230.5] | 44% |

Dollar-weighted IS vs VWAP: **-89.6 bps** (larger orders fill even better vs VWAP).

## Interpretation for 105 §9.4 prereg

1. **Fill vs open** (mean -17, CI includes zero): we are filling essentially AT the
   open. No systematic early-session overpay.
2. **Fill vs VWAP** (mean -35, CI includes zero): fills are at or below the intraday
   average — no leak to recover.
3. **Fill vs close** (mean -73): early-session fills are cheaper than EOD. Consistent
   with momentum stocks drifting up after our entry, which is the directional
   edge we expect, NOT an execution problem.
4. **Dollar-weighted IS more negative** (-90 bps): our larger orders (NVDA, NVTS, NET,
   MU — liquid names) fill even better relative to VWAP.

**Conclusion:** The execution-leak rationale for 105's entry-timing optimization
is not supported. Current fills are already competitive. The 105 engineering
prize should be re-anchored to:
- **Execution timing of exits** (not measured here — requires sell-side IS)
- **Order-type optimization** (limit vs market, but current market orders perform well)
- **Overnight gap management** (fills vs next-close show noise, not leak)

## Data quality notes

- **30/67 trades unmatched** — weekend `run_date` entries (Sat/Sun pipeline runs)
  have no FMP OHLCV data. These are duplicate pipeline invocations where the
  actual fill occurred on the adjacent weekday; the matched 36 are the clean sample.
- **HON excluded** — fill at $217.70, FMP open at $428.22. Exact 2:1 ratio indicates
  a stock split adjustment mismatch between Alpaca (post-split) and FMP (pre-split
  or differently adjusted). IS = -4916 bps is a data artifact, not execution quality.
- **MU -431 bps** — retained as legitimate; large intraday move, not a split artifact.

## Method

- Source: `runs.alpaca.db` live buys joined to FMP `historical-price-eod/full`
- Dedup: `DISTINCT (run_date, ticker, shares, price, invest)` in SQL
- Outlier filter: |IS_vs_open| > 1000 bps excluded (1 trade = HON split artifact)
- Bootstrap: 10,000 resamples, 95% CI (seed=42, reproducible)
- IS convention: positive = overpaid = leak
- Script: `scripts/s10_open_auction_is.py`

## Per-ticker detail (clean, sorted by invested)

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
