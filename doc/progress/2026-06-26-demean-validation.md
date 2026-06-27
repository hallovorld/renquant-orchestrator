# Demean / signal-direction gate — early realized-return validation

2026-06-26.

## What & why
A no-trade daily-full refused 49/83 candidates on the signal-direction gate
(demean, `_2026_06_24_demean_monitored_exception`). Question: is demean dropping
real winners? The decision-ledger is now wired richly enough to answer it on
realized forward returns, so this validates it instead of guessing.

## Findings (read-only, `data/runs.alpaca.db` sim ledger 2024→2026) — verdict is MIXED
The validator reports **two lenses** and the real `--as-of 2026-06-27` run has them
**disagree**, so `gate_status=MIXED_MONITOR_ONLY` / `verdict=MIXED_NO_CLEARANCE`:
- **Lens A (relative rank):** demean-refused names underperform the kept set —
  within-date (refused − kept) fwd60 = −0.6028, block-bootstrap CI
  [−0.6791, −0.5085] (excludes 0); x-sec rank-IC(mu, fwd60) +0.1758. Looks good.
- **Lens B (absolute mu≥floor operational):** the monitored-enable's own named
  revert metric is **positive** — `dropped_by_demean_mean_fwd = +1.1952`
  (BULL_VOLATILE +4.1341, n=2; BULL_CALM −0.2743, n=4), so
  `revert_trigger_tripped = true` (thin n=6, leakage-inflated, but tripped).
- **Net: NO operational clearance.** The tool refuses to emit `DEMEAN_BETTER` while
  the revert metric is positive. So this is **monitor-only, NOT a positive
  validation** — one lens says keep, the named revert metric says revert. The
  no-trade is not "a bug to force through", but neither is demean "validated".
  Caveats: in-sample sim, 42-ticker subset, overlapping 60-session labels (naive t
  ≈12.9/−5.6 anti-conservative → block bootstrap used). Decide at the late-Aug #190
  live-aged review.

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
  block-bootstrap field coverage, and the two-lens conflict test (relative-positive
  AND absolute-dropped-positive → `MIXED_MONITOR_ONLY`, never `DEMEAN_BETTER`). 6 pass.
- `doc/research/2026-06-26-demean-signal-direction-validation.md` — full write-up,
  the two-lens (relative vs absolute-floor) decision surface, methodology (run_id-date
  provenance, not a `pipeline_runs` join), caveats. Framed as MIXED / monitor-only.

## Not done / follow-up
Production-faithful absolute-floor number awaits LIVE aged dates (accruing); the
late-Aug #190 review re-runs this on live data. Updates the now-obsolete
"validation blocked by unwired ledger" position.
