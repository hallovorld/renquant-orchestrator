# L2 bandit backtest — deep record: engine beats champion, floor priced at 2pp

STATUS:    delivered as a research record at the operator's depth standard
           (formal setup, theorem instantiated with this experiment's
           constants, 10 enumerated assumptions, sensitivity, failure modes,
           "what this does not show"). No production surface touched.
           r2 (codex CHANGES_REQUESTED at 7e47b3d, all three findings
           accepted): P0 — the unconstrained Hedge bound never applied to
           the floored recursion; §2 restated as the projected-OMD bound
           against the best comparator IN K = {w_panel ≥ ½} (proof in the
           doc). P1 — hash-pinned input manifest committed; the derivation
           verifies every digest before deriving, fail closed. P2 — the
           staleness rule is singular (7 calendar days), single-sourced in
           data/l2_staleness.py and pinned by a test.

WHAT:      doc/research/2026-08-09-l2-bandit-backtest.md + committed 541-row
           daily CSV (arm returns, hedge book, full weight path) + verifier
           that re-runs the Hedge recursion from the CSV alone (recursion
           matches the committed path to 4e-16) + provenance derivation +
           hash-pinned input manifest (r2) + single-sourced staleness rule
           with its regression test (r2).

WHY/DIR:   Operator: waiting is out, backtests are in; design PRs must be
           deep and scientific. This is L2's empirical companion to the
           merged engine (orch#923): the frozen recursion evaluated over
           point-in-time replay arms on a 541-day dense calendar.

EVIDENCE:  artifact:      committed CSV + verifier output [VERIFIED]:
             hedge  +45.9% / Sharpe 1.33 / maxDD −29.2%
             champion-only +39.2% / 0.87 / −37.6%   (engine +6.7pp, DD −8.4pp)
             uniform +47.9% / 1.49  → THE FLOOR'S PRICE ≈ 2pp/yr, now a
             number rather than a slogan
             regret vs best-in-K comparator 0.0754 vs valid bound 3.443
             (T=541; r2 — the floor confines weights to K = {w_panel ≥ ½},
             so the theorem benchmark is the best fixed mix IN K; regret vs
             the unconstrained best arm, 0.1194, is descriptive only — no
             theorem covers it, counterexample in §2)
             eta sensitivity flat (43.7–46.4% across 0.05–1.0)
           prod or exp:   experiment — replay arms, cost-free paper top-3
                          books, champion is a replay PROXY (assumptions 4–6)
           existing data: supersedes the two broken earlier runs, both kept
                          as failure modes IN the doc: rank-then-filter
                          collapsed the calendar 541→135 (and made every arm
                          spuriously negative); sparse-label scores gave 78
                          scattered days. The dense rescore (652 consecutive
                          days) unblocked the real run.
           best-known?:   yes — first sound evaluation of the L2 engine; also
                          logs a frame-dependence result: mom_fast, harmful
                          in blend-IC space (#913), runs Sharpe 1.33 as a
                          standalone top-3 book — conclusions do NOT transfer
                          between functionals, stated in both directions.
           scope:         research only; deployed engine parameters unchanged.

TESTS:     the verifier recomputes every reported statistic AND the full
           recursion from the committed CSV (max errs 4e-16 / 1e-16);
           tests/test_l2_backtest_staleness.py pins the singular
           7-calendar-day staleness rule, including a date pair where the
           two candidate rules disagree; the derivation refuses to run on
           any manifest digest mismatch (fail closed) and its re-run
           regenerates the committed CSV from the pinned inputs.

NEXT:      cost pass over the arm books (assumption 4 biases toward the
           high-turnover fast clock — required before any cross-arm ranking
           is decision-grade); then the L3 clean-label build (fwd forward
           returns, no pairing).
