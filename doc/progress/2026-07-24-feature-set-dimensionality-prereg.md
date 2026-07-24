# 2026-07-24 — Prereg: the production panel-LTR is effectively a ~13-feature model (PR #573)

STATUS:    in-progress
WHAT:      Adds a design-only preregistration (`doc/research/2026-07-24-feature-set-
           dimensionality-prereg.md`) plus its (unwired, unrun) study script
           `scripts/research_feature_count_cv.py`. No results; the study has not
           been executed. Fix pass: closed the anchor/`--n-splits` mismatch (see
           EVIDENCE below), hardened the H3 PIT-confound open question into a §5
           precommit guard, repaired this progress doc's C5 fields, and rebuilt the
           branch's commit attribution.
WHY/DIR:   Split census of the live production booster shows 38% of its 172
           features are provably inert (zero XGBoost splits) and 14 non-technical
           columns carry 60.7% of total gain; this study is the first feature-count
           sweep ever run against the production XGB `rank:pairwise` panel-LTR
           (four prior reductions all targeted a different model/level). Directly
           advances the standing "does the panel-LTR need 172 features" question
           left open by the 06-24 group ablation and D3 core-shrink NULL.
EVIDENCE:
  artifact:      scripts/research_feature_count_cv.py `--census` / `--diagnose` output
                 against `artifacts/prod/panel-ltr.alpha158_fund.json` (read-only)
  prod or exp:   prod artifact, read-only census only — no training run, no write
  existing data: matches the split-census numbers in the prereg (66/172 zero-split,
                 60.7% non-technical gain share, effective rank 10.4/172)
  best-known?:   n/a — this PR asserts no IC/Sharpe claim; it is a design +
                 unrun-script preregistration only
  scope:         "split census + label-free redundancy diagnostics on the live prod
                 artifact, descriptive only; no trained-arm result exists yet"
NEXT:      Two items outstanding, not resolved by this fix pass:
           (1) the design reviewer's structural finding that
           `scripts/research_feature_count_cv.py` is model-training research and
           does not belong in `renquant-orchestrator` per the multi-repo code-
           placement rule — it needs to move to `renquant-model` before any run
           produces results; this fix pass did not perform that move.
           (2) re-review of the corrected anchor gating and H3 guard language.
           Once (1) and (2) clear, the study itself is the next bounded action.

## What this PR is

A **preregistration only**. Design + script, **no results, study not run**.
Requesting adversarial review of the design before compute is spent.

- `doc/research/2026-07-24-feature-set-dimensionality-prereg.md` — frozen on merge
- `scripts/research_feature_count_cv.py` — implements it; deterministic, seeded,
  read-only against production (refuses output paths containing `artifacts/prod`,
  `artifacts/sim`, `strategy_config`, `/data/`, `walkforward`, `panel-ltr`)

Results land in a **separate PR** that may not amend §§0-6.

## The finding that motivates it — measured on the LIVE booster

Split census of `artifacts/prod/panel-ltr.alpha158_fund.json`
(`trained_date` 2026-06-21, `oos_mean_ic` 0.0533), decoded from
`booster_raw_json` — reproduce with `--census`:

| | |
|---|---|
| features receiving **ZERO splits** | **66 of 172 (38%)**, 65 of them alpha158 technical |
| **14 non-technical features (8% of count)** | **60.7% of total gain** |
| 158 alpha158 technical | 39.3% of total gain |
| **50% of total gain** | **top 4**: `gross_profitability` 17.8%, `book_to_price` 13.5%, `asset_growth` 9.8%, `STD60` 9.6% |
| 80% of total gain | top 13 |

A zero-split feature **provably cannot affect that booster's output** — a
structural fact, not an importance attribution, so it is not subject to the
correlated-predictor identification critique in
`doc/research/2026-07-11-meta-score-attribution.md`. The 60.7% gain share IS an
attribution and is labelled descriptive-only throughout.

Label-free redundancy of the same matrix (724,359 rows, per-date standardized,
`--diagnose`): participation-ratio effective rank **10.4** of 172
(**16.5× redundant**); 50% of variance in 5 components; **84%** of columns are
the same base operator at another window; greedy de-dup at |r| ≤ 0.70 leaves 69.

**The production model is already, in effect, a ~13-feature model dominated by
five SEC fundamentals, carrying 66 provably inert columns.** Whether making
that explicit changes OOS IC is the question.

## Prior art — checked before designing (prereg §0)

Four prior reductions exist and were all neutral-to-negative — E51 top-K on the
**NGB QuantileHead** (reduction hurts monotonically, all-169 best), the 06-24
group ablation (163 vs 158, practical-NULL), the PatchTST prune line (both arms
FAIL gate), and E11/E39 (adding features hurts). D3 core-shrink is the standing
house prior: *"selection adds nothing over random shrink"*.

**Genuinely absent, hence this study:** no feature-count sweep has ever run on
the production XGB `rank:pairwise` panel-LTR; no collinearity/PCA analysis of
alpha158 exists; the **V5 (drop sentiment → 169) and V6 (drop PEAD/SUE → 167)
arms preregistered 2026-06-24 were deferred unrun** and are discharged here; no
split census was persisted anywhere.

Incidental correction: the 06-24 plan's "159 alpha158 + 13" is an off-by-one —
the artifact has 158 + 14.

## Harness

Production, apples-to-apples; only the feature list varies. `fwd_60d_excess`,
XGB `rank:pairwise` with `PANEL_LTR_PARAMS`, purged walk-forward, 60-day
embargo, train-only normalization rebuilt per fold, seeds 42/43/44.

**Anchor validated before writing the prereg:** `all_172` reproduces
`mean_ic = 0.0488`, folds `[0.0781, −0.0010, 0.0693]` vs the live artifact's
`0.0533`, `[0.0852, 0.0013, 0.0734]` (gap consistent with the artifact's
2026-06-21 vintage against this panel's 2026-04-23 cutoff). The script **voids
the run** if the anchor does not reproduce.

## Design decisions a reviewer should attack

1. **Non-inferiority is primary** (δ = 0.005). The actionable finding is "drop N
   features at no cost"; a superiority-only frame would discard it.
2. **Paired ΔIC, never absolute IC** — the standing ~+0.04 leakage floor means
   the anchor sits on the floor. A `placebo` arm measures it in-harness.
3. **Moving-block bootstrap, block 60.** `fwd_60d_excess` makes consecutive
   per-date ICs share up to 59/60 of their window; a naive t-test over ~1,400
   dates would overstate significance by roughly √60.
4. **Random-K control**, per D3. Pre-committed to reporting "selection adds
   nothing" prominently if that is what lands.
5. **Three primaries** (H1 `used_only`, H2 `dedup_r70`, H3 `nontechnical_only`
   vs `technical_only`), Bonferroni α = 0.0167; multi-seed sign stability
   required.
6. **Structural selectors preferred** over attribution-based ones; the single
   gain-ranked arm is flagged `[attribution-dependent]` in the output.

Six questions are posed to the reviewer in prereg §7 — block length, the δ
choice, residual leakage in in-fold `gain_top{K}`, 5 folds vs 3, **whether a
strong `sec_fund_only` result would be evidence about features or about
fundamental look-ahead in the panel builder**, and whether E51's monotone
result makes this a predictable NULL that should be descoped.

## Provenance — why this is preregistered

The author's immediately preceding **un-preregistered** study of
regime-conditional feature selection reported IC +193% (p = 0.0007), APY 47.9%,
Sharpe 1.57, "beats SPY". Self-audit found five defects: full-sample `qcut`
regime labels (22.4% of days used future volatility), embargo 0 against a
forward label, SPY as benchmark instead of the 17.4% panel equal-weight floor,
wrong label (`fwd_20d_excess`), wrong model (rank composite, not
`rank:pairwise` XGB). Corrected, the effect **reversed**: −4.1%/yr, t = −0.48,
p = 0.634, 49% win rate; both arms also lost to panel equal-weight on Sharpe
(0.62/0.59 vs 0.86). Prereg §8 maps each design choice to the defect it guards.
No claim from that study survives or is carried here.

## Memory tier touched

None yet — no verdict exists. On results this earns a `VERDICTS.md` row
(exploratory arms may not carry one). **No result here authorizes a config
change**: a recipe change re-fingerprints the artifact and must route through
the normal WF-promote gate.

## Tests

`../RenQuant/.venv/bin/python -m pytest -q --ignore=tests/test_bundle_seal.py`
→ **4261 passed, 2 skipped** (116s).

`tests/test_bundle_seal.py` fails to collect on `ModuleNotFoundError:
renquant_artifacts.bundle_schema`. **Verified pre-existing on `origin/main`** —
not introduced by this PR, which is additive only (2 docs + 1 unwired script).

`ruff check scripts/research_feature_count_cv.py` → clean.
