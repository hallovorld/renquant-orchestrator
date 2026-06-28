# Forward snapshotter for FMP estimate-revision history (design)

**Status:** proposed / collector script only. No cron, no canonical writes. 2026-06-28.

Companion to `doc/design/2026-06-24-analyst-revision-feature.md` (the feature
design) and `doc/decisions/2026-06-25-analyst-data-source-strategy.md` (the
source decision). Those say *what* the revision signal is and *which* source to
buy; this says *how we start accruing the point-in-time history it needs*, today,
for ~free.

## Problem

The analyst estimate-**revision** signal — Δ(consensus EPS/target estimate) over a
trailing window, as-of each date — is the literature's best large-cap orthogonal
lead (post-revision drift: Womack 1996; Gleason–Lee 2003). The 2026-06-23 trade
review found exactly the disagreement that makes it useful: the model's vol-tilt
picks sit near analyst targets with the least forward upside, while the
beaten-down Buy/Strong-Buy names carry the most.

But the signal is **un-buildable from what we have**. Our FMP harvest
(`data/fmp_harvest/` in the umbrella, umbrella PR #409) is a single **current
snapshot**: each `analyst_estimates_291.parquet` etc. reflects the consensus only
as it stood on the harvest day. A point-in-time audit confirms we cannot
reconstruct "what the consensus was 1m / 3m ago" from one shot — and using
*today's* consensus on *past* dates is exactly the look-ahead leakage the
walk-forward gate exists to catch. The revision **level** is in the snapshot; the
revision **change** (the actual alpha) is not, and never will be from a
single-snapshot harvest.

The missing ingredient is not money or a new vendor — it is **time**. If we
snapshot the estimates forward from today, a real as-of revision history accrues
on its own, leakage-free.

## What this collects, and where it writes

`scripts/snapshot_fmp_estimates.py` fetches, for the renquant-104 universe (read
read-only from the golden `strategy_config.json` `watchlist`, or a `--universe`
file), the current FMP analyst series from the same `stable` endpoints the
harvest already uses:

| endpoint | FMP `stable` path | carries |
|---|---|---|
| `analyst_estimates` | `analyst-estimates?symbol=…&period=annual` | mean/low/high EPS + revenue estimate, n analysts — **the series that revises** |
| `grades_consensus` | `grades-consensus?symbol=…` | strongBuy/buy/hold/sell counts + consensus rating |
| `price_target_consensus` | `price-target-consensus?symbol=…` | target high/low/consensus/median |
| `price_target_summary` | `price-target-summary?symbol=…` | last-month/quarter target averages + counts |

It writes a **dated** snapshot to a **NEW dedicated path**:

```
data/estimate_snapshots/<YYYY-MM-DD>/<endpoint>.parquet
data/estimate_snapshots/<YYYY-MM-DD>/<endpoint>.manifest.json
```

`data/estimate_snapshots/` is a new directory. The script **never** writes any
canonical/existing path — there is a structural guard (`is_canonical_path`) that
refuses `fmp_harvest`, `sec_fundamentals_daily`, `rawlabel.parquet`, `score_db`,
or any non-`estimate_snapshots` leaf (a `/tmp` scratch path is the only other
allowed target, for demos). Every row is stamped with `snapshot_as_of` so the
accruing series is self-describing PIT. Each manifest carries `as_of`, `endpoint`,
`sha256`, `ticker_count`, and `fetched_at` (mirroring the harvest manifest shape).

Auth/endpoint match the harvest exactly: the FMP `stable` base, `?…&apikey=` query
param, key read **read-only** from the umbrella `.env` (`FMP_API_KEY`, env var
override first).

## Cadence

**Daily.** Estimates and targets move on a multi-day-to-weekly cadence, so one
snapshot per trading day fully captures the revision series with margin; a
pre-market or post-market slot is fine (the as-of date is what matters, not the
intraday time). The writer is **idempotent per as-of date** — re-running a date
overwrites only that date's directory, so a missed day backfilled with
`--as-of` (re-stamping the as-of label) and a retried day both stay clean.

For a real scheduled deploy, wrap the call in a `flock` guard so two runs can't
race the same date dir:

```
flock -n /tmp/snapshot_fmp_estimates.lock \
    python scripts/snapshot_fmp_estimates.py --out data/estimate_snapshots
```

**Scheduling (cron/launchd) is a separate operator deploy decision and is NOT
done in this PR.** This PR ships the collector and proves it runs; turning it on
is an explicit operator action.

## How the revision signal gets built later (from accrued snapshots)

Once N dated snapshots exist, the feature builder (a later PR) computes, per
(ticker, as-of date), trailing **as-of** deltas with no look-ahead:

- `eps_rev_1m`, `eps_rev_3m` = `epsAvg[as_of] − epsAvg[as_of − {21,63} trading days]`,
  normalized (e.g. by |prior| or by price), using **only snapshots dated ≤ as_of**.
- `target_rev_*` = same on `targetConsensus`.
- `grade_drift_*` = Δ in the buy-minus-sell share of `grades_consensus`.
- coverage / dispersion as confidence weights (`numAnalystsEps`, target spread).

Because each snapshot is the consensus *as it was known that day*, the trailing
delta is genuinely point-in-time. This is the only way to get a leakage-free
revision series without a vendor PIT feed. Missing/thin names get explicit
missing handling (no median-impute — that's the DataIntegrity failure mode in
reverse). Validation is the feature's **own** pre-registered per-regime
walk-forward + placebo gate, placebo-clean positive, before anything goes live —
unchanged from the feature design.

## Cost

~**free**. The free FMP plan already returns these endpoints for ~134/142 names
(the ~8 misses are plan-locked, not rate-limited; see the data-vendor memo). One
daily pass for ~142 names × 4 endpoints is ~570 light requests, comfortably
inside even free limits with a 0.2s throttle. No new subscription is required
*to start accruing* — a paid upgrade only matters later if we want fuller
coverage of the few locked names, which is an independent decision.

## What this PR explicitly does NOT do

- No cron / launchd / scheduler (operator deploy decision).
- No write to any canonical/existing data path (structural guard).
- No feature engineering, no retrain, no model change.
- No claim the signal works — that needs accrued history (~3–6 months) and its
  own gate.

## Open questions for discussion

1. **Path layout** — is `data/estimate_snapshots/<date>/<endpoint>.parquet` the
   right shape, or should it be `<endpoint>/<date>.parquet`? (date-major is
   simpler to prune/backfill; endpoint-major is simpler to concat a single
   series.)
2. **Cadence + endpoints** — daily right? are these four the correct set, or
   should `grades_historical` / earnings-estimate endpoints be added?
3. **When is there enough history to test** — first defensible revision-signal
   validation is ~3 months (21–63d trailing deltas need at least that span);
   ~6 months is a more honest first per-regime gate. Agree on the no-look bar.
4. **Universe breadth** — snapshot only the 142-name watchlist, or a broader set
   (e.g. the russell_1000 universe already in the repo) so the eventual
   cross-sectional revision signal has more breadth and the watchlist can grow
   without a history gap? Broader is still ~free here.
