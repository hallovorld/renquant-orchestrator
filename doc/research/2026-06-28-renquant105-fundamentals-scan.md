# renquant-105: fundamental value/quality/growth scan

Date: 2026-06-28
Author: Ren Hao (with Claude Opus 4.8)
Lane: canonical fundamental value / quality / growth factors on the 134-name
large-cap universe.
Kind: **current-vintage retrospective diagnostic** — NOT a point-in-time backtest,
NOT survivorship-corrected. See "What this is / is NOT" below.
Method: identical cheap screen to the prior orthogonal-lane scans — per-day
cross-sectional rank-IC vs forward returns, vs a within-date label-shuffle floor.
**NO CPCV / FWER / DSR.** First-look triage only, not a promotion gate.

Reproduce (explicit CLI + manifest, matching #202's sighunt.py standard):

```
python scripts/fundamentals_scan.py --as-of 2026-06-26 --out /tmp/fund_scan
```

writes `results.csv` + `manifest.json` (as-of, code commit, bars-cache sha256, all
five harvest-input sha256s, the source harvest endpoint manifests, parameters,
kept-symbol list + hash). Universe = 134-name large-cap bars panel
(`/tmp/sighunt/bars.parquet`); fundamentals = a single one-shot FMP `/stable`
annual harvest (`data/fmp_harvest/*_291.parquet`, harvested 2026-06-25 per the
endpoint manifests).

## What this is / is NOT (PIT label removed)

This is **not** a PIT-clean lane. The fundamentals come from a *current* one-shot
FMP `/stable` annual pull (`period=annual&limit=20`, harvested 2026-06-25). We
attach each row's `acceptedDate`/`filingDate` and lag it, but the harvest retains
**no as-filed snapshot**: a historical annual row in a current harvest can already
reflect later restatements/revisions, and nothing in the source manifest or API
proves each value equals what was visible on its original acceptance date. So the
time-alignment is a best-effort **vintage** alignment, not proven as-filed PIT.
There is no "PIT-clean orthogonal lane" here — only a current-vintage retrospective
diagnostic on a biased current-watchlist panel. Read every number accordingly.

## What was tested

9 canonical factors, each keyed to its **acceptedDate** (falling back to
`filingDate` when acceptedDate is missing), made usable on the next trading session
at/after acceptance + 1 trading-day slack, held constant until the next annual
filing:

| lane | factor | construction |
|---|---|---|
| Value | earnings yield | harvested diluted EPS / **live price** |
| Value | book/price | harvested BVPS / **live price** |
| Value | FCF yield | harvested FCF-per-share / **live price** |
| Value | EV/EBIT (inv.) | harvested EBIT / period-end EV (stale multiple) |
| Quality | ROE | key_metrics returnOnEquity |
| Quality | gross margin | grossProfit / revenue |
| Quality | low accruals | −(NetIncome − CFO) / TotalAssets |
| Growth | revenue growth | financial_growth revenueGrowth |
| Growth | EPS growth | financial_growth epsgrowth |

Timing detail: income/balance/cash_flow carry `acceptedDate` natively (no nulls in
this harvest; ~16% of rows have an acceptedDate the calendar day *before*
filingDate, i.e. after-hours acceptance). key_metrics/financial_growth do not carry
it, so acceptedDate+filingDate are attached from income_statement on
(symbol, fiscalYear) with the same next-session rule; the documented fallback is
`filingDate` whenever acceptedDate is absent.

Horizons: forward 20 / 60 / 120 / 252d. n ≈ 1,777–2,009 scored dates per
factor/horizon.

## Dependence treatment (the "−7.9" was overlap-inflated)

Forward returns overlap up to the horizon, so the daily-IC series is heavily
autocorrelated — **lag-1 autocorr 0.93–1.00**, ≈0.99 at 252d (column
`ic_lag1_autocorr`). The original 21-day moving-block bootstrap is far too short for
252d-overlapping windows; it understated uncertainty and inflated the t-stat. We
now report, per factor/horizon:

* `nonover_t (n)` — t-stat on **non-overlapping** IC samples (one IC every `h`
  sessions → approximately independent windows; n=8 at 252d). The most honest, and
  smallest-n, significance read.
* `sb_t_{21,63,126,252}` — **stationary-bootstrap** (Politis-Romano, geometric
  blocks) t-stats across four mean block lengths, a **sensitivity sweep**. Longer
  blocks retain more dependence → wider SE → smaller |t|.

What this does to the headline value result, EY-252d (IC −0.122):

| stat | value |
|---|---:|
| old 21-day block-t (reported in PR) | **−7.92** |
| stationary-bootstrap t, block 21 / 63 / 126 / 252 | −6.19 / −4.18 / −3.76 / **−3.47** |
| non-overlapping t (n=8 windows) | **−2.41** |

The t shrinks from −7.9 toward −2.4 to −3.5 once the overlap is respected. The
sign is stable and negative, but the **magnitude of significance is much smaller**
than the original block-t implied. Given this — and the biased panel and the
deflated shuffle floor — we do **not** call the value result statistically
strong or stable; it is a soft, biased-panel negative tilt.

## Candidate table (dependence-aware; full CSV `results.csv`)

| factor | h(d) | mean IC | ac1 | nonover_t (n) | sb_t @21/63/126/252 | hit | L/S bps |
|---|---:|---:|---:|---:|---:|---:|---:|
| value_earnings_yield | 252 | −0.122 | 0.99 | −2.41 (8) | −6.19/−4.18/−3.76/−3.47 | 0.21 | −3307 |
| value_book_to_price | 252 | −0.115 | 0.99 | −1.79 (8) | −5.11/−3.55/−3.38/−3.57 | 0.23 | −1941 |
| value_fcf_yield | 252 | −0.091 | 1.00 | −2.00 (8) | −4.25/−2.73/−2.29/−2.14 | 0.34 | −1793 |
| value_ebit_to_ev | 252 | −0.075 | 0.99 | −1.12 (8) | −3.14/−2.23/−2.01/−2.00 | 0.34 | −3467 |
| quality_roe | 252 | −0.040 | 0.99 | −0.36 (8) | −2.24/−1.48/−1.27/−1.25 | 0.26 | −2397 |
| quality_gross_margin | 252 | −0.024 | 1.00 | −0.36 (8) | −1.01/−0.70/−0.59/−0.64 | 0.56 | −1842 |
| quality_low_accruals | 252 | +0.015 | 0.99 | +0.08 (8) | +0.74/+0.50/+0.42/+0.38 | 0.51 | +644 |
| growth_revenue | 252 | +0.024 | 1.00 | +0.05 (8) | +0.71/+0.49/+0.39/+0.42 | 0.56 | +719 |
| growth_eps | 252 | −0.041 | 0.99 | −0.40 (8) | −2.88/−2.10/−2.04/−1.98 | 0.38 | −1974 |

(shorter horizons in the CSV; the shuffle_floor column is reported but **deflated**
by overlap — read the dependence-aware t-stats, not the floor.)

## Verdict — blunt, softened for the dependence/panel caveats

**Nothing clears the bar as a usable standalone long edge.** The strongest signal
is value, and on this panel it points the WRONG way (negative), but it is **only
softly significant once overlap is respected** — not the "strong, stable" edge the
original inflated t implied.

1. **Value is the strongest signal and is NEGATIVE on this panel — but soft.**
   Earnings yield / book-to-price / FCF yield carry negative IC that grows with
   horizon. Under the honest non-overlapping t it is roughly −2.4 (EY), −1.8 (B/P),
   −2.0 (FCF) at 252d; the stationary-bootstrap sweep lands around −2 to −4
   depending on block length. So "cheap-by-fundamentals underperformed expensive"
   over 2018–2026 on this watchlist is directionally supported (consistent with the
   documented growth-led mega-cap regime), but it is a soft, biased-panel read, not
   a strong anomaly. Sign convention verified (high-EY = GS/TSM/KLAC/banks; low =
   SNOW/RBLX/MDB/CRWD). A textbook long-value tilt would have bled here.

2. **The sign is regime-conditional.** Year-by-year 60d IC for value EY is negative
   in 2018/2020/2023/2024 but POSITIVE in the 2021/2022 value rotation. A factor
   that flips with the macro regime is not a carry-able standalone signal at this
   scale.

3. **Quality and growth are null.** Under the dependence-aware stats, ROE, gross
   margin, accruals, and revenue growth all sit at |nonover_t| < 0.9 and
   |sb_t| < 2.3 at every horizon — indistinguishable from noise. EPS growth is
   weakly negative at 252d (sb_t ≈ −2.0 at block 21, fading to −2.0 by block 252).

**Bottom line: no fundamental factor is worth carrying as a long signal on THIS
panel.** Limited strictly to this biased current-watchlist retrospective panel, the
lane comes up empty for a usable long edge. We do NOT extrapolate to a clean
universe.

## Is anything orthogonal to PEAD worth a second look?

Mechanically, the slow value level-tilt is orthogonal to PEAD (a fast post-filing
drift on the surprise/revision). But the only framing that even arguably survives
is **value as a short/avoid overlay, not a long** — and even that is (a)
soft once overlap is respected, (b) sign-flipping by regime, (c) a documented
large-cap-weak factor, and (d) acting on it = shorting cheap mega-caps, which the
shorting mandate makes a very high bar. **Recommendation: carry no fundamental
factor.** At most, log value-EY rank as a *context/regime feature*
(cheap-underperforming = glamour regime on), never as a tradable score.

## Caveats (label, dependence, survivorship, harness)

- **Not PIT.** Current one-shot vintage harvest; no as-filed snapshot retained;
  historical rows can carry later restatements. acceptedDate-keyed (filingDate
  fallback) + next-session + 1-day slack, forward-filled to next filing. Price-based
  value uses the **live** daily price; EV/EBIT uses a stale period-end EV (weakest).
  ~9 filings/name in window; turnover ≈ 1 refresh/name/yr.
- **Dependence:** IC lag-1 autocorr ≈0.99 at long horizons. We report
  non-overlapping t and a stationary-bootstrap block-length sweep; the value t falls
  from the inflated −7.9 toward −2.4 to −3.5. The within-date shuffle floor is
  **deflated** by overlap and is NOT used for the verdict. No CPCV/FWER/DSR — triage.
- **Survivorship (framing corrected):** the 134-name universe is today's surviving
  large-cap watchlist projected backward. Failed/delisted/distressed names a real
  historical value screen would have held are absent. This does **not** cleanly
  "harden" the negative read — it removes names and shifts both ranks and realized
  returns in directionally **ambiguous** ways. All conclusions are limited to this
  biased current-watchlist panel.
- **Annual-only data:** no interim (quarterly) PIT; the cross-section is near-constant
  at 20d/60d. Read-only on the data tree; no canonical path written; no git in the
  live tree; no self-merge.
- Sign convention spot-checked against the latest cross-section (passes).
