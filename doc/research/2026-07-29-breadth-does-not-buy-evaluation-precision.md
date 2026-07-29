# Breadth does not buy evaluation precision: 292 → 830 names is worth ~3%

**Date:** 2026-07-29
**Status:** measurement, not a proposal. Nothing here asks for a decision; it
supplies a number that GOAL-6 Stage 2 scoping currently assumes rather than
measures.
**Bottom line:** on the clf walk-forward corpus, 91% of per-date IC variance is
breadth-proof. Going from 292 to 830 names narrows the per-date IC standard
deviation by **2.9%**. The binding constraint on resolving power is TIME, not
cross-sectional width.

---

## 1. Why this was measured

GOAL-6 sequences Stage 1 (build an 830-name point-in-time panel) into Stage 2
("breadth retraining"). The programme's stated motivation for breadth includes
better measurement. That link had never been measured — it was inherited from
the general intuition that a wider cross-section gives a less noisy daily IC.

The intuition is correct in direction and almost irrelevant in magnitude, which
is the kind of thing worth knowing before building a panel.

## 2. Method

Subsample the cross-section of the clf walk-forward corpus to `N` names per
date, recompute the per-date Spearman IC, and measure its variance as a
function of `N`. Fit the standard decomposition

```
Var(IC) = a + b/N
```

where `b/N` is the finite-sample estimation term (shrinks with breadth) and `a`
is everything else — genuine day-to-day variation in the signal's strength,
regime, and the model's own instability. `a` is what breadth cannot touch.

Corpus: `clf_wf_scores.parquet` — 178,191 rows, 625 score dates, 43 folds,
292 tickers, all rows carrying `fwd_60d_excess`. Restricted to the 594 dates
carrying ≥250 names so the subsampling ladder is comparable across `N`.
3 independent draws per (date, N).

## 3. Result

| names/date `N` | Var(per-date IC) | sd |
|---:|---:|---:|
| 20 | 0.08485 | 0.2913 |
| 40 | 0.05874 | 0.2424 |
| 80 | 0.04832 | 0.2198 |
| 140 | 0.04195 | 0.2048 |
| 200 | 0.04022 | 0.2005 |
| 250 | 0.03948 | 0.1987 |
| 292 | 0.03899 | 0.1975 |

```
fit:  Var(IC) = 0.03535 + 0.9814/N        [VERIFIED — measured this session]
irreducible share at N=292: 91%
```

Extrapolating the fitted curve:

| `N` | sd(per-date IC) | vs N=292 |
|---:|---:|---:|
| 292 | 0.1968 | — |
| 500 | 0.1932 | −1.8% |
| **830** | **0.1911** | **−2.9%** |
| 2000 | 0.1893 | −3.8% |

**Even an infinitely wide cross-section caps out at −4.4%** (`sqrt(a)` = 0.1880).

## 4. The corroborating observation

This is not an artefact of one corpus. Compare the two walk-forward corpora
measured this session, both over the same 625 score dates:

| corpus | names/date | mean IC | CI half-width | resolves? |
|---|---:|---:|---:|---|
| PatchTST | 142 | +0.0310 | 0.0562 | no |
| clf | 292 | +0.0608 | 0.0733 | no |
| prod XGB | — | +0.0731 | 0.1004 | no |

The clf corpus has **twice** PatchTST's cross-sectional width and a **wider**
confidence interval. Breadth is simply not the axis the interval is sitting on.
Both have 11 independent 60-day blocks, and that is the number that binds.

(An earlier session measured `Var(IC) = 0.01877 + 1.065/N` on a different
corpus — a different `a`, the same conclusion about which term dominates at
realistic `N`.)

## 5. What this does NOT say

This measures the precision of the **evaluation**, not the quality of the
**model**. They are different axes and conflating them would be a serious
error:

- A wider training panel may well produce a **better model** — more rows, more
  sector coverage, less overfitting to a narrow universe. Nothing here bears on
  that.
- A wider **tradeable** universe is worth real money independently: the top
  decile of 830 names is 83 candidates against 29, which changes portfolio
  construction and capacity.
- **Stage 1's original justification stands untouched.** The 830-name PIT panel
  exists to remove survivorship bias, which is a correctness requirement, not a
  power argument. A biased panel is wrong at any width.

What it does say: if Stage 2 is scoped, budgeted, or sequenced on the premise
that breadth will make results *resolvable*, that premise is false by roughly an
order of magnitude. Resolving the effects this programme chases needs more
independent time blocks, and no amount of cross-sectional width substitutes.

## 6. Caveats

- Restricting to dates with ≥250 names means `N=292` draws are occasionally
  from a pool slightly smaller than 292; this biases the last row toward the
  `N=250` value and, if anything, *understates* how flat the curve is.
- The `a + b/N` form is fitted, not derived. It tracks the measured ladder
  closely (predicted 0.03871 vs measured 0.03899 at `N=292`; predicted 0.08445
  vs measured 0.08485 at `N=20`), but extrapolation to `N=2000` is an
  extrapolation.
- `a` is corpus- and model-specific. A different signal with genuinely stabler
  day-to-day strength would carry a smaller `a`. That is a reason to re-measure
  per corpus, not a reason to assume breadth helps more elsewhere.

## 7. Provenance

All figures `[VERIFIED — measured this session]` from
`scratchpad/clf-wf/clf_wf_scores.parquet`, read-only, in the quarantined scratch
namespace. No production data, config, or artifact was read for write or
modified. The corpus itself is complete: 43/43 folds, no smoke-only folds,
178,191/178,191 rows carrying labels, with the leakage contract enforced in code
(`effective_train_cutoff_date + lookahead_days < first OOS score date`, raising
`AssertionError` per fold rather than warning).
