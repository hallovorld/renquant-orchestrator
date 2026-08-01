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

---

## ROUND 3 2026-08-01 — the published numbers now ship with their evidence

Reviewed `[codex on orch#696]`: *"the only reproduction test hard-codes a local absolute
backtesting artifact and skips in CI, while neither the document nor a checked-in manifest
binds that artifact to a content fingerprint, producer run, or corpus-day source."*

Correct. **816 / 1.33× / 882 were numbers in prose**, reproducible only on this machine.

`--manifest` and `--evidence-out` now emit a checked-in evidence manifest carrying:

| | |
|---|---|
| artifact | name + **sha256** |
| walk-forward manifest | name + **sha256** |
| corpus span | **derived**, not asserted: `rows_key`, `n_folds`, `first_cutoff`, `last_cutoff`, and the subtraction |

Emitted `[本次实测 2026-08-01]`: **43** folds under key `retrains`, **2023-10-02 …
2026-03-02**, `corpus_days = 882` — the number the document has been quoting, now with the
arithmetic and both digests beside it.

**Two tests, and the split matters.** One reads the **committed manifest** and checks the
derivation and the headline numbers — it runs **everywhere, including CI**, because it
touches no artifact tree. The other recomputes both digests from the named files and
**skips loudly** when the tree is absent: a verification that cannot run must not read as
one that passed.

21 tests (was 19). Suite: **5097 passed, 2 skipped**.

### A worktree hazard, second occurrence

`git stash pop` here restored a stash belonging to `goal4/ensemble-existence-evidence`
again. The cause is now clear: **`git stash` is repo-global, not worktree-local**, so
`pop` in any worktree takes the repository's most recent entry whatever branch it came
from. Committing with `-A` would have pulled another lane's files into this PR for the
second time today. Cleaned by removing only the foreign index entry and committing
**explicit paths** — and the pattern itself is the defect: do not `stash`/`pop` in a
multi-worktree repo.

---

## ROUND 3 — a basename plus a digest lets a reader VERIFY, never FIND

Reviewed `[codex on #696]`: *"evidence.json has only basenames and hashes. It does not
identify the producing repository/ref, repository-relative source paths, or producer/run/
artifact identity, so a reader cannot locate or interpret the hashed inputs outside this
workstation layout."*

That distinction is the whole point. A digest lets someone check a file **they already
have**; it does nothing to help them get it. Every hashed input now carries where it came
from, derived from the file's own checkout rather than from any assumption about where
repos live:

| field | for the artifact |
|---|---|
| `repo` / `repo_remote` | `RenQuant` / `https://github.com/hallovorld/RenQuant.git` |
| `repo_head` | `3f4e3d6b857f8d8a4234eb4b9f71d997b84211bb` |
| `repo_relative_path` | `backtesting/renquant_104/artifacts/prod/panel-ltr.alpha158_fund.previous.json` |
| `tracked_and_clean` | `false` — the artifact has uncommitted changes, which a reader needs to know before trusting the ref |

and the same block for the corpus manifest (`…/artifacts/sim/…`, clean).

**Producer identity is READ, never reconstructed** — `train_run_id: eeee9542`,
`trained_date: 2026-07-05`, `kind: panel_ltr_xgboost`, `gate_run_at: 2026-07-05T22:25:10`,
`gate_eval_scope: walkforward_manifest`. A field the artifact does not carry stays `None`:
an invented producer id would defeat the purpose more thoroughly than an absent one.

A file **outside any checkout** reports `in_git: false` and stops — a fabricated
repo-relative path is worse than none.

## The malformed-manifest crash

> *"the current `date.fromisoformat` comprehension raises uncaught `ValueError` for a
> structurally bad upstream manifest."*

Now a controlled `manifest_unreadable` naming the offender
(`1 of 2 cutoff_date value(s) are not ISO dates; first offender: 'not-a-date'`) **and
still carrying the manifest's digest** — a refusal that does not identify what it refused
is only marginally better than a crash.

## A defect in my own test, found by mutating

My first provenance test read the **committed `evidence.json`**, so deleting
`repo_relative_path` from `_repo_provenance` left it green: the guard was validating the
record rather than the producer. Caught by mutating the helper and watching nothing fail.
`test_the_PRODUCER_still_emits_repo_ref_and_relative_path` binds to the code, and that
mutation now fails.

Tests 21 → 27.
