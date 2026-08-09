# Capital funnel re-measured; grant package re-ranked

STATUS:    measurement + plan re-scope; read-only; Phase-3 step 8.

WHAT:      doc/research/2026-08-09-capital-funnel-pareto.md — the current
           window's blocker Pareto (3 buys / 41 sessions; rank floor
           2,390; BULL_CALM admission 1,155; qp threshold 12.6pp Kelly),
           the staleness of the July diagnosis, the #942 root-cause link,
           and the visible re-scoping of step 9 behind #942.

WHY/DIR:   The operator's Phase-3 asked for the deployable-cash
           simulation; the accounting pass found the binding constraint
           moved since July — and bottomed out in the zero-admissible
           served model (#942). Simulating switch relaxations before #942
           would be theater.

EVIDENCE:  artifact:      the Pareto table [VERIFIED — runs DB, 41 live
                          sessions]; artifact stamps [VERIFIED — prod
                          panel JSON read]; 3 buys / 5,040 blocks.
           prod or exp:   read-only measurement
           existing data: entirely
           best-known?:   yes — §5 states what is NOT shown (per-gate
                          relaxation P&L needs a post-#942 backtest)
           scope:         GRANT PACKAGE, re-ranked (operator's single
                          decision list):
                          1. #942 fork: (a) repair retrain/promote until
                             a monotonicity-passing model serves, or
                             (b) review the monotonicity bar; EITHER plus
                             the one-line promotion refusal for
                             zero-admissible stamps.
                          2. #941: stamp binding cutoffs into promote
                             receipts (review-sized fix).
                          3. (demoted) fractional/one-share switches,
                             wash-sale floor confirmation, alerts.py sync,
                             L2 shadow job, sigma* — all still wanted,
                             none capital-critical this window.

TESTS:     none — measurement; every number re-runnable read-only.

NEXT:      operator picks the #942 fork (the only decision that unblocks
           the book); per-gate relaxation backtest follows a serving,
           buy-admissible model.
