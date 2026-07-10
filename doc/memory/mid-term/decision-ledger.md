# Workstream: S5 decision ledger + mechanical gate scorecard (roadmap P5)

STATUS:   measuring. Verdict ledger live since 2026-07-05 and complete at run grain
          (5/5 sessions, 23 runs x 6 gates); per-name outcome half unwired by design
          until fwd_60d matures (~2026-09-29). First health check + retro done
          2026-07-10. `[VERIFIED — doc/research/2026-07-10-ledger-health-first-gate-review.md]`
GOAL:     a monthly gate scorecard that runs mechanically off the ledger: per-gate
          value-of-information (veto floor, conviction/demean, exits) with maturity
          labels, no hand analysis.
NEXT:     (1) pipeline stamping fixes A2-A4 (conviction mu_floor wrong config path →
          stamps 0.0; vol/wash read non-existent ctx.blocked_by → permanently "none
          blocked"; rotation halve on 0-considered) — telemetry-only PR;
          (2) 2026-07-13 acceptance check: ticker_forward_returns(as_of=07-10) must
          reach ~86 rows, 6 = observer enumeration bug (A9);
          (3) re-run the evidence script as 5d (07-17) / 20d (early Aug) mature;
          (4) per-ticker ledger registry design (A8) — observer must stay sole
          writer of decision_outcomes (#351 poisoning trap).
EVIDENCE: earliest signals, ALL DIRECTIONAL/LOW-POWER: veto 0.5-1.0σ marginal band
          rel_fwd_5d −0.41pp vs admitted +1.28pp (no case for relaxing the floor);
          demean-ON counterfactual admits ≤1 name 7/9 runs, adds 0, drops realized
          5d SPY-beaters (+0.77pp) — supports the 06-29 revert; exits invisible to
          the ledger (4/5 window sells from non-ledger monitor runs).
          `[VERIFIED — doc/research/evidence/ledger_health/ledger_health_2026-07-10.json]`
CONSTRAINT: do NOT re-litigate #145/#190 demean before fwd_60d matures (~Sep);
          scorecard reads must stay ro/immutable; never write production stores.
