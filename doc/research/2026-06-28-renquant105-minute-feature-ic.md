# renquant-105 — does MINUTE data carry cross-sectional IC? (CHEAP GATE — corrected, honest null)

- **Date:** 2026-06-28. First cut run as-of `2026-06-26`; **corrected** re-run as-of pin
  `2026-06-25` (the cached panel's last full session).
- **Scope:** READ-ONLY. TEST whether minute-derived cross-sectional features carry Spearman
  rank-IC on the renquant-104 single-name universe — standalone AND **marginal over the 5
  daily price factors** — at short (1d/3d) and multi-day (5d/20d) horizons, **measured from a
  next-session tradable entry**, with a **chronological out-of-sample holdout**. Cheap gate
  BEFORE any heavy "PatchTST-on-minute" experiment. Not a backtest, not a promotion.
- **Verdict (one line):** **NULL.** After fixing a DST-contaminated RTH filter, an optimistic
  same-close entry, and an invalid "marginal IC" calc, **no minute feature carries marginal
  cross-sectional IC over the daily price factors at 1d/3d** (or any horizon) — and **zero
  candidates survive the OOS holdout**. The earlier "short-horizon edge, net Sharpe ~4" was an
  **artifact of the three bugs**, not a real effect. The "minute data is noise" prior is **not
  refuted** on this evidence.
- **Reproduce:** `scripts/minute_feature_scan.py --as-of 2026-06-25 --out /tmp/rq206f_out`
  (cache-first: reads `minbars.parquet` WITHOUT Alpaca credentials; add `--refresh` to re-pull).
  Writes `results.csv`, `marginal_placebo_floor.json`, `oos_winners.json`, `manifest.json`.

## Why the first cut was wrong (the 4 corrected bugs, from the #206 review)

| # | First cut (WRONG) | Corrected |
|---|---|---|
| 1 | RTH = fixed **UTC 13:30–21:00 union** | DST-correct: bars filtered to each session's **`[open, close)` from the XNYS exchange calendar** (09:30–16:00 LOCAL, half-days truncated) |
| 2 | Forward return from **close[D]** (signal known only *after* close[D] → look-ahead) | **Next-session entry:** enter `open[D+1]`, ret = `close[D+h]/open[D+1] − 1` |
| 3 | "Marginal IC" = residualize the **return only**, correlate with the **RAW** feature (invalid partial) | Proper **FWL**: residualize BOTH feature and return on the SAME 5 controls, correlate residuals |
| 4 | Standalone shuffle floor reused for the marginal claim | **Separate marginal placebo** built on the residualized feature vs residualized return |
| 5 | "real edge / prior refuted" on the same 627-session sample | **Chronological 70/30 OOS holdout**; winners selected on discovery, reported on the untouched holdout |

**The DST filter was not cosmetic.** It admitted **290,917 bars (11.8% of the kept rows)** that
were **pre-market** (08:30–09:30 ET in EST) or **after-hours** (16:00–17:00 ET in EDT), and
those bars *created* the apparent VWAP/close-location signal. The corrected filter also truncates
the 6 half-days in the window (early close 13:00 ET: 2024-07-03, 11-29, 12-24; 2025-07-03, 11-28,
12-24) to 14 RTH bars instead of 26.

## The decomposition — where the headline went (vwap_dev, 1d, marginal IC)

Re-running ONLY the vwap_dev 1d marginal IC, adding one fix at a time (full 626-date sample):

| variant | marginal IC | NW t |
|---|--:|--:|
| **OLD** (fixed-UTC RTH + close-entry + invalid-FWL) — reproduces the headline | **+0.0279** | **5.10** |
| + DST-correct RTH only | **−0.0151** | −2.86 |
| + next-session entry | +0.0020 | 0.36 |
| + proper FWL (FULL FIX) | **+0.0004** | **0.07** |

The "+0.028 t=5.2" headline was the product of all three bugs. **DST-correct RTH alone flips the
sign** (the signal lived in the contaminated pre/after-hours bars); **next-session entry** kills
what's left; **proper FWL** confirms ~zero. This is a clean null, not a shrunk edge.

## Data window

- **Universe:** 134 renquant-104 golden single names (8 ETFs dropped from 142); shared kept-symbol
  set with `sighunt.py` (`kept_symbols_sha256 = 7f9687c4a01b`).
- **Minute granularity: 15-minute bars** (not 1-minute; the principal data caveat — see below).
- **Window:** DST-correct RTH bars **2023-12-22 → 2026-06-25**, **627 sessions**, **2,174,757 RTH
  rows** (down from 2,465,674 under the old filter — the 290,917-row contamination removed).
- **OOS split:** chronological on signal-sessions — **DISCOVERY = first 438** (≤ 2025-09-23),
  **OOS holdout = last 189** (≥ 2025-09-24).
- **Labels / daily factors:** reuse `sighunt`'s daily split/div-adjusted close panel for forward
  returns and the 5 daily factors (mom_12_1, mom_6_1, st_rev_21, ma200_dist, pct_52w_high). The
  next-session **open** is derived from the corrected RTH minute bars (first RTH bar's open).

## Results — DISCOVERY, proper-FWL marginal IC at 1d/3d (the horizons in question)

Marginal placebo floor (`|mean_ic|` 95th pct): **DISCOVERY h1=0.0077, h3=0.0146**.
"marg clears" = `|marg_IC| > floor`. A real, usable short-horizon edge would need a **positive**
marginal IC clearing the floor with a NW t ≥ 3.

| feature | h | marg_IC | marg t | marg clears | standalone IC | standalone t |
|---|--:|--:|--:|:--:|--:|--:|
| vwap_dev | 1 | **+0.0017** | 0.23 | ✗ | −0.0029 | −0.30 |
| intraday_mom_last | 1 | −0.0059 | −0.94 | ✗ | −0.0090 | −1.16 |
| close_loc | 1 | +0.0049 | 0.74 | ✗ | +0.0020 | 0.25 |
| amihud_illiq | 1 | +0.0070 | 1.23 | ✗ | +0.0120 | 1.90 |
| overnight_gap | 1 | −0.0108 | −1.36 | ✓† | −0.0183 | −1.65 |
| range_pct | 1 | −0.0102 | −1.34 | ✓† | −0.0045 | −0.40 |
| open_range | 1 | −0.0077 | −1.13 | ✓† | +0.0013 | 0.12 |
| intraday_rvol | 1 | −0.0053 | −0.64 | ✗ | −0.0035 | −0.28 |
| vwap_dev | 3 | +0.0173 | 1.62 | ✗ | +0.0279 | 1.96 |
| intraday_mom_last | 3 | +0.0112 | 1.05 | ✗ | +0.0201 | 1.64 |
| close_loc | 3 | +0.0096 | 1.00 | ✗ | +0.0198 | 1.65 |
| overnight_gap | 3 | +0.0206 | 1.73 | ✓† | +0.0338 | 1.98 |
| intraday_rvol | 3 | +0.0166 | 1.20 | ✓† | +0.0375 | 1.82 |

† The only cells that "clear" the marginal floor at 1d/3d do so with **|t| < 1.8** and several
with the **wrong (negative) sign** — none meets a positive-marg + t≥3 winner bar. The three
ex-headliners (vwap_dev / intraday_mom_last / close_loc) are now **at or near zero** at 1d
(t = 0.23 / −0.94 / 0.74). vwap_dev 3d is the best survivor at +0.017 (t=1.62) and still does
**not** clear its floor. Full 8×4 table (discovery + OOS) in `results.csv`.

## OOS holdout — does any DISCOVERY winner survive?

**Winner-selection on DISCOVERY (positive marginal IC, clears floor, NW t ≥ 3 at 1d/3d): ZERO
features qualify.** There is nothing to carry into OOS. (`oos_winners.json` is an empty list.)

For completeness, the OOS holdout (189 sessions) was scanned with the same features: a couple of
isolated cells clear their (wider) OOS floor — e.g. amihud_illiq 1d marg +0.015 (t=1.67),
intraday_mom_last 5d marg +0.049 (t=3.39) — but none corresponds to a discovery winner, none is
the 1d/3d vwap_dev/close_loc cluster the first cut claimed, and at 5d/20d the OOS n is 9–37
non-overlapping dates (too thin to weigh). **No discovery → OOS survival path exists.**

## 5d / 20d (the actual renquant-105 multi-day objective)

Same as the first cut's *direction* but now also clean: **no minute feature carries marginal IC
over the daily factors at 5d or 20d** that survives both the marginal placebo and the thin-sample
caveat. The multi-day null is, if anything, more robust now (the contaminated bars had inflated
the standalone vol/range cells). **Feeding 15-min bars to a multi-day PatchTST would re-encode
what the daily price factors already carry.**

## Does this justify a PatchTST-on-minute experiment? **NO.**

- **For the renquant-105 MULTI-DAY trend goal:** NO — no marginal multi-day IC (unchanged
  conclusion, now on clean data).
- **For a short-horizon (1–3d) sleeve:** also NO, on this evidence. The 1–3d "edge" that
  motivated a separate short-horizon discussion **evaporated** under DST-correct RTH + next-session
  entry + proper FWL. There is no floor-clearing, OOS-surviving, next-tradable marginal signal to
  build a minute-aware model around.

## Caveats (unchanged; they do not rescue the null)

- **15-min, not 1-min.** Finer 1-min order-flow / tick imbalance is unmeasured. But the gate
  question — *does minute data carry next-tradable, marginal cross-sectional IC?* — is answered
  negatively here; finer bars are a separate, heavier pull and would have to overcome a clean null.
- **Bounded 2.5y single-regime window; current-watchlist survivorship.**
- **Lean mandate:** one marginal placebo floor + NW t + one chronological OOS holdout. No
  CPCV/FWER/DSR — and none is needed to read a null.
- READ-ONLY: no canonical paths written, no orders, no live-tree git.

---

# Execution economics — does the short-horizon signal monetize from a next-tradable entry?

- **Added:** 2026-06-28 (same as-of pin `2026-06-25`). Extends #206; **corrected** for the same
  three bugs (DST-correct RTH, **next-session-open entry**, OOS holdout).
- **The question:** with a real `open[D+1]` entry and faithful turnover cost, does the
  **market-neutral L/S** (the clean, beta-free read) monetize? (The IC scan already says the
  marginal signal is ~0, so this is the economic confirmation.)
- **Reproduce:** `scripts/minute_signal_costtest.py --as-of 2026-06-25 --out /tmp/rq206f_out`.
  Writes `costtest_summary.csv`, `costtest_perperiod.csv`, `costtest_by_year.json`,
  `costtest_manifest.json`.

## Method (faithful, next-session entry)

- **Signal:** `vwap_dev` and an equal-weight combo of {vwap_dev, intraday_mom_last, close_loc},
  rank-standardized per date — identical #206 feature path, now DST-correct.
- **Entry:** the next session's **open** (`open[D+1]`); per-period return = `close[D+step]/open[D+1]
  − 1`, non-overlapping, 1-day and 3-day rebalance.
- **Portfolios:** top-decile / top-quintile **long-only** and top-minus-bottom decile
  **market-neutral L/S** (dollar-neutral — the clean read).
- **Faithful cost:** one-way turnover = `Σ|w_t−w_{t−1}|/2`; round-trip **5 / 11 / 20 bps**
  sensitivity; net = gross − cost. Breakeven = round-trip at which net = 0. Reported full-window
  AND on the OOS holdout, with active-day exposure (1.0 — always invested).

## Net economics — MARKET-NEUTRAL L/S (the clean, beta-free read)

| window | signal | step | gross ann | **net ann @11 bps** | **net Sharpe @11** | one-way turn | breakeven RT (bps) |
|---|---|--:|--:|--:|--:|--:|--:|
| full | vwap_dev | 1d | −6.2% | **−25.9%** | **−2.34** | 0.85 | **−3.0** |
| full | vwap_dev | 3d | +12.0% | +3.6% | +0.28 | 0.85 | 15.9 |
| full | combo | 1d | −2.9% | **−24.1%** | **−2.74** | 0.89 | **−1.3** |
| full | combo | 3d | +15.1% | +6.1% | +0.57 | 0.88 | 19.1 |
| **OOS** | vwap_dev | 1d | −6.9% | **−26.7%** | **−2.17** | 0.86 | **−3.3** |
| **OOS** | vwap_dev | 3d | −1.7% | **−9.2%** | **−0.77** | 0.86 | **−2.4** |
| **OOS** | combo | 1d | −3.6% | **−24.7%** | **−2.50** | 0.89 | **−1.6** |
| **OOS** | combo | 3d | +18.4% | +9.2% | +0.79 | 0.88 | 22.8 |

- **1d L/S: gross is NEGATIVE before any cost** (−3% to −7%/yr; net Sharpe −2.2 to −2.7). No edge —
  the breakeven cost is *negative* (you lose at zero cost). Hard fail, full window AND OOS.
- **3d L/S:** the only positive cells are the full-window combo (+6%/yr, Sharpe 0.57) and combo
  OOS (+9%/yr, Sharpe 0.79) — but **vwap_dev 3d goes negative out-of-sample** (−9%/yr, Sharpe
  −0.77). One signal's one horizon's L/S barely clearing 11 bps in one thin holdout (62
  non-overlapping periods) is **not a monetizable edge** — it is exactly the marginal-IC-≈0 result
  expressed in dollars, and it does not replicate across the two signals.

## The beta trap (why the long-only legs look "good" and aren't)

The long-only legs post large positive annualized numbers (e.g. combo 3d long-quintile +75–102%
by year), but that is **market beta**: over this 2024–26 tech rally the universe is up hard, and a
long-only book is mechanically long the tape. The **market-neutral L/S strips that out — and it is
negative at 1d and not robust at 3d.** The clean read is the verdict: there is **no beta-free
short-horizon alpha** here.

## Verdict — does it MONETIZE? **NO.**

1. **1d** — no gross edge at all (negative before cost), market-neutral net Sharpe ≈ −2.3,
   full-window and OOS. The original "+30 bps/day net, Sharpe ~4" was the DST-contamination +
   close-entry artifact; it is gone.
2. **3d** — at best a single signal (combo) clears 11 bps in one thin OOS holdout (+9%/yr, Sharpe
   0.79), while the other signal (vwap_dev) is negative OOS. Not robust, not a product.
3. The IC scan (marginal ≈ 0, zero OOS survivors) and the economics (market-neutral L/S negative
   at 1d, fragile at 3d) **agree**: the corrected short-horizon minute signal is a **null**, not a
   monetizable edge.

**Bottom line:** this is another **honest null**, in the same family as the PEAD / fundamentals
nulls — except here the IC itself was a bug artifact (DST + look-ahead + invalid partial), not a
real-but-cost-killed effect. **Do NOT spin up a PatchTST-on-minute experiment for renquant-105 (or
for a short-horizon sleeve) on this evidence.** The "minute = noise" prior is not refuted.
