# GOAL-2v2 Stage-A preregistration — FROZEN before any fit

STATUS: **TERMINAL RECORD — K5 fired during review; Stage A stops here
and 2020–2023 is NOT run under this document.** [codex r3] The K5 screen
was executed as an exploratory run during this PR's review, at the
operator's direct request for backtest evidence, BEFORE the document
merged — a breach of this document's own "no training before merge" line,
recorded rather than reworded. Its result is therefore already known and
frozen: on the 2016-07..2019-12 OOF folds, NO base achieved an OOF
block-mean IC > 0 with block-t ≥ 1.0 (best: quality_fund +0.0096,
t +0.73; the four §4 price-only bases: −0.007..+0.009, |t| ≤ 0.51). Under
K5's own terms Stage A terminates without touching the evaluation window.
The exploratory run's ancillary findings (all five bases positive in the
approximate-BEAR state; a fifth quality base nearly orthogonal to the
price bases) are DEVELOPMENT observations on 2016–2019 and cannot amend
§4 of this document — using a run's results to rewrite the prereg that
gated the run is adaptive selection. The successor is a
DEVELOPMENT-SELECTION design: 2016–2019 is declared CONSUMED for
development (every attempt enumerated), the confirmatory prereg freezes
only after development concludes, and — because this amends merged
#1061's frozen-before-fit provenance contract — it proceeds only after
explicit operator acknowledgement. Original prospective text preserved
below for the record. Design: `2026-08-25-goal2v2-stacked-meta-model.md`
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
min_child_weight=50`; inputs = the base scores, each cross-sectionally z-scored PER DAY using
only that day's contemporaneously available scores (a per-day
transformation has no fitted parameters [codex r2]; winsorization
thresholds and any other FITTED scaling constants come from training/OOF
data only and are frozen before evaluation) + macro/state features.

**Macro availability/vintage rule [codex r1/r2 — these are LAGGED
LATEST-VINTAGE inputs, not PIT-vintage-identified values]:** only MARKET-QUOTE series are admissible (VIXCLS,
DGS10, T10Y2Y, BAMLH0A0HYM2 — exchange/market quotes, not statistically
revised releases; series like CPI/PAYEMS are inadmissible in Stage A
precisely because their latest-vintage history embeds revisions). The
frozen availability lag is **2 business days**: the feature at session T
uses series values dated ≤ T−2, strictly more conservative than FRED's
next-business-day posting for these series. The limitation is recorded:
the local store is latest-vintage, and for quote series the revision risk
is de minimis but not zero — if revision evidence for any chosen series
surfaces, the K1 data-provenance kill fires for the affected feature set.
Features: VIXCLS level and 20d change; DGS10 20d change; T10Y2Y level;
BAMLH0A0HYM2 20d change (each under the T−2 rule); sector breadth (share
of sectors whose equal-weight index sits above its 50d MA — computed from
the OHLCV store, T−1); PIT regime label (one-hot, from SPY closes ≤ T−1);
cross-sectional dispersion (std of day's demeaned 20d returns, T−1).

## 6. Hypothesis, metric, baselines, decision rule (frozen)

* **Primary statistic, one estimand [codex r1]**: the DAILY cross-sectional
  Spearman IC of the score vs the 20td demeaned forward return, AVERAGED
  within each frozen non-overlapping block; the block means are the unit of
  inference. Block starts spaced ≥ 40td apart (20td label overlap + 20td
  gap; [[block-length-equals-horizon-is-the-defect]]).
* **Baselines, named before unblinding**: B1 = the single base with the
  highest OOF BLOCK-MEAN IC (the same block statistic as the primary
  estimand, computed on OOF; identity written into the run artifact at
  freeze time); B2 = equal-z sum of the base scores.
* **Claim tested — intersection-union rule [codex r2]:** TWO separate
  one-sided paired block-t tests on the evaluation blocks — (meta − B1) and
  (meta − B2) — and survival requires BOTH to reject at α=0.05, critical
  values from t(n_eff − 1) ([[borrowed-critical-values-on-small-n]]).
  No post-unblinding comparator selection exists: "max of the baselines"
  is never computed, so the stated α is preserved (the IU construction is
  conservative by design).
* **Sensitivity, ex-ante** (#1045 r4 semantics): BEFORE any evaluation
  outcome is unblinded, n_eff (the count of assembled evaluation blocks)
  and the MDE at α=0.05/power 0.80 are computed and recorded. **The MDE's
  variance source is frozen [codex r1/r2]:** for EACH of the two paired
  series (meta − B1, meta − B2), s² = the sample variance of that paired
  per-block ΔIC on the OOF blocks only — training-side data; SE =
  √(s²/n_eff); per-series MDE = (t_{0.95} + t_{0.80}) · SE at (n_eff − 1)
  df. **The recorded MDE for labeling is the LARGER of the two** (the IU
  test passes only if both reject, so sensitivity is bounded by the worse
  comparison). Conservative fallback: if fewer than 6 OOF blocks exist,
  each s is floored at 0.020 IC. Estimating any threshold from unblinded
  evaluation differences is prohibited.
  **Minimum effect of interest, frozen now: ΔIC = 0.010.**
  Nonsurvival with MDE ≤ 0.010 → NOT-DEMONSTRATED (terminal). Nonsurvival
  with MDE > 0.010 → UNDERPOWERED-NULL. NO-EFFECT is not an available
  label. Estimate + interval reported regardless.

## 7. Kill table (frozen)

| kill | fires when |
|---|---|
| K1 coverage | universe rule yields < 80 tickers on either window, or feature coverage < 80% of name-days on either window |
| K2 ESS | assembled evaluation panel n_eff < 12 non-overlapping blocks (the #1061 ceiling note: ~16 is the perfect-coverage ceiling; THIS check decides) |
| K3 provenance | any base recipe found to violate the §4 channel it declares (0b-α-style review, run before evaluation) — the base is quarantined, and the ENTIRE downstream is rebuilt from the surviving bases under the same frozen procedure: meta inputs shrink to the survivors, B1 is re-selected from the survivors' OOF ICs, B2 becomes the equal-z of the survivors; if < 3 bases survive, the stage kills |
| K4 outcome | the §6 intersection-union rule — BOTH one-sided paired block-t tests, (meta − B1) and (meta − B2), must reject at α=0.05 with critical values from t(n_eff−1) — otherwise nonsurvival, labeled per §6 sensitivity with the LARGER precomputed MDE governing (NOT-DEMONSTRATED or UNDERPOWERED-NULL); no point-estimate rule substitutes |
| K5 OOF screen | computed on OOF data ONLY, before the evaluation window is touched: if NO base achieves an OOF BLOCK-MEAN IC > 0 with block-t ≥ 1.0 (the same block statistic as §6), the stage stops without spending the one-shot evaluation — a stack of bases showing no life on training-side data has no claim on the quarantined window ([[over-engineering-validation-before-alpha]]: the cheap screen precedes the expensive shot). The K5 reading is recorded either way. |

## 8. Artifacts and boundaries

Ownership [codex r1 — the hard boundary admits no single-file exception]:
the base and meta FIT/PREDICT implementations live in **renquant-model**
(new module, its own PR + review). `renquant-orchestrator` keeps ONLY
prereg enforcement, cross-repo invocation, artifact binding (digests of
universe list, transforms, boosters, OOF matrix), and the evaluation
orchestration. Frozen digests and result tables →
`doc/research/data/goal2v2-stageA/…`; bulk intermediates → the operator
data root `data/goal2v2/`, a NEW directory no production job reads.
Nothing writes production paths; the committed OHLCV/FRED stores are
read-only inputs.

## 9. What Stage A cannot claim

Nothing about 2024–2026; nothing about intraday; nothing about serving.
Survival licenses exactly one thing: building Stage B (forward-shadow-only)
per the merged design.
