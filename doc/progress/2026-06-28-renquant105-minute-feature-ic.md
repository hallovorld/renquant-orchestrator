# renquant-105 minute-feature cross-sectional IC scan — cheap gate (for discussion)

2026-06-28.

## STATUS
READ-ONLY research GATE. Settles, with DATA, whether minute-derived features carry
cross-sectional IC on renquant-104 — at SHORT (1d/3d) and multi-day (5d/20d) horizons,
standalone and marginal-over-the-daily-price-factors — BEFORE any heavy PatchTST-on-minute
experiment. **Not** a backtest, **not** a promotion, **not** a model change. No canonical
path written, no order placed, no git in the live tree, no self-merge.

## VERDICT
**Minute data DOES carry real cross-sectional IC — but only at SHORT horizons.**
- **1d / 3d:** `vwap_dev`, `intraday_mom_last`, `close_loc` clear the shuffle floor by 2.4–5.3×
  AND survive residualization on the 5 daily price factors (marginal NW t = 3.3–5.2).
  vwap_dev is strongest (1d marginal IC +0.028 t=5.2; 3d +0.030 t=3.3). The "minute = noise"
  prior is **refuted at short horizons.**
- **5d:** every feature's marginal IC over daily factors is below floor (best 0.67×).
- **20d:** standalone vol/range/illiquidity "clear" but their MARGINAL IC is ~zero (subsumed by
  daily factors); n=31 too thin. **No robust marginal multi-day IC.**

## SO WHAT (the discussion the PR opens)
- For the renquant-105 **multi-day** goal: this gate is **NEGATIVE** — minute features add no
  robust marginal 5d/20d IC, so a PatchTST-on-minute experiment is **NOT justified for the
  multi-day objective** on this evidence.
- The **short-horizon (1–3d)** edge is **real and marginal** — a genuinely different angle. If
  renquant ever wants a short-horizon sleeve, a minute-aware model is worth a scoped TEST (mind
  turnover/cost/PDT and that PatchTST is the multi-day primary, not this product).

## WHAT / HOW
`scripts/minute_feature_scan.py` (pinned `--as-of`, cache-first, manifest — mirrors
`sighunt.py`'s contract). Pulled 15-min RTH bars (1-min too large for a gate) for 134 golden
single names, **2023-12-22→2026-06-25, 627 sessions, 2.47M RTH rows**; 8 PIT cross-sectional
features as-of each close; Spearman rank-IC vs fwd 1/3/5/20d on non-overlapping dates (NW
t-stat); marginal IC vs forward returns residualized on the daily price factors; 200-perm
within-date shuffle placebo floor. Labels + daily factors reuse sighunt's `bars.parquet`.

## REPRODUCIBILITY / SAFETY
- `--as-of 2026-06-26` pinned (no `datetime.now` in the math). Cache-first: re-run reads
  `minbars.parquet` WITHOUT Alpaca credentials and reproduces identically (verified:
  `used_cache_without_credentials=true`, vwap_dev 1d IC 0.0351 unchanged).
- `manifest.json` pins as-of, universe-config sha, min-cache sha, daily-bars sha, kept-symbol
  list+sha (`7f9687c4a01b`, shared with sighunt), all params, code commit.
- READ-ONLY market data via `.env` (Alpaca); output/cache in `/tmp/minfeat_out` only. No
  canonical writes, no orders, no live-tree git.

## CAVEATS
15-min (not 1-min) granularity; bounded 2.5y single-regime window + current-watchlist
survivorship; IC ≠ net P&L (no cost model); no CPCV/FWER/DSR (lean gate — single placebo +
NW t + marginal residual). The short-horizon cluster (vwap_dev/mom_last/close_loc, marginal
t>3) is consistent across 1d & 3d, not one lucky cell; the multi-day null is robust to the
thin-n caveat because it is a *marginal*-IC null.

## NEXT (for discussion, not committed)
1. Decide: short-horizon sleeve in scope at all? (operating-model question, not a quant one.)
2. If yes → 1-min pull + cost/turnover model + proper CPCV before any model spend.
3. If no → minute-on-multi-day is closed by this gate; do NOT spin up PatchTST-on-minute for 105.

DO NOT merge / approve — opened for review by the counterpart agent.

---

## ADDENDUM 2026-06-27 — MONETIZATION under faithful costs (extends this branch / #206)

The IC was the cheap gate; the decisive question is whether ~0.02–0.03 marginal IC clears
realistic cost at 1–3d turnover. Added `scripts/minute_signal_costtest.py` (pinned `--as-of`,
cache-first, manifest — mirrors the #206 contract): builds the actual cross-sectional portfolio
(`vwap_dev` + the 3-feature combo; top-decile/quintile LONG-ONLY and top-minus-bottom L/S; 1d
and 3d rebalance) and charges **faithful** turnover cost (one-way `Σ|Δw|/2` × round-trip bps),
base 11 bps with a 5/20 bps sensitivity band — exactly like the PEAD faithful-cost fix.

**Result — it MONETIZES, decisively, at every tested cell.** Net of 11 bps round-trip:
- vwap_dev market-neutral **L/S decile: +30 bps/period @1d (Sharpe 4.1), +50 bps/period @3d
  (Sharpe 2.8)**; breakeven round-trip **47 / 71 bps** (4–6× the base cost).
- vwap_dev **long-only decile: +49 bps/period @1d (Sharpe 3.7), +104 @3d (Sharpe 2.6)**;
  breakeven **70 / 134 bps**. (Caveat: long-only carries ~+13 bps/day market beta over this
  2024–26 rally; the L/S leg is the clean, beta-free alpha read.)
- **No cell flips negative anywhere in 5–20 bps.** Net-positive in EVERY full year (2024/2025/
  2026); only the 2023 n=5 stub is negative (statistically empty).

This is the **opposite of the PEAD/fundamentals nulls** (there cost killed the IC; here the IC
is real AND clears cost with multiples of headroom). It is a **genuine short-horizon (1–3d)
product candidate** — but NOT a deployable book yet (needs OOS/walk-forward + CPCV/DSR on the
portfolio + execution realism beyond flat bps + borrow on the short leg), and it remains a
**different product** from the multi-day PatchTST primary. The shorting mandate constrains the
clean L/S leg; the long-only leg is deployable but carries rally beta.

Repro: `scripts/minute_signal_costtest.py --as-of 2026-06-26 --out /tmp/minfeat2_out` (reuses
#206's `minbars.parquet` WITHOUT credentials + sighunt `bars.parquet`); writes
`costtest_summary.csv` / `costtest_perperiod.csv` / `costtest_by_year.json` /
`costtest_manifest.json`. READ-ONLY, no orders, no canonical writes, no live-tree git, no
self-merge.
