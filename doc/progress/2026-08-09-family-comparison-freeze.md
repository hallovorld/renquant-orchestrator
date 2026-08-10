# Design freeze: served blend vs WF-recipe xgb, realized 5d outcomes

STATUS:    design freeze, pre-outcome; no computation run; task #26 next
           increment.

WHAT:      doc/design/2026-08-09-family-comparison-freeze.md — every
           choice fixed before the outcome join: window 05-20..07-31
           (last date whose fwd_5d realizes inside the extension build),
           arms = live-recorded panel_score (the #949/#950-verified
           record) vs the frozen v2 harness fold-8 xgb_mom score — the
           mean of the three boosters from the harness's frozen seed
           tuple (42, 43, 44) (train ≤ 2025-12-31, no leakage into the
           window), per-day
           intersection universe with #950-style coverage accounting,
           k=5 only, outcome = top-k mean fwd_5d_excess minus the
           intersection mean, stationary bootstrap (5/2000/99) on daily
           arm differences, NO verdict authority, no sweeps, post-merge
           edits void the freeze.

WHY/DIR:   The serving-fidelity cells (orch#948/#949/#950) validated the
           RECORD; the operator's question "which family should the
           machine serve" now needs realized outcomes on the same days
           and names. Freezing first prevents the garden of forking
           paths on a comparison that feeds (diagnostically, not as a
           gate) the qp re-enable evidence chain — the 05-23 recorded
           condition. The runner is a follow-up PR bound to this
           document (§5 freeze surface: harness constants ast-read,
           corpus pin asserted, verbatim evidence outputs).

EVIDENCE:  artifact:      the design document only; no numbers produced
           prod or exp:   none run
           existing data: window bounds derive from orch#948 (extension
                          build edge 08-07; fwd_5d coverage 8,771 rows);
                          arm identities from model#213 (frozen harness)
                          and the #949/#950-verified live record
           best-known?:   yes — §4 lists the deliberate exclusions (no
                          k/horizon sweeps, no 60d until labels exist,
                          no P&L, panel-family arm = separate design)
           scope:         one design doc + this progress doc

TESTS:     none — docs only.

NEXT:      runner PR bound to §5 (separate, after this merges); outcome
           table published with the #950 coverage discipline.
