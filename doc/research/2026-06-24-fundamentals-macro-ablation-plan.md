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

## Non-goals (explicitly out of scope)
- **Macro / regime conditioning.** Macro (FRED) is not in the scorer, so this
  experiment answers "does macro help *stock selection*" — and that is answered
  structurally (no, by construction), not experimentally. It does **NOT** answer
  whether macro/regime conditioning improves *portfolio decisions* (sizing,
  regime gating, exposure); that needs a separate regime-conditioning ablation
  and is not claimed here. The title pairs "fundamentals / macro" only because
  the operator's question did.
- **Production config.** This plan produces evidence only; any strategy-104
  change is a separate, gated follow-up decision.

## Hypotheses
- **H0:** dropping fundamentals + sentiment + PEAD/SUE (i.e. alpha158-only) does
  NOT reduce per-regime placebo-clean IC beyond noise. (They are dead weight.)
- **H1:** at least one non-technical group adds placebo-clean IC in at least one
  regime.

## Design (ablation, same harness as #171/#176/#177)
Train + evaluate these **6 fully-enumerated variants** through the per-regime
walk-forward + placebo gate. The matrix is spelled out so the runner cannot pick
a different interpretation (group sizes: 159 alpha158 + 5 fund + 3 sentiment + 5
PEAD/SUE = 172):

| # | variant | feature set | # feats | purpose |
|---|---|---|---|---|
| V1 | **A** baseline | full | 172 | reference |
| V2 | **B** alpha158-only | drop all 13 non-technical | 159 | headline bundle contrast |
| V3 | **C** +fund only | alpha158 + 5 fund | 164 | fundamentals **ADD** test |
| V4 | **D1** drop-fund (LOGO) | full − 5 fund | 167 | fundamentals **leave-one-out** test |
| V5 | **D2** drop-sentiment (LOGO) | full − 3 sentiment | 169 | sentiment LOGO |
| V6 | **D3** drop-pead_sue (LOGO) | full − 5 PEAD/SUE | 167 | PEAD/SUE LOGO |

V3 (add fund to the technical base, `C−B`) and V4 (remove fund from the full set,
`A−D1`) **bracket fundamentals' marginal value** from below and above; both must
agree before any fundamentals-specific decision (see decision rule).

Harness (unchanged, validated): XGBoost rank:pairwise, per-regime split via GMM
regime argmax (BULL_CALM / BEAR / BULL_VOLATILE), 6 purged walk-forward cuts,
60d-embargo; **placebo = label shifted +60d**, report **placebo-clean = real −
placebo IC**. Dataset: `data/alpha158_291_fund_regime_dataset.parquet`.

## Metrics & decision rule
- Primary: **per-regime placebo-clean IC**, as a DIFFERENCE vs A (`B−A`, each
  `LOGO−A`, and `C−B` for the fundamentals add). Not absolute IC (the ~0.036
  shuffled-label leakage floor makes absolutes untrustworthy — see
  [[wf-gate-embargo-leakage-floor]]).
- Secondary: feature-group gain shares; optional costed non-overlap P&L for any
  group that looks decisive (the n≈10 hardened-P&L test from the trend-scan
  pass).

### Pre-registered equivalence threshold (set BEFORE running)
"≈ within seed noise" is fixed up front so the same numbers cannot be re-read
afterward as either weak-null or inconclusive:
- **Practical-null margin:** treat `|Δ placebo-clean IC| < 0.01` per regime (≈ ¼
  of the 0.046 leakage-floor sd) as no practical effect.
- **Paired test:** pair Δ on `(regime × WF-window × seed)`; a group counts as
  "adds IC" only if its paired mean Δ > 0 **and** the sign holds in ≥5 of 6 WF
  windows in that regime. A single regime/window flip is not decisive (the
  trend-scan lesson).
- Report the **seed distribution AND the per-window dispersion**, never a point
  estimate (see the seeds≠power caveat below).

### Decision — two separate decisions, do not conflate
1. **Whole non-technical bundle (`B vs A`):** if B ≈ A within the margin across
   all regimes → the 13 non-technical features are **dead weight as a bundle** →
   candidate to drop fund + sentiment + PEAD together.
2. **Fundamentals pipeline specifically:** retire the (bug-prone) fundamentals
   pipeline ONLY if BOTH the add (`C−B ≈ 0`) AND the leave-one-out (`A−D1 ≈ 0`)
   contrasts show no fundamentals IC — AND only on a rerun against the
   **post-#398/#401 refreshed + sanitized** fundamentals, with the
   freshness/corruption state (panel last-date, completeness %, e16 check)
   **recorded in the run manifest**. A null on stale/corrupt fundamentals proves
   nothing about the signal, so `B≈A` alone does **not** license retiring the
   fundamentals pipeline — it only indicts the bundle.
3. Any group that adds placebo-clean IC → keep it; invest in its data quality.

## Power & threats to validity (the honest part)
- **Underpowered harness:** ~10 non-overlapping 60d windows + a +0.036±0.046
  leakage floor. So this can **REJECT** (a group whose removal clearly drops
  placebo-clean IC is real) but a "no difference" is the WEAKER conclusion — it
  bounds the effect as *small*, not zero. Mitigate with **≥5 seeds** and report
  the seed distribution, not a point estimate.
- **Seeds ≠ statistical power.** The ≥5 seeds vary model init / subsampling only;
  they bound *optimizer* noise. The dominant uncertainty is window-to-window
  sampling over the ~10 non-overlapping 60d windows, which seeds do NOT reduce.
  So the pre-registered margin is a *practical-equivalence bound*, not a
  significance test — a "null" means "effect smaller than 0.01 IC at this power,"
  never "effect is zero." Per-regime windows are even fewer (~3–4 each), so any
  single-regime claim is the weakest of all.
- Confounds: the fundamentals data is itself stale/imperfect, so a null result
  could mean "the feature is weak" OR "the data is too degraded to help." Re-run
  C on the freshly-backfilled + sanitized fundamentals (post #398/#401) so a null
  is about the SIGNAL, not the data.
- Do NOT read a single regime's flip as decisive (the trend-scan lesson).

## Strategic payoff
Every P0 data incident on 2026-06-23 (91d staleness, e16 corruption, silent
refresh degradation) originated in the **fundamentals pipeline**. If the
fundamentals-specific gate fires (decision rule #2: both `C−B` and `A−D1` null on
*refreshed* data), **retiring the entire fundamentals data pipeline** is a large
net win: simpler model, smaller bug surface, zero maintenance — and it reframes
the P1 analyst-revision feature as the *replacement* fundamental-type signal to
validate, not an addition.

## Execution (after this plan is approved)
1. Build the 6 variant feature matrices from the regime dataset (post-backfill).
2. Run the per-regime placebo WF harness, 5 seeds, log placebo-clean IC per
   variant × regime × seed.
3. Report ONLY placebo-clean DIFFERENCES + seed distributions; state reject /
   weak-null per group. No production change without a follow-up decision.
