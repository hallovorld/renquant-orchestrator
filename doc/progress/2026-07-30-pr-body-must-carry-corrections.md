# A correction that lands only in the diff is half a correction (#652)

**Date:** 2026-07-30 · **PR:** hallovorld/renquant-orchestrator#652 · **GOAL-5**

## What shipped

`ops/pr_body_correction_check.py` — if an open PR carries a commit whose subject
**announces a correction**, its body must acknowledge one. Weak on purpose: it
cannot judge whether the acknowledgement is *adequate* and does not try; it closes
the case where there is **none at all**, which is the case that happened six times
on 2026-07-30 (model#129, #648, #646, pipeline#233 caught by review or by hand;
#611 and #594 found only by this tool).

`CORRECTION_IN_COMMIT` deliberately excludes a bare `fix(...)`: fixing a bug is the
normal business of a PR and says nothing about the body. The **first commit** is
excluded too — a PR whose opening commit says "withdraw" is not correcting anything
it previously claimed.

## The correction this PR had to make to itself

Codex review (2026-07-31T00:34Z) found a **fail-open** in the first version, which
is the same shape the tool exists to catch:

> the per-PR detail failure is silently skipped … a partial GitHub outage can
> report clean while omitting exactly the PRs under review.

The list query returns scalars for all open PRs, then commits are fetched one PR at
a time (`gh pr list --json commits` across 100 PRs trips the GraphQL 500,000-node
limit `[VERIFIED — rc=1, 2026-07-31Z]`). A PR whose per-PR fetch raised was
`continue`d — it contributed neither a finding nor a visible gap, and the printed
denominator was the *measured* set, so a half-read run was typographically
identical to a clean one.

**Fixed:**

- Every selected PR gets a **preserved row**, born `UNMEASURABLE`; only a
  successful end-to-end read earns one of `stale_body` / `acknowledged` /
  `no_corrections`. Nothing enumerates the ways a read can fail — the ways it can
  succeed are enumerated instead, so an unanticipated failure lands on
  UNMEASURABLE, never on OK.
- Denominator is now **`measured/selected`**, printed on every line.
- `author` moved into the LIST query. It does **not** trip the node limit
  `[VERIFIED — gh pr list --json number,author --limit 100, rc=0, 2026-07-31Z]`;
  the previous docstring and the PR body both said it did, and that is withdrawn.
  Selection therefore no longer depends on the fetch that can fail: a PR that
  cannot be read can still be placed in or out of scope. If the author field
  itself is absent, scope is undecidable and the row stays UNMEASURABLE rather
  than being dropped as someone else's.
- An empty or missing `commits` payload is UNMEASURABLE, not "no corrections" —
  every PR has at least one commit, so an empty list means the read did not happen.
- **Exit codes:** `0` clean, `1` stale bodies, `2` the list query itself failed,
  **`3` some selected PR could not be read**. `3` takes precedence over `1`: the
  findings are real but they are not the whole answer, and an incomplete run must
  not be handed to a caller as a verdict. Both are nonzero, so `if rc != 0` catches
  either. The one outcome ruled out is a partial read exiting `0`.

## Tests

`tests/test_pr_body_correction_check.py` — 22 tests, `gh` stubbed in-memory, an
autouse fixture turns any unstubbed call into a failure so nothing reaches the
network `[VERIFIED — 22 passed, 2026-07-30]`.

Covered: first-commit exclusion; a later correcting commit **without** a body
acknowledgement → finding; **with** one → not a finding; author filtering;
`author: null` → UNMEASURABLE not dropped; the partial-read path (row preserved,
counted in the denominator, exit `3`); unmeasurable-beats-findings precedence; an
exception type the module has never seen; empty/missing commits payload; all four
exit codes distinct; the list query never asks for `commits` and does ask for
`author`; and that bare `fix(...)` is not matched.

**Mutation-checked, not just asserted:**

| mutant | tests that fail |
| --- | --- |
| `acknowledged = False` (flag everything) | 1 — `test_correcting_commit_with_body_acknowledgement_is_not_a_finding` |
| restore the silent skip on detail failure | 7 |

The first row is the **anti-vacuity control**: without it, a checker that flags
every PR with a later correcting commit passes the stale-body test.

## Real run

```
$ python3 ops/pr_body_correction_check.py --repo hallovorld/renquant-orchestrator
hallovorld/renquant-orchestrator: measured 14/14 selected PR(s); 2 carry a
correcting commit; 0 have a body that never mentions one
$ echo $?
0
```

`[VERIFIED — 2026-07-30 17:4x PDT]`. Read-only: the tool only ever runs
`gh pr list` and `gh pr view`.

## Suite

`make test` → **4659 passed, 1 failed, 2 skipped**. The failure is
`test_run_surface_drift_check.py::TestManifestGeneration::test_committed_manifest_matches_live_surface`,
**pre-existing and unrelated** — it reproduces on the unmodified PR head
`[VERIFIED — 2026-07-30]` and compares the committed launchd manifest against this
machine's live surface (the "tests that measure the operator's disk" shape).
Nothing in this change touches launchd.
