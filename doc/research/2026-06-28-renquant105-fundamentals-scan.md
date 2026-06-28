# renquant-105: fundamental value/quality/growth scan

Date: 2026-06-28
Author: Ren Hao (with Claude Opus 4.8)
Lane: the last untested cheap PIT-clean orthogonal lane — canonical fundamental
value / quality / growth factors.
Method: identical cheap screen to the prior orthogonal-lane scans — per-day
cross-sectional rank-IC vs forward returns, vs a within-date label-shuffle floor.
**NO CPCV / FWER / DSR.** First-look triage only, not a promotion gate.

Reproduce: `scripts/fundamentals_scan.py` (universe = 134-name large-cap bars
panel `/tmp/sighunt/bars.parquet`, fundamentals = `data/fmp_harvest/*` annual).

## What was tested

9 canonical factors, each as-of the **filing date** (+2 trading-day lag), held
constant until the next annual filing:

| lane | factor | construction |
|---|---|---|
| Value | earnings yield | filed diluted EPS / **live price** |
| Value | book/price | filed BVPS / **live price** |
| Value | FCF yield | filed FCF-per-share / **live price** |
| Value | EV/EBIT (inv.) | filed EBIT / period-end EV (stale multiple) |
| Quality | ROE | key_metrics returnOnEquity |
| Quality | gross margin | grossProfit / revenue |
| Quality | low accruals | −(NetIncome − CFO) / TotalAssets |
| Growth | revenue growth | financial_growth revenueGrowth |
| Growth | EPS growth | financial_growth epsgrowth |

Horizons: forward 20 / 60 / 120 / 252d (slow horizons included because
fundamentals refresh ~annually). n ≈ 1,776–2,008 scored dates per factor/horizon.
t = circular block-bootstrap (21-day blocks, 1,000 resamples) of the daily IC mean.

## Candidate table (selected; full CSV `fund_scan_results.csv`)

| factor | h(d) | mean IC | block t | hit | IC/floor* | L/S decile bps |
|---|---:|---:|---:|---:|---:|---:|
| value_earnings_yield | 60 | **−0.0526** | **−3.07** | 0.39 | 40.0 | −428 |
| value_earnings_yield | 252 | **−0.1235** | **−7.92** | 0.20 | 76.0 | −3310 |
| value_book_to_price | 60 | **−0.0518** | **−3.12** | 0.39 | 34.2 | −282 |
| value_book_to_price | 252 | **−0.1153** | **−7.16** | 0.23 | 78.7 | −1939 |
| value_fcf_yield | 60 | −0.0399 | −2.93 | 0.40 | 24.5 | −219 |
| value_fcf_yield | 252 | −0.0914 | −5.42 | 0.34 | 52.8 | −1794 |
| value_ebit_to_ev | 252 | −0.0748 | −4.17 | 0.34 | 39.9 | −3469 |
| quality_roe | 252 | −0.0403 | −2.99 | 0.25 | 26.2 | −2399 |
| quality_gross_margin | 252 | −0.0239 | −1.31 | 0.56 | 13.3 | −1844 |
| quality_low_accruals | 252 | +0.0167 | +1.12 | 0.53 | 9.9 | +644 |
| growth_revenue | 252 | +0.0242 | +0.92 | 0.56 | 13.7 | +717 |
| growth_revenue | 60 | +0.0187 | +0.81 | 0.56 | 12.3 | +192 |
| growth_eps | 252 | −0.0440 | −3.63 | 0.39 | 27.9 | −1983 |

\* IC/floor is **not trustworthy** here — see caveats. The IC daily series has
lag-1 autocorr ≈ 0.98 (overlapping forward windows), so the within-date shuffle
floor (~0.0015) badly understates the true null. **Read the block-t, not the
ratio.** This is the same embargo/overlap-floor artifact seen on the WF gate.

## Verdict — blunt

**Nothing clears the bar as a usable standalone long edge. The only statistically
strong, stable result is value, and it points the WRONG way on this universe.**

1. **Value is the strongest signal — and it is robustly NEGATIVE.** Earnings
   yield, book/price, FCF yield and EV/EBIT all carry large, monotone-in-horizon,
   high-t **negative** IC (EY-252d t = −7.9; B/P-252d t = −7.2). Sign convention
   verified: high-EY/high-B/P names are GS/TSM/KLAC/banks; low are
   SNOW/RBLX/MDB/CRWD. So on this 134-name large-cap universe over 2018–2026,
   **cheap-by-fundamentals systematically UNDERPERFORMED expensive** — the
   documented growth/quality-led, mega-cap-momentum regime. A textbook long-value
   tilt would have bled; the only "edge" is a short-value / long-glamour tilt,
   which is just the realized regime, not a durable anomaly.

2. **The sign is regime-conditional, not stable.** Year-by-year 60d IC for value
   EY: 2018 −0.09, 2020 −0.14, 2023 −0.15, 2024 −0.08 (negative) BUT 2021 +0.04,
   2022 +0.05 (the rate-hike value-rotation, positive). B/P and revenue growth
   flip the same way. A factor that changes sign with the macro regime is not a
   carry-able standalone signal at this scale — it is a regime bet wearing a
   factor costume.

3. **Quality and growth are null-to-weak.** ROE is weakly negative (glamour
   again). Gross margin, accruals, revenue growth: |t| < 1.4 at every horizon —
   indistinguishable from noise once you discount the deflated floor. EPS growth
   is negative at 252d (mean-reversion of growth, not momentum).

**Bottom line: no fundamental factor is worth carrying as a long signal here.**
The result strengthens the standing DATA+UNIVERSE-constraint conclusion: on a
~134-name survivorship-curated mega-cap list in a growth-led regime, slow annual
value/quality has no usable orthogonal long edge.

## Is anything orthogonal to PEAD worth a second look?

Only one framing survives, and weakly: **value as a short/avoid overlay, not a
long.** The negative-value signal is mechanically orthogonal to PEAD (PEAD is a
fast post-filing drift on the *surprise/revision*; this is a slow *level* tilt on
the *price/fundamental ratio*). But (a) the sign flips with regime, (b) it is a
documented large-cap-weak factor, and (c) acting on it = shorting cheap mega-caps,
which the shorting mandate makes a very high bar. **Recommendation: do not carry
any fundamental factor.** If anything, log value-EY rank as a *context/regime
feature* (cheap-underperforming = glamour regime on), never as a tradable score.

## Caveats (PIT / survivorship / harness)

- **PIT:** factors keyed to `filingDate` (native on income/balance/cashflow;
  attached via (symbol, fiscalYear) for key_metrics/financial_growth), +2 trading-day
  lag, forward-filled to next filing. Price-based value uses the **live** daily
  price (the only live input); EV/EBIT uses a stale period-end EV and is the
  weakest PIT-wise. ~9 filings/name in window; turnover ≈ 1 refresh/name/yr.
- **Survivorship:** the 134-name universe is today's large-cap watchlist projected
  backward. Failed/delisted/small names that a real value screen would have bought
  are absent — this makes a "value works" reading OPTIMISTIC, yet value still came
  out negative, which only hardens the conclusion.
- **Shuffle floor is deflated** by overlapping forward windows (IC autocorr ≈0.98).
  IC/floor ratios are inflated and not used for the verdict; the block-bootstrap
  t-stat is the load-bearing statistic. No CPCV/FWER/DSR — this is triage.
- **Annual-only data:** no interim (quarterly) PIT here, so the signal is as slow
  as it gets; 20d/60d horizons are mostly testing a near-constant cross-section.
- Sign convention spot-checked against the latest cross-section (passes).
