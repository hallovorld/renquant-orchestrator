# Does the demean / signal-direction gate drop real winners? (early read: NO)

2026-06-26. Read-only validation of the `demean_cross_sectional` monitored
exception (strategy-104 #33, enabled 2026-06-25) on realized forward returns.
Trigger: a no-trade daily-full where the signal-direction gate refused 49/83
candidates ("calibrated ER of opposite sign to raw") — is that the gate working,
or dropping winners?

## TL;DR
**Demean refuses relative under-performers, not winners.** Today's no-trade is the
validated gate correctly declining a weak cross-section — not a bug. Forcing buys
would mean buying names the model expects to relatively under-perform.

## The blocker is gone
The earlier validation wall (no persisted per-name raw+mu+forward history) is
**resolved**: `data/runs.alpaca.db` now carries `candidate_scores` (236k rows;
`mu` populated on the full **sim** backtest 2024-01→2026-03 + live),
`ticker_daily_state` (116k), and the panel dataset supplies realized
`fwd_60d_excess`. `validate_conviction_gate.py` was only ever reading
`expected_return` (NULL on every sim row), so it reported INSUFFICIENT despite 2+
years of aged `mu`. Keying on `coalesce(mu, expected_return)` unblocks it →
**527 aged dates**.

## Method
Join `candidate_scores → pipeline_runs(run_id→run_date, run_type) →
dataset.fwd_60d_excess` (per-regime), age-cut to dates whose 60d window has closed.
Demean = subtract the per-date cross-sectional mean of mu (pipeline #147); the
signal-direction gate then refuses names below the cross-sectional average.

The **absolute-floor** admitted-set means are in-sample **leakage-inflated** (RAW
+2.15 / DEMEAN +2.21 fwd60_excess — implausible magnitudes) and, on sim, only ~71
names clear an absolute 0.03 floor. So the trustworthy lens is **within-date
relative**, which cancels any uniform per-date level/leakage offset.

## Result (within-date, leakage-robust)
| metric | value | reading |
|---|---|---|
| x-sec rank-IC(mu, fwd60_excess) | **+0.176** (t=12.9, 451d) | mu ranks forward returns |
| within-date (demean-refused − kept) fwd60 | **−0.60** (t=−5.6, 92d, 74% of days) | demean drops the relative losers |
| BULL_CALM rank-IC | +0.168 (t=10.6, 317d) | holds in today's regime |
| BULL_VOLATILE rank-IC | +0.196 (t=7.4, 134d) | holds |
| by year (refused vs kept fwd60) | 2024 +6.7 vs +10.7 · 2025 +11.9 vs +22.8 · 2026 +8.0 vs +28.0 | every year |

Cross-checked on an independent return source (`ticker_forward_returns.fwd_60d`,
plausible 8–17% magnitudes): same sign, same t (−5.9), monotonic by demeaned-mu
quintile (Q0 +5.5% → Q4 +34.5% in 2026). The absolute-floor lens agrees
directionally (DEMEAN_BETTER, demean−raw +0.06) but is leakage-inflated and thin.

## Caveats (do not over-read)
- **In-sample sim** → absolute admitted-set magnitudes are leakage-inflated
  (~+0.04 shuffled-label floor known). Trust the **within-date relative** sign/t,
  not the levels.
- **42-ticker** joined subset (sim universe with realized fwd); live is 145.
- Sim `mu` may span model versions; the transform under test (cross-sectional
  demean) is applied per-date regardless, so the relative read still holds.
- The **production-faithful absolute-floor** number needs LIVE aged dates, which
  accrue going forward — confirm at the ~late-Aug `#190` review on live data.

## Decision
- **Keep demean.** Early evidence is positive and robust; the monitored-enable
  revert gate (`dropped_by_demean_mean_fwd > 0`) is not tripped on the relative
  evidence. Re-confirm at the late-Aug live-aged review.
- **The no-trade is not a bug to "fix".** The honest lever for more trades is
  stronger/orthogonal alpha and more names clearing the (validated) bar — not
  loosening a gate that is demonstrably filtering correctly.

## Reproduce
`python scripts/validate_conviction_gate.py --runs-db data/runs.alpaca.db`
(read-only; prints both the absolute-floor lens and the robust `rank_evidence`).
