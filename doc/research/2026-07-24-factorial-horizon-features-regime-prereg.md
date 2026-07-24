# Prereg — horizon × features × regime, FACTORIAL (supersedes the OFAT design)

Date: 2026-07-24
Status: **PREREGISTRATION — design under review, NOT YET RUN**
Script: `scripts/research_factorial_hfr.py` (in this PR; deterministic, seeded)
Supersedes: `doc/research/2026-07-24-feature-set-dimensionality-prereg.md` (PR #573)
Decision rule: §5. Frozen on merge. Results land in a SEPARATE PR that may not
amend §§0-6.

---

## 0. Why this supersedes #573 — the OFAT defect

Three studies were run or designed in this session. **Every one varied a single
factor and held the others at an arbitrary constant.** If those factors
interact, all three conclusions are unsound — including the two that felt
solid.

| study | conclusion reached | what it held fixed | how the conclusion dies |
|---|---|---|---|
| regime-conditional feature selection | **NULL** (−4.1%/yr, p=0.634) | label `fwd_20d`, model = rank composite | regime conditioning may only pay at `fwd_60d`, or only inside the production XGB |
| feature-set dimensionality (#573) | not yet run | label `fwd_60d`, regime = pooled | reduction may hurt pooled and help per-regime — pooling averages the effect away |
| label horizon | 20d > 60d at 5d/20d eval (Bonferroni-surviving) | features = all 172, regime = pooled | the best horizon may differ **by regime** — pooling hides it |

The third is not hypothetical. In a high-volatility or BEAR tape a 60-day
cross-sectional forecast is close to hopeless; in BULL_CALM a longer horizon
plausibly has better SNR. A pooled read averages a real crossover into a
mush that looks like "20d is slightly better everywhere".

**A one-factor-at-a-time design cannot detect that. This one is factorial and
its PRIMARY hypotheses are the interactions.**

#573's question survives intact — it becomes the F main effect and the F×R
interaction here. The split census, redundancy analysis, and PIT precommit
from #573 §§0-1, 5 are carried forward verbatim and are not re-derived.

## 1. Carried forward from #573 (not re-litigated)

- **Split census, live booster:** 66 of 172 features (38%) receive ZERO splits
  — provably inert; 14 non-technical features (8% of count) carry 60.7% of
  total gain; 50% of gain in 4 features, 80% in 13.
- **Label-free redundancy:** participation-ratio effective rank 10.4 of 172
  (16.5× redundant); 84% of columns are one operator at another window;
  greedy de-dup at |r| ≤ 0.70 leaves 69.
- **Prior art:** E51 (top-K hurts on the NGB head), 06-24 group ablation
  (practical-null), the PatchTST prune line (both arms FAIL), E11/E39 (adding
  features hurts), D3 core-shrink (*"selection adds nothing over random
  shrink"* — the standing prior any shrink pitch must beat).
- **PIT precommit (HARD, carried verbatim):** a `nontechnical` or `sec_fund`
  arm that is SUPERIOR or NON-INFERIOR is **precommitted to INCONCLUSIVE for
  any feature-strategy or promotion claim** until the fundamentals ingestion in
  `renquant-base-data` is audited against source filing/as-of timestamps. The
  5 SEC columns carry 54.2% of gain, so look-ahead there would manufacture
  exactly this result.
- **Gain attribution is not identified** under correlated predictors
  (`2026-07-11-meta-score-attribution.md`). No hypothesis rests on it; all
  feature levels below are structural or label-free.

## 2. Design — 3 factors, fully crossed

| factor | levels | why these |
|---|---|---|
| **H** — training label | `fwd_5d_excess`, `fwd_20d_excess`, `fwd_60d_excess` | production is 60d; the live book exits winners at ~8d with 69% of names gone in 20d |
| **F** — feature set | `all_172`, `dedup_r70` (69, label-free), `nontechnical_14`, `random_14` | `all_172` vs `dedup_r70` isolates **redundancy**; `nontechnical_14` vs `random_14` isolates **selection at fixed count** |
| **R** — regime mode | `pooled`, `specialist` | `specialist` = one model per production regime, mirroring `RegimeEnsemblePanelScorer`'s fallback semantics |

3 × 4 × 2 = **24 cells**, each also run as a **matched placebo** (§4) = 48
configurations × 3 seeds × 5 folds. Measured runtime **≈ 87 min** (feasibility
probe, §7).

`random_14` is the size-matched control for `nontechnical_14`. Per D3, if they
tie, the finding is about **model capacity**, not feature quality — precommitted
to reporting that prominently either way.

## 3. The measurement problem this design must solve

**Each cell has its OWN leakage floor, so raw IC is not comparable across
cells.** Label autocorrelation at the gate shift
(`2026-06-10-m6-placebo-gate-verdict.md` §2.1):

| label | AC @ 2× horizon |
|---|---|
| `fwd_5d_excess` | −0.0009 |
| `fwd_20d_excess` | +0.0093 |
| **`fwd_60d_excess`** | **+0.0489** |

`fwd_60d` predicts *itself* at +0.049. Comparing a 60d cell's raw IC against a
5d cell's raw IC therefore compares two different floors, not two skills.

**This is very likely why E35 (2026-05-08) chose 60d.** It ranked horizons by
raw IC (+0.066 / +0.040 / +0.024) on a metric that systematically rewards the
longest label. The autocorrelation was measured a month later and **the horizon
comparison was never re-run.** This study re-runs it on a floor-subtracted
response.

**Primary response: placebo-clean IC.**

```
clean_IC(cell, date) = IC_real(cell, date) − IC_placebo(cell, date)
```

The placebo is the SAME cell — same horizon, same feature set, same regime
mode, same folds, same seed — trained on **labels shuffled within date** in the
training rows only, validation labels real. It measures what that exact
configuration manufactures with no signal. Every cell carries its own.

## 4. Harness

Production, apples-to-apples; nothing varies but the three factors.

| element | value |
|---|---|
| model | XGB `rank:pairwise`, groups = one per date, `PANEL_LTR_PARAMS`, 100 rounds |
| CV | purged walk-forward, expanding train, **5 folds** |
| embargo | **60 trading days for ALL cells** — see below |
| normalization | rebuilt train-only per fold |
| regime labels | production 5-task chain (Hurst→CUSUM→GMM→BEAROverride→Finalize), **causal by construction** |
| panel | `alpha158_291_fundamental_dataset.parquet`, 724,359 rows, 2,591 dates |
| seeds | 42, 43, 44 |

**Embargo held at 60 for every cell, including the 5d and 20d ones.** A
label-matched embargo (5/20/60) would give short-horizon cells 55 more training
days per fold — a real production advantage, but a confound for the question
"which target is better". Holding it at 60 isolates the target. *The
label-matched variant is registered as a SECONDARY read and reported
separately; it must not be mixed with the primary.*

**Specialist estimability — measured, not assumed** (feasibility probe, §7).
Per-regime training dates by fold, minimum 60 to fit:

| regime | folds where estimable | validation dates | independent 60d blocks |
|---|---|---|---|
| BULL_CALM | 5/5 | 1480 (68.6%) | ~24 |
| BEAR | 4/5 | 412 (19.1%) | ~6 |
| BULL_VOLATILE | 2/5 | 183 (8.5%) | **~3** |
| CHOPPY | 2/5 | 82 (3.8%) | **~1** |

**Precommitted: only BULL_CALM and BEAR may carry a per-regime verdict.**
BULL_VOLATILE and CHOPPY are reported for completeness and are **not
registrable at any significance level** — with 1–3 independent blocks the
interval is uninformative. A specialist that cannot be fit on a fold falls back
to the pooled model for that fold, exactly as `RegimeEnsemblePanelScorer` does
in production, and the fallback count is reported per cell.

## 5. Decision rule — FROZEN

**Statistic.** Per-validation-date placebo-clean IC, averaged over 3 seeds,
evaluated at a common evaluation horizon. Contrasts are **paired by date**.

**Evaluation horizon.** Every cell is scored against all three horizons, so
train-horizon × eval-horizon is a reported grid. **PRIMARY eval horizon =
`fwd_20d_excess`**, pre-registered on the measured live holding period: winners
exit at ~8d, 69% of names gone within 20 days. The realized horizon sits
between `fwd_5d` and `fwd_20d`; `fwd_20d` is the closer available proxy and the
more conservative of the two. `fwd_5d` and `fwd_60d` are SECONDARY.

**Dependence correction.** Moving-block bootstrap, B = 10,000, seed 20260724,
**block = the evaluation label's horizon** (not a constant 60 — a 5d label's
dependence range is 5 days, and forcing 60 there is needlessly conservative).
Sensitivity re-run at 2× block is reported for every primary contrast. No naive
t-test is reported as evidence.

**PRIMARY hypotheses — the interactions.**

- **I1 (H×R).** Does the best training horizon differ between BULL_CALM and
  BEAR? Contrast: `[clean_IC(60d,BEAR) − clean_IC(20d,BEAR)] −
  [clean_IC(60d,BULL_CALM) − clean_IC(20d,BULL_CALM)]`, at `all_172`.
  **Non-zero ⇒ the pooled horizon verdict (this session's and E35's) is void.**
- **I2 (F×R).** Does feature reduction pay differently pooled vs per-regime?
  Contrast: `[clean_IC(dedup_r70,specialist) − clean_IC(all_172,specialist)] −
  [clean_IC(dedup_r70,pooled) − clean_IC(all_172,pooled)]`, at the primary
  horizon. **Non-zero ⇒ #573's pooled-only design would have been wrong.**
- **I3 (H×F).** Does the best feature set differ by horizon? Contrast as I2
  with H in place of R.

**SECONDARY — main effects**, read only after the corresponding interaction is
resolved. A main effect whose interaction is significant is reported as
**"not interpretable marginally"**, not as a result.

- M1 (H): best training horizon at the primary eval horizon, pooled, `all_172`
- M2 (F): `dedup_r70` vs `all_172`; `nontechnical_14` vs `random_14`
- M3 (R): `specialist` vs `pooled`

**Multiplicity.** Holm–Bonferroni over the pre-registered set of 3 interactions
+ 4 main-effect contrasts = **7 tests**, family-wise α = 0.10. Every other cell
comparison is EXPLORATORY and may not carry a verdict into `VERDICTS.md`.

**Seed stability.** Any registered verdict requires the sign of the contrast to
agree across all 3 seeds. Split signs ⇒ INCONCLUSIVE regardless of interval.

**Non-inferiority margin** δ = 0.005 for the F contrasts (≈10% of the 0.0488
anchor). Registered alternative for the reviewer to rule on: tie δ to the
measured placebo spread instead.

**Anchor.** `all_172` / `pooled` / `fwd_60d` at the production 3-fold setting
must reproduce `mean_ic = 0.0488 ± 0.010` (live artifact: 0.0533). The anchor
is only validated at 3 folds; the script **fails closed** on any other fold
count rather than compare against an unvalidated expectation. Anchor failure
⇒ the run is VOID and no cell is read.

**Pre-committed consequences.**

- **I1 significant ⇒ this session's horizon conclusion AND E35's are both
  retracted**, and the successor question becomes per-regime horizon selection,
  not a global horizon swap.
- **I2 significant ⇒ #573 is void as designed**, and feature-set questions must
  be asked per-regime from here on.
- **All interactions null ⇒ the OFAT reads are rehabilitated** and the main
  effects may be read marginally. *This is a real possible outcome and would
  vindicate the earlier designs; it is not a failure of this study.*
- **Any horizon result is IC-only.** E42v2 (2026-05-12) ran a portfolio sim and
  found fwd_60d best (APY +18.5% / Sharpe 0.52 vs fwd_20d +10.7% / 0.14). **A
  contrary IC result here does NOT overturn it** — different metric, and the
  gap between IC and P&L runs through the meta-label filter, QP sizing, and
  costs, none of which are in this harness. Reconciling them requires a P&L
  study; that is named as the successor, not claimed here.
- **No result authorizes a config change.** Changing the label is a **strategy
  change** — holding period, turnover, tax profile — per
  `2026-06-08-overlapping-label-and-gate-architecture` §2c, not a label swap.

## 6. Evidence boundaries (declared before the run)

1. **Survivorship.** 292-name present-day panel. All cells share it, so paired
   contrasts are unaffected; no absolute number may be quoted as achievable.
2. **Regime power.** Only BULL_CALM and BEAR are registrable (§4). Any claim
   about BULL_VOLATILE or CHOPPY from this study is invalid by construction.
3. **PIT.** Carried precommit from §1 — an unaudited `nontechnical_14` or
   `sec_fund` result is INCONCLUSIVE for any feature-strategy claim.
4. **One model family.** XGB `rank:pairwise`. Nothing transfers to PatchTST or
   to a linear scorer. In particular **the earlier regime-selection NULL used a
   rank composite**, so this study can rehabilitate or bury that conclusion only
   within the XGB family.
5. **No P&L, no costs, no meta-label, no QP.** IC only. See the E42v2 clause.
6. **5 folds, not production's 3.** Early folds train on less history than
   production would. Anchor is checked at 3.
7. **What is held fixed and therefore untested:** XGB hyperparameters, the
   universe, the 100-round budget, the meta-label stage, sizing, and costs. A
   fourth factor is not affordable at 24 cells; these are declared, not
   silently assumed away.

## 7. Feasibility — measured, not estimated

Probe run 2026-07-24 on the real panel: pooled 172-feature fit ≈ 7.5 s/fold;
2-specialist fit ≈ 7.0 s/fold. 24 cells × 2 (real + placebo) × 5 folds ×
3 seeds ⇒ **≈ 87 min**. Per-regime estimability and block counts in §4 come
from the same probe.

## 8. Questions for the reviewer

1. Is placebo-clean IC the right response, or should the floor be handled by
   restricting to a common label and comparing only within-horizon?
2. Block = eval horizon — defensible, or should regime persistence (89.8%
   day-to-day) force a longer block regardless of label?
3. Is `fwd_20d` the right PRIMARY eval horizon given the ~8d realized hold, or
   should the primary be `fwd_5d` with `fwd_20d` secondary?
4. Holm over 7 pre-registered tests — or should the 3 interactions carry the
   whole family and the main effects be exploratory by construction?
5. Is holding embargo at 60 for all cells right for the target question, given
   it denies short-horizon cells a real production advantage?
6. **Is 24 cells over-fitting the design to the data?** With 7 registered tests
   and 24 cells there is room to tell a story post hoc. Is the Holm set tight
   enough, or should cells outside the registered contrasts not be computed at
   all?

## 9. Provenance

The un-preregistered study that opened this line reported IC +193%
(p = 0.0007), APY 47.9%, Sharpe 1.57, "beats SPY". Self-audit found five
defects — full-sample `qcut` regime labels (22.4% of days used future
volatility), embargo 0 against a forward label, SPY as benchmark instead of the
17.4% panel equal-weight floor, wrong label, wrong model. Corrected, the effect
**reversed**: −4.1%/yr, t = −0.48, p = 0.634, 49% win rate.

That failure produced the countermeasures in #573. **This document adds the one
#573 still had: the recognition that fixing every other factor at an arbitrary
constant is itself a design defect.**
