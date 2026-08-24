# The attestation verified who and when, never what

STATUS:   delivered. One function + its reporting + tests. Read-only audit
          logic; no gate threshold changed, nothing deployed.

WHAT:     BOTH accepted attestation paths must now identify the merged commit.

          * a REVIEW attests only when `review.commit.oid` == the PR's
            `headRefOid`; otherwise `review_not_bound_to_merged_commit`;
          * a MARKER attests only when the merged `headRefOid` appears in the
            comment body — the convention already writes
            `- Head SHA: <40 hex>`; otherwise
            `marker_not_bound_to_merged_commit`.

          Each near-miss keeps its own status rather than folding into
          `missing_pre_merge_audit`, because "attested to a DIFFERENT commit"
          and "nobody attested at all" are different findings and only one is a
          near-miss. An unbound marker does not veto a review that DID bind —
          the two records stay independent; they simply both have to name the
          commit.

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
  scope:         both attestation paths, and nothing else. The `merged by`
                 convention's FORMAT is unchanged — it already carries the head
                 SHA, so no producer had to change; what changed is that the
                 audit now reads it. Independence of the two records is
                 preserved and tested (an unbound marker does not veto a bound
                 review); sufficiency is not — a record that names no commit no
                 longer audits, on either path. No gate threshold, window or
                 producer was touched.

VERIFICATION:
  83 passed. Mutation-verified per PATH, because closing one and leaving the
  other is exactly what round 2 caught:
    remove the REVIEW binding    -> 2 failed
    remove the MARKER binding    -> 3 failed
    restored                     -> 83 passed
  [VERIFIED 2026-08-24]

  RUN AGAINST REAL MERGED PRs, because a stricter audit that mis-flags honest
  merges is worse than the gap it closes. With BOTH bindings live, the last 40
  merged PRs on this repo score **25 × `ok` + 15 × `review_attested`, ZERO
  unaudited** [VERIFIED 2026-08-24]. Measured before tightening the marker
  path: 26 of 26 markers already contained the head SHA, so nothing existing
  was invalidated. The check tightens without inventing findings.

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
