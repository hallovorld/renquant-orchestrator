# Progress: VetoWeakBuys r2 evidence script + memo correction

Date: 2026-07-18

## What

- `scripts/vetoweakbuys_smalln_evidence.py`: the seeded, reproducible
  r2 evidence computations behind the approved small-n guard RFC
  (pipeline#204) — mixture Monte Carlo P(all-veto) vs n, 0.50-threshold
  scale-stability + forward-return split, three-rule admission
  comparison. Read-only DB access (mode=ro&immutable=1).
- Correction appendix to
  `doc/research/2026-07-17-vetoweakbuys-smalln-analysis.md`: retracts
  the "essentially deterministic" overstatement (corrected: ~1-in-5 per
  session at n=5 under the fitted mixture); qualitative conclusion
  unchanged. Accuracy in a reviewed ledger over ego.

## Why

Promised in the #204 r2 review round: the design PR cites these numbers;
the reproducible script and the correction belong in the repo where the
memo lives.
