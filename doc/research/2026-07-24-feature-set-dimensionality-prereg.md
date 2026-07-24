# Prereg — the production panel-LTR is effectively a ~13-feature model (FROZEN ON MERGE)

Date: 2026-07-24
Status: **PREREGISTRATION — design under review, NOT YET RUN**
Script: `scripts/research_feature_count_cv.py` (in this PR; deterministic, seeded)
Decision rule: §5. Frozen when this PR merges. Results land in a SEPARATE PR
that may not amend §§0-6.

Requesting adversarial review of the DESIGN before compute is spent. §8 records
the un-preregistered failure this design is built against.

---

## 0. Prior art — what already exists, and what is actually new

This section exists so the reviewer can reject the study as redundant if it is.

**Already answered (do not re-derive):**

| finding | source | date | result |
|---|---|---|---|
| Top-K by univariate \|IC\|, 169 feats, **NGBoost QuantileHead** | `RenQuant/doc/research/failed-experiments-log.md` E51; `logs/phaseB_featsel.log` | 2026-05-09 | Reduction HURTS monotonically: K=40 → −0.0071, K=100 → +0.0200, **all-169 → +0.0224 (best)**. Single seed; noise ≈ 6 bp |
| alpha158+fund (163) vs alpha158-only (158) group ablation | `doc/research/2026-06-24-fundamentals-macro-ablation-results.md` | 2026-06-24 | Practical-NULL, all Δ inside ±0.01. "The model is ~entirely an alpha158 technical/price model" |
| PatchTST 15-feat and 42-feat prunes | `doc/research/2026-06-{19,20,21}-patchtst-edge-recovery-*.md` | 2026-06-21 | Both FAIL gate; the 42-prune cleaned placebo but **degraded the WF trading sim** |
| Adding features hurts (52 macro; 5→12 fund) | E11, E39 | 2026-05 | Monotone IC loss. House lesson: *"the cross-sectional ranker has a feature-budget; bad features dilute good ones via colsample"* |
| **Ticker**-panel shrink (D3 core-shrink) | `doc/research/2026-07-03-d3-core-shrink-check.md` | 2026-07-03 | **NULL**, 18/18 paired ΔIC negative. *"Selection adds nothing over random shrink"* — the standing house prior any shrink pitch must beat |

**Genuinely absent (this study's claim to novelty):**

1. **No feature-count sweep has ever been run on the production XGB
   `rank:pairwise` panel-LTR.** E51 was the NGB QuantileHead; the prune line
   was PatchTST; 06-24 was group-level only.
2. **No collinearity / PCA / correlation-structure analysis of alpha158
   exists** anywhere in the corpus.
3. **The V5 (drop 3 sentiment → 169) and V6 (drop 5 PEAD/SUE → 167) arms were
   preregistered on 2026-06-24 and DEFERRED unrun** — the then-available panel
   lacked those columns. `alpha158_291_fundamental_dataset.parquet` has them.
   This study discharges that deferral.
4. **No split census or persisted importance ranking of the 172 production
   features exists on disk.** §1 computes one.

**Correction to the record (incidental).** `doc/research/2026-06-24-fundamentals-macro-ablation-plan.md:13,44` states "159 alpha158 + 5 fund + 3 sentiment + 5 PEAD/SUE = 172". The live artifact has **158 uppercase alpha158 columns + 14 named columns**, not 159 + 13. Off-by-one; noted, not load-bearing here.

## 1. The finding that motivates this — measured on the LIVE booster

Split census of `artifacts/prod/panel-ltr.alpha158_fund.json`
(`trained_date` 2026-06-21, `oos_mean_ic` 0.0533), decoded from
`booster_raw_json`:

| | |
|---|---|
| features receiving **ZERO splits** | **66 of 172 (38%)** — 65 of them alpha158 technical |
| features actually used | 106 |
| **14 non-technical features (8% of the count)** | **60.7% of total gain** |
| 158 alpha158 technical features | 39.3% of total gain |
| **50% of total gain** | **top 4 features** |
| 80% of total gain | top 13 features |
| 99% of total gain | top 65 features |

Top 4: `gross_profitability` 17.8% · `book_to_price` 13.5% ·
`asset_growth` 9.8% · `STD60` 9.6%. The five SEC fundamentals alone are
54.2% of gain.

A feature with zero splits **provably cannot affect that booster's output** —
this is a structural fact, not an importance attribution, and is not subject
to the identification critique below.

Label-free redundancy of the same matrix (724,359 rows, per-date standardized):
participation-ratio effective rank **10.4** of 172 (**16.5× redundant**); 50%
of variance in 5 components; **84%** of columns are the same base operator at
another window; greedy de-dup at \|r\| ≤ 0.70 leaves 69.

**So the production model is already, in effect, a ~13-feature model dominated
by five SEC fundamentals, carrying 66 provably inert columns.** Whether making
that explicit changes OOS IC is the empirical question.

**Declared methodological limit.** Gain-based attribution is **not identified**
under correlated / jointly-generated predictors — see
`doc/research/2026-07-11-meta-score-attribution.md` (Ma & Tourani 2020; Apley &
Zhu 2020). The 60.7% figure is therefore descriptive, not causal, and no
hypothesis below rests on it alone. Arms are built on structural facts
(zero-split census, label-free correlation, family membership) wherever
possible; the one gain-ranked arm is flagged and paired with a random control.

## 2. Hypotheses

Primary (3, Bonferroni-corrected):

- **H1 (non-inferiority).** `used_only` — the 106 features receiving ≥1 split
  in a production-vintage fit — is non-inferior to `all_172`. *Tests whether
  the 66 inert columns are free to drop. Note this is NOT tautological: on
  retrain, colsample re-exposes dropped columns and the split set shifts.*
- **H2 (non-inferiority).** `dedup_r70` (69 features, label-free) is
  non-inferior to `all_172`. *Tests structural redundancy with a selector that
  never touches the label.*
- **H3 (two-sided).** `nontechnical_only` (14 features) vs `technical_only`
  (158). *If 14 columns carrying 60.7% of gain match or beat 158 columns, the
  alpha158 block is decorative and the book's feature strategy is wrong.*

Secondary / exploratory: every other arm in §4, including the deferred V5/V6.

**Interpretation control (not a hypothesis).** `random{K}` at matched K. Per
D3's standing finding — *"selection adds nothing over random shrink"* — any
non-inferiority result that `random{K}` also achieves is a statement about
**model capacity**, not feature quality. Pre-committed to reporting this either
way, prominently, whichever direction it falls.

## 3. Harness — production, apples-to-apples

Only the feature list varies.

| element | value | source |
|---|---|---|
| label | `fwd_60d_excess` | `panel_trainer.DEFAULT_LABEL` |
| model | XGB `rank:pairwise`, groups = one per date | `PANEL_LTR_PARAMS` |
| params | eta 0.05, depth 5, min_child_weight 50, subsample 0.7, colsample_bytree 0.7 | `PANEL_LTR_PARAMS` |
| rounds | 100 | `DEFAULT_N_ROUNDS` |
| CV | purged walk-forward, expanding train | `evaluate_walk_forward_cv` |
| embargo | **60 trading days** | production `cv_embargo_days` |
| normalization | rebuilt train-only per fold | `build_normalization` |
| panel | `alpha158_291_fundamental_dataset.parquet`, 724,359 rows, 2,591 dates | `panel_data.PANEL_FILE` |
| folds | **5** (production uses 3; declared trade-off — only the 3-fold anchor is validated, see §6.3) | this prereg |
| seeds | **42, 43, 44** | this prereg |

**Anchor — validated before this prereg was written.** `all_172` at the
production 3-fold setting reproduces `mean_ic = 0.0488`, folds
`[0.0781, −0.0010, 0.0693]`, vs the live artifact's `0.0533`,
`[0.0852, 0.0013, 0.0734]` — gap consistent with the artifact's 2026-06-21
vintage against this panel's 2026-04-23 cutoff. **If the anchor does not
reproduce on the run, the run is VOID and no arm is read.** The script enforces
this.

## 4. Arms

Structural / label-free (no leakage surface — computed from the feature
covariance, family membership, or a split census; never from the label):

- `all_172` — baseline
- `used_only` (106) / `zero_split_only` (66) — from the split census
- `dedup_r{95,90,80,70,60}` — greedy \|r\| de-dup (140/121/85/69/55)
- `win{5,10,20,30,60}_only` — one alpha158 window + the 27 non-windowed columns
- `nontechnical_only` (14) / `technical_only` (158)
- `sec_fund_only` (5) — the 54.2%-of-gain block, alone
- **`drop_sentiment` (169) — discharges deferred V5**
- **`drop_pead_sue` (167) — discharges deferred V6**

Label-dependent (selection runs **inside each training fold**; the validation
fold is never seen by the selector). Flagged as attribution-dependent per §1:

- `gain_top{80,40,20,10,5}`

Controls:

- `random{40,20,10}_s{0,1,2}` — 3 draws each
- `placebo` — labels shuffled **within date** in TRAINING rows only; validation
  labels real. Measures the IC this harness manufactures with no signal.

## 5. Decision rule — FROZEN

**Primary statistic: per-validation-date paired ΔIC against `all_172`**
(H3: against `technical_only`), averaged over the 3 seeds.

**Dependence correction (mandatory).** `fwd_60d_excess` makes consecutive
per-date ICs share up to 59/60 of their label window. A naive t-test over
~1,400 dates would overstate significance by roughly √60. Inference uses a
**moving-block bootstrap, block = 60 trading days, B = 10,000, seed 20260724**
on the paired differences. No naive t-test is reported as evidence.

This matters because the standing house finding (`VERDICTS.md`, WF-gate
embargo floor) is a **~+0.04 leakage floor under ABSOLUTE IC** in this corpus —
the production anchor of 0.0488 sits essentially on it. **Absolute IC is not
evidence here; only paired differences are.** The `placebo` arm measures the
floor in this harness and is reported with every primary read.

Non-inferiority margin **δ = 0.005** (≈ 10% of the anchor). Registered
alternative the reviewer should rule on: tie δ to the measured placebo spread
instead of to the anchor.

| verdict | condition on the bootstrap CI of mean paired ΔIC |
|---|---|
| **SUPERIOR** | lower bound > 0 |
| **NON-INFERIOR** | lower bound > −δ (and not SUPERIOR) |
| **INFERIOR** | upper bound < −δ |
| **INCONCLUSIVE** | CI spans both −δ and 0 |

Multiplicity: H1/H2/H3 are the only primary tests; Bonferroni over 3 →
α = 0.0167 two-sided each. All other arms are **EXPLORATORY** and may not carry
a verdict into `VERDICTS.md`.

Seed stability: a primary verdict requires the **sign of mean ΔIC to agree
across all 3 seeds**. Split signs ⇒ INCONCLUSIVE regardless of the interval.

**Pre-committed consequences:**

- H1 NON-INFERIOR → the 66 inert columns are recorded as droppable. This is a
  recipe-simplification finding, not an alpha finding, and must be reported as
  such.
- H3 shows `nontechnical_only` ≥ `technical_only` → registered as a **material
  finding about the book's feature strategy**: the alpha158 block is
  decorative and effort should move to fundamental/event features. This
  aligns with the standing G4 conclusion (`2026-07-23-g4-ensemble-AUTHORITATIVE.md`)
  that *"the ceiling is the FEATURE FAMILY, not the model"*.
- Any reduced arm NON-INFERIOR **and** matched `random{K}` also NON-INFERIOR →
  registered as **"selection adds nothing; the result is about model
  capacity"**, consistent with D3. This is a likely outcome and must not be
  buried.
- All primaries INFERIOR/INCONCLUSIVE → NULL. The 172-feature recipe stands and
  the "158 is too many" intuition is answered **NO on evidence**, redundancy
  and the split census notwithstanding. No re-pitch absent a materially
  different hypothesis.
- **No result here authorizes a config change.** A recipe change
  re-fingerprints the artifact (`config_fingerprint`) and must route through
  the normal WF-promote gate.
- **H3 interpretation guard (hard, not an open question).** This harness
  consumes the already-built panel and cannot itself establish that the 5 SEC
  fundamental columns are free of look-ahead — see §6.4. A `nontechnical_only`
  or `sec_fund_only` result that is SUPERIOR or NON-INFERIOR is **precommitted
  to INCONCLUSIVE for any feature-strategy or promotion claim** until the
  fundamentals ingestion in `renquant-base-data` (the repo that owns the
  panel's manifests/schemas/materialization) is independently audited against
  source filing/as-of timestamps, or the arm is repeated on an
  audited lagged/masked panel. Owner: whoever runs that audit; artifact: a
  named PIT-audit doc in `renquant-base-data/doc/`. No H3 result may be cited
  as feature-strategy evidence before that artifact exists.

## 6. Evidence boundaries (declared before the run)

1. **Survivorship.** 292-name present-day panel. Absolute numbers inflated; all
   arms share it, so paired differences are unaffected. No absolute figure from
   this study may be quoted as achievable.
2. **Regime coverage.** 2016-01-04 → 2026-04-23. Production 4-regime mix over
   this span (computed via the production task chain): BULL_CALM 72.3% / BEAR
   16.3% / BULL_VOLATILE 7.2% / CHOPPY 4.2%. **No per-regime verdict is
   registrable from this design** — CHOPPY has 107 days.
3. **5 folds, not production's 3.** Early folds train on less history than
   production would. Only the 3-fold anchor is empirically validated
   (§3); the script fails closed (VOID, per §5) on any `--n-splits` other
   than 3 unless run with `--skip-anchor`, in which case the run is
   exploratory-only and carries no primary verdict.
4. **Point-in-time.** The 5 SEC fundamental columns' PIT integrity is inherited
   from the panel builder and NOT re-verified here. Given those five carry
   54.2% of gain, **this is the single largest threat to any positive H3
   result** — hardened to a §5 precommit: an unaudited H3 result is
   INCONCLUSIVE for any feature or promotion claim, not merely a caveat.
5. **One model family.** XGB `rank:pairwise` only. Nothing transfers to
   PatchTST or to a linear scorer.
6. **Gain attribution is not identified** under correlated predictors (§1).
   `gain_top{K}` arms inherit this; structural arms do not.
7. **No P&L.** OOS IC only. No APY or Sharpe will be quoted from this study.

## 7. Questions posed to the reviewer

1. Is block length 60 right, or should it be Politis-White automatic as in the
   G2 prereg?
2. Should δ be tied to the measured placebo spread rather than to the anchor?
3. Does in-fold `gain_top{K}` still leak, given the first-pass model sees
   training rows whose 60-day label window extends past the training cutoff?
4. Is 5 folds worth the shorter early-fold training, or should this stay at 3?
5. **Is H3 confounded by PIT?** §5 now precommits an unaudited H3 result to
   INCONCLUSIVE for any feature/promotion claim, naming the
   `renquant-base-data` PIT audit as the prerequisite artifact. Is that guard
   sufficient, or does a positive H3 read also require blocking the result
   from `VERDICTS.md` entirely (not just labelling it) until the audit lands?
6. Given E51 found top-K hurts monotonically on the NGB head, is there a reason
   to expect XGB `rank:pairwise` to behave differently — or is this study
   predictably a NULL that should be descoped to the split census plus V5/V6?

## 8. Provenance — the failure this design guards against

The author's immediately preceding, **un-preregistered** study of
regime-conditional feature selection reported IC +193% (0.017 → 0.050,
p = 0.0007), APY 47.9%, Sharpe 1.57, "beats SPY". Self-audit found five
defects: (1) full-sample `pd.qcut` regime labels — 22.4% of days labelled with
future volatility; (2) embargo 0 against a forward-looking label; (3) SPY as
benchmark when the correct floor was the 17.4% panel equal-weight; (4) wrong
label (`fwd_20d_excess`; production trains `fwd_60d_excess`); (5) wrong model
(rank composite; production is `rank:pairwise` XGB).

Corrected, the effect **reversed**: regime minus pooled −4.1%/yr, t = −0.48,
p = 0.634, 49% win rate. Both arms also lost to the panel equal-weight on
Sharpe (0.62 / 0.59 vs 0.86). The original claim was entirely leakage. No claim
from it survives; none is carried here.

Mapping of countermeasures: production label and model (defects 4-5);
production 60-day embargo (2); paired differences against an in-harness
baseline instead of an external benchmark (3); label-free selectors preferred
and in-fold selection where a label is unavoidable (1); plus a placebo arm, a
random-selection control, block bootstrap for the overlapping label, multi-seed
sign stability, and a decision rule frozen before the run.

## 9. Reproduction

```bash
cd /Users/renhao/git/github/RenQuant
.venv/bin/python <orchestrator>/scripts/research_feature_count_cv.py \
    --census                                  # split census on the live artifact
.venv/bin/python <orchestrator>/scripts/research_feature_count_cv.py \
    --diagnose                                # label-free redundancy
.venv/bin/python <orchestrator>/scripts/research_feature_count_cv.py \
    --out <research-output-dir>/2026-07-24-feature-count.json
```

Read-only against production: reads the panel parquet, the live artifact (to
decode the split census), and the published `renquant_model_gbdt` API. Writes
only to the research output path — the script refuses any path containing
`artifacts/prod`, `artifacts/sim`, `strategy_config`, `/data/`, `walkforward`,
or `panel-ltr`.
