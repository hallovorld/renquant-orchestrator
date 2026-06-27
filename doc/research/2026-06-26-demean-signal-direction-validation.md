# Does the demean / signal-direction gate drop real winners? (read: MIXED — monitor only)

2026-06-26 (revised 2026-06-27 twice after PR #196 review rounds 1 and 2).
Read-only validation of the `demean_cross_sectional` monitored exception
(strategy-104 #33, enabled 2026-06-25) on realized forward returns. Trigger: a
no-trade daily-full where the signal-direction gate refused 49/83 candidates
("calibrated ER of opposite sign to raw") — is that the gate working, or dropping
winners?

## TL;DR (MIXED — the two lenses DISAGREE; monitor-only, no operational clearance)
**The two evidence lenses disagree on the real 2026-06-27 ledger, so there is NO
operational clearance — keep the monitored exception running and keep watching.**
- The **relative-rank** lens (floor-free, leakage-robust) says demean is good:
  within-date the names it refuses realize **−0.6028** lower fwd60 than the names
  it keeps, block-bootstrap 95% CI **[−0.6791, −0.5085]** (excludes 0).
- The **absolute-floor** operational lens — which carries the NAMED
  monitored-enable revert metric — says the opposite: the few names demean drops
  realize **POSITIVE** fwd, `dropped_by_demean_mean_fwd = +1.1952` (and
  `BULL_VOLATILE` `+4.1341`). That is the literal definition of "demean dropped
  winners," i.e. the `dropped_by_demean_mean_fwd > 0` **revert trigger is tripped**.

Because one lens says keep and the named revert metric says revert, the validator
now emits `gate_status = MIXED_MONITOR_ONLY` / `verdict = MIXED_NO_CLEARANCE`
(it can no longer print a clean `DEMEAN_BETTER` while the revert metric is
positive). On this evidence we **keep** the monitored exception (it is already
running and the relative read is supportive) and **do not** treat the no-trade as
a bug to force through, but we **do NOT declare demean validated** — the absolute
revert metric is positive, it is thin (n=6) and in-sample leakage-inflated, and the
production-faithful live-aged read is deferred to the late-Aug `#190` review.

## The blocker is gone
The earlier validation wall (no persisted per-name raw+mu+forward history) is
**resolved**: `data/runs.alpaca.db` now carries `candidate_scores` (236k rows;
`mu` populated on the full **sim** backtest 2024-01→2026-03 + live),
`ticker_daily_state` (116k), and the panel dataset supplies realized
`fwd_60d_excess`. `validate_conviction_gate.py` was only ever reading
`expected_return` (NULL on every sim row), so it reported INSUFFICIENT despite 2+
years of aged `mu`. Keying on `coalesce(mu, expected_return)` unblocks it → on the
2026-06-27 trading-session run, `ledger_dates=610`, `aged_joined_dates=527`
(`aging=trading_sessions`, `aged_cutoff=2026-02-06`). (The `527` here is the
trading-session-aged count; the first draft printed `527` too but under the
now-corrected 60-**calendar**-day cutoff, which on this dataset happens to land on
the same figure — the cutoff date itself, 2026-02-06, is the audited
trading-session one.)

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

## Actual run (2026-06-27, read-only on the live ledger)
Command (read-only):
```
python scripts/validate_conviction_gate.py \
  --runs-db   /Users/renhao/git/github/RenQuant/data/runs.alpaca.db \
  --dataset   /Users/renhao/git/github/RenQuant/data/alpha158_291_fund_regime_dataset.parquet \
  --as-of 2026-06-27
```
`status=OK ledger_dates=610 aged_joined_dates=527 aging=trading_sessions
aged_cutoff=2026-02-06`. The validator now prints **two clearly-labelled lenses and
a revert-safe `gate_status`** — and they DISAGREE on this run:

### Lens A — relative rank (floor-free, leakage-robust) → `RELATIVE_DEMEAN_BETTER`
Significance is a **moving-block bootstrap** (block = 60 sessions, the
label-overlap span), **not** a naive iid t: adjacent dates share overlapping
~60-session forward windows and common regime shocks, so date-level obs are not
iid and a naive t (the earlier "t=12.9 / t=−5.6") is anti-conservative. The table
gives the point estimate and the bootstrap 95% CI. (The naive t is retained in the
JSON only as a clearly-labelled `t_iid_anticonservative` reference.)

| metric | point estimate | direction (block-bootstrap) |
|---|---|---|
| x-sec rank-IC(mu, fwd60_excess) | **+0.1758** (451d) | mu ranks forward returns; CI **[+0.0558, +0.2555]** > 0 |
| within-date (demean-refused − kept) fwd60 | **−0.6028** (92d, 74% of days) | demean drops the relative losers; CI **[−0.6791, −0.5085]** < 0 |
| by year (refused vs kept fwd60) | 2024 +6.7 vs +10.7 · 2025 +11.9 vs +22.8 · 2026 +8.0 vs +28.0 | every year |

### Lens B — absolute mu≥floor admitted set (operational; THIN / leakage-inflated; the NAMED revert metric) → `ABSOLUTE_REVERT_TRIGGER_TRIPPED`
This lens carries the monitored-enable revert number, and on the real run it is
**positive** — i.e. it says "demean dropped winners":

| field | value | note |
|---|---|---|
| `raw_admitted` mean fwd60 | +2.1513 (n=71) | in-sample leakage-inflated magnitudes — do not read levels |
| `demean_admitted` mean fwd60 | +2.2116 (n=67) | |
| **`dropped_by_demean_mean_fwd`** | **+1.1952 (n=6)** | **POSITIVE → `revert_trigger_tripped=true`** |
| `by_regime.BULL_VOLATILE.dropped_by_demean.mean` | **+4.1341 (n=2)** | most extreme; demean dropped 2 realized BULL_VOLATILE winners |
| `by_regime.BULL_CALM.dropped_by_demean.mean` | −0.2743 (n=4) | the only regime where dropped names were losers |
| `demean_minus_raw_mean_fwd` | +0.0604 | admitted-set delta still slightly positive, but mixes in names both rules keep |

The naive-iid t-values printed in the first draft (t≈12.9 / −5.6) materially
overstate significance because of the overlapping-label dependence and should not
be cited as validation-grade; trust the block-bootstrap CI sign and the
per-regime / per-year consistency instead. Cross-checked on an independent return
source (`ticker_forward_returns.fwd_60d`, plausible 8–17% magnitudes): same
relative sign, monotonic by demeaned-mu quintile (Q0 +5.5% → Q4 +34.5% in 2026).

### The disagreement (made explicit, not hidden)
Lens A says demean drops relative under-performers (good); Lens B's named revert
metric `dropped_by_demean_mean_fwd = +1.1952` says demean dropped realized
winners (revert). These answer **different questions** — Lens A is a *relational*
within-date read that cancels the per-date leakage/level offset and is the
trustworthy in-sample lens; Lens B is the *operational* absolute-floor set, which
is **thin** (only n=6 names clear the 0.03 floor and then fall below the
cross-sectional mean) and in-sample **leakage-inflated**, so its level is not
validation-grade. But Lens B is the metric the monitored-enable contract names as
the revert trigger, so a positive value **blocks any clean clearance**. The
validator therefore emits `gate_status = MIXED_MONITOR_ONLY` and refuses to print
`verdict = DEMEAN_BETTER` while the revert metric is positive.

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
- **MIXED — monitor only, NO operational clearance.** The relative-rank lens is
  positive and robust across regimes/years, but the **named** monitored-enable
  revert metric `dropped_by_demean_mean_fwd = +1.1952` (BULL_VOLATILE +4.1341) IS
  tripped on the real 2026-06-27 run. The two lenses disagree, so this is **not**
  a clearance to declare demean validated. The validator emits
  `gate_status = MIXED_MONITOR_ONLY`.
- **Keep demean (monitored), keep watching.** The exception is already running and
  the relative read is supportive, so there is no positive trigger to *revert it
  now on this evidence* either — but the positive absolute revert metric means we
  must keep monitoring and **resolve the disagreement on live-aged data** at the
  late-Aug `#190` review before any "validated" or "loosen the gate" decision. The
  absolute metric is thin (n=6) and in-sample leakage-inflated, which is the most
  likely reason it disagrees with the leakage-robust relative lens, but that has
  to be *shown* on live-aged dates, not assumed.
- **Do not treat the no-trade as a bug to force through.** On this evidence,
  loosening the gate would mean buying names the model ranks as relative
  under-performers; the honest lever for more trades is stronger/orthogonal alpha
  and more names clearing the bar, not a looser gate. (Stated as the current
  best read, pending the live-aged confirmation.)

## Reproduce
`python scripts/validate_conviction_gate.py --runs-db data/runs.alpaca.db --as-of 2026-06-27`
(read-only; prints **Lens A** relative rank, **Lens B** absolute floor with the
named revert metric, and the revert-safe `gate_status`. Add `--json` for the full
two-lens payload — `relative_lens`, `absolute_floor_lens`, `gate_status`. The
`verdict` field is retained for back-compat but is mechanically prevented from
reading `DEMEAN_BETTER` while the revert metric is positive; read `gate_status`.)
