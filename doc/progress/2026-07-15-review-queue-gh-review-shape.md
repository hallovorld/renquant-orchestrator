# Fix review-queue predicates: gh review shape, reviewer supersession, head dedup

STATUS: delivered
WHAT: `agent_workflows` queue predicates read each review's commit as
`commit_id`, but `gh pr list --json reviews` (the shape `fetch_open_prs`
returns) nests it as `commit.oid`. Every predicate therefore saw zero reviews
at head: the review queue re-listed already-reviewed PRs forever (6 duplicate
`reviewed by claude` reviews each on RenQuant#479 and strategy-104#58 on
2026-07-15/16 UTC) and the merge queue could never see an approval. This PR
(1) reads both shapes, (2) reduces to the latest state-changing review per
reviewer (GitHub `reviewDecision` semantics — a reviewer's later APPROVED
supersedes their earlier CHANGES_REQUESTED; DISMISSED/COMMENTED never veto),
and (3) skips review-queueing a PR whose current head already carries this
agent's CHANGES_REQUESTED review (author's move; a new push re-opens review).

A first-round fix on this same PR still dropped DISMISSED reviews from the
per-reviewer reduction entirely instead of using them to retract that
reviewer's prior state, so a reviewer's own later DISMISSED never cleared an
earlier CHANGES_REQUESTED (permanent block) or an earlier APPROVED (stale
approval kept counting). It also made `has_unaddressed_findings` reuse the
vote-counting reduction (which correctly excludes COMMENTED from
APPROVE/CHANGES_REQUESTED counting) for findings-scanning too, so a
severity-tagged COMMENTED review silently disappeared from the author's fix
queue. Both are fixed in this round: DISMISSED is now tracked in the
per-reviewer latest-by-submission-time reduction (so a later review from the
same reviewer still supersedes the dismissal) and then filtered out of the
effective list; and `has_unaddressed_findings` adds raw COMMENTED bodies at
head back into its severity-tag scan, on top of the vote-reduced bodies.
WHY/DIR: agent-control workstream — the review/fix/merge control plane must
converge instead of spamming duplicate reviews; approvals must be visible to
the merge workflow so the mechanical gate works as designed.
EVIDENCE: n/a
NEXT: hydrate `files` + `progressDocContent` (and `commits` for the
reviewer-separation guard) in `fetch_open_prs` — today those keys are absent
from `_PR_FIELDS`, so `contract_findings` fail-closed reports
"missing progress doc" for every PR and the branch-identity /
reviewer-separation guards never fire on live data.

## Verification

- `pytest -q tests/test_agent_workflows.py` → 53 passed (50 from the first
  round + 3 new regression tests for the DISMISSED-retraction and
  COMMENTED-findings fixes).
- New regression tests use the real gh-CLI review shape (`commit.oid`,
  `author.login`, `submittedAt`): gh-shape approval detection, non-head
  exclusion, same-reviewer supersession, DISMISSED/COMMENTED neutrality,
  reviewer-side dedup + author-side fix-queue handoff, new-head re-entry,
  operator (marker-less) CHANGES_REQUESTED still queueing a review, a
  reviewer's own DISMISSED retracting an earlier CHANGES_REQUESTED (leaving
  only a still-valid other approval) or an earlier APPROVED (no longer
  counted), and a severity-tagged COMMENTED review still landing in the
  author's fix queue.
- End-to-end against live GitHub data: with this fix on `PYTHONPATH`, the
  review queue drops strategy-104#58 (claude CHANGES_REQUESTED at head →
  author's move) and keeps RenQuant#479 only for its real
  missing-progress-doc finding, instead of re-listing both unconditionally.
