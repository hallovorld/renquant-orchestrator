# renquant105 PEAD %-surprise — candidate signal (event-driven long-only economics + orthogonality)

- **Date:** 2026-06-28
- **Status:** EXPLORATORY (lean candidate-style — NOT a CPCV/FWER/DSR validation, NOT a
  promote recommendation). The one lead out of the trend/factor signal hunt. This doc does
  the proportionate follow-up the cheap screen earned: a FAITHFUL event-driven long-side
  economics pass + orthogonality.
- **PIT status — NON-POINT-IN-TIME (downgraded per PR #203 review):** the earnings parquet
  is a SINGLE CURRENT one-shot harvest. `epsEstimated` on a historical row is the value in
  *today's* harvest, NOT a captured pre-announcement consensus snapshot, and `lastUpdated`
  is a generic floor before 2024-09 so it cannot establish per-event vintage. The +1d entry
  convention controls ENTRY TIMING only; it does NOT prove the estimate was the consensus
  that existed pre-event or was not later revised. **ALL results here are non-PIT
  exploratory evidence — a directional probe, not a clean PIT backtest.** Do not call this
  "PIT-clean in principle."
- **Reproduce:** `scripts/pead_test.py --as-of 2026-06-26` (cheap screen) then
  `scripts/pead_longonly_orthogonality.py --as-of 2026-06-26` (this doc's economics +
  orthogonality). Both take `--as-of` / `--bars-cache` / `--earnings` / `--out`, are pinned
  (no datetime.now), hash inputs and write a manifest. READ-ONLY: bars
  `/tmp/sighunt/bars.parquet` (134 single names, 2018-05..2026-06), earnings
  `data/fmp_harvest/earnings_291.parquet`. No orders, no git in the live tree, no canonical
  writes.
- **Round-2 review corrections (PR #203, 2026-06-28):** the event-driven economics had two
  execution bugs that invalidated the old −705 bps/yr headline — (1) idle (cash) days were
  scored against a rising market (a benchmark-exposure artifact) and ALL calendar days were
  counted active; (2) event selection used one full-sample %-surprise threshold (future
  information). Both are fixed: economics/significance are now restricted to ACTIVE days (with
  a separate total-strategy line), and selection uses an EXPANDING strictly-prior-history
  threshold. The cheap-screen IC/HAC path's NumPy overflow/invalid warnings are fixed with
  finite-value guards that fail loudly (tests: `tests/test_research_pead_finite_guards.py`).
  The corrected number is reported below — the −705 figure is NOT preserved.

## The measured candidate

### Cross-sectional IC (the cheap screen) — winsorized denominator

Per-date Spearman rank-IC of the as-of earnings-surprise signal vs forward returns; NW
t-stat (overlap lag = horizon); within-date shuffle placebo floor (200 perms). The
%-surprise denominator is now WINSORIZED — `|epsEstimated|` floored at its 5th percentile
(0.110) — so tiny estimates near zero cannot dominate the top-positive selection.

| signal | horizon | n_dates | mean_IC | NW_t | hit_rate | shuffle_IC_std | IC / floor |
|---|---|---|---|---|---|---|---|
| **pct_surprise** | **20** | 2006 | **+0.0290** | **2.96** | 0.589 | 0.00217 | **13.3×** |
| pct_surprise | 60 | 1966 | +0.0281 | 1.63 | 0.594 | 0.00211 | 13.3× |
| SUE | 20 | 1758 | +0.0216 | 2.12 | 0.568 | 0.00251 | 8.6× |
| raw_surprise | 20 | 2006 | +0.0050 | 0.63 | 0.518 | 0.00229 | 2.2× |

(SUE and raw_surprise are unchanged by the winsorization, which touches only the %-surprise
denominator; their values are from the same run.)

The headline is **%-surprise @20d: IC +0.0290, NW t=2.96, ~13× the shuffle floor,
placebo-clean** (modestly attenuated from the prior +0.0313 once the denominator is
winsorized — the tiny-estimate names were inflating it). The raw (unscaled) surprise is
null — **scaling is load-bearing** (%/SUE only). Low-turnover at the *signal* level
(~quarterly cadence: one earnings event per name per quarter), but see the event-driven
turnover below — at 20d the portfolio churns hard.

### (1) EVENT-DRIVEN long-only economics (the faithful usability test)

The short leg is unmonetizable under our shorting mandate, so usability rests on the LONG
leg. **The prior table sampled one arbitrary calendar phase (`trading_days[252::63]`,
28 rebalances) and subtracted a single fixed 11 bps per sampled horizon return — that
overstated the edge.** It is replaced with a faithful design, and that design is now
corrected for two execution bugs Codex flagged in round 2 (PR #203 review, 2026-06-28):

- **Look-ahead-free selection (fix 2):** an event is selected only if its %-surprise clears
  the top-quintile / top-decile of the **EXPANDING distribution of STRICTLY-PRIOR positive
  surprises** — no single full-sample quantile applied retroactively. (Warmup: events before
  40 prior positives are skipped — ~1% of events; selection barely moved, 693→686.)
- **Active-day economics (fix 1):** excess vs the EW universe, and its significance, are
  computed on **ACTIVE days only** — days the (lagged) portfolio actually holds names. The
  prior table computed `excess = port − universe` over the WHOLE sample and counted ALL
  calendar days as active, so idle (cash) days were scored as an invested portfolio shorting
  a rising market — a benchmark-exposure artifact. The fully-funded **total-strategy** return
  (idle days held as cash @0) is reported alongside.

Each selected event opens +1d, closes at the horizon; overlapping holdings aggregate into one
EW portfolio, rebalanced daily; weights lagged one day; **cost on ACTUAL daily turnover**
(`|Δw|` = entry + exit) at 11 bps one-way.

| leg | horizon | n_active | avg_held | turnover | gross cum (active) | cost | **net cum (active)** | net/yr active | net/yr total | daily t |
|---|---|---|---|---|---|---|---|---|---|---|
| top-quintile | 20 | 1792 | 7.6 | 372.0× | −2058 bps | 4092 bps | **−6150 bps** | **−865 bps/yr** | −1111 bps/yr | **−0.34** |
| top-quintile | 60 | 1989 | 20.3 | 116.5× | +3329 bps | 1281 bps | **+2048 bps** | **+259 bps/yr** | +200 bps/yr | **+0.92** |
| top-decile | 20 | 1605 | 4.1 | 294.7× | +2649 bps | 3241 bps | **−592 bps** | **−93 bps/yr** | −634 bps/yr | +0.35 |
| top-decile | 60 | 1987 | 9.8 | 118.5× | +7205 bps | 1304 bps | **+5901 bps** | **+748 bps/yr** | +713 bps/yr | +1.18 |

**This is the decisive change, and the corrected number kills the old headline.** Under the
look-ahead-free, active-day turnover model:

- **Top-quintile @20d is NET-NEGATIVE: −865 bps/yr on active days (−1111 total), daily
  t = −0.34.** The prior −705 bps/yr was NOT mainly a cash-vs-market artifact — restricting to
  active days makes 20d slightly WORSE, because the active-day GROSS excess is itself negative
  (−2058 bps): the 20d hold with ~7.6 names churns fast (turnover ≈ 372× → ~4092 bps cost)
  and there is no positive gross to pay it from. The prior "+42.8 bps net @20d" does not
  survive a faithful entry/exit cost — Codex's original flag holds.
- **Top-quintile @60d is positive but EVEN WEAKER than before: +259 bps/yr net on active days
  (+200 total), daily t = +0.92 (was +398 bps/yr, t 1.27 under the buggy whole-sample
  framing).** Removing the look-ahead threshold and the idle-day benchmark exposure pulls the
  60d net DOWN and below t = 1 — directional at best, clearly NOT significance-grade.
- **Top-decile** mirrors it: net-negative at 20d (−93 bps/yr active), +748 bps/yr at 60d
  (t = 1.18, also down from +843/yr, t 1.33). Concentrating helps a little at 60d but does
  not change the verdict.

The honest read: **the monetizable long leg is unusable at 20d after real costs (net-negative
on active days) and only weakly/insignificantly positive at 60d (t < 1 at the quintile).** The
20d horizon is where the original tilt was proposed; it does not survive.

### (1b) 63-phase dispersion of the OLD calendar-sampled design

To show how phase-sensitive the prior single-phase framing was, the old
`trading_days[252::63]` design is swept over all 63 phase offsets (top-quintile, fixed
11 bps/rebal):

| horizon | n phases | net mean | net std | min | max | frac phases > 0 |
|---|---|---|---|---|---|---|
| 20 | 63 | +58.3 bps | 46.3 | −30.0 | +211.4 | 0.94 |
| 60 | 63 | +220.6 bps | 48.0 | +118.8 | +360.6 | 1.00 |

The 20d net ranges from −30 to +211 bps across phases (std 46) — **the originally-reported
single number was one draw from a wide distribution.** Note this calendar-sampled framing
*understates* turnover (one rebalance per 63 days), so even its "best" phases are not the
faithful economics; the event-driven table above is. The 60d calendar-sampled phases are
all positive, consistent with the corrected event-driven +259 bps/yr active being a small
positive-but-insignificant (daily t ≈ 0.92) 60d tilt. (This phase sweep is unchanged — it
diagnoses the OLD design and is kept verbatim for that purpose.)

### (1c) Long-only IC (positive-surprise side only)

| horizon | n_dates | long-only mean IC | hit_rate |
|---|---|---|---|
| 20 | 2006 | **+0.0259** | 0.566 |
| 60 | 1966 | **+0.0301** | 0.577 |

The long-only IC (+0.026 @20d, +0.030 @60d, winsorized) is the more stable measure than the
small-N economics and remains positive — i.e. there *is* a weak positive rank-signal on the
long side, but it does not monetize at 20d once you pay to trade it.

### (2) ORTHOGONALITY vs canonical price factors

Per-date cross-sectional Spearman rank correlation of the %-surprise signal vs the canonical
price factors from the hunt (recomputed on the same bars panel).

| factor | n_dates | mean rank-corr | abs-mean rank-corr | p05 | p95 |
|---|---|---|---|---|---|
| mom_12_1 | 1778 | +0.149 | 0.156 | −0.029 | +0.302 |
| mom_6_1 | 1904 | +0.138 | 0.157 | −0.066 | +0.337 |
| ma200_dist | 1881 | +0.179 | 0.184 | −0.011 | +0.365 |

Correlations are **low-to-moderate (+0.14 to +0.18)** — a mild positive tilt (positive
surprisers also tend to have positive price momentum) but far from collinear. As a *rank
signal* it is a genuinely different bet; that orthogonality survives even though the
*tradable economics* do not.

**PENDING (follow-up, NOT fabricated):** correlation of %-surprise ranks vs the LIVE model
(PatchTST) scores requires faithful per-name decision-ledger data. The ledger is currently
too thin/impaired for a faithful cross-section (see the 2026-06-27 trend-signal baseline
audit: ≈0.45 overlap-ratio, scorer-mixture). Flagged as a required follow-up once the ledger
reaches sufficiency — it is **not** computed or estimated here.

## Honest caveats (verbatim — do not soften)

- **NON-PIT exploratory.** Single current one-shot harvest; `epsEstimated` is today's value,
  not a captured pre-announcement consensus; `lastUpdated` is a generic floor pre-2024-09.
  The +1d convention is entry timing only. Treat every number as a directional probe.
- **The long leg does not monetize at 20d.** Under a look-ahead-free (expanding-threshold),
  active-day, turnover-based cost model, top-quintile @20d is **net-negative (−865 bps/yr on
  active days, −1111 total, daily t −0.34)**; the prior +42.8 bps was a single-phase /
  fixed-cost artifact, and the earlier −705 figure was computed with a future-information
  threshold and an idle-day benchmark exposure (both now removed; the corrected active-day
  number is WORSE).
- **60d is positive but insignificant — weaker than first reported.** +259 bps/yr net on
  active days (+200 total), daily t ≈ 0.92 (below 1) — was +398/yr, t 1.27 under the buggy
  whole-sample / look-ahead framing. Directional, clearly not significance-grade.
- **Modest IC, scaling load-bearing.** ~2.6–3.0% IC; the RAW surprise is null; only the
  SCALED (%-surprise winsorized, SUE) forms clear the floor.
- **NOT regime-stable.** Year-by-year SUE×fwd60 IC is negative in some years (e.g. 2022,
  2024) and positive in others — conditional on regime, not constant.
- **Small-N / phase-sensitive economics.** The calendar-sampled design swings −30..+211 bps
  @20d across phases; the event-driven read is the faithful one and it is weak.

## Proposed use (NOT a core signal)

Given the corrected economics, **there is no clean case for a 20d tilt** — it loses money
after costs (net-negative on active days). The most that is defensible from this evidence is a
**low-turnover ~60d %-surprise LONG-side overweight**, where lower churn keeps a small
positive net (+259 bps/yr at the quintile on active days, daily t ≈ 0.92) — but with the
look-ahead and idle-day artifacts removed that net is now **below t = 1, i.e. directional and
insignificant**, so it would need stronger validation (a real PIT estimate-vintage source, a
placebo on the long-only 60d net, a longer/wider universe) before any live use. It remains an
**orthogonal complement candidate at best, NOT a core signal and NOT a replacement** for the
PatchTST primary, and **size-capped + regime-aware** if ever used.

## Honesty ledger

- READ-ONLY: bars and earnings parquet read from `/tmp` and `data/fmp_harvest`; no canonical
  path written; no git in the live tree; no order placed; no self-merge / no self-approve.
- All numbers reproduce from the two pinned scripts above (`--as-of 2026-06-26`); inputs are
  hashed into `manifest_pead_test.json` / `manifest_pead_longonly.json`.
- PIT status is downgraded to NON-PIT exploratory; the long-only 20d economics are
  net-negative under faithful costs.
- Event selection is now look-ahead-free (expanding strictly-prior-history threshold);
  excess/significance are restricted to ACTIVE days (idle days reported separately as cash@0).
  The old −705 bps/yr headline is corrected (NOT preserved) to −865 bps/yr active @20d.
- The IC/HAC path is finite-guarded and fails loudly on non-finite inputs/outputs (no more
  spurious NumPy matmul overflow/invalid warnings); covered by
  `tests/test_research_pead_finite_guards.py`.
- The LIVE-model-score orthogonality is a flagged follow-up, NOT estimated here.
- This is an EXPLORATORY doc. Do not act on it as a validated signal.
