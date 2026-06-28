# Forward snapshotter for FMP estimate-revision history (design)

**Status:** proposed / collector script only. No cron, no canonical writes. 2026-06-28.

Companion to `doc/design/2026-06-24-analyst-revision-feature.md` (the feature
design) and `doc/decisions/2026-06-25-analyst-data-source-strategy.md` (the
source decision). Those say *what* the revision signal is and *which* source to
buy; this says *how we start accruing the point-in-time history it needs*, today,
for ~free.

> **Ownership note (read first).** Data acquisition/storage is a
> `renquant-base-data` responsibility, not an orchestrator one (see
> "Repo boundary / proper home" below). The orchestrator's only durable role is
> to *schedule/invoke* a base-data primitive and persist its fingerprint. This
> PR lands the collector here only as a working, reviewed reference; **moving it
> into `renquant-base-data` is the proposed resolution and is left as an explicit
> operator decision** (this PR does not create a base-data PR).

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
allowed target, for demos). The guard follows symlinks (`resolve()`), so a link
named `estimate_snapshots` that actually points into a forbidden tree is still
rejected. Every row is stamped with `snapshot_as_of` so the accruing series is
self-describing PIT. Each manifest carries `as_of`, `endpoint`, `sha256`,
`ticker_count`, `coverage`, `status`, and `fetched_at` (mirroring the harvest
manifest shape).

Auth/endpoint match the harvest exactly: the FMP `stable` base, `?…&apikey=` query
param, key read **read-only** from the umbrella `.env` (`FMP_API_KEY`, env var
override first).

## PIT provenance: `snapshot_as_of` is always the actual fetch date

Every row is fetched **now**. The only honest `snapshot_as_of` is therefore the
actual UTC fetch date — the collector derives it from `datetime.now(timezone.utc)`
and a row is never stamped with a user-supplied past date. `--as-of` is accepted
**only for today's UTC date or a future date** (e.g. to pre-name a scheduled
slot); a **past `--as-of` is rejected** with an error, because stamping freshly
fetched rows with a past date would manufacture point-in-time history that never
existed — exactly the look-ahead the walk-forward gate exists to catch. This
forward collector therefore cannot, and must not, produce historical backfill.
Legitimate historical backfill is valid **only from an immutable source that was
actually captured at that historical time, with its own provenance** — not from
re-labelling a live fetch.

## Atomic publish, partial handling, non-destructive idempotency

A fetch can fail partway (HTTP errors, network drops). The collector never
publishes a partial result over a good one:

- **Staged write.** Every endpoint is written into a sibling temp dir under the
  out-root, not the final date dir.
- **Coverage floor + status.** Each endpoint computes `coverage` = share of the
  universe reached (data **or** a clean no-data). If coverage is below
  `--min-coverage` (default 0.90) **or** any HTTP/network error occurred, that
  endpoint's manifest is marked `status: partial`.
- **Atomic publish only on success.** Only if **every** endpoint is `ok` is the
  date published via a single atomic `os.replace` of the staged dir onto the
  final date dir. A partial run is **not** published; any prior good snapshot is
  left untouched, and the staging dir is cleaned up. A real shortfall exits
  non-zero so a scheduler/alert can react.
- **Idempotency = no-op verify, not destructive refetch.** If the date is
  already fully published, a re-run is a **no-op** (it does not refetch or
  overwrite). `--force` is required to deliberately re-publish, and even then a
  partial fetch will not clobber the prior good snapshot.

## Repo boundary / proper home (`renquant-base-data`)

Per the orchestrator's CLAUDE.md hard boundary, **data acquisition and storage
belong in `renquant-base-data`**, not the orchestrator. The orchestrator's
durable role is to *schedule/invoke* a base-data primitive and *persist its
fingerprint* into the run bundle — not to own the fetch/write logic.

The proper home for this collector is therefore a `renquant-base-data` primitive
(e.g. `renquant_base_data.estimate_snapshots`), with the orchestrator keeping only
the scheduling wiring + fingerprint persistence. This PR intentionally lands the
collector under `scripts/` here **only as a reviewed reference implementation**;
**relocating it to `renquant-base-data` is the proposed resolution and is flagged
as an explicit operator decision** — analogous to the earlier umbrella ADR move.
This PR does **not** open a base-data PR or relocate the code unilaterally.

## Scheduling — PROPOSAL ONLY (not deployed in this PR)

Scheduling a cron/launchd job is a separate operator deploy decision and is
**not** done here. This PR ships the collector and proves it runs; turning it on
is an explicit operator action. The proposal the operator would sign off on:

- **Deployment owner.** Ideally a `renquant-base-data` scheduled primitive once
  the collector is relocated (see ownership note); until then, the operator's
  daily-run host, invoked alongside the existing FMP harvest.
- **Cadence.** **Daily**, one snapshot per trading day. Estimates/targets move on
  a multi-day-to-weekly cadence, so daily captures the revision series with
  margin; a pre- or post-market slot is fine (the as-of *date* is what matters,
  not the intraday time). A `flock` guard prevents two runs racing the same date:

  ```
  flock -n /tmp/snapshot_fmp_estimates.lock \
      python scripts/snapshot_fmp_estimates.py --out data/estimate_snapshots
  ```

- **Retry / backfill policy (NO fake timestamps).** A failed/partial run is
  marked `partial`, **not** published, and exits non-zero → retry the **same UTC
  day**. A day that is fully missed stays a genuine gap: it is **not**
  back-dated. There is no honest way to recover a missed day's *as-of consensus*
  from a later fetch, so the feature builder simply treats it as missing (the
  trailing-delta windows already tolerate sparse dates). Re-running a published
  day is a no-op verify; `--force` re-publishes only the current/future day.
- **Freshness alert.** A monitor (extending the existing data-freshness audit)
  should alert if the newest `data/estimate_snapshots/<date>/` is older than N
  trading days, or if the most recent run's manifest `status != ok` — so a silent
  outage surfaces instead of quietly starving the future feature.

These are a proposal for operator review, not an installed schedule.

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

- No cron / launchd / scheduler (operator deploy decision — see scheduling
  proposal above).
- No write to any canonical/existing data path (symlink-following structural
  guard).
- **No backdating.** A past `--as-of` errors out; `snapshot_as_of` is always the
  actual UTC fetch date.
- No relocation into `renquant-base-data` — flagged as the proposed resolution
  for an operator decision, not done here.
- No feature engineering, no retrain, no model change.
- No claim the signal works — that needs accrued history (~3–6 months) and its
  own gate.

## Open questions for discussion

0. **Relocate to `renquant-base-data`?** (Recommended.) Should the collector
   move to a base-data primitive now, with the orchestrator keeping only
   scheduling + fingerprint persistence? Operator decision.
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
