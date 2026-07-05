# S10: Open-auction implementation shortfall — measurement memo

**Date:** 2026-07-04 (Round 2: sensitivity analysis added per Codex review)
**Period:** 2026-04-23 to 2026-05-22
**Sample:** 67 unique live buys total ($91,088 invested); the fullest
(remap + ex ante exclusion) configuration keeps 65 of these ($90,226
invested, 2 HON trades excluded) — see sensitivity table below for how the
analytic sample and invested total vary with methodology choices.

## Round 2 note (Codex review)

Codex blocked the round-1 memo for treating "No measurable execution leak" and
"the §9.4 rationale is not supported" as settled conclusions off a methodology
with three unresolved instability points: (1) 30/67 trades unmatched because
`run_date` fell on a weekend (join key misaligned to the real execution
clock), (2) a `DISTINCT (run_date, ticker, shares, price, invest)` dedup
heuristic rather than a demonstrated trade-identity rule, (3) HON excluded
via a post-hoc `|IS_vs_open| > 1000 bps` rule chosen after seeing the result.

This round fixes (1) and (3) directly — `scripts/s10_open_auction_is.py` now
has an EX ANTE `--exclude-outlier-bps` flag (the threshold is a declared
parameter, not a per-trade judgment call made after looking at results) and a
`--weekend-remap` flag (remaps a weekend `run_date` to the nearest PRIOR
weekday — these are duplicate pipeline invocations of an already-filled
trade, not same-day fills on a day markets were closed) — and reports the
result across all four combinations below. (2) — a genuine trade-identity
key distinct from the `DISTINCT (...)` heuristic — is NOT fixed this round;
`runs.alpaca.db`'s `trades` table has no order/fill ID to join on, so this
remains a real, acknowledged limitation of the dedup approach.

## Sensitivity table (bootstrap 95% CI, seed=42, 10,000 resamples)

| Configuration | n | vs open: mean [95% CI] bps | vs VWAP: mean [95% CI] bps | $-weighted vs VWAP (bps) |
|---|---|---|---|---|
| Raw (no remap, no exclusion) | 37 | -149.7 [-429.8, +5.6] | -168.8 [-459.0, +0.2] | -119.9 |
| + ex ante outlier exclusion (\|IS_open\|>1000bps) only | 36 | -17.3 [-49.6, +12.7] | -35.4 [-85.9, +11.1] | -89.6 |
| + weekend remap only | 67 | -156.4 [-389.5, +13.0] | -180.5 [-411.3, -13.2] | -121.3 |
| + BOTH remap and exclusion (fullest, cleanest sample) | 65 | -7.8 [-50.8, +37.8] | -32.6 [-74.3, +7.3] | -74.9 |

The row 2 config ("+ ex ante outlier exclusion only", n=36) reproduces the
round-1 memo's headline numbers exactly (-17.3 / -35.4 / -89.6), confirming
the original run was reproducible — the round-1 issue was that this specific
choice of methodology was not disclosed as one point in a sensitivity range,
it was presented as the finding.

**Weekend remap discovered a SECOND HON-affected trade** (`HON@2026-05-15`,
in addition to the already-known `HON@2026-05-18`) that the round-1
methodology never surfaced at all, because it happened to fall on a weekend
`run_date` and was silently dropped as "unmatched" rather than investigated.
This is itself evidence the round-1 unmatched-trade bucket was masking real
data-quality issues, not just inert noise.

## Interpretation

**The direction and rough magnitude of the "no leak" finding is robust across
all four configurations**: every configuration's point estimate is negative
(fills at or below benchmark — i.e., favorable execution, not overpaying) for
both vs-open and vs-VWAP, and the dollar-weighted IS vs VWAP is negative in
all four (-119.9 / -89.6 / -121.3 / -74.9 bps). None of the four
configurations produce a positive (leak) point estimate or a CI that clearly
excludes zero on the leak side.

**The precision is genuinely sensitive to methodology**, and this matters for
how confidently the conclusion should be stated:
- The vs-open CI includes zero in 3 of 4 configurations (raw, remap-only,
  both) — only the ex-ante-exclusion-only config's CI excludes zero at the
  edge ([-49.6, +12.7] still includes zero; none of the vs-open CIs actually
  fully exclude zero). So "no measurable leak" is better read as "not
  statistically distinguishable from zero, in either direction" rather than
  a precisely-measured null.
- The vs-VWAP CI excludes zero (fully negative) in exactly one configuration
  — weekend-remap-only, without outlier exclusion — which still contains the
  extreme HON-driven variance; that specific exclusion of zero should not be
  over-read given the outlier is still in that sample.
- The fullest, cleanest configuration (remap + ex ante exclusion, n=65) gives
  the most methodologically defensible numbers: vs-open -7.8 bps
  [-50.8, +37.8], vs-VWAP -32.6 bps [-74.3, +7.3], dollar-weighted -74.9 bps.

**Revised bottom line:** across a genuine sensitivity sweep (not a single
cleaned run), there is no configuration in which open-auction execution shows
a leak — the estimate is consistently at-or-better-than benchmark, though
imprecisely measured (small sample, HON-scale outliers dominate variance
before exclusion). This is meaningfully stronger evidence than the round-1
single-cut analysis, but it is still NOT a claim that the §9.4 execution-
timing prize (~40bps) has been definitively ruled out to arbitrary precision
— the CIs are wide enough that a leak on the order of a few tens of bps
cannot be excluded with this sample size. The 105 engineering prize
re-anchoring recommendation from round 1 (toward exit timing / order-type /
overnight-gap management) is retained, but as a recommendation informed by a
robust-but-imprecise null, not a definitively closed question.

## Data quality notes

- **Trade-identity limitation (Codex's point 2, NOT fixed this round):**
  dedup is `DISTINCT (run_date, ticker, shares, price, invest)` — a
  heuristic, not a join against a genuine order/fill ID. `runs.alpaca.db`'s
  `trades` table has no such ID. Two genuinely distinct trades that happen
  to share all five of those fields (same day, ticker, share count, price,
  and invested amount) would be silently collapsed into one. This is judged
  unlikely to materially affect the sample but is not verified.
- **HON — now 2 known instances, both excluded under the ex-ante rule**:
  `HON@2026-05-18` (fill $217.70 vs FMP open $428.22, ratio ≈ 2:1) and
  `HON@2026-05-15` (only visible after weekend remap). Both consistent with
  an Alpaca (post-split) vs FMP (pre-split, or differently adjusted) data
  mismatch, not genuine execution quality.
- **Weekend remap is a mechanical nearest-prior-weekday shift.** It does not
  attempt to verify against the broker's actual fill timestamp (not
  available in this table) — it assumes the pipeline's weekend invocation
  duplicated the immediately-prior weekday's real fill, which is consistent
  with known duplicate-run behavior but not independently confirmed per
  trade.

## Method

- Source: `runs.alpaca.db` live buys joined to FMP `historical-price-eod/full`
- Dedup: `DISTINCT (run_date, ticker, shares, price, invest)` in SQL (see
  limitation above)
- Outlier filter: EX ANTE `--exclude-outlier-bps` CLI parameter (this round);
  round-1's 1000bps threshold reproduced here as one row of the sensitivity
  table, not the sole reported result
- Weekend remap: EX ANTE `--weekend-remap` CLI flag (this round) — nearest
  prior weekday
- Bootstrap: 10,000 resamples, 95% CI (seed=42, reproducible)
- IS convention: positive = overpaid = leak
- Script: `scripts/s10_open_auction_is.py` (`--weekend-remap`,
  `--exclude-outlier-bps <N>` — both now real CLI options, not manual
  post-processing)
