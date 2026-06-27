# Does the demean / signal-direction gate drop real winners? (early read: NO)

2026-06-26 (revised 2026-06-27 after PR #196 review). Read-only validation of the
`demean_cross_sectional` monitored exception (strategy-104 #33, enabled
2026-06-25) on realized forward returns. Trigger: a no-trade daily-full where the
signal-direction gate refused 49/83 candidates ("calibrated ER of opposite sign
to raw") — is that the gate working, or dropping winners?

## TL;DR (early hypothesis, not yet validation-grade)
**Early in-sample read: demean appears to refuse relative under-performers, not
winners.** On the sim ledger the names demean drops realize lower forward returns
than the names it keeps, within-date. This is a **monitored positive read**, not a
confirmed result: the evidence is in-sample sim, on a 42-ticker joined subset,
with overlapping 60-session labels, and the production-faithful (live-aged,
absolute-floor) number is still pending. On this evidence we **keep** the
monitored exception and **do not** treat the no-trade as a bug to force through —
but the strong "validated / not a bug" claim is deferred to the late-Aug `#190`
live-aged review.

## The blocker is gone
The earlier validation wall (no persisted per-name raw+mu+forward history) is
**resolved**: `data/runs.alpaca.db` now carries `candidate_scores` (236k rows;
`mu` populated on the full **sim** backtest 2024-01→2026-03 + live),
`ticker_daily_state` (116k), and the panel dataset supplies realized
`fwd_60d_excess`. `validate_conviction_gate.py` was only ever reading
`expected_return` (NULL on every sim row), so it reported INSUFFICIENT despite 2+
years of aged `mu`. Keying on `coalesce(mu, expected_return)` unblocks it → **many
hundreds of aged dates** (a `527` figure appears in the first draft, but that was
computed under the now-corrected 60-**calendar**-day age cutoff; the
trading-session cutoff trims the not-yet-realized tail, so the exact aged-date
count is lower and is to be re-read from a fresh read-only run, not quoted from the
old draft).

## Method
Read `candidate_scores(run_id, ticker, mu)`, parse the run **date** directly out of
the `run_id` string (regex `\d{4}-\d{2}-\d{2}`; one run per date = the pool with the
most candidate rows) — the validator does **not** join `pipeline_runs`; provenance
is the date embedded in the run_id, which is the assumption to keep in mind. Join
that to the panel `dataset.fwd_60d_excess` on `(date, ticker)`, label the regime
from `regime_p_*`, then **age-cut by TRADING SESSIONS**: a date counts only once
>= `horizon_days` sessions from the dataset's own sorted date index fall in
`(date, as_of]`. `fwd_60d_excess` is a `c.shift(-60)` bar label (≈84 calendar days,
**not** 60 calendar days — confirmed in renquant-base-data
`alpha158_qlib_panel._compute_excess_label_frame` and the `purged_cv.py` "purge in
BARS" note), so a calendar-day cutoff would have admitted not-yet-realized labels.
Demean = subtract the per-date cross-sectional mean of mu (pipeline #147); the
signal-direction gate then refuses names below the cross-sectional average.

The **absolute-floor** admitted-set means are in-sample **leakage-inflated** (RAW
+2.15 / DEMEAN +2.21 fwd60_excess — implausible magnitudes) and, on sim, only ~71
names clear an absolute 0.03 floor. So the trustworthy lens is **within-date
relative**, which cancels any uniform per-date level/leakage offset.

## Result (within-date, leakage-robust)
Significance is reported with a **moving-block bootstrap** (block = 60 sessions,
the label-overlap span), **not** a naive iid t: adjacent dates share overlapping
~60-session forward windows and common regime shocks, so date-level obs are not
iid and a naive t (the earlier "t=12.9 / t=−5.6") is anti-conservative. The table
gives the point estimate and the sign/direction; the bootstrap 95% CI is the
significance lens the tool now prints. (The naive t is retained in the JSON only as
a clearly-labelled `t_iid_anticonservative` reference.)

| metric | point estimate | direction (block-bootstrap) |
|---|---|---|
| x-sec rank-IC(mu, fwd60_excess) | **+0.176** (451d) | mu ranks forward returns; CI > 0 |
| within-date (demean-refused − kept) fwd60 | **−0.60** (92d, 74% of days) | demean drops the relative losers; CI < 0 |
| BULL_CALM rank-IC | +0.168 (317d) | holds in today's regime |
| BULL_VOLATILE rank-IC | +0.196 (134d) | holds |
| by year (refused vs kept fwd60) | 2024 +6.7 vs +10.7 · 2025 +11.9 vs +22.8 · 2026 +8.0 vs +28.0 | every year |

The naive-iid t-values printed in the first draft (t≈12.9 / −5.6) materially
overstate significance because of the overlapping-label dependence and should not
be cited as validation-grade; trust the block-bootstrap CI sign and the
per-regime / per-year consistency instead. Cross-checked on an independent return
source (`ticker_forward_returns.fwd_60d`, plausible 8–17% magnitudes): same sign,
monotonic by demeaned-mu quintile (Q0 +5.5% → Q4 +34.5% in 2026). The
absolute-floor lens agrees directionally (DEMEAN_BETTER, demean−raw +0.06) but is
leakage-inflated and thin.

## Caveats (do not over-read)
- **In-sample sim** → absolute admitted-set magnitudes are leakage-inflated
  (~+0.04 shuffled-label floor known). Trust the **within-date relative** sign,
  not the levels.
- **Overlapping 60-session labels** → date obs are not iid; significance is a
  block-bootstrap CI sign, not a naive t. This is direction-of-effect evidence,
  not a clean significance test.
- **42-ticker** joined subset (sim universe with realized fwd); live is 145.
- Sim `mu` may span model versions; the transform under test (cross-sectional
  demean) is applied per-date regardless, so the relative read still holds — but
  it remains a sim-mu read, not a production-faithful one.
- The **production-faithful absolute-floor** number needs LIVE aged dates, which
  accrue going forward — confirm at the ~late-Aug `#190` review on live data.

## Decision
- **Keep demean (monitored).** The early in-sample read is positive and
  directionally robust across regimes/years, and the monitored-enable revert gate
  (`dropped_by_demean_mean_fwd > 0`) is not tripped on the relative evidence. This
  is a reason to **leave the monitored exception running**, not a clearance to
  declare it validated — that is deferred to the late-Aug live-aged `#190` review.
- **Do not treat the no-trade as a bug to force through.** On this evidence,
  loosening the gate would mean buying names the model ranks as relative
  under-performers; the honest lever for more trades is stronger/orthogonal alpha
  and more names clearing the bar, not a looser gate. (Stated as the current
  best read, pending the live-aged confirmation.)

## Reproduce
`python scripts/validate_conviction_gate.py --runs-db data/runs.alpaca.db`
(read-only; prints both the absolute-floor lens and the robust `rank_evidence`).
