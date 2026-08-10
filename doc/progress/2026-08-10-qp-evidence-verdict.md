# qp evidence official verdict: PASS — the 05-23 condition is met under the frozen prereg

STATUS:    the official execution of the merged freeze (orch#955) on
           the merged runner (orch#956) against adjudicated artifacts
           (model#221 + #222 stamps ruling). Verdict authority per the
           freeze; publication batch.

WHAT:      doc/research/2026-08-10-qp-evidence-verdict.md — PASS:
           898/1,357 realized days (floor 700), mean +0.0981σ/day vs
           bar 0.0658, CI [+0.0139, +0.1782] excludes 0, oracle +3.341
           sane. Three-run trail recorded in full (run 1 void: cadence
           defect; run 2 void: non-compliant stamps, HELD unpublished
           and disclosed pre-ruling on model#222; run 3 official).
           Evidence files are the merged runner's verbatim outputs
           with every pin asserted at runtime.

WHY/DIR:   Task #24 (G-E): the recorded re-enable condition for
           qp_min_invested_pct is MET under the reviewed
           reinterpretation. §6 deliverable follows as a separate
           strategy-104 PR through review; machine deployment stays a
           separately granted step. 459 gate-starved days (33.8%) are
           the measured decision input for the #942 fork.

EVIDENCE:  artifact:      doc/research/data/2026-08-10-qp-evidence_daily.csv +
                          …_coverage.csv + …_summary.json [VERIFIED —
                          run 2026-08-10 on adjudicated main, exit 0,
                          committed files are the verbatim outputs]
           prod or exp:   read-only measurement; no production surface
                          touched
           existing data: freeze #955; runner #956; artifacts model#221
                          + #222; pre-verdict P0 sweep (#817 cleared)
           best-known?:   yes — §3 states what PASS does NOT mean
                          (gross/selection-level/pre-sizing; no gate
                          change; no auto-deployment)
           scope:         verdict note + 3 evidence files + this doc;
                          the knob PR is a SEPARATE deliverable

TESTS:     make test not run — docs+evidence only; the runner's 15
           committed controls passed in orch#956; official run exit 0.

NEXT:      (a) strategy-104 qp_min_invested_pct PR citing this verdict;
           (b) #942 fork decision input posted; (c) memory + #954
           closure updates.
