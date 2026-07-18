# Progress: VetoWeakBuys small-n analysis (read-only)

Date: 2026-07-17

## What

Evidence memo for the VetoWeakBuys small-sample defect
(`doc/research/2026-07-17-vetoweakbuys-smalln-analysis.md`): on both
governed-override sessions (07-16, 07-17) the adaptive mean+1σ buy floor
exceeded the maximum candidate score at n=5 and vetoed 5/5, freezing the book
at ~86% cash while vetoed ATI outscored held GRMN.

## Findings

- All-vetoed sessions since 04-22: 05-04 (n=43), 05-06 (n=45), 07-16 (n=5),
  07-17 (n=5). Monte Carlo: P(all-veto) ≈ 20% at n=5 iid, near-deterministic
  with the real bimodal stock+ETF scan sets.
- Era-wide marginal counterfactual (16–18 sessions, top-3 vetoed vs admitted,
  session-paired bootstrap): NULL at all horizons — no evidence the floor
  misbehaves at normal n. Fix must be surgical to the small-n branch.
- Recommended: minimum-n guard (N0=10) with absolute calibrated fallback
  (0.50), fail-closed to status quo without config; plus a sentinel LOUD rule
  for `all-vetoed AND n < N0`. Full AC6 HARD-gate framing in the memo.

## Boundaries respected

Read-only DB/parquet access; no strategy/pipeline/config changes; the fix
itself is a separate design PR in renquant-pipeline (task owner).
