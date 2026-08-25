# GOAL-2v2 Stage-A preregistration — FROZEN before any fit

STATUS: preregistration for review. Once merged, every constant below is
frozen; the runner may refuse but may not reinterpret
([[runner-guards-are-prereg-content]]). No training code exists yet and none
runs before this merges. Design: `2026-08-25-goal2v2-stacked-meta-model.md`
(#1061, merged).

## 1. Data substrate, measured not assumed

| input | source | measured coverage |
|---|---|---|
| daily OHLCV panel | committed umbrella `data/ohlcv/<T>/1d.parquet` (read-only) | 2,790 tickers; ~50% begin ≤2016-01; median ~2,604 rows [MEASURED 2026-08-25, 200-ticker sample] |
| SPY (regime input) | same store | 2016-01-04 → present [MEASURED] |
| VIX | `data/fred/VIXCLS.parquet` | from 2016-03 [MEASURED] |
| 10y yield / 2s10s / HY spread | `data/fred/DGS10, T10Y2Y, BAMLH0A0HYM2` | from 2016-03 [MEASURED] |
| sector map | `data/ticker_sectors.json` | present |

**Survivorship disclosure (C3 §7 applies verbatim):** the panel applies a
CURRENT universe retrospectively; membership partly reflects survival. The
Stage-A claim is therefore a current-universe retrospective diagnostic whose
bias direction is NOT identified. This bounds the claim, not the discipline.

## 2. Windows and folds (frozen dates)

* **Train**: 2016-07-01 .. 2019-12-31 (start gives macro series a ≥3-month
  warm-up past their 2016-03 frontier).
* **OOF folds — forward-chaining, expanding, embargo 20 trading days**
  (#1061 §Protocol; blocked folds with later-trained models prohibited):

| fold | base trains on ≤ | predicts (OOF) |
|---|---|---|
| F1 | 2017-06-30 | 2017-08-01 .. 2018-01-31 |
| F2 | 2018-01-31 | 2018-03-01 .. 2018-07-31 |
| F3 | 2018-07-31 | 2018-09-01 .. 2019-01-31 |
| F4 | 2019-01-31 | 2019-03-01 .. 2019-07-31 |
| F5 | 2019-07-31 | 2019-09-01 .. 2019-12-31 |

  Every gap between train-end and predict-start is ≥ 20 trading days. The
  meta model trains ONLY on the union of OOF slices. All transforms
  (winsorization at 1%/99%, cross-sectional z-scores, feature scalings) are
  fitted on train/OOF data and frozen before evaluation.
* **Evaluation**: 2020-01-02 .. 2023-12-29, ONE pass, after the full stack
  (bases + transforms + meta) is frozen and its digests recorded.

## 3. Universe rule (rule frozen; list materialized and recorded pre-outcome)

A ticker enters the panel iff its 1d.parquet covers ≥ 95% of NYSE sessions
in 2016-07-01..2023-12-29 and median daily dollar volume over the train
window ≥ $5M. The materialized list and its sha256 are written to the run
artifact BEFORE any label is computed.

## 4. Base recipes (all price-only; provenance channel per #1061 §1 recorded)

Common: label = 20-trading-day forward return, cross-sectionally demeaned;
xgboost generic defaults frozen here: `max_depth=3, n_estimators=300,
learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
min_child_weight=20` — channel (b), outcome-blind defaults.

| id | features | provenance channel + citation |
|---|---|---|
| `mom_12_1` | returns t-252..t-21 (12-1), t-126..t-21 (6-1), t-63..t-21 (3-1); 52-week-high proximity; each vol-scaled by 60d realized vol | (a) Jegadeesh & Titman 1993; George & Hwang 2004 |
| `strev_lowvol` | 21d return (short-term reversal), 5d return, realized vol 20d/60d, max daily return over 21d (MAX) | (a) Jegadeesh 1990; Lehmann 1990; Ang, Hodrick, Xing, Zhang 2006; Bali, Cakici, Whitelaw 2011 |
| `regime_mom` | same features as `mom_12_1`; SEPARATE booster per regime bucket of training rows; serving uses the session's PIT regime's booster | features (a) as above; the regime rule is the repo's SPY-based classifier — channel (c), its thresholds were set from this fleet's 2024–26 development and consumed no 2016–2023 outcomes [recorded; if 0b-α-style provenance review finds otherwise, this base is quarantined and the stack proceeds with the remaining three] |
| `xsec_vol` | realized vol 20d/60d, vol-of-vol 60d, cross-sectional vol rank | ridge (α=1.0); channel (b) generic |

Duplicated-name, NaN, and coverage handling: a name-day missing any feature
is dropped from that day's cross-section (never imputed); a base emitting
NaN for a name yields no score for that name (NaN propagates to the meta as
missing, and the meta is fitted with xgboost's native missing handling).

## 5. Meta layer (frozen)

xgboost `max_depth=3, n_estimators=200, learning_rate=0.05,
min_child_weight=50`; inputs = the 4 base scores (cross-sectionally z-scored
per day on OOF-fitted parameters) + macro/state features, all at T-1 close
(PIT): VIXCLS level and 20d change; DGS10 20d change; T10Y2Y level;
BAMLH0A0HYM2 20d change; sector breadth (share of sectors whose
equal-weight index sits above its 50d MA); PIT regime label (one-hot);
cross-sectional dispersion (std of day's demeaned 20d returns).

## 6. Hypothesis, metric, baselines, decision rule (frozen)

* **Primary metric**: pooled Spearman IC of the score vs the 20td demeaned
  forward return, computed per day and averaged within NON-OVERLAPPING
  20-trading-day blocks (gap ≥ 20; [[block-length-equals-horizon-is-the-defect]]
  satisfied by block starts spaced ≥ 40td apart: 20td of forward-return
  overlap plus 20td gap).
* **Baselines, named before unblinding**: B1 = the single base with the
  highest pooled OOF IC (its identity is written into the run artifact at
  freeze time, from OOF only); B2 = equal-z sum of the four base scores.
* **Claim tested**: meta IC − max(B1, B2) IC > 0 on the evaluation blocks,
  paired block-t, α=0.05 one-sided, critical value from the t distribution
  at (n_blocks − 1) df — never a borrowed 1.96
  ([[borrowed-critical-values-on-small-n]]).
* **Sensitivity, ex-ante** (#1045 r4 semantics): at assembly (before any
  outcome), n_eff and the MDE at α=0.05/power 0.80 are computed and
  recorded. **Minimum effect of interest, frozen now: ΔIC = 0.010.**
  Nonsurvival with MDE ≤ 0.010 → NOT-DEMONSTRATED (terminal). Nonsurvival
  with MDE > 0.010 → UNDERPOWERED-NULL. NO-EFFECT is not an available
  label. Estimate + interval reported regardless.

## 7. Kill table (frozen)

| kill | fires when |
|---|---|
| K1 coverage | universe rule yields < 80 tickers on either window, or feature coverage < 80% of name-days on either window |
| K2 ESS | assembled evaluation panel n_eff < 12 non-overlapping blocks (the #1061 ceiling note: ~16 is the perfect-coverage ceiling; THIS check decides) |
| K3 provenance | any base recipe found to violate the §4 channel it declares (0b-α-style review, run before evaluation) — the base is quarantined; if < 3 bases survive, the stage kills |
| K4 outcome | meta beats neither baseline (per §6) → NOT-DEMONSTRATED, line closes at Stage A |
| K5 OOF screen | computed on OOF data ONLY, before the evaluation window is touched: if NO base achieves pooled OOF IC > 0 with block-t ≥ 1.0, the stage stops without spending the one-shot evaluation — a stack of bases showing no life on training-side data has no claim on the quarantined window ([[over-engineering-validation-before-alpha]]: the cheap screen precedes the expensive shot). The K5 reading is recorded either way. |

## 8. Artifacts and boundaries

Runner + artifacts live in `renquant-orchestrator` experiment surfaces
(`doc/research/data/goal2v2-stageA/…` for frozen digests and results; bulk
intermediates under the operator data root `data/goal2v2/`, a NEW directory
no production job reads). Nothing writes production paths; the committed
OHLCV/FRED stores are read-only inputs. Base-model TRAINING CODE, if it
grows beyond a self-contained runner script, moves to renquant-model per the
design's repo split — Stage A's single-file runner with frozen constants is
the orchestrator's prereg-execution instrument, mirroring the AC1 grid
precedent.

## 9. What Stage A cannot claim

Nothing about 2024–2026; nothing about intraday; nothing about serving.
Survival licenses exactly one thing: building Stage B (forward-shadow-only)
per the merged design.
