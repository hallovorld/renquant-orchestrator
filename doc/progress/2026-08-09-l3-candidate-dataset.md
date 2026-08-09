# L3 candidate-level training dataset — the prescribed construction, built

STATUS:    delivered for review. Read-only over the runs DB; writes one CSV +
           manifest wherever pointed. No production surface.

WHAT:      src/renquant_orchestrator/l3_candidate_dataset.py + 5 tests. One
           row per (run_date, ticker) from each date's WIDEST candidate run
           (equal-width ties: latest created_at wins — the canonical same-day
           run, the same dedup rule as the M3 haircut replay; exact
           created_at ties fall to the latest run_id — a total order);
           label = market forward return at the score date (fwd_20d primary —
           declared frozen horizon; fwd_60d carried for the 60d thesis);
           NO pairing, therefore NO lot ambiguity by construction — exactly
           the construction the paired audit's refusal message prescribes.

WHY/DIR:   The paired audit measured 99.7% lot ambiguity and refuses to serve
           training labels. The meta-label filter needs candidate-level rows
           (names the panel scored and did NOT act on are the abstention
           context), acted/not-acted as COLUMNS (selected, blocked_by), and
           run provenance as a COLUMN (run_type) — never filter defaults.

EVIDENCE:  artifact:      real-DB build, post-tie-break [VERIFIED — module
                          stdout, review-fix session]: 7,167 rows / 523
                          dates; 1,275 candidates without a forward row
                          EXCLUDED AND COUNTED; run_type split live 2,189 /
                          sim 4,978; selected 135; base win rate (fwd_20d>0)
                          0.6307
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

TESTS:     5 passed — widest-run selection + label join + exclusion count;
           equal-width tie-break regression guard (fails on the pre-fix
           module [VERIFIED — stash run]); equal-created_at run_id
           total-order guard (fails on the pre-r3 module [VERIFIED — this
           session, run before the module fix]); absent-regime recorded not
           invented; CLI empty-refusal + manifest.

CORRECTION (review r1, Codex MED): the initial build had NO tie-break on
           equal-width same-date runs — SQLite group order silently picked
           an arbitrary run on tied dates (reviewer measured 154 tied dates,
           127 with materially different payloads). Fixed: ties now break to
           the latest created_at (canonical rule per
           doc/research/2026-07-02-m3-haircut-replay.md). Effect measured
           this session [VERIFIED — read-only re-derivation]: 109 of 541
           candidate-bearing dates now resolve to a later canonical run than
           the pre-fix selection; manifest deltas vs the figures previously
           stated here: selected 136 → 135, base win rate 0.6311 → 0.6307
           (rows / dates / exclusions unchanged: 7,167 / 523 / 1,275).

CORRECTION (review r3, Codex P1): the r1 fix comment and this doc claimed a
           run_id "final total-order guard" that the code did NOT have — the
           comparison sliced run_id away ([:2]), so equal-width runs with
           EQUAL created_at would still resolve by SQLite iteration order.
           Fixed: the selection now compares the full (count, created_at,
           run_id) tuple, and a distinct fixture pins the equal-created_at
           case (latest run_id wins, carrying its payload; fails pre-fix
           [VERIFIED — this session]). The duplicate
           test_equal_width_tie_breaks_to_latest_created_at definition —
           which Python silently overwrote, holding collection at 4 — was
           renamed into that fixture; collection is now 5. Real-DB effect:
           NONE — manifest re-measured after the fix [VERIFIED — module
           stdout, this session]: 7,167 rows / 523 dates / 1,275 excluded /
           live 2,189 / sim 4,978 / selected 135 / win rate 0.6307,
           identical to the r1 figures (consistent with the reviewer's
           read-only audit of 0 exact-created_at ties on the current DB).

NEXT:      the L3 classifier experiment on this dataset (small model,
           provenance-explicit training choice, evaluated against the 64
           honest trade_evaluations rows and shadow-first per the design).
