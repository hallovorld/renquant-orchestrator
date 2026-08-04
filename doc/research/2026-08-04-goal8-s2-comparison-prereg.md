# GOAL-8 S2 preregistration — the three-lane comparison (FROZEN ON MERGE)

STATUS: FROZEN ON MERGE, deliberately BEFORE the S1 lane's first session,
so no arm's outcome exists when the criteria are set. Amending any FROZEN
section after the S1 clock starts voids S2 and restarts its window.
S2 is the RETURNS rung of the GOAL-8 ladder (S1 = operational
reliability, its own frozen prereg orch#777); S2's verdict gates S3 (MoE)
and S4 (capital sleeve, operator quota sign-off).

## Arms

| arm | source of record |
|---|---|
| PROD (reversal/panel, the served model) | prod runs.db (`candidate_scores`) |
| MOMENTUM-alone (slow v0, weekly ledger) | the in-process momentum shadow lane's identity-stamped records |
| S1 BLEND (z(prod)+z(momentum)) | the S1 e2e lane's runs db (`runs.alpaca_shadow_blend_mom.db`, `candidate_scores`) |

## FROZEN primary metric (score-level — the only layer all three arms share)

Measured 2026-08-04: prod records trade+score level; momentum-alone
records SCORE level only (no e2e lane); the blend lane records
trade+score. Therefore the PRIMARY comparison is fixed at score level:

- Per session and arm: the arm's TOP-3 names by that arm's own score
  (ties broken by lexicographic ticker, deterministic).
- Outcome per name: next-session simple return from the shared
  `ticker_forward_returns` surface (the same join for every arm; a name
  with no forward return recorded is EXCLUDED from that session's basket
  for EVERY arm — never imputed).
- Per-session arm value: equal-weight mean of the basket's returns.
- Window: the SAME 20 scheduled sessions as the S1 operational window
  (from the S1 deployment boundary, every scheduled session counting).
  Sessions where an arm has no record contribute NO basket for that arm
  and are tallied as that arm's MISSING count (S1 already counts them as
  not-green; S2 does not re-litigate).

## FROZEN comparison + verdict rule

After the 20 sessions, compute per arm: mean per-session basket return,
its sign, and the pairwise session-matched differences (blend − prod,
blend − momentum, momentum − prod) over sessions where BOTH arms of a
pair have baskets.

- **PROMOTE-interest verdict** (feeds S3/S4 consideration, licenses
  nothing by itself) requires ALL of:
  (a) blend's session-matched mean difference vs PROD is positive;
  (b) blend's missing count ≤ 1;
  (c) MINIMUM MATCHED-PAIR COVERAGE — both the blend-vs-PROD and the
      blend-vs-momentum pairs have ≥19 matched sessions out of 20. A
      positive mean over an arbitrarily small matched set is not a
      comparison at the declared sample size `[codex on orch#781]`: if
      EITHER pair's coverage misses the threshold, the outcome is the
      EXTENSION (if unused) or the explicit verdict
      "INSUFFICIENT RECORD — no promotion interest", never promotion.
- **STOP verdict**: blend's session-matched mean difference vs BOTH
  single arms is negative → the ladder pauses at S2 and the result is
  published as a negative finding.
- Anything else → EXTEND once by 20 more sessions (one extension max,
  declared here; a second inconclusive window closes the ladder rung as
  "no detectable blend advantage at this sample size"). The coverage
  threshold applies unchanged in the extension window; a second coverage
  miss closes the rung as INSUFFICIENT RECORD.
- NO significance theater at n=20: means and signs are reported with
  per-session tables; no t-statistics are quoted on single-digit
  effective samples (borrowed-critical-values lesson). The verdict rule
  above is deliberately ordinal.

## FROZEN placebo/context arms (reported alongside, never gating)

- SHUFFLED-BASKET placebo: per session, 3 names drawn uniformly (seeded
  by session date, seed recipe fixed here: sha256 of the ISO date string,
  first 8 hex as int) from that session's prod-scored universe — controls
  for market drift in the window.
- The qp-live-shadow divergence record (incumbent vs candidate) is
  attached as context if present; it gates nothing.

## Measurement mechanics (declared now so the window needs no decisions)

- The readout is a one-shot script run AFTER session 20; it reads only
  persisted records named above; it is written and reviewed DURING the
  window but may not run against real records before session 20
  (positive-control fixture runs are required and exempt).
- All three arms' record surfaces already exist (measured 2026-08-04);
  no new serving surface is created for S2.

## What S2 does NOT do

No capital, no promotion, no MoE weights (S3 has its own prereg with
placebo arms per AC3), no per-name attribution claims, no retroactive
window selection. The 20 sessions are whatever the calendar delivers.
