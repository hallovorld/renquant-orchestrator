# The merge-audit gate becomes satisfiable, and its alarm says something

STATUS: complete. Operator-reported 2026-08-05 ("the issue has been repeatedly
showing up for months! fix fundamentally"). No live surface is touched.

WHAT: `audit_merged_prs()` keeps measuring all fetched history but now gates on a
rolling `GATE_WINDOW_DAYS = 7` window of merges. `repos merge-audit` aggregates the
window figures and emits a one-line `summary` an operator can act on. Historical
misses are still counted and reported — they simply do not gate.

WHY/DIR: the gate could not be satisfied, by construction.

A PR passes when it carries a comment matching `^\s*merged\s+by\b` created **at or
before** `mergedAt`. A merged PR can still receive comments; it can never receive a
*pre-merge* one. So a single violation pinned that PR non-compliant **permanently**,
and `ok = (total_missing == 0)` over all history meant the gate could never return
green no matter how anyone behaved afterwards.

Measured on the live repos before the change:

| | |
|---|---|
| PRs audited | 454 |
| compliant | **79** |
| missing | **375** |
| by month | 05: 0/4 · 06: 10/64 · 07: 54/139 · 08: 15/168 |

`agent_pr_loop` runs this with `--strict` every 5 minutes. It has been exiting 1
continuously — 288 failures a day about a condition no action could clear.

**A gate that cannot be satisfied is not a gate.** It is a generator of pages nobody
can act on, and it trains everyone to ignore the channel that also carries the real
alarms.

A rolling window is satisfiable *by behaviour*: comply for seven days and it clears
itself, with no retroactive edit to immutable history. Nothing is hidden — the
historical count rides along in every report.

## The alarm

Before: `merge audit failed`. No count, no repo, no example, no next step.

After, measured live:

```
merge-audit: 189/217 merges in the last 7d lack a pre-merge 'Merged by' comment
(e.g. RenQuant#582 by haorensjtu-dev). Post it BEFORE merging; it cannot be added
afterwards. [375 historical, not gating]
```

It is still RED, and it should be: 87% of the last week's merges genuinely violate the
policy. The difference is that this red is clearable by behaviour and names who, which,
and what to do.

EVIDENCE:

| claim | value | provenance |
|---|---|---|
| historical compliance | 79 ok / 375 missing of 454 | [VERIFIED — `repos merge-audit --repo all --strict` on the live repos, 2026-08-05] |
| real exit code before | `rc=1` | [VERIFIED — run without a pipe; the first attempt read `tail`'s rc and showed 0] |
| the criterion is achievable | both agents have produced passing markers (69 + 10), most recent 2026-08-04 | [DERIVED — audit JSON author counts] |
| module tests | 59 passed (3 new) | [VERIFIED — `pytest -q tests/test_agent_workflows.py`] |
| the new tests are load-bearing | both gate tests fail against the pre-change module | [VERIFIED — `git show HEAD:…`, re-run] |

## One pre-existing test changed deliberately

`test_audit_merged_prs_summarizes_missing_pre_merge_markers` asserted `ok is False`
for a PR merged 2026-06-09. Under a rolling window that assertion depends on the wall
clock — it would have started passing on its own as the date receded. The measurement
assertions are unchanged; the gate assertion now pins `now` explicitly.

NEXT: the second half of the operator's report — the alarm repeats identically every
five minutes for a standing condition. `ops/liveness_common.py::alert()` has no
suppression, so every caller pages on every run. A `dedup_key` with a recorded
(not silent) skip is the fix, opt-in per caller so nothing is silenced by default.
Separate PR.

NOT DONE, and deliberately: retry. The operator asked for it, and it is the wrong
remedy here — this failure is deterministic (the same PRs fail every run), so retrying
would produce identical failures and multiply the noise. The problem is repetition of
an unchanged verdict, not a transient one.

## Review round 1: the window gate could return a FALSE GREEN

`fetch_merged_prs` returns only the `limit` most recent merges. When a repo merges more
than `limit` times inside the window, every fetched PR lies inside it, the window extends
past what was fetched, and an older in-window violation is invisible — `ok` could read
True while the stated window was never clean.

**A false green on a compliance gate is worse than the permanently-red gate this
replaced: one gets ignored, the other gets believed.**

Coverage is now measured. If no fetched merge predates the cutoff, the window was not
fully seen and the audit **fails closed** with `coverage_note` — "I could not see the
whole window" is a third state, never folded into "the window is clean".

Confirmed live on the first run: `renquant-model` and `renquant-orchestrator` both
tripped it at the old default.

**The finding also corrected my numbers.** The figure in this doc's first version —
189/217 — was itself truncated. With the window fully covered:

| | first (truncated) | corrected |
|---|---|---|
| in-window missing | 189/217 | **261/356** |
| historical missing | 375 | **790** |

`--limit` default 50 → 200, from measurement rather than taste: merges in the last 7d
per repo were model 50+, orchestrator 50+ (both *capped* by the old default, so truly
higher), RenQuant 36, pipeline 36, then 21, 19, 6, 5, 1. 200 clears the busiest with
headroom, and the coverage note still fires if a repo outgrows it — so the number cannot
silently become wrong.

The `--strict` help text now defines the bounded gate, the non-gating historical
measurement, and the coverage failure, instead of claiming every audited miss fails.

## Review rounds 2 and 3: the coverage rule was fail-closed but UNATTAINABLE

Both follow-ups flagged the same defect from different angles, and both are right.
`covered = bool(rows) and oldest < cutoff` asks whether a merge older than the cutoff
was seen. That is not the question. **Only truncation can hide an in-window merge**,
so truncation is what the test must ask about. The old rule called three fully
observed situations "uncovered" and gated them red with no action that could clear it
— reintroducing, in the coverage check, exactly the unclearable gate this change
exists to remove:

| situation | old rule | correct |
|---|---|---|
| fewer rows returned than `limit` (response exhausted) | uncovered | **covered** — nothing older exists to fetch |
| repo with zero merged PRs | uncovered (`bool(rows)`) | **covered** — and clean |
| a merge landing exactly ON the cutoff | uncovered (`<`) | **covered** — the window is inclusive, so it was observed |

That last one had the boundary classified two different ways inside one function:
`merged_at >= cutoff` put the merge *in* the window while `oldest < cutoff` said the
window had not been reached. Now:

```python
exhausted = len(rows) < int(limit)
covered   = exhausted or (oldest is not None and oldest <= cutoff)
```

Three regression tests added — exhausted-but-all-recent, zero-merge repo, and the
cutoff boundary. All three fail against the previous rule [VERIFIED — `git stash push
src/…`, re-run: 3 failed]; the suite is 64 passed.

Live after the fix: `uncovered_windows: []` — every repo is now correctly observed,
and the gate is red on merit rather than on blindness.

```
merge-audit: 264/358 merges in the last 7d lack a pre-merge 'Merged by' comment
(e.g. RenQuant#582 by haorensjtu-dev). Post it BEFORE merging; it cannot be added
afterwards. [793 historical, not gating]
```

[VERIFIED — `repos merge-audit --repo all --strict`, 2026-08-05 12:5x PDT, rc=1 read
without a pipe]. These counts drift upward as merges land; the 261/356 and 790 quoted
above were the same measurement taken earlier the same day.
