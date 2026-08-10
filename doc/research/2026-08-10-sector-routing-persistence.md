# Sector-routing Stage-0 pre-test: leadership does not persist — the trailing-performance routing policy dies here

Operator question (2026-08-10): how would a backtest decide which model
each sector uses NEXT quarter? Design answer: you backtest the POLICY, not
the table — quarterly walk-forward with a frozen selection rule, cost
model, permutation placebo and an oracle upper bound. But the whole
edifice rests on ONE testable premise — that per-sector model leadership
PERSISTS — and that premise is the cheapest thing to test first.

## Stage 0 verdict `[VERIFIED — committed derivation over the #936 dailies; decisions CSV committed]`

| metric | value |
|---|---|
| decisions (sector × adjacent-quarter pairs) | 54 |
| "best stays best" hit rate | **27.8%** vs chance 33.3% (one-sided binomial p = 0.84) |
| adjacent-quarter ranking Spearman (mean) | **−0.185** |
| follow-the-winner capture of oracle | **41%** (+7.6%/q vs oracle +18.8%/q) |

Leadership is not merely non-persistent — it leans ANTI-persistent on this
history. Any trailing-performance routing rule (follow-the-winner with or
without hysteresis) inherits this and cannot beat blind selection; the
Stage-1 walk-forward policy evaluation is therefore NOT built. That is the
pre-test doing its job: one cheap number kills the cathedral.

## What survives

* The oracle gap (+18.8%/q available in hindsight) shows real dispersion
  exists between sector-books — the failure is IDENTIFIABILITY from
  trailing returns, not absence of differences.
* The living alternative is STATE-conditioning, not calendar-routing: the
  #215 line asks "under what observable CONDITION does a model lead"
  rather than "who led last quarter" — a leading variable is immune to
  this anti-persistence by construction.
* The −0.185 tempts a contrarian rule (route to last quarter's loser). It
  is NOT promoted to a hypothesis here: it was observed in this same
  data (the post-selection lesson, model#215 r2) and may only enter a
  future prereg as an a-priori design, never as this table's conclusion.

## Caveats

Replay frame throughout (#937 serving divergence, #944 CUTS footnote on
the panel arm); ~9 quarters × 6 correlated sectors; the pre-test must be
re-run on served data as it accrues (the same derivation applies).
