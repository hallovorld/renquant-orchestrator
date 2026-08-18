# FROZEN DEFINITIONS — tail-skill ON-switch exploratory study
Written 2026-08-17 BEFORE any conditional statistic was computed.
(Only inventory/schema inspection preceded this file: corpus spans, column
lists, label-unit verification on one ticker-date, and the DGTW memo's
construction. No conditional mean, tercile, or t-statistic has been computed.)

## Corpora
- PRIMARY: renquant-model/doc/research/data/2026-08-01-clf-wf-lineage-bundle/clf_wf_scores.parquet
  (walk-forward OOS certified top-decile clf; 625 dates 2023-10-03..2026-03-31;
  ~285 tickers/date; label `fwd_60d_excess` verified to be per-date
  cross-sectionally z-scored raw-fwd60-excess-vs-SPY).
- SECONDARY (corroboration only, LOOK-AHEAD caveat): renquant-orchestrator/
  experiments/phase_a_data/ xgb daily scores (230 dates 2025-03-13..2026-02-10,
  scores from a model trained 2026-07-06 → in-sample for the whole span) +
  forward_returns.csv (PatchTST z-scored fwd_60d_excess label).
- Regime labels: renquant-orchestrator/doc/research/data/2026-08-10-bear-exit-regime-days.csv,
  column `prod_gmm_label` (committed serving-plane prod-GMM reconstruction,
  2017-01-03..2026-08-07).

## Date filter
A corpus date enters only if it has >= 100 scored names.

## Outcome variables (horizon = 60 trading days, matching the DGTW memo)
Score for ranking = `raw` (per date exactly one WF fold serves; calibration is
monotone within fold so top-N is unchanged by using `cal`).
- Y_z(t) = mean of z-scored label over the TOP 10 names by score at t.
  (Universe z-mean is 0 by construction, so this IS the spread in SD units.)
- Y_r(t) = mean raw fwd-60-trading-day close-to-close return in excess of SPY
  (same window) over the TOP 10 names, MINUS the universe mean of the same —
  the exact construction of structural_decomposition.py (TOP_N=10,
  top mean − universe mean). Computed from data/ohlcv/<T>/1d.parquet closes,
  dividends excluded on both legs (limitation, stated).
- Pre-declared secondary N: top-decile (N = round(n_t/10)) for both Y variants.
  Both N choices will be REPORTED; neither will be dropped after seeing results.

## Ex-ante state variables (all computable at t, closes only, info <= t)
Universe for (a),(b) = the corpus's scored tickers at t intersected with OHLCV
availability (coverage reported).
- (a) DISP20(t) = mean over s in {t-19..t} of std_i( 1d close return_{i,s} ).
- (b) BREADTH(t) = fraction of universe with close_t > SMA50(close, t-49..t).
- (c) SPYVOL20(t) = std of SPY 1d returns over {t-19..t} * sqrt(252).
- (d) SCOREDISP(t) = cross-sectional std of `cal` at t (cal chosen because raw
  scales can shift across WF folds; cal is a probability, cross-fold comparable).
  For the phase-A corpus: std of its xgb score (single model → scale-stable).
- (e) SKILL60(t) = mean of Y_z(s) over the 60 most recent dates s <= t-60
  (labels complete by t; PIT). Requires >= 30 such dates, else NaN.

## Conditional analysis (frozen)
- Terciles per state variable with corpus-wide breakpoints (in-sample
  breakpoints — an acknowledged exploratory limitation; a deployment rule needs
  expanding-window breakpoints and a frozen prereg).
- Inference: non-overlapping 60-trading-day blocks over the corpus date
  sequence (block = 60 >= horizon h = 60; trailing remainder block kept only if
  >= 30 days). Unconditional t = block-mean / SE(block means), df = n_blocks-1,
  Student-t critical values (NO 1.96 on single-digit blocks).
  Conditional cell: a block contributes iff it has >= 15 days in that cell;
  cell t computed the same way over contributing blocks; t reported only when
  contributing blocks >= 5, otherwise mean + n only. n and n_blocks reported
  for every number. Overlapping 60d labels inside a block are dependent; the
  block construction is exactly what discharges that, and adjacent-block
  boundary overlap (up to 59d of one label window) is stated as residual
  dependence.
- Two-way: DISP20 x SPYVOL20 median splits (4 cells), same block rules.
- BULL-only cut: repeat all one-way tables on dates with prod_gmm_label != 'BEAR'.
- NO other variants. Any deviation will be listed in the memo's full ledger.
