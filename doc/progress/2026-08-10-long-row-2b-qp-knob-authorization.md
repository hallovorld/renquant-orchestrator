# LONG row 2b — operator authorization for the qp knob production-config write

STATUS:    LONG-ledger transcription of an operator decision (C4);
           unblocks the s104#97 governance BLOCKER.

WHAT:      Row 2b added to doc/memory/long-term-agreements.md,
           following the row-2a template: verbatim operator directive
           (2026-08-10, this session), exhaustive scope (exactly
           s104#97's two knobs + reason string across the 11 profiles),
           basis (orch#957 PASS with its numbers), explicit
           non-authorization of deployment (pin sync = the operator's
           separate step-② "开"), expiry-on-merge, and the row-2a
           countersignature convention (Codex audit-record on the PR
           thread, since Claude shares the hallovorld login).

WHY/DIR:   The s104#97 review correctly blocked on the control
           contract: a production-config write requires an
           operator-authored LONG row (row 2 protects auditability).
           The operator issued the directive this session; this PR is
           its transcription. After this merges, s104#97 re-review is
           requested citing this row.

EVIDENCE:  artifact:      the row-2b diff in this PR
           prod or exp:   ledger transcription; no production surface
                          touched by THIS PR
           existing data: orch#957 (merged verdict), s104#97 (the
                          authorized PR), the row-2a precedent format
           best-known?:   yes — the row states what it does NOT
                          authorise (deployment) and its expiry
           scope:         one ledger row + this progress doc

TESTS:     none — ledger text.

NEXT:      merge → re-request s104#97 review citing row 2b → after #97
           merges, await the operator's "开" for the landing batch.
