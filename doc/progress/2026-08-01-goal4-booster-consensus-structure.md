# GOAL-4 — the disagreement is structured: two thirds of traded slots already carry a majority

**Date:** 2026-08-01 · `renquant-orchestrator` · GOAL-4 (multi-model ensemble)

## The question this answers

orch#712 measured that 12 same-recipe boosters disagree on **35.7%** of the real top decile
and closed with *"disagreement is a precondition for an ensemble to be worth anything,
never evidence that one works."* That leaves one thing open and answerable without labels:
**is the disagreement uniform churn, or is there a stable core?**

## Measured

Same 12 boosters, same 20 sessions (2026-04-07 … 2026-05-04, 144–153 names/date,
`k` = 14–15), **3 528** top-decile slots `[本次实测 2026-08-01]`:

| votes | names | % names | slots | % slots |
|---|--:|--:|--:|--:|
| 1/12 | 220 | **29.8%** | 220 | 6.2% |
| 2/12 | 105 | 14.2% | 210 | 6.0% |
| 4/12 – 11/12 | 28–45 each | 3.8–6.1% each | — | 4.7–10.0% each |
| **12/12** | **76** | **10.3%** | **912** | **25.9%** |

- **66.9%** of traded slots are held by names with a **majority** (≥7/12).
- **25.9%** by **unanimous** names — the single largest bucket by slots.
- The 220 singleton appearances are **29.8% of names but only 6.2% of slots**.
- Per date the union of all twelve top deciles is a median of **38** against `k = 15` —
  **2.50×** one arm — with a median of **4** unanimous and **10** singletons.

**So the precondition is met with room to spare:** there is a stable core to concentrate on
and a large, cheap tail to drop.

## Two corrections I made to my own claims

**"U-shaped" was wrong, and my own test caught it.** I first described the by-name
distribution as U-shaped and asserted `12/12` exceeds every middle bucket. It **failed**:
76 at 12/12 against **105 at 2/12**. The data was right; the description was not. What
holds is narrower and still decisive — 4/12–11/12 is a flat plateau (28–45 names) and
unanimity stands clear above **all of it**, forming a distinct second mode. Both the
`h[n] > max(plateau)` and the `h[n] < h[2]` halves are now pinned.

**A silent zero, caught because it was impossible.** My first aggregation wrote
`for v, c in cnt.items(): slots[v] += c` where `cnt` maps *ticker → votes* — so the slot
histogram was keyed by ticker string and every integer lookup returned 0. It reported
"0.0% of slots" at **every** vote level, which cannot be true, and that is the only reason
I looked. The loop variables were swapped.

## By-name and by-slot disagree fourfold, so both are reported

A name picked by one booster is one name and **one** slot; a name picked by twelve is one
name and **twelve**. Counting names says singletons dominate at 29.8%; counting slots says
they are 6.2% of what is traded. Publishing only the first would understate the stable core
by roughly four times.

## Not claimed

**That a consensus rule would perform better.** No label and no forward return is read
anywhere — asserted against the source by a test, not promised in prose. Twelve models
sharing one recipe can share one blind spot, and agreement cannot distinguish a real signal
from a common error. That question needs the forward returns, which for the blend ledger
mature around late October 2026.

## Tests

12. Including the arithmetic identity that total slots must equal `n_boosters × k ×
scored_dates` — if that drifts, a date was double-counted or silently dropped — and a
source-level assertion that no `fwd_*` or `label` column name appears in the file.

Suite: **5196 passed, 2 skipped**, run before the push.
