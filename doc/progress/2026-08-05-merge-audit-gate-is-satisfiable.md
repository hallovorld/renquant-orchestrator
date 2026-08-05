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
