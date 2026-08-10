# Sector-routing Stage-0 pre-test: the 1-quarter follow-the-winner rule shows no persistence (scope narrowed in review)

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
| blind equal-weight baseline | **+8.1%/q — follow-the-winner UNDERPERFORMS blind by −0.5%/q** |

SCOPE (review r1): this evaluates exactly ONE rule — the 1-quarter argmax
follow-the-winner. On this history that rule shows no persistence (hit
rate below chance), full adjacent-quarter rankings lean anti-persistent
(Spearman −0.185), and the rule underperforms blind equal-weight. Other
lookbacks, hysteresis variants, and richer policies are UNTESTED — and
testing a family of them on this same small sample would be a
multiplicity exercise requiring its own prereg. The 54 rows are six
CORRELATED sectors across ~9 quarters, not independent observations; the
binomial p treats them as independent and is therefore optimistic about
precision in both directions. On this evidence the Stage-1 walk-forward
for THIS rule family is not built; that decision is scoped to the tested
rule, not to all conceivable routing.

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
