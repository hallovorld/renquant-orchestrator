# Demean / signal-direction gate — early realized-return validation

2026-06-26.

## What & why
A no-trade daily-full refused 49/83 candidates on the signal-direction gate
(demean, `_2026_06_24_demean_monitored_exception`). Question: is demean dropping
real winners? The decision-ledger is now wired richly enough to answer it on
realized forward returns, so this validates it instead of guessing.

## Findings (read-only, `data/runs.alpaca.db` sim ledger 2024→2026)
- Early in-sample read: demean **appears to refuse relative under-performers, not
  winners**: within-date (refused − kept) fwd60 = −0.60 (92d, 74% of days);
  x-sec rank-IC(mu, fwd60) = +0.176 (451d); direction holds per-regime incl.
  BULL_CALM (+0.168) and every year. Significance is a **block-bootstrap CI sign**
  (overlapping 60-session labels → date obs not iid); the first-draft naive t
  (≈12.9 / −5.6) overstates it and is retained only as a labelled reference.
- So the no-trade reads as the gate declining a weak cross-section — a **monitored
  positive read**, not yet validation-grade and not a bug to force through. Revert
  gate not tripped. Caveats: in-sample sim, 42-ticker subset, overlapping labels →
  trust the within-date relative *direction*, not absolute magnitudes or naive t;
  confirm at the late-Aug #190 live-aged review.

## Deliverables
- `scripts/validate_conviction_gate.py` — (1) unblock: key the ledger on
  `coalesce(mu, expected_return)` (mu spans the sim history; `expected_return` is
  live-only and was NULL on every sim row → falsely INSUFFICIENT); many hundreds
  of aged dates now qualify. (2) add `rank_evidence`: floor-free, leakage-robust
  within-date rank-IC + refused-vs-kept gap, with a **moving-block-bootstrap** CI
  (block = label horizon in sessions) for significance, since overlapping
  60-session labels make date obs non-iid (the naive iid t is kept only as a
  labelled, anti-conservative reference). (3) **age-cut by TRADING SESSIONS** off
  the dataset's date index, not calendar days — `fwd_60d_excess` is a `shift(-60)`
  bar label (~84 calendar days), so the old 60-calendar-day cutoff counted
  not-yet-realized labels as evidence. Column-defensive (older DBs without a `mu`
  column still work).
- `tests/test_validate_conviction_gate.py` — mu-path + rank-evidence test, a
  trading-session-vs-calendar-day age regression test (fails on the old cutoff),
  and block-bootstrap field coverage. 5 pass.
- `doc/research/2026-06-26-demean-signal-direction-validation.md` — full write-up,
  methodology (incl. run_id-date provenance, not a `pipeline_runs` join), caveats,
  cross-check on an independent return source. Framed as an early monitored read.

## Not done / follow-up
Production-faithful absolute-floor number awaits LIVE aged dates (accruing); the
late-Aug #190 review re-runs this on live data. Updates the now-obsolete
"validation blocked by unwired ledger" position.
