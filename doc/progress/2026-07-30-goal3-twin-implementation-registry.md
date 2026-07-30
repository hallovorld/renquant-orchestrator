# Progress: register the seven twin-implementation sites (PR #623)

STATUS:   delivered. Registry only — no code, config, pin, or artifact changed.
          This entry covers the fixed-by-claude round addressing codex's
          CHANGES_REQUESTED review (missing progress doc; untagged claims).

WHAT:     Added `doc/arch/twin-implementation-registry.md` — a GOAL-3
          audit-and-register deliverable cataloguing seven sites (R1-R7) where
          two-or-more copies of the same logic exist and the copy that RUNS
          differs from the one a reader would find first. Each row states
          which copy runs, how that was identified, the cost of getting it
          wrong, and (where resolved) the fix.

          Fix round: added a provenance tag to every flagged numeric/assertive
          claim per `doc/memory/long-term-agreements.md` item 10, corrected
          the one invalid tag shape (`[VERIFIED-prior]` ->
          `[VERIFIED — prior work, <ref>]`), narrowed R3's "bit-identical"
          clause to what its cited source actually proved (a two-way
          stamping-branch-vs-`origin/main` check, not an independent
          three-way trainer reproduction), and fixed an unrelated garbled
          character in R6's cost line ("Only<CJK> out" -> "Only laying out").

WHY/DIR:  GOAL-3 is audit-and-register and had zero deliverables this session
          before this PR. Four of the seven rows record a defect filed or a
          fix written against a copy that does not run — the registry's point
          is that nothing in the repo states which copy executes, so this is
          the durable record that closes that gap.

EVIDENCE: This document asserts no new facts — every row cites the issue/PR/
          progress-doc where the underlying number was actually measured.
  artifact:      `doc/arch/twin-implementation-registry.md` (this PR).
  prod or exp:   n/a — documentation only; no code, config, or artifact path
                 touched.
  existing data: yes, all seven rows are backed by already-merged prior work,
                 confirmed by reading each source this round:
                   R1 -> renquant-pipeline#222
                   R2 -> renquant-base-data#55
                   R3 -> renquant-orchestrator#620 (booster-identity check);
                         `train_gbdt.py:228` / `train_production_model.py:58`
                         read directly this session to confirm the file:line
                         claims
                   R4 -> renquant-orchestrator#620
                   R5 -> RenQuant#544, RenQuant#546
                   R6 -> RenQuant#547
                   R7 -> renquant-pipeline#227,
                         `doc/progress/2026-07-29-wash-sale-block-starves-deployment.md`
  best-known?:   yes for the citations added — each is the PR/issue/doc that
                 actually made the measurement, not a reconstruction. R3 is
                 explicitly narrowed rather than overstated: orch#620 proves
                 the stamping change left the booster byte-identical, not a
                 three-way comparison against the other two trainers, and the
                 doc now says so `[ASSUMED — inferred from orch#620's
                 booster-identity methodology]`.
  scope:         `renquant-orchestrator` only — one doc file plus this
                 progress doc. No pin, config, or code path touched in any
                 repo. `[VERIFIED — each row's citation read directly this
                 session: renquant-pipeline#222/#227, renquant-base-data#55,
                 renquant-orchestrator#620, RenQuant#544/#546/#547,
                 doc/progress/2026-07-29-wash-sale-block-starves-deployment.md]`

NEXT:     Per-row remediation, per the doc's own retirement criteria (an
          executable pointer, a parity test, a single source for role
          assignment, a reachability assertion). Each row's fix has a
          different owner and blast radius; R5 in particular changes what the
          daily run trains on and needs its own reviewed PR, not a follow-up
          here.
