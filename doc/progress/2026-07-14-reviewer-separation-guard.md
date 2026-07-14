# Reviewer Separation Guard

STATUS: revised for review

WHAT: The agent review queue now separates two attribution signals. It excludes
the current GitHub actor and rejects its approval after an explicit
`fixed by <github-login> (agent: <agent>)` marker, while retaining GitHub
mixed GitHub commit attribution as a merge-blocking branch-identity violation.

WHY/DIR: GitHub prevents a PR creator from approving its own PR, but it does not
prevent a reviewer from approving a peer-authored PR after directly modifying
that branch. The earlier guard treated GitHub co-author attribution as an
advisory warning and also instructed agents to add co-author trailers. That
creates a structurally mixed-identity branch, which can no longer support an
independent approval/merge decision. The corrective policy is simpler: one PR
branch has one GitHub identity, reviewers never push peer branches, and the PR
owner rebuilds any mixed branch from a clean target-base history.

EVIDENCE: focused tests cover explicit-fix queue exclusion, rejection of an
explicit contributor approval, and single-owner branch identity. A live queue
must surface mixed commit attribution under `branch_identity_violations` and
exclude it from merge eligibility.

NEXT: Claude should challenge the explicit-marker compliance path and confirm
that direct `gh pr review` / `gh pr merge` invocations perform the same check.
After independent review, configure the matching rule in any external agent
runner that bypasses `repos agent`.
