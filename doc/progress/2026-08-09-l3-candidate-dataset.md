# L3 candidate-level training dataset — the prescribed construction, built

STATUS:    delivered for review. Read-only over the runs DB; writes one CSV +
           manifest wherever pointed. No production surface.

WHAT:      src/renquant_orchestrator/l3_candidate_dataset.py + 3 tests. One
           row per (run_date, ticker) from each date's WIDEST candidate run;
           label = market forward return at the score date (fwd_20d primary —
           declared frozen horizon; fwd_60d carried for the 60d thesis);
           NO pairing, therefore NO lot ambiguity by construction — exactly
           the construction the paired audit's refusal message prescribes.

WHY/DIR:   The paired audit measured 99.7% lot ambiguity and refuses to serve
           training labels. The meta-label filter needs candidate-level rows
           (names the panel scored and did NOT act on are the abstention
           context), acted/not-acted as COLUMNS (selected, blocked_by), and
           run provenance as a COLUMN (run_type) — never filter defaults.

EVIDENCE:  artifact:      real-DB build this session [VERIFIED — module
                          stdout]: 7,167 rows / 523 dates; 1,275 candidates
                          without a forward row EXCLUDED AND COUNTED;
                          run_type split live 2,189 / sim 4,978; selected
                          136; base win rate (fwd_20d>0) 0.6311
           prod or exp:   experiment — read-only
           existing data: no candidate-level labelled dataset existed; the
                          paired CSV is a descriptive audit only
           best-known?:   yes — first valid L3 training input. Regime joins
                          from live_state_snapshots with regime_source =
                          snapshot|absent (an absent join is recorded, never
                          invented).
           scope:         orchestrator module + tests. Canonical path
                          resolution; widest-run-per-date stated; sim
                          cross-sections are 1-13 names/day in 2024-25, so
                          n_candidates_that_date is a row column for explicit
                          width flooring by consumers.

TESTS:     3 passed — widest-run selection + label join + exclusion count;
           absent-regime recorded not invented; CLI empty-refusal + manifest.

NEXT:      the L3 classifier experiment on this dataset (small model,
           provenance-explicit training choice, evaluated against the 64
           honest trade_evaluations rows and shadow-first per the design).
