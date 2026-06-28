# renquant-105 minute-feature cross-sectional IC scan — corrected to an honest null

2026-06-28 (corrected after the #206 review).

## STATUS
READ-ONLY research GATE. Settles, with DATA, whether minute-derived features carry
**next-tradable, marginal-over-the-daily-factors** cross-sectional IC on renquant-104 — and
whether any candidate survives a chronological OOS holdout — BEFORE any heavy PatchTST-on-minute
experiment. Not a backtest, not a promotion, not a model change. No canonical path written, no
order placed, no git in the live tree, no self-merge.

## VERDICT — NULL (the first cut's "edge" was a bug artifact)
The first cut claimed a real short-horizon edge (vwap_dev 1d marginal IC +0.028 t=5.2,
"net Sharpe ~4"). The #206 review identified that the headline rested on three bugs. Fixing all
three **collapses the signal to zero**:
- **Marginal IC (proper FWL), DISCOVERY:** vwap_dev 1d **+0.0017 (t=0.23)**; intraday_mom_last
  1d −0.006 (t=−0.94); close_loc 1d +0.005 (t=0.74); vwap_dev 3d +0.017 (t=1.62) — **none clears
  the marginal placebo floor with a positive sign and t≥3.**
- **OOS holdout (chronological 70/30):** **ZERO discovery winners** to test — nothing survives
  because nothing qualified in discovery.
- **Economics (next-session entry, market-neutral L/S, the clean read):** 1d gross is **negative
  before cost** (net Sharpe ≈ −2.3, full window AND OOS); 3d clears 11 bps only for one signal in
  one thin OOS cell (combo +9%/yr Sharpe 0.79) while vwap_dev 3d is **negative OOS**. **Does not
  monetize.**

## THE DECOMPOSITION (why it collapsed)
vwap_dev 1d marginal IC, adding one fix at a time (full 626-date sample):
- OLD (fixed-UTC RTH + close-entry + invalid-FWL): **+0.0279 (t=5.10)** ← reproduces headline
- + DST-correct RTH: **−0.0151 (t=−2.86)** ← sign flips; signal lived in contaminated bars
- + next-session entry: +0.0020 (t=0.36)
- + proper FWL (full fix): **+0.0004 (t=0.07)** ← null

The old fixed UTC 13:30–21:00 filter admitted **290,917 bars (11.8%)** of pre-market (EST) /
after-hours (EDT) data that *created* the apparent VWAP/close-location signal.

## THE 6 FIXES (mapped to the review)
1. **DST-correct RTH:** XNYS `exchange_calendars` `[session_open, session_close)` per session in
   UTC = 09:30–16:00 LOCAL, half-days truncated (6 early closes in window → 14 bars not 26).
2. **Next-session entry:** signal known after close[D] → enter `open[D+1]`; fwd ret =
   `close[D+h]/open[D+1] − 1`. (Day-open derived from the corrected RTH bars.)
3. **Proper FWL marginal IC:** residualize BOTH feature and forward return on the same 5
   rank-standardized daily factors, then correlate residuals (was: residualize return only,
   correlate with raw feature — invalid).
4. **Marginal placebo:** separate within-date shuffle floor on residualized-feature vs
   residualized-return, per horizon (was: reused standalone floor).
5. **Chronological OOS holdout:** 70/30 split; winners selected on discovery, reported on the
   untouched holdout; "real edge / prior refuted" downgraded to "candidate, pending OOS" → then
   shown to be a null.
6. **Execution economics from next-tradable entry:** cost-test re-run with `open[D+1]` entry,
   actual turnover, 5/11/20 bps sensitivity, active-day exposure, full-window + OOS.

## WHAT / HOW
- `scripts/minute_rth.py` — shared DST-correct RTH filter + daily-factor helpers (one source of
  truth for both scripts and tests).
- `scripts/minute_feature_scan.py --as-of 2026-06-25 --out /tmp/rq206f_out` — DST-correct, 627
  sessions, **2,174,757 RTH rows** (was 2,465,674); discovery 438 / OOS 189; proper-FWL marginal
  IC + marginal placebo + OOS survival. Writes `results.csv`, `marginal_placebo_floor.json`,
  `oos_winners.json`, `manifest.json`.
- `scripts/minute_signal_costtest.py --as-of 2026-06-25 --out /tmp/rq206f_out` — next-session
  entry economics, full + OOS. Writes `costtest_*`.
- `tests/test_minute_feature_scan.py` — 11 focused tests: DST premarket/afterhours filtering,
  half-day truncation + schedule, next-session label alignment / no-look-ahead, proper-FWL
  partial-correlation (nulls a no-marginal case, detects a genuine one, residual orthogonality).

## REPRODUCIBILITY / SAFETY
- `--as-of 2026-06-25` pinned (no `datetime.now` in the math). Cache-first: reads
  `minbars.parquet` WITHOUT Alpaca credentials (`used_cache_without_credentials=true`).
- `manifest.json` pins as-of, RTH-filter + entry-timing + marginal-IC method, universe/min-cache/
  daily-bars shas, kept-symbol list+sha (`7f9687c4a01b`, shared with sighunt), OOS split date,
  all params, code commit.
- READ-ONLY; output/cache in `/tmp/rq206f_out` only. No canonical writes, no orders, no live-tree
  git, no self-merge.

## CAVEATS
15-min (not 1-min); bounded 2.5y single-regime window + current-watchlist survivorship; lean
mandate (one marginal placebo floor + NW t + one chronological OOS holdout; no CPCV/FWER/DSR —
none needed to read a null). Finer 1-min bars are a separate heavier pull and would have to
overcome a clean null.

## NEXT
- **Do NOT** spin up a PatchTST-on-minute experiment for renquant-105 multi-day OR for a
  short-horizon sleeve on this evidence — both gates are negative. The "minute = noise" prior is
  not refuted.

DO NOT merge / approve — opened for review by the counterpart agent.
