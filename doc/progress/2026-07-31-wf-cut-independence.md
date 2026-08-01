# GOAL-6 — "3 of 3 cuts positive" is three correlated windows, and 2 is the ceiling

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-6, evaluation path

## The measurement

`prod/panel-ltr.alpha158_fund.previous.json`, gate stamp read canonically
`[本次实测 2026-07-31]`:

| | |
|---|---:|
| economic cuts | **3** — 364, 364, 361 days |
| sum of cut lengths | **1089 d** |
| calendar actually covered | **816 d** (2024-01-02 … 2026-03-28) |
| **redundancy** | **1.33×** (1.00 = disjoint) |
| overlap cut1 ↔ cut2 | **183 d = 50%** of the shorter window |
| overlap cut2 ↔ cut3 | **90 d = 25%** |

So `n_positive_cuts: 3` and `n_cuts_beat_spy_apy: 0` are counts over **three correlated
windows**. That matters beyond statistics: *"absolute returns positive (3/3 cuts)"* is the
reason recorded in the **2026-07-05 operator override** that admitted this artifact.

## A hypothesis this refuted — mine

Going in, I expected the economic arm to be leaving calendar on the table: 43 manifest
folds spanning 882 days, only a handful evaluated. **It is not.** The evaluated union
covers **816 of 882 days — 92.5%** — leaving 66 days outside it.

**The problem is not unused time. It is reused time.** Recording this because the
hypothesis was the more attractive story and it was wrong; the measured version is the one
that survives.

## The structural ceiling — the part that actually binds

At the current ~364-day window, 882 days of corpus admits **at most 2 disjoint windows**:

| window | max disjoint windows in 882 d |
|---:|---:|
| 364 d | **2** |
| 252 d | 3 |
| 182 d | 4 |

So the economic arm **cannot** report more than n=2 independent observations without
shortening the window. Any "N of N cuts" threshold is being read against a set that
structurally cannot contain N independent members at N=3.

That is a design constraint on the gate, not a bug in it — and it is what such a threshold
has to be calibrated against.

## What this does NOT do

- It does **not** re-score anything.
- It does **not** compute an effective sample size. Redundancy and pairwise overlap are
  **geometry**, derived from the window boundaries with no assumption. Converting geometry
  into an effective *n* requires a correlation this tool does not measure, and doing that
  from an assumed ρ is a **standing correction** in this programme.
- It does **not** propose a threshold or a window length. The ceiling table is arithmetic,
  offered so a proposal can be argued against a number.

Read-only: opens artifacts, writes nothing, never invokes git.

## Tests

15, aimed at the ways this measurement could **overstate** independence: an unreadable cut
is **reported, never dropped** — silently shrinking the set makes the remainder look more
independent, which is the exact quantity being measured; an inverted or non-object cut is
rejected rather than counted; **no gate block exits 1**, because "no cut set" must never
read as "the cuts are independent"; a malformed `metadata` container does not crash; the
legacy stamp location is read and its source recorded; overlap is expressed as a fraction
of the **shorter** window, since against the longer one a large overlap looks small;
anti-vacuity where genuinely disjoint cuts exit `0`; the scope note refusing the
effective-*n* reading is asserted present; and the live artifact is asserted to **reproduce
the docstring's numbers**, so the docstring cannot become an assertion with a citation
attached.

Suite: **5046 passed, 2 skipped** — run before the push.

---

## CORRECTION 2026-08-01 — `calendar_union_days` was the OUTER SPAN, not the union

Reviewed `[codex on orch#696]`: *"With two disjoint cuts separated by a gap, the report
counts the gap as covered and `sum_of_lengths / calendar_union_days` falls below 1 even
though the cuts are disjoint. That makes the documented invariant '1.00 means disjoint'
false and overstates coverage."*

Correct. I computed the span from earliest start to latest end and called it the union.
For the cuts actually measured they coincide — all three overlap, so the merged interval
*is* the outer span, and **the published 816 d / 1.33× are unchanged**. But the metric was
wrong for any corpus with a gap, and the invariant I documented was false in exactly the
case a reader would use it to check.

**Fixed by merging intervals.** `redundancy` is now `sum(lengths) / true_union` and is
**exactly 1.00 iff the cuts are disjoint** — it can no longer fall below 1. The outer span
is retained separately as `outer_span_days`, because *"the cuts run from X to Y"* is a real
fact; conflating it with the union was the defect, and dropping it would lose something
true.

Four regressions: two disjoint cuts **separated by a gap** assert union = sum of lengths
and redundancy **exactly 1.0**; the outer span is asserted to exceed the union in that
case; adjacent (touching) cuts merge to one interval and stay at 1.0; and redundancy is
asserted **≥ 1.0** across shapes — the invariant the outer-span version broke.

19 tests (was 15). Suite: **5095 passed, 2 skipped**.
