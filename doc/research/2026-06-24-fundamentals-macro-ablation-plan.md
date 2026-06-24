# Experiment plan — do fundamentals / macro earn their keep in the panel model?

2026-06-24. **Plan only — for review before execution.** Designed to be falsifiable
and to avoid the over-claiming that the 2026-06-23 neutralization/trend-scan
passes were (rightly) pushed back on.

## Question
Does the panel-LTR scorer actually gain from its non-technical features
(fundamentals / sentiment / earnings-event), or is it ~entirely an alpha158
technical/price model? And is macro relevant at all?

## Current state (verified from the live artifact `panel-ltr.alpha158_fund.json`)
- 172 feature_cols: **159 alpha158 (technical/price, 92%)** + 5 fundamental
  (earnings_yield, book_to_price, gross_profitability, roe, asset_growth) + 3
  sentiment + 5 PEAD/SUE. Fundamentals' gain share ≈ 8%.
- **Macro (FRED) is NOT in the scorer at all** — it only feeds GMM regime
  detection. So for *stock selection* macro already contributes zero; "is macro
  meaningful to the model" is answered (no) for the scorer, and is a *separate*
  question for regime conditioning (out of scope here).
- Circumstantial: fundamentals were 91d stale AND e16-corrupt on 2026-06-23 yet
  the picks (NFLX/ZM) did not change — suggestive of low marginal value, but not
  proof.

## Hypotheses
- **H0:** dropping fundamentals + sentiment + PEAD/SUE (i.e. alpha158-only) does
  NOT reduce per-regime placebo-clean IC beyond noise. (They are dead weight.)
- **H1:** at least one non-technical group adds placebo-clean IC in at least one
  regime.

## Design (ablation, same harness as #171/#176/#177)
Train + evaluate these variants through the per-regime walk-forward + placebo gate:

| variant | features |
|---|---|
| **A** baseline | full 172 |
| **B** alpha158-only | 159 (drop all 13 non-technical) — the headline contrast |
| C | alpha158 + fundamentals only |
| D-LOGO | leave-one-group-out: drop {fund} / drop {sentiment} / drop {pead_sue} |

Harness (unchanged, validated): XGBoost rank:pairwise, per-regime split via GMM
regime argmax (BULL_CALM / BEAR / BULL_VOLATILE), 6 purged walk-forward cuts,
60d-embargo; **placebo = label shifted +60d**, report **placebo-clean = real −
placebo IC**. Dataset: `data/alpha158_291_fund_regime_dataset.parquet`.

## Metrics & decision rule
- Primary: **per-regime placebo-clean IC**, as a DIFFERENCE B−A (and each LOGO −
  A). Not absolute IC (the ~0.036 shuffled-label leakage floor makes absolutes
  untrustworthy — see [[wf-gate-embargo-leakage-floor]]).
- Secondary: feature-group gain shares; optional costed non-overlap P&L for any
  group that looks decisive (the n≈10 hardened-P&L test from the trend-scan
  pass).
- **Decision:**
  - If B ≈ A (placebo-clean IC within seed noise) across regimes → fundamentals +
    sentiment + PEAD are **dead weight** → retire them.
  - If a group adds placebo-clean IC → keep it; invest in its data quality.

## Power & threats to validity (the honest part)
- **Underpowered harness:** ~10 non-overlapping 60d windows + a +0.036±0.046
  leakage floor. So this can **REJECT** (a group whose removal clearly drops
  placebo-clean IC is real) but a "no difference" is the WEAKER conclusion — it
  bounds the effect as *small*, not zero. Mitigate with **≥5 seeds** and report
  the seed distribution, not a point estimate.
- Confounds: the fundamentals data is itself stale/imperfect, so a null result
  could mean "the feature is weak" OR "the data is too degraded to help." Re-run
  C on the freshly-backfilled + sanitized fundamentals (post #398/#401) so a null
  is about the SIGNAL, not the data.
- Do NOT read a single regime's flip as decisive (the trend-scan lesson).

## Strategic payoff
Every P0 data incident on 2026-06-23 (91d staleness, e16 corruption, silent
refresh degradation) originated in the **fundamentals pipeline**. If the ablation
shows fundamentals don't earn placebo-clean IC, **retiring the entire
fundamentals data pipeline** is a large net win: simpler model, smaller bug
surface, zero maintenance — and it reframes the P1 analyst-revision feature as
the *replacement* fundamental-type signal to validate, not an addition.

## Execution (after this plan is approved)
1. Build the 6 variant feature matrices from the regime dataset (post-backfill).
2. Run the per-regime placebo WF harness, 5 seeds, log placebo-clean IC per
   variant × regime × seed.
3. Report ONLY placebo-clean DIFFERENCES + seed distributions; state reject /
   weak-null per group. No production change without a follow-up decision.
