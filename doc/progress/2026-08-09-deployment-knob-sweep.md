# Deployment-knob sweep: λ is dead; min_invested × turnover cap are the levers

STATUS:    measurement; read-only; the last Phase-3 evidence item.

WHAT:      doc/research/2026-08-09-deployment-knob-sweep.md + committed
           derivation (run-scoped copy of scripts/poc_lambda_sweep.py
           with three repairs, each stated) + raw JSON. λ has zero effect
           at any value in any scenario; min_invested flips deployment
           0.706→1.0; turnover cap paces it monotonically; every
           post-05-21 run is unusable for the sweep (orch#931 sigma
           drift) — 4 usable runs, 2026-05-18..21.

WHY/DIR:   #942's final-layer framing said λ=0 was the lock; measured:
           the lock is qp_min_invested_pct=0 alone — VISIBLE CORRECTION
           posted to #942. The 05-23 re-enable condition (WF alpha
           evidence) still governs; this sweep prices mechanics only.

EVIDENCE:  artifact:      doc/research/data/2026-08-09-deployment-knob-sweep.json
                          [VERIFIED — 4 runs × 3 scenarios × 5 λ × 4
                          tcaps; deployed identical across λ everywhere];
                          derivation committed beside it with the three
                          repairs in its header.
           prod or exp:   read-only; DB mode=ro; nothing served
           existing data: the committed poc_lambda_sweep script + its
                          test suite (mechanical-null/positive-control)
           best-known?:   yes — scope note verbatim from the script; the
                          May-only evidence window is stated as the
                          orch#931 consequence, not hidden
           scope:         no config change proposed HERE; the proposal
                          shape (min_invested restored + tcap 0.2-0.3)
                          activates only when the 05-23 evidence
                          condition is met via the task #26 chain.

TESTS:     the committed poc test suite covers the mechanism
           (test_poc_lambda_sweep.py); the run-scoped repairs are guards
           and selection only.

NEXT:      producer fix for orch#931 (hard prerequisite for current-data
           evidence) → task #26 same-source chain → WF alpha evidence for
           the served blend → the one-knob-pair strategy-104 PR.
