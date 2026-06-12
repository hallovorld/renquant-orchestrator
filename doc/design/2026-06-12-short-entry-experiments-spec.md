# Experiment Spec — Short-Entry Trigger Validation (E2–E7)

**Status:** spec / awaiting review. Companion to
`2026-06-12-short-selling-design.md` §4. All code/results →
`epic/model-edge-experiments`; nothing merges to main.

## 0. Common protocol (applies to every experiment)

- **Data:** prod model val predictions (`pred`, `mu`, `sigma`; 254d,
  2025-02-06→2026-02-10; tickers recovered by within-date rank pairing —
  documented method, match rate 100%). Real OHLCV for outcomes. Extend to a
  2nd year with PIT model #1 (cutoff 2023-10, val 2022-10→2023-07) where noted.
- **No look-ahead:** signals computed at close of day *t*; entry priced at
  **open of t+1**; outcomes from that entry price.
- **Universe:** single names only (ETFs excluded: SPY, XL*, GLD, TLT).
- **Event dedup:** max 1 event per ticker per 20 trading days (first trigger
  wins); overlapping events across tickers allowed but reported.
- **Cost model:** borrow 1.0%/yr (conservative ETB), slippage 5 bps/side,
  zero commission. Dividends: subtract actual dividends paid during the hold
  (short pays them) — from the OHLCV dividend column.
- **Outcomes:** raw and SPY-hedged returns at 20d and 60d horizons; stop-sim
  uses daily HIGHs (conservative: a high touching the stop = stopped).
- **Statistics:** report n per cell; cells n<30 = inconclusive. Block
  bootstrap (by calendar month) for 90% CIs on mean P&L.
- **Multiple-testing control:** each experiment names ONE pre-registered
  primary cell; the parameter grid is sensitivity analysis only. Pass/fail is
  judged on the primary cell. PASS = hit-rate(fall, 20d) ≥ 55% AND net hedged
  mean P&L > 0 (90% CI excluding 0 preferred) AND stop-simulated worst event
  ≥ −25%.

## E8 — Efficiency-extension replay (NEW in v3; runs after long-side WF gate is green)

- **Setup:** identical inputs, QP with vs without a bounded short sleeve
  (gross ≤120%, short leg ≤10% NAV, per-name 3%, borrow 1%/yr priced in the
  objective). Short candidates = lowest-rank liquid single names (ETB).
- **PASS:** net IR improvement (costs priced) AND MaxDD not worsened AND
  turnover increase ≤ 1.5×.
- **Primary cell:** 110/10. Sensitivity: 120/20.

## E2 — Inverted protection (sustained bearish μ) — DEPRIORITIZED (v3)

- **Event:** calibrated μ < −τ_strong on **N consecutive** trading days;
  event date = Nth day.
- **Primary cell:** τ_strong = pooled 2.5th percentile of μ; N = 3.
- **Grid:** τ ∈ {1%, 2.5%, 5% pooled quantiles} × N ∈ {2, 3, 5}.
- **Output:** events table (date, ticker, μ-path), metrics per cell, primary
  verdict. Also run on PIT-#1 year (different regime mix) as out-of-period check.

## E3 — Broken momentum (fresh rank breakdown) — DEPRIORITIZED (v3)

- **Event:** ticker's cross-sectional pred-rank was in the **top 50%** at
  t−k and is in the **bottom decile** at t.
- **Primary cell:** k = 10 trading days, bottom 10%.
- **Grid:** k ∈ {5, 10} × bottom ∈ {5%, 10%}.
- **Rationale check built in:** report what fraction of events are
  defensive/mega-cap (the E1 failure mode) vs genuinely broken names.

## E4 — Trend veto overlay — DEPRIORITIZED (v3)

- **Filter:** price < 200-DMA at event date (real OHLCV).
- **Test:** paired comparison of E2/E3 cells with vs without the filter —
  the filter must IMPROVE hedged P&L by ≥ 2pp without cutting n below 30.

## E5 — Short-interest dynamics overlay (blocked on FINRA backfill)

- **Backfill:** FINRA bi-monthly short-interest archives; **point-in-time
  join: data usable only from publication date (+9 business days after
  settlement), not settlement date** — anything else is look-ahead.
- **Features:** Δshares_short (m/m), days-to-cover (DTC).
- **Overlay:** rising shares_short AND DTC ∈ [2, 8] (above 8 = squeeze-risk
  veto, below 2 = no crowding signal).
- **Test:** same paired-improvement criterion as E4.

## E6 — Phase-0 index-hedge replay (independent; can run now)

- **Windows:** 2022 bear (2022-01→12, requires PIT-#1-era data), 2025-04 dip
  (2025-03-15→05-15), dead window (2025-10→2026-01), full validation year.
- **Book proxy:** daily top-8 tranche basket (documented limitation: proxy,
  not the live book; live equity curve used where it exists).
- **Hedge:** short SPY, notional = h · β_basket · NAV; β = 60d rolling OLS.
  Grid h ∈ {0.25, 0.5, 0.75, 1.0}; **primary h = 0.5**.
- **Triggers compared:** (a) drawdown breaker armed, (b) hard_bear active,
  (c) always-on (cost baseline). Costs: SPY borrow 0.3%/yr; SH variant priced
  separately (0.89% ER + measured daily-reset drag).
- **PASS:** MaxDD reduction ≥ 25% in stress windows AND bull-window drag
  ≤ 2% NAV/yr on the primary cell.

## E7 — Exit-parameter scan (runs on whichever trigger passes)

- **Grid:** hold ∈ {10, 20, 40, 60}d × hard stop ∈ {8%, 12%, 20%} ×
  profit-lock ∈ {none, (15% arm, ⅓ giveback)}.
- **Primary cell:** 20d / 12% / lock-on (the §4.5 priors).
- **Output:** final exit constants for the design's §4.5 table.

## Sequencing & effort

v3 order: E6 now; E8 after long-side gate green; FINRA backfill → E5; E2/E3/E4 optional sensitivity only; E4 after; E5 after backfill; E7 last. Each experiment is
a CPU-only script over existing artifacts (minutes), except the FINRA
backfill (network + parsing, ~half day). Verdicts append to this spec.
