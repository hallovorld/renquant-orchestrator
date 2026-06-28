# renquant105 PEAD %-surprise — candidate signal (long-side economics + orthogonality)

- **Date:** 2026-06-28
- **Status:** CANDIDATE SIGNAL (lean, candidate-style — NOT a CPCV/FWER/DSR validation).
  The one real lead out of the trend/factor signal hunt. This doc does the
  *proportionate* follow-up the cheap screen earned: long-side-only economics +
  orthogonality. It is NOT a promote recommendation.
- **Reproduce:** `scripts/pead_test.py` (the cheap screen) then
  `scripts/pead_longonly_orthogonality.py` (this doc's new economics + orthogonality).
  READ-ONLY: bars `/tmp/sighunt/bars.parquet` (134 single names, 2018-05..2026-06),
  earnings `data/fmp_harvest/earnings_291.parquet`. No orders, no git in the live tree,
  no canonical writes.

## The measured candidate

### Cross-sectional IC (the cheap screen that passed)

Per-date Spearman rank-IC of the as-of earnings-surprise signal vs forward returns;
NW t-stat (overlap lag = horizon); within-date shuffle placebo floor (200 perms).

| signal | horizon | n_dates | mean_IC | NW_t | hit_rate | shuffle_IC_std | IC / floor |
|---|---|---|---|---|---|---|---|
| **pct_surprise** | **20** | 2006 | **+0.0313** | **3.12** | 0.594 | 0.00215 | **14.5×** |
| pct_surprise | 60 | 1966 | +0.0327 | 1.83 | 0.604 | 0.00212 | 15.4× |
| SUE | 20 | 1758 | +0.0216 | 2.12 | 0.568 | 0.00251 | 8.6× |
| SUE | 60 | 1718 | +0.0107 | 0.75 | 0.547 | 0.00244 | 4.4× |
| raw_surprise | 20 | 2006 | +0.0050 | 0.63 | 0.518 | 0.00229 | 2.2× |
| raw_surprise | 60 | 1966 | −0.0082 | −0.59 | 0.456 | 0.00219 | −3.8× |

The headline is **%-surprise @20d: IC +0.0313, NW t=3.12, 14.5× the shuffle floor,
placebo-clean.** The raw (unscaled) surprise is null — **scaling is load-bearing**
(%/SUE only). Low-turnover: ~quarterly cadence (one earnings event per name per quarter).

### (1) LONG-SIDE-ONLY economics (the usability test)

The short leg is unmonetizable under our shorting mandate, so usability rests entirely
on the LONG leg. On each quarterly rebalance (every 63 trading days, non-overlapping;
28 rebalances) we take names with a POSITIVE recent %-surprise (the monetizable side),
rank them, take the top-quintile / top-decile, equal-weight, and measure excess return
vs the equal-weight universe mean. NET subtracts one-way 11 bps per quarterly rebalance.

| leg | horizon | n_rebal | avg_names | gross excess bps | **net excess bps** | hit-rate vs uni | rebal pos-frac |
|---|---|---|---|---|---|---|---|
| top-quintile | 20 | 28 | 21.9 | +53.8 | **+42.8** | 0.468 | 0.54 |
| top-quintile | 60 | 28 | 21.9 | +309.7 | **+298.7** | 0.512 | 0.61 |
| top-decile | 20 | 28 | 11.3 | +1.9 | **−9.1** | 0.432 | 0.50 |
| top-decile | 60 | 28 | 11.3 | +257.6 | **+246.6** | 0.519 | 0.61 |

**Long-only IC** (IC restricted to the monetizable positive-surprise names only):

| horizon | n_dates | long-only mean IC | hit_rate |
|---|---|---|---|
| 20 | 2006 | **+0.0298** | 0.571 |
| 60 | 1966 | **+0.0378** | 0.592 |

**Blunt read of the long leg.** The earlier event study showed the drift is
**short-skewed** (Q1 −101 vs Q5 −24 bps @20d): most of the L/S spread is the bad-news
leg falling, which we cannot trade. So the question is exactly how much the LONG leg
delivers alone — and the answer is *positive but modest and noisy*:

- **Top-quintile @20d: +42.8 bps net** excess — but this is a **mean** over only 28
  quarters with **std ≈ 215 bps** (median only +20.7 bps, right-skewed); the per-rebalance
  t-stat is **≈ 1.30** (not significant). Worst quarter −344 bps, best +553 bps.
- **Top-quintile @60d: +298.7 bps net** — large but with **std ≈ 683 bps** over 28
  quarters (worst −1061 bps, best +1716 bps); per-rebalance t ≈ **2.36**. The 60d window
  overlaps less cleanly into quarters and carries far more beta/market dispersion.
- **Top-decile @20d is net-NEGATIVE (−9.1 bps)** — concentrating into the top 10% of
  positive surprises does NOT help at 20d; the quintile is the better long-only cut.
- Hit-rate vs the universe is ≈ **47–52%** (coin-flip at the name level); the edge is a
  small mean tilt, not a high name-level win-rate. Rebalance-level pos-frac 0.50–0.61.

The **long-only IC (+0.030 @20d, +0.038 @60d)** is the more stable measure than the
small-N per-rebalance excess and is consistent with the full-cross-section screen.

### (2) ORTHOGONALITY vs canonical price factors

Per-date cross-sectional Spearman rank correlation of the %-surprise signal vs the
canonical price factors from the hunt (recomputed on the same bars panel).

| factor | n_dates | mean rank-corr | abs-mean rank-corr | p05 | p95 |
|---|---|---|---|---|---|
| mom_12_1 | 1778 | +0.153 | 0.160 | −0.034 | +0.311 |
| mom_6_1 | 1904 | +0.140 | 0.160 | −0.079 | +0.345 |
| ma200_dist | 1881 | +0.181 | 0.188 | −0.017 | +0.379 |

Correlations are **low-to-moderate (+0.14 to +0.18)** — a mild positive tilt (positive
surprisers also tend to have positive price momentum, as expected) but far from
collinear. This is a **genuinely different bet** (Fundamental-Law value: an orthogonal
complement, not a re-skin of momentum).

**PENDING (follow-up, NOT fabricated):** correlation of %-surprise ranks vs the LIVE
model (PatchTST) scores requires faithful per-name decision-ledger data. The ledger is
currently too thin/impaired for a faithful cross-section (see the 2026-06-27 trend-signal
baseline audit: ≈0.45 overlap-ratio, scorer-mixture). This correlation is flagged as a
required follow-up once the ledger reaches sufficiency — it is **not** computed or
estimated here.

## Honest caveats (verbatim — do not soften)

- **Modest effect.** ~2–3% IC. This is a small cross-sectional edge, not a strong signal.
- **Scaling is load-bearing.** The RAW surprise is null (IC +0.005 / −0.008, NW t<1);
  only the SCALED forms (%-surprise, SUE) clear the floor. %-surprise is the strongest.
- **Short-skewed drift.** The L/S spread is driven by the bad-news (short) leg, which is
  unmonetizable under our shorting mandate. The monetizable LONG leg alone is positive
  but modest (+42.8 bps net @20d top-quintile) and noisy (per-rebalance t≈1.3, 28 quarters).
- **NOT regime-stable.** Year-by-year SUE×fwd60 IC is **negative in 2022 (−0.047) and
  2024 (−0.041)** (pos-frac 0.36 and 0.29) and positive in 2019/2021/2023/2025. The edge
  is conditional on regime, not a constant.
- **PIT timing.** epsEstimated is point-in-time-clean in principle, but the harvested
  `lastUpdated` field only carries meaningful per-event timestamps from **2024-09 onward**;
  pre-2024 events carry a generic floor timestamp. So the pre-2024 point-in-time guarantee
  rests on the **enter-signal-+1-trading-day-after-announcement timing convention**, not on
  a per-event PIT update stamp. No look-ahead beyond that convention.
- **Small-N economics.** The long-only excess rests on 28 non-overlapping quarterly
  rebalances on a 134-name universe. Treat the per-rebalance means as directional, not
  significance-grade; the long-only IC is the more robust statistic.

## Proposed use (NOT a core signal)

A **low-turnover 20d %-surprise LONG-side TILT / overweight** on the 104 book:
overweight names with a recent strong positive %-surprise (top-quintile of positive
surprisers), rebalanced ~quarterly to match the earnings cadence. Rationale:

- It is **orthogonal** (+0.14–0.18 to momentum/trend) → a genuine diversifying complement.
- The monetizable LONG leg is **net-positive** at the quintile cut (top-decile is not — use
  the quintile).
- Low turnover (~1 rebalance/quarter) keeps cost drag small (one-way 11 bps).

It is explicitly an **orthogonal complement / sizing tilt, NOT a core signal** and NOT a
replacement for the PatchTST primary. Given the regime instability (2022/2024 negative)
and modest IC, any live use should be **size-capped and regime-aware**, not a standalone bet.

## Honesty ledger

- READ-ONLY: bars and earnings parquet read from `/tmp` and `data/fmp_harvest`
  respectively; no canonical path written; no git in the live tree; no order placed.
- All numbers reproduce from the two scripts above on the stated inputs.
- The LIVE-model-score orthogonality is a flagged follow-up, NOT estimated here.
- This is a CANDIDATE doc. Do not act on it as a validated signal.
