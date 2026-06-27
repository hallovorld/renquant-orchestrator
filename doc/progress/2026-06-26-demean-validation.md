# Demean / signal-direction gate — early realized-return validation

2026-06-26.

## What & why
A no-trade daily-full refused 49/83 candidates on the signal-direction gate
(demean, `_2026_06_24_demean_monitored_exception`). Question: is demean dropping
real winners? The decision-ledger is now wired richly enough to answer it on
realized forward returns, so this validates it instead of guessing.

## Findings (read-only, `data/runs.alpaca.db` sim ledger 2024→2026)
- Demean **refuses relative under-performers, not winners**: within-date
  (refused − kept) fwd60 = −0.60 (t=−5.6, 74% of days); x-sec rank-IC(mu, fwd60)
  = +0.176 (t=12.9); holds per-regime incl. BULL_CALM (+0.168) and every year.
- So the no-trade is the validated gate declining a weak cross-section — not a
  bug. Early POSITIVE read for the demean monitored-enable; revert gate not
  tripped. Caveat: in-sample sim → trust the within-date relative result, not
  absolute magnitudes; confirm at the late-Aug #190 live-aged review.

## Deliverables
- `scripts/validate_conviction_gate.py` — (1) unblock: key the ledger on
  `coalesce(mu, expected_return)` (mu spans the sim history; `expected_return` is
  live-only and was NULL on every sim row → falsely INSUFFICIENT); now 527 aged
  dates. (2) add `rank_evidence`: floor-free, leakage-robust within-date rank-IC
  + refused-vs-kept gap — the significance lens the tool's own caveat asked for.
  Column-defensive (older DBs without a `mu` column still work).
- `tests/test_validate_conviction_gate.py` — +1 test for the mu-path + rank
  evidence (drops relative losers). 4 pass.
- `doc/research/2026-06-26-demean-signal-direction-validation.md` — full write-up,
  methodology, caveats, cross-check on an independent return source.

## Not done / follow-up
Production-faithful absolute-floor number awaits LIVE aged dates (accruing); the
late-Aug #190 review re-runs this on live data. Updates the now-obsolete
"validation blocked by unwired ledger" position.
