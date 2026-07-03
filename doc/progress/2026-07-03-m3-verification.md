# Progress: M3 haircut verdict independent adversarial verification

DATE: 2026-07-03
BRANCH: `research/m3-verification`
SCOPE: read-only verification study; no config or behavior change.

## What

Adversarial independent recomputation of the merged M3 uncertainty-haircut
AC-FAIL verdict (`doc/research/2026-07-02-m3-haircut-replay.md`), which
blocked the `mu - k*SE > floor` config change. Own code end to end: own SQL
+ dedup, own SE-proxy implementation, outcomes recomputed from ohlcv
parquets (not trusted from `ticker_forward_returns`), exact-enumeration
bootstrap (the 8-date block-5 bootstrap has only 64 possible resamples),
permutation + cluster inference, and the positive/null controls the
original lacked. All data read-only (`mode=ro`).

## Result — WEAKENED

- **"Actively harmful at k=1.0/20d" (CI excluding 0): OVERTURNED as
  statistics.** Point estimate reproduces exactly (delta −0.51 pp,
  28W/22L removed; their MC CI reproduced to 1e-15), but the significance
  event rests on 1 atom of 64, and a null control shows the block-5 CI
  machinery fires on the harm side 28.4% of the time under a no-effect
  null (nominal 2.5%). Calibrated permutation test: p = 0.31. i.i.d.
  anchor: |t| = 0.87. One-of-six cells nominal at p = 0.031 vs Bonferroni
  0.0083. Three defensible one-knob reconstruction variants kill nominal
  significance; the delta's SIGN is negative in all 15 variants.
- **"Not demonstrably helpful" / AC-FAIL / config stays blocked: UPHELD.**
  No variant, horizon, k, or inference engine shows the haircut helping;
  thin-margin composition reproduces exactly (share drops only to
  20-24%); the OXY/GRMN SE-undefined fixture hole stands.
- **Positive control** (planted "high-dispersion names are losers", real
  noise scales): machinery detects an 8 pp planted gap at 89% power, but
  at the 2 pp claimed-effect size detection is 35.6% vs ~30% false-positive
  rate — likelihood ratio ~1.2; the sample is uninformative at that size.
- Data integrity confirmed: `ticker_forward_returns` matches parquet
  close-to-close recompute on all 191 universe rows (0 label flips); SE
  values match the original on all 1,769 rows.

## Files

- `scripts/m3_independent_verification.py` — the harness (~9 s runtime).
- `doc/research/2026-07-03-m3-verification.md` — full memo + per-check table.
- `doc/research/evidence/2026-07-03-m3-verification/m3_verification.json`.

## Consequence

Keep the config change blocked (unchanged), but strike "actively harmful"
from the standing record: M4-b and successors should premise on "no
evidence of help, harm unproven, sample uninformative", i.e. the master
plan's pre-declared "replay inconclusive" branch. Method note for S5-era
re-runs: exact tail masses + a null control are mandatory below ~15 dates;
the date-block bootstrap is unusable at n_dates/block_len < ~4.
