# Progress: M8 wave-1 NO-GO independent adversarial verification (2026-07-03)

## What

Adversarial independent verification of the M8 cluster wave-1 NO-GO (PR
#261) — the verdict stopped ALL breadth waves, so it was re-derived from
scratch with an independently written harness rather than trusted. Full
memo: `doc/research/2026-07-03-m8-verification.md`; machine evidence:
`doc/research/evidence/2026-07-03-m8-verification/verification_results.json`;
script: `scripts/m8_independent_verification.py`.

## Verdict

**UPHELD.** No bug found. All gate numbers recompute exactly (mean paired
Δ qualifying −0.047666; per-cut, placebo-clean, pooled date-level, fwd_20d
all exact). The NO-GO is robust to training seed (gate −0.0506/−0.0159/
−0.0452 at seeds 42/7/2026 — all fail the −0.010 band), to the qualifying-
cut rule (all 7 alternative inclusions fail), and to implementation
(independent IC/grouping/normalization code; seed-42 cut-5 numbers
reproduce to 6 dp; their own impl reruns committed numbers to 0.000000).
Harness parity with production (`PANEL_LTR_PARAMS`, 100 rounds, E35 CUTS,
158 features) verified byte-for-byte. Selection-window overlap ruled NOT
outcome leakage (features only, never labels; bias direction favors PASS;
worst cut is out-of-window 2025).

## Material correction (interpretive, does not reopen the gate)

A random-wave control (3×100 random candidates, same harness) shows random
names mostly IMPROVE the incumbent-book IC where the similarity-selected
wave degrades it, and random waves fail the gate more narrowly (mean
−0.0185 vs −0.048; one marginal band-pass). The original §4 generalization
("even the most similar names dilute the panel fit") is therefore
inverted: the dilution is specific to the similarity-selected wave, not
generic to breadth. The pre-registered consequence (waves STOP; BR via D3
down-cap) binds procedurally; any future D3 synthesis should cite the
frozen-wave gate failure, not "similarity-proof dilution." Also noted: the
gate statistic carries ~±0.02 seed noise vs a ±0.010 band — under-powered
for marginal outcomes (immaterial here).

## Notes

- All production data read-only; work done in a scratchpad worktree
  (`research/m8-verification`); no git operations in any primary checkout.
- Runtime ~50s (24 XGB trainings) with the umbrella venv.
