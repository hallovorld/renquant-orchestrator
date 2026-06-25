# BULL_CALM momentum admission guard (#51) — design for review

A DESIGN proposal for operator review **before** any pipeline change (same discipline as
the mu-floor plan): does the data justify vetoing low-momentum names from admission in the
BULL_CALM regime, and if so, how — without curve-fitting the threshold to exclude specific
names?

## Problem
The panel scorer has a documented **vol-tilt** (raw_panel↔vol corr +0.607) and a constant
mu intercept, giving ~zero placebo-clean IC in BULL_CALM. The practical symptom: it
repeatedly admits beaten-down, high-vol, **low-momentum** names (NFLX/ZM-type) in calm
markets. Momentum (`ROC60`) is already an alpha158 feature the model *sees*, yet the
vol-tilt overrides it — so a post-hoc, regime-gated **admission veto** (a cost-aware entry
filter, the lever #186 endorses) is the candidate fix, not new alpha.

## Data evidence (per-regime placebo-clean, 2016-11..2026-05, 291 names)
Momentum = `-ROC60` (qlib `ROC{d}=Ref(close,d)/close`, so intuitive momentum is its
negation), ≈3-month. placebo = per-ticker label `fwd_60d_excess` shifted +60 rows;
placebo-clean = real − placebo.

| regime | momentum placebo-clean IC | n_days | read |
|---|---|---|---|
| **BULL_CALM** | **−0.006** | 1214 | ~zero (real +0.037 IC is *entirely* leakage: placebo +0.043) |
| BEAR | +0.026 | 77 | noisy, tiny n (77 days) — not usable |
| BULL_VOLATILE | −0.062 | 1037 | negative |

> Verified 2026-06-24 by independent reproduction (`/tmp` script, same regime-argmax +
> placebo-shift harness). An earlier draft of this table reported BULL_CALM +0.0166 / BEAR
> −0.32; those IC figures did NOT reproduce and are corrected here. The decile table below
> DID reproduce to the digit.

So momentum has **~zero clean cross-sectional IC** in BULL_CALM (−0.006, well inside the
~0.036±0.046 leakage floor) and is negative in BULL_VOLATILE — its daily *ranking* power is
nil. **Ranking IC is therefore NOT the case for the guard.** The case is the admission-VETO
question — "are the names we'd admit at the bottom systematically bad?" — and the BULL_CALM
momentum-decile table answers yes (this is the load-bearing evidence, and it reproduces):

| mom60 decile | mean fwd_60d_excess | **median** | count |
|---|---|---|---|
| 0 (lowest mom) | −0.0329 | **−0.1073** | 34.4k |
| 1 | −0.0329 | −0.0752 | 33.5k |
| 2 | −0.0182 | −0.0606 | 33.4k |
| 3 | −0.0359 | −0.0705 | 33.6k |
| 4 | −0.0424 | −0.0724 | 33.6k |
| 5 | −0.0356 | −0.0525 | 33.4k |
| 6 | −0.0102 | −0.0441 | 33.5k |
| 7 | +0.0097 | −0.0204 | 33.5k |
| 8 | +0.0221 | −0.0172 | 33.4k |
| 9 (highest mom) | +0.1748 | +0.0212 | 33.9k |

The **median** forward excess return rises monotonically with momentum; the bottom decile's
median is **−0.107**. Low-momentum names reliably underperform in BULL_CALM — the exact
bucket the vol-tilt parks its picks in.

**Honest caveats:** (1) the cross-sectional placebo-clean IC (−0.006) is essentially **zero**
— the ranking power is nil, so the guard rests ENTIRELY on the bottom-decile median
underperformance, not on any ranking signal. (2) The decile **mean** spread (+0.21) is outlier-driven (decile-9
mean +0.175 vs median +0.021); the robust signal is the **bottom-decile underperformance by
median**, not a smooth mean gradient. (3) Prior art: fundamental-momentum was REJECTED
(#177); price trend-scan was "relatively promising but harness-caveated" (#176) — this is
in the latter, weaker-but-not-dead camp.

## Proposed guard (conservative, default-OFF)
A new **regime-gated admission veto**, evaluated alongside the existing `ConvictionGateTask`
(does NOT replace mu_floor or the #145 demean; it is an additional, independent veto):

- **Scope:** only when the detected regime is **BULL_CALM**. No effect in BEAR/BULL_VOLATILE
  (where momentum is negative/unreliable).
- **Rule:** veto admission of a candidate whose cross-sectional momentum percentile (within
  the day's scored universe, `mom60 = -ROC60`) is **below the 10th percentile** (bottom
  decile) — the bucket whose median forward excess is −0.107. Start at the *bottom decile*
  (most defensible: only the clearly-bad tail), not a median split.
- **Config (strategy-104), default OFF:**
  ```
  ranking.bull_calm_momentum_guard.enabled: false
  ranking.bull_calm_momentum_guard.percentile: 0.10   # veto below this momentum pct
  ranking.bull_calm_momentum_guard.feature: ROC60      # negated internally
  ```
- **WARN-first option:** like the data-integrity gate, support an `enforce:false` mode that
  only flags (down-weights / logs) so we can watch it shadow before it vetoes.

## Anti-curve-fit justification
The percentile is set by **where forward returns turn reliably negative in the decile table
(bottom decile, median −0.107)** — a universe-relative, name-agnostic cut — NOT reverse-
engineered to exclude NFLX/ZM. It is cross-sectional (per-day percentile), so it adapts to
the universe and cannot be gamed by absolute levels. Default-OFF + WARN-first means merging
changes no behaviour.

## Validation plan (before any enable)
1. Backtest the **admitted-set forward return** with vs without the veto, per regime, on the
   placebo-clean harness — confirm the veto raises BULL_CALM admitted-set median forward
   excess without starving admissions (count impact).
2. Confirm on ≥5 seeds / multiple windows that the bottom-decile underperformance is not a
   single-window artifact (the #186 lesson).
3. Only then does the operator flip `enabled:true` (a strategy-104 change), ideally after a
   WARN-mode shadow period.

## Recommendation
**Build the guard, default-OFF + WARN-first, design reviewed here first.** The evidence is
suggestive not strong (weak IC, mean outlier-driven), so it ships dark and must pass the
admitted-set validation before enable — but the bottom-decile underperformance is real
enough, and the strategic fit (entry filter over the vol-tilt failure mode) is right.
Pairs with the #145 cross-sectional demean as the two independent levers on the same
bad-pick problem.

Companion progress note: `doc/progress/2026-06-24-bull-calm-momentum-admission-guard.md`.
