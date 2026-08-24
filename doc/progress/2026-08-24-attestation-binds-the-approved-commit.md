# The attestation verified who and when, never what

STATUS:   delivered. One function + its reporting + tests. Read-only audit
          logic; no gate threshold changed, nothing deployed.

WHAT:     `_review_attestation` now requires the attesting review's
          `commit.oid` to equal the PR's `headRefOid`. A review that cannot be
          bound to the merged commit is reported as
          `review_not_bound_to_merged_commit` — a status of its own, not folded
          into `missing_pre_merge_audit`.

WHY/DIR:  orch#991, my own deferred finding from the #989 review — raised then,
          not blocked on, recorded as a decision rather than left to be
          discovered. The gap:

              1. codex APPROVES head A
              2. the author force-pushes head B — no new review
              3. codex merges B

          The merger's latest state-changing review at/before `mergedAt` is
          APPROVED, so the audit reported `review_attested`. Its commit was A.
          **Nobody approved B.** Reachable on this repo specifically because
          `require_last_push_approval` is FALSE here — measured, and per-repo,
          not a family constant.

          This is the "digests verify identity, not validity" shape one level
          up: the record was real, the parties were right, the ordering was
          right, and it attested to a different object than the one that
          landed.

EVIDENCE:
  artifact:      src/renquant_orchestrator/agent_workflows.py
                 (`_review_attestation`, `merge_audit_status`) and
                 tests/test_agent_workflows.py.
  prod or exp:   neither — the audit reads GitHub records and returns a status.
  existing data: everything needed was ALREADY fetched — `headRefOid` is in
                 `_MERGE_AUDIT_FIELDS` and `reviews[].commit.oid` is in the
                 payload `gh` returns [VERIFIED: `gh pr view 1035 --json reviews`
                 → `{"commit":{"oid":"c778426b…"},"state":"APPROVED"}`]. The
                 function simply never read either.
  best-known?:   yes, and the near-miss is reported SEPARATELY on purpose.
                 Collapsing "approved a different commit" into "nobody
                 reviewed" would hide the one case that is a near-miss rather
                 than an absence — and hiding it is what #991 is about.
  scope:         the attestation path only. The `merged by` comment convention
                 is untouched and still audits independently; a test pins that
                 a marker audits even when the approval bound elsewhere,
                 because the marker is its own attestation.

VERIFICATION:
  80 passed. Mutation-verified per property:
    drop the commit comparison (restore the original gap)  -> 2 failed
    let a MISSING commit pass as an attestation            -> 2 failed
    restored                                               -> 80 passed
  [VERIFIED 2026-08-24]

  RUN AGAINST REAL MERGED PRs, because a stricter audit that mis-flags honest
  merges is worse than the gap: the last 12 merged PRs on this repo score
  8 × `review_attested` + 4 × `ok`, **zero** `review_not_bound_to_merged_commit`
  [VERIFIED]. The check tightens without inventing findings.

  The fixture change is the quiet half. `_merged_pr_with_review` built reviews
  with no `commit` key at all — but a real `gh --json reviews` payload ALWAYS
  carries one. That fiction is precisely why the gap could exist with a green
  suite: no test could distinguish "approved this commit" from "approved
  something". The fixture now models the real shape.

## Review round 2 (codex) — I closed one path and CODIFIED the hole on the other

The first pass bound the review path and left the marker path exactly as it was,
and my own test said so out loud:
`test_a_pre_merge_MARKER_still_audits_regardless_of_the_commit_check`. Post the
marker, force-push B, merge B — a plain timestamped comment still returned `ok`.

I justified it as "the two records never blur". That is true about their
INDEPENDENCE and wrong about their SUFFICIENCY: a comment that names no commit
cannot attest to one, however independent it is. Writing a test around the
wrong half of a true sentence is how a hole gets a green tick.

The convention already carries what was missing — markers state the head
explicitly:

    - Head SHA: `259900e331e25322e260cbbbcaf1d74f3b10508a`

So a marker attests only when the merged `headRefOid` appears in its body, the
same rule as the review path, reading data that was already there. MEASURED
BEFORE TIGHTENING: **26 of 26** markers across the last 40 merged PRs already
contain the head SHA, so nothing existing is invalidated.

Unbound markers get their own status, `marker_not_bound_to_merged_commit`, and
an unbound marker does NOT veto a review that DID bind — the records stay
independent, they simply both have to identify the commit.

  Mutation-verified per path: removing the marker binding -> 3 failed; removing
  the review binding -> 2 failed; restored -> 83 passed.

  Against 40 REAL merged PRs after both tightenings: 25 `ok` + 15
  `review_attested`, **zero unaudited** [VERIFIED 2026-08-24].

  The fixture story repeated exactly: marker fixtures carried no head SHA while
  every real marker does, which is why the marker hole also had a green suite.
  Eight existing tests went red on the first run for that reason alone.

NEXT:     Not attempted here: `require_last_push_approval = true` would close
          the same hole at the platform level for this repo, and is a branch
          protection change with its own review. This audit stays useful either
          way — it is the record that a merge WAS bound, not the mechanism that
          forces it.
