# S9: Track A conditional pick-quality test — NULL

STATUS: research evidence (read-only), FROZEN-SPEC EXECUTION. The spec is
`doc/design/2026-06-28-renquant105-direction-decision.md` §4 (origin/main) —
pre-registered criteria, executed exactly, NOT altered. Per the spec, a NULL is
recorded, never re-argued.
DATE: 2026-07-03
SCRIPT: `scripts/s9_track_a_conditional.py` (one-command reproduce, frozen
constants at top).
EVIDENCE: `doc/research/evidence/2026-07-03-s9/{substrate_verification,
pit_checks,s9_results}.json`.

## Verdict

**NULL (STOP).** No conditioning clears all of §4's pre-registered gates
(a)–(e) on the held-out test window. Pre-registered consequence, recorded as
required: **Track A is null — Track B (an input change: universe down-cap or
new PIT-clean data) is the only remaining directional path to a renquant105
directional edge.** No meta-label filter is built; no filter fishing follows.

This is the expected outcome the merged plan priced in (P(GO) ≈ 0.30, with the
known BEAR-only skill slice making gate (d) likely binding — which is exactly
what happened to the regime conditioning).

## Substrate (verified before anything ran)

The freshly regenerated durable OOS pick table
(`RenQuant/data/exp/oos_pick_table_recipe_v2.parquet`, umbrella tree,
read-only), verified with the owning contract
`renquant_backtesting.analysis.pick_table.verify_pick_table`
(renquant-backtesting@main 68b222e = #59 + #60):

- canonical content hash `ba964b407ec1e0a5…` — **matches** the sidecar anchor;
  counts verified (508 dates / 292 names / 147,066 rows); parquet transport
  hash also matches.
- schema per the #59 contract: `{date, name, score, decile_rank,
  fwd_60d_excess, regime}`; OOS window 2024-02-02 → 2026-02-11; top decile
  (`decile_rank == 9`) ≈ 30 candidates/date, 15,109 pick rows.

**Label-units note (material, documented, not a spec change).** The table's
`fwd_60d_excess` column is the per-date **cross-sectionally standardized**
training label (per-date mean ≈ 0, std ≈ 1 — verified). §4's label and every
gate are denominated in **return units** (11 bps cost proxy, +5 bps/60d,
+50 bps/yr), so the raw-unit label `fwd_60d_excess_raw` was joined from §4's
own named durable label input,
`RenQuant/data/alpha158_291_fundamental_dataset_rawlabel.parquet`. The join is
proven faithful: 15,109/15,109 rows joined and the panel's standardized column
reproduces the table's **exactly** (max |Δ| = 0.0). Frozen label: `y = 1` iff
`fwd_60d_excess_raw > 0.0011`.

## Conditioning variables — PIT check outcomes (§4's flags, applied mechanically)

| # | Variable | §4 PIT flag | Outcome |
|---|---|---|---|
| 1 | Regime at pick date | VERIFIED | **RAN** (table column) |
| 2 | Cross-sectional score dispersion | VERIFIED | **RAN** (per-date std of `score`, derived) |
| 3 | Score margin vs decile cutoff | VERIFIED | **RAN** (`score` − within-date decile-9 cutoff, derived) |
| 4 | Earnings-surprise window | GUESS — needs check | **DROPPED — PIT check FAILED.** `data/fmp_harvest/earnings_291.parquet` has **no `acceptedDate` column** (columns: symbol/date/eps*/revenue*/lastUpdated/ticker/fetched_at/source); `fetched_at` is a single 2026-06-25 harvest snapshot, i.e. the announcement dates are backfilled, not point-in-time collected. Per §4 the variable is dropped; substituting an unmerged source would be Track B. |
| 5 | Liquidity / vol state (60d realized vol + ADV) | GUESS — needs check | **RAN — PIT check PASSED.** Durable bars panel confirmed at `RenQuant/data/ohlcv/<T>/1d.parquet`: all 292 names present, every name has ≥ 61 trailing sessions before its first pick, closes are back-adjusted (verified across the NVDA 2024-06-10 10:1 split row), feature coverage 100.0%. Trailing-window vol/ADV are PIT-safe by construction. |

Surviving model features: regime dummies, dispersion, margin, vol60,
within-date ADV percentile rank.

## Method (frozen §4, executed exactly)

- **Split (chronological, no shuffling):** 508 OOS dates → train = first 60%
  = **305 dates (2024-02-02 → 2025-04-22)**; **embargo = 60 trading days
  (2025-04-23 → 2025-07-18, excluded)**; test = **143 dates (2025-07-21 →
  2026-02-11)** — matching §4's stated ≈2025-08 → 2026-02 test window.
- **Baseline:** the unconditional top-decile candidate set on the test window
  (4,159 picks; hit-rate 49.96%).
- **Bootstrap:** date-block bootstrap, block = 13 (A1 convention), 2,000
  resamples, fixed seed, 95% percentile CIs; capital fraction recomputed per
  resample for the book-level gate.
- **Annualization:** 252/60 ≈ 4.2 60d-periods/yr (§4's "×≈4").
- **Turnover:** per-date membership symmetric difference summed over the
  window, conditioned vs baseline.
- **Conditioning candidates (structure fixed ex ante; fit on TRAIN only):**
  - **C1 `logit_all`** — logistic regression on all surviving variables;
    keep picks with predicted P(y=1) ≥ train-median (τ = 0.5107, ≈50%
    retention). Converged (7 iterations, finite coefficients; largest
    coefficient = BEAR dummy +0.32, consistent with A1's BEAR-slice skill).
  - **C2 `regime_whitelist`** — keep regimes whose train hit-rate exceeds the
    unconditional train hit-rate (0.5227). Whitelist learned on train:
    **{BEAR}** (BEAR 0.690 vs BULL_CALM 0.502, CHOPPY 0.489,
    BULL_VOLATILE 0.449).
  - **C3 `margin_top_half`** — keep picks with within-date margin ≥ the
    within-date median margin (structural rule).
- **Multiplicity honesty:** three candidates were evaluated. A
  champion-by-train protocol is reported (below), but the verdict applies §4's
  literal rule — GO iff **any** conditioning clears all (a)–(e) on test —
  which is the GENEROUS direction. A NULL under it is decision-grade.

## Per-regime cell counts (§4 requirement — thin slices visible)

| Regime | Train dates | Train picks | Test dates | Test picks |
|---|---|---|---|---|
| BULL_CALM | 232 | 6,960 | 118 | 3,485 |
| BEAR | 38 | 1,140 | **1** | **30** |
| CHOPPY | 24 | 720 | 16 | 404 |
| BULL_VOLATILE | 11 | 330 | 8 | 240 |

The test window contains **one** BEAR date — the thin slice §4 warned about is
maximally thin exactly where the model's only measured skill lives.

## Results (held-out test window; baseline = 4,159 unconditional top-decile picks)

| Metric (test) | Gate | C1 logit_all | C2 regime_whitelist | C3 margin_top_half |
|---|---|---|---|---|
| (a) Book-return lift, annualized capital-weighted | ≥ +50 bps/yr, CI LB > 0 | **−635.6** [−1351.9, +63.6] | −2.3 [−15.8, +2.7] | +1158.3 [+631.7, +1713.0] ✓ |
| (b) Per-pick net expectancy lift (bps/60d) | ≥ +5, CI LB > 0 | −266.9 [−550.7, +28.8] | −75.8 [−237.4, +71.8] | +550.4 [+300.8, +814.3] ✓ |
| (c) Hit-rate lift (pp) | ≥ +3, CI excl. 0 | −0.64 [−4.18, +3.93] | +6.70 [+3.10, +9.11] ✓ | +6.99 [+3.41, +10.47] ✓ |
| (d) Active-day exposure | ≥ 25% | 90.9% ✓ | **0.7%** (1 date) | 100.0% ✓ |
| (e1) Baseline winners dropped | ≤ 1/3 | **44.0%** (915/2,078) | **99.2%** | **42.9%** (891/2,078) |
| (e2) Turnover multiple | ≤ 2× | 0.86× ✓ | 0.05× ✓ | 0.54× ✓ |
| **All gates (a)–(e)** | | **FAIL** | **FAIL** | **FAIL** |

(Capital fractions: C1 56.7%, C2 0.7%, C3 50.1%. Baseline test hit-rate
49.96%; baseline per-pick net expectancy +582.3 bps/60d before conditioning —
a survivorship-biased-panel level, see caveats.)

### Reading the three failures honestly

- **C1 (logit)** is a textbook overfit: train book lift +592 bps/yr
  [+183, +1007] flips to **−636 bps/yr** out-of-sample. The learned
  meta-model has no stable conditional signal to find.
- **C2 (BEAR whitelist)** is the pre-registered failure mode, realized: the
  only regime with train skill (hit-rate 0.690) appears on **one** of 143 test
  dates → active exposure 0.7% vs the 25% floor, capital fraction 0.7%, book
  lift −2.3 bps/yr. A conditional state that is identifiable but almost never
  occurs is not a book lever — gate (d) exists precisely for this.
- **C3 (margin top-half)** passes (a)–(d) on the test window but **fails the
  missed-winner cap (e)**: it drops 42.9% of baseline winners (> 1/3). Two
  pre-registered reasons this is not a near-miss to re-argue:
  1. **It was not selectable ex ante.** On train, C3's hit lift is
     **−0.30 pp** [−2.61, +1.95] and its book lift +103 bps/yr
     [−141, +358] — CI includes 0. Train and test disagree on sign; the
     test-window strength (which coincides with 118/143 BULL_CALM dates in a
     rallying tape) is a window artifact, not an identifiable conditional
     state. The champion-by-train protocol picked C1, not C3.
  2. **Gate (e) is geometrically demanding by design.** For a filter retaining
     a fraction f of picks, winners dropped = 1 − f·(HR_cond/HR_base); the
     ≤ 1/3 cap requires f·HR_cond/HR_base ≥ 2/3 — at 50% retention that means
     a hit-rate enrichment ≥ 4/3 (≈ +16.7 pp at a 50% base). No candidate came
     close. §4 set this cap deliberately ("a filter that buys a small hit-rate
     gain by dropping many eventual winners is not a win"), and its thresholds
     are open to tightening, not loosening.

### Champion-by-train protocol (selection-discipline read)

No candidate passed train-window (d)+(e) (winner-drop fails on train for all
three), so the champion fell back to the best train book lift: **C1**
(+592 bps/yr on train). C1 then failed the test window outright. Under the
stricter champion protocol the result is the same **NULL**.

## Caveats (stated, not hedged)

- The panel is the current-watchlist, survivorship-biased 292-name universe —
  the same scope limit as A1/A2; absolute levels (e.g. the baseline's
  +582 bps/60d net expectancy on the test window) should not be read as
  tradable truth. The test
  is a *difference* test, which is the part the substrate supports.
- The single 143-date test window is 82.5% BULL_CALM. That is not a flaw of
  the execution — it is §4's chronological split applied to reality — but it
  means conditional states other than BULL_CALM are measured on thin cells
  (visible in the cell-count table above).
- Three candidates under the generous any-pass rule is mild multiplicity in
  the GO direction; it did not matter (zero passed), and the champion
  protocol agrees.

## Pre-registered consequence (recorded)

Per §4: **Track A is null.** No conditioning delivers materially higher pick
quality at book level on the held-out window. **Track B — an input change
(universe down-cap toward small/mid-cap, or new PIT-clean orthogonal data) —
becomes the only remaining directional path** for renquant105. Non-directional
Track A levers (vol/risk-timing sizing, execution/cost) remain available but
are explicitly not directional edge. We do not go fishing for a filter.

## Reproduce

```bash
PYTHONPATH=<renquant-backtesting-main>/src \
python3 scripts/s9_track_a_conditional.py \
    --umbrella /Users/renhao/git/github/RenQuant \
    --out-dir doc/research/evidence/2026-07-03-s9
```

All inputs read-only (umbrella tree data + the #59-contract verifier); no git
operations anywhere; deterministic (fixed seed 20260703, 2,000 resamples).
