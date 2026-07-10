STATUS:   research memo (read-only; no production store touched)
WHAT:     Decision-ledger health check + first gate retro-verification, roadmap P5.
          Deliverable: `doc/research/2026-07-10-ledger-health-first-gate-review.md`
          + reproducible evidence (`doc/research/evidence/ledger_health/`:
          analysis script + JSON snapshot). Health: 5/5 NYSE sessions since the
          07-05 S5 enable recorded (23 runs x 6 gates, no nulls; 5 active-path,
          17 shadow-path, 1 unscoped orphan), but 4 of 6 gate rows carry
          structurally wrong/vacuous inputs (conviction mu_floor read from the
          wrong config path and stamped 0.0; vol/wash read a non-existent
          `ctx.blocked_by` so they can only ever say "none blocked"; rotation
          stamps `halve` on 0-considered). Per-name ledger outcome table absent
          by design until fwd_60d matures (~2026-09-29); interim per-name truth
          is runs.alpaca.db candidate_scores JOIN ticker_forward_returns, which
          is healthy (fwd_1d populating daily) except: `selected` unstamped
          since 07-06, zero candidate rows on 07-08/09, and 07-08/09/10 forward
          rows currently holdings+SPY only (acceptance check set for 07-13).
          Retro (all DIRECTIONAL/LOW-POWER, labeled by maturity): (a) veto
          marginal band (0.5-1.0 sigma) rel_fwd_5d −0.41pp (n=74, hit 41%) vs
          admitted +1.28pp (n=95, 62%) → no earliest-signal case for a 0.5σ
          floor; (b) demean-ON counterfactual would have admitted ≤1 name on
          7/9 XGB-era runs, added 0 ever, and dropped realized 5d SPY-beaters
          (+0.77pp, n=65) → directionally supports the 06-29 revert, formal
          #190 metric still ~Sep; (c) exit verdicts not recorded — 4/5 window
          sells came from monitor runs that never write the ledger. §4 of the
          memo lists 11 concrete automation gaps (A1-A11) blocking a monthly
          mechanical gate scorecard, citing the kpi_2026-07-07.json placeholders.
EVIDENCE: script re-derivation of the veto floor agrees with stamped
          `blocked_by` on 100% of scored name-days (both analysis windows);
          all DB reads via sqlite ro/immutable URIs; ledger row count moved
          136→142 during analysis (live writer) — snapshot pinned in the JSON.
NEXT:     (1) pipeline PR for the A2-A4 stamping fixes (telemetry-only, no
          behavior risk); (2) 07-13 acceptance check on the 07-10 forward-return
          cross-section (86 rows expected, 6 = observer enumeration bug);
          (3) re-run the script 07-17 / early-Aug as 5d/20d mature — tables
          upgrade in place; (4) do NOT re-litigate demean before fwd_60d.
