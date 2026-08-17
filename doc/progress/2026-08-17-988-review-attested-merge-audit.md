# orch#988: the approve-and-merge path is audited by its own review record

STATUS:    fix — closes the structural merge-audit gap (84% of codex's merges unmarked)
           without weakening what the audit actually protects. Source-repo change to the
           audit logic, itself going through the normal codex-gated review.

WHAT:      `agent_workflows.py`: a merge now counts as AUDITED by EITHER (a) the existing
           pre-merge `merged by` comment, OR (b) a **review attestation** — the merger's
           LATEST state-changing review (APPROVED/CHANGES_REQUESTED/DISMISSED) submitted
           at/before `mergedAt`, on a PR they did NOT author, has state APPROVED
           (`_review_attestation`; `_MERGE_AUDIT_FIELDS` gains `reviews`). An approval
           the merger later superseded with CHANGES_REQUESTED pre-merge does NOT attest
           (see CORRECTIONS). `status`
           distinguishes `ok` / `review_attested` / `missing_pre_merge_audit` so the two
           records never blur; `audited` is the gate-facing bit; `audit_merged_prs` gates
           the window on `audited` and reports `n_review_attested_in_window`.
           `repos.py`: the summary now says UNAUDITED (neither record) and counts
           attested merges, replacing the unactionable "post it BEFORE merging" advice
           for a path that structurally cannot.

WHY/DIR:   Operator-assigned issue #988. Measured there: 84% of codex's window merges
           carry no marker — structural, not careless: its path approves and merges in
           one action (model#226: APPROVED 21:26, merged 21:26:34, zero comments), and
           the marker convention is satisfiable only on the two-token `agent-workflow
           merge` path. GitHub's own review record on the approve-and-merge path already
           carries what the marker encodes (who, before-merge, counterparty). This is the
           issue's option 2 with the attestation being the ALREADY-EXISTING review — the
           only shape that closes the gap with zero behavior change asked of anyone.
           The gate KEEPS firing on merges with NEITHER record: self-merges can never
           self-attest (author==merger excluded), unreviewed merges still page.

EVIDENCE:
  artifact:      `agent_workflows.py` (+`_review_attestation`, status/gate changes),
                 `repos.py` (summary), `tests/test_agent_workflows.py` (6 new tests) +
                 this doc.
  prod or exp:   neither — audit-logic + tests; no live change, no merge performed, no
                 branch-protection/CODEOWNERS surface touched (the mechanical gate is
                 untouched; this is the observability/queue gate only).
  existing data: [VERIFIED — issue #988's measured window] 32 merges / 14 unmarked;
                 codex 11/13 unmarked vs claude 3/19; model#226 zero-comment
                 approve-and-merge confirmed. [VERIFIED — code] the marker regex +
                 `created_at <= mergedAt` rule make post-hoc marking impossible, so the
                 old gate was structurally unsatisfiable for one of the two paths.
  best-known?:   yes — considered and rejected: option 1 (wrapper posts marker) requires
                 controlling codex's merge tooling, which no surface here does; option 3
                 alone (scope the gate) silences without closing, as the issue itself
                 notes. The attestation is deliberately NARROW (merger==approver,
                 pre-merge, author≠merger) so nothing the old gate caught is lost:
                 marker-less+review-less merges and self-merges still fail. 86/86
                 audit-suite tests pass (80 pre-existing unchanged + 6 new); full orch
                 suite 2126 passed with ONE failure
                 (`test_the_orchestrator_revision_comes_from_THIS_repo_not_the_cwd`)
                 which also — [VERIFIED] — passes on the plain main checkout and fails
                 only under a git-worktree layout: environmental, not from this diff
                 (diff = 3 files, merge-audit only).
  scope:         "changes what the recurring merge-AUDIT accepts as a traceable merge
                 (marker OR the merger's pre-merge counterparty approval). Does NOT touch
                 branch protection, CODEOWNERS, required reviews, or any merge mechanics;
                 does NOT bypass anything — un-reviewed and self-merged PRs still fail
                 the audit. agent_pr_loop heals structurally once deployed (-run sync,
                 operator-gated)."

TESTS:     10 new (6 original + 4 from the review fix, see CORRECTIONS): attestation
           accepted (codex's real shape), self-merge cannot self-attest, post-merge
           approval rejected, CHANGES_REQUESTED / third-party reviewer rejected, marker
           precedence unchanged, gate accepts attested + fires on record-less;
           approve-then-request-changes pre-merge rejected, re-approval after changes
           accepted, post-merge CHANGES_REQUESTED does not revoke, same-second
           supersession deterministic. Original full-suite figures: 2126 passed /
           1 environmental worktree-only failure (verified passing on main checkout);
           re-measured focused results after the review fix are in CORRECTIONS.

NEXT:      codex review (codex is the counterparty whose merges this affects — the right
           reviewer) → merge → -run sync (operator-gated) → agent_pr_loop stops paging on
           the structural misses while continuing to page on genuinely untraceable
           merges. Follow-up (separate, from the issue's 'Related'): the `fixed by`
           sibling marker's literal-string rigidity.

CORRECTIONS (2026-08-17, review fix):
  Codex's MED finding on the initial head (10e82957): `_review_attestation`
  accepted ANY earlier pre-merge APPROVED review by the merger, even when that
  same reviewer later submitted CHANGES_REQUESTED before the merge — an
  explicitly superseded approval still attested. Fixed: the function now
  reduces the merger's state-changing reviews (APPROVED / CHANGES_REQUESTED /
  DISMISSED, mirroring `_effective_reviews_at_head`) to the LATEST one
  submitted at/before `mergedAt` — deterministic ordering by parsed timestamp
  with list position breaking ties — and attests only if that latest state is
  APPROVED. Post-merge reviews stay excluded (they cannot revoke a pre-merge
  attestation).
  Figures reconciled: "6 new tests" → 10 new tests (4 added:
  superseded-approval rejected [failed pre-fix, passes post-fix],
  re-approval-after-changes accepted, post-merge changes do not revoke,
  same-second supersession deterministic [failed pre-fix, passes post-fix]).
  Re-measured [VERIFIED — pytest, this session]:
  `tests/test_agent_workflows.py -k "merge_audit or review_attested"` 12
  passed; `tests/test_agent_workflows.py` 73 passed / 1 pre-existing
  token-environment failure (`test_resolve_token_env_precedence`, present
  before this diff, also called out in Codex's approval note);
  `tests/test_repos.py` 16 passed; `tests/test_cli.py -k merge_audit` 1
  passed.
