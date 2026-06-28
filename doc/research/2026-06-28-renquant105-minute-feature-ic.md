# renquant-105 — does MINUTE data carry cross-sectional IC? (CHEAP GATE, for discussion)

- **Date:** 2026-06-28 (run as-of pin `2026-06-26`).
- **Scope:** READ-ONLY. Directly TEST whether minute-derived cross-sectional features
  carry Spearman rank-IC on the renquant-104 single-name universe, at SHORT (1d/3d) AND
  multi-day (5d/20d) horizons, standalone AND marginal-over-the-daily-price-factors. This
  is the **cheap gate BEFORE** any heavy "PatchTST-on-minute" experiment in renquant-model.
  Not a backtest, not a promotion recommendation, not a model change.
- **Verdict (one line):** **Minute data DOES carry real, floor-clearing, marginal-over-daily
  cross-sectional IC — but ONLY at SHORT horizons (1d/3d), and it DECAYS to noise by 5d and
  is NULL (after residualization) at 20d.** So the genuine angle is short/intraday-adjacent,
  NOT the multi-day renquant-105 trend goal.
- **Reproduce:** `scripts/minute_feature_scan.py --as-of 2026-06-26 --out /tmp/minfeat_out`
  (cache-first: reads `minbars.parquet` WITHOUT Alpaca credentials; add `--refresh` to re-pull).
  Every run writes `results.csv`, `placebo_floor.json`, `manifest.json`.

## Data window used (state it plainly)

- **Universe:** 134 renquant-104 golden single names (8 ETFs dropped from 142), shared
  kept-symbol set with `sighunt.py` (`kept_symbols_sha256 = 7f9687c4a01b`).
- **Minute granularity: 15-minute bars** (NOT 1-minute). Reason: 1-min over 134 names ×
  ~2.5y RTH is ~26M rows — too large/rate-limit-prone to pull for a *gate*. 15-min (26 RTH
  bars/day) is ample for the 8 features below. This is the principal data caveat.
- **Window:** RTH bars **2023-12-22 → 2026-06-25**, **627 sessions**, 2,465,674 RTH rows
  (3,635,496 raw before RTH filter). RTH = 13:30–21:00 UTC union window (pre-market excluded).
- **Labels / daily factors:** reuse `sighunt`'s daily split/div-adjusted close panel
  (`bars.parquet`, 2030d × 134n) for forward 1d/3d/5d/20d returns and the 5 daily price
  factors (mom_12_1, mom_6_1, st_rev_21, ma200_dist, pct_52w_high). PIT: every feature for
  day D uses only bars ≤ D's close; labels are `close.shift(-h)`, strictly future.

## Features (8, PIT, as-of each day's close)

intraday realized vol (Σ squared 15-min log-returns); last-2-bar (~30-min) momentum;
opening-range (first-2-bar return); VWAP deviation (close vs volume-weighted day VWAP);
overnight gap (open vs prev daily close); intraday range %; close-location-in-range; an
Amihud-style illiquidity proxy (|day return| / dollar-volume). All have ~full coverage
(84,018 non-null cells each = 627 × ~134).

## Method

Per feature, per day: cross-sectional Spearman rank-IC vs forward return. Headline IC + NW
t-stat computed on **NON-overlapping** rebalance dates (step == horizon) so daily-IC samples
are ~independent (naive-overlap IC also in `results.csv`). **Marginal IC** = IC of the
feature vs the forward return **residualized cross-sectionally on the 5 daily price factors**
(per-date OLS on rank-standardized factors) — i.e. signal NOT already in the daily factors.
**Placebo floor** = within-date label shuffle, 200 perms, `|mean_ic|` 95th pct.

## Results — feature × horizon IC (standalone + marginal over daily factors)

Placebo `|mean_ic|` 95th-pct floor: **h1=0.0067, h3=0.0117, h5=0.0151, h20=0.0302**.
"clears" = |mean_ic| > floor. n_obs = non-overlapping rebalance dates.

| feature | h | n | mean_IC | NW t | IC/floor | clears | **marg_IC** | marg t | marg/floor | **marg clears** |
|---|--:|--:|--:|--:|--:|:--:|--:|--:|--:|:--:|
| **vwap_dev** | 1 | 627 | **+0.0351** | 4.17 | 5.28 | ✓ | **+0.0282** | **5.16** | 4.24 | **✓** |
| **intraday_mom_last** | 1 | 627 | **+0.0261** | 4.60 | 3.93 | ✓ | **+0.0189** | **4.50** | 2.84 | **✓** |
| **close_loc** | 1 | 627 | **+0.0232** | 3.30 | 3.49 | ✓ | **+0.0160** | **3.28** | 2.41 | **✓** |
| intraday_rvol | 1 | 627 | +0.0162 | 1.53 | 2.44 | ✓ | −0.0033 | −0.65 | 0.50 | ✗ |
| amihud_illiq | 1 | 627 | +0.0158 | 2.94 | 2.37 | ✓ | +0.0086 | 1.85 | 1.30 | ✓ |
| range_pct | 1 | 627 | +0.0131 | 1.31 | 1.97 | ✓ | −0.0074 | −1.41 | 1.12 | ✓ |
| open_range | 1 | 627 | −0.0072 | −1.10 | 1.08 | ✓ | −0.0121 | −2.88 | 1.81 | ✓ |
| overnight_gap | 1 | 627 | −0.0045 | −0.46 | 0.67 | ✗ | +0.0048 | 0.93 | 0.72 | ✗ |
| **vwap_dev** | 3 | 209 | **+0.0537** | 4.41 | 4.61 | ✓ | **+0.0296** | **3.32** | 2.54 | **✓** |
| **close_loc** | 3 | 209 | **+0.0383** | 3.62 | 3.28 | ✓ | +0.0202 | 2.39 | 1.73 | ✓ |
| **intraday_mom_last** | 3 | 209 | **+0.0347** | 4.73 | 2.98 | ✓ | **+0.0241** | **4.20** | 2.06 | **✓** |
| overnight_gap | 3 | 209 | +0.0345 | 2.12 | 2.96 | ✓ | +0.0164 | 1.95 | 1.40 | ✓ |
| intraday_rvol | 3 | 209 | +0.0291 | 1.88 | 2.50 | ✓ | −0.0017 | −0.21 | 0.15 | ✗ |
| range_pct | 3 | 209 | +0.0230 | 1.50 | 1.97 | ✓ | −0.0014 | −0.19 | 0.12 | ✗ |
| amihud_illiq | 3 | 209 | +0.0163 | 2.16 | 1.40 | ✓ | +0.0125 | 2.07 | 1.07 | ✓ |
| open_range | 3 | 209 | −0.0123 | −0.97 | 1.06 | ✓ | −0.0128 | −1.53 | 1.09 | ✓ |
| intraday_rvol | 5 | 125 | +0.0397 | 2.02 | 2.62 | ✓ | +0.0064 | 0.79 | 0.42 | ✗ |
| range_pct | 5 | 125 | +0.0265 | 1.33 | 1.75 | ✓ | +0.0007 | 0.08 | 0.05 | ✗ |
| amihud_illiq | 5 | 125 | +0.0094 | 0.73 | 0.62 | ✗ | +0.0101 | 1.00 | 0.67 | ✗ |
| (all others h5) | 5 | 125 | ≤ floor | | <1.5 | ✗ | ≤ floor | | <0.5 | ✗ |
| overnight_gap | 20 | 31 | −0.0848 | −2.01 | 2.81 | ✓ | −0.0483 | −1.59 | 1.60 | ✓† |
| intraday_rvol | 20 | 31 | +0.0762 | 1.86 | 2.52 | ✓ | +0.0074 | 0.41 | 0.25 | ✗ |
| range_pct | 20 | 31 | +0.0639 | 1.76 | 2.12 | ✓ | −0.0025 | −0.17 | 0.08 | ✗ |
| amihud_illiq | 20 | 31 | +0.0373 | 2.32 | 1.23 | ✓ | +0.0265 | 1.58 | 0.88 | ✗ |
| (others h20) | 20 | 31 | ≤ floor | | <1 | ✗ | ≤ floor | | <0.6 | ✗ |

† the only "marginal-clears" at 20d is overnight_gap, but with **n=31** non-overlapping obs,
NW t=−1.6 (not significant), and it is a *daily* gap (open vs prev close), not really a
"minute microstructure" feature — discount it.

## Honest verdict (blunt)

1. **YES, minute data carries cross-sectional IC at SHORT horizons (1d/3d).** Three features —
   **VWAP deviation, last-30-min momentum, close-location-in-range** — clear the shuffle floor
   by 2.4–5.3× AND survive residualization on the daily price factors with NW t-stats of
   3.3–5.2. **vwap_dev** is the standout (1d marginal IC +0.028, t=5.2; 3d marginal +0.030,
   t=3.3). This is a *genuine, non-redundant, short-horizon* signal — economically a
   close-vs-VWAP / late-session-drift reversal-continuation effect. **The "minute data is
   noise" prior is REFUTED at short horizons.**

2. **NO robust MARGINAL multi-day IC.** By 5d, every minute feature's *marginal* IC over the
   daily factors is below floor (best marg/floor = 0.67). At 20d the only standalone clears are
   vol/range/illiquidity — but their **marginal** IC over daily factors is ~zero (rvol marg/floor
   0.25, range 0.08), i.e. they are subsumed by the daily price factors. n=31 at 20d is also too
   thin to trust. **Minute features do NOT add exploitable multi-day cross-sectional signal here.**

3. **Decay is monotonic and sharp:** the marginal short-horizon edge (1d/3d, t>3) is essentially
   gone by 5d. This is exactly the microstructure-reversal signature — real but fast-decaying.

## Does this justify a PatchTST-on-minute experiment in renquant-model?

- **For the renquant-105 MULTI-DAY trend goal: NO, not on this evidence.** Minute features add
  no robust marginal IC at 5d/20d. Feeding 15-min bars to a multi-day PatchTST would be
  re-encoding information the daily price factors already carry. This gate does NOT justify the
  heavy experiment *for the multi-day objective*.
- **For a SHORT-HORIZON (1–3d) sleeve: the data says there IS a real, marginal edge** (vwap_dev /
  last-30-min-mom / close_loc). IF renquant ever pursues a separate short-horizon book, a
  minute-aware model would be justified to TEST. But note the operating-model context: short
  horizons mean higher turnover/cost and PDT constraints (see `shorting-mandate` / win-rate
  memory), and PatchTST is currently the *multi-day* primary — a 1–3d minute model is a
  different product, not a drop-in renquant-105 upgrade. **Recommendation: do NOT spin up
  PatchTST-on-minute for renquant-105 multi-day; the cheap-gate answer for the 105 goal is
  negative. The short-horizon signal is real and worth a separate, explicitly-scoped discussion.**

## Caveats (do not over-claim)

- **15-min, not 1-min:** finer microstructure (1-min order-flow, tick imbalance) is unmeasured;
  a 1-min pull could surface more, but the *gate* question (does minute data carry CS IC) is
  answered positively at short horizons and negatively-marginal at multi-day — finer bars would
  not rescue the *multi-day* null.
- **Bounded recent window (2.5y, 2023-12→2026-06):** one macro regime mix; survivorship from
  applying the current watchlist back. Short-horizon signals are notoriously regime/cost-sensitive.
- **No cost model:** IC ≠ net P&L. A +0.03 1d IC at 134-name cross-section is real but small;
  whether it beats round-trip cost at the implied turnover is NOT tested here (out of gate scope).
- **No CPCV/FWER/DSR** (per the lean mandate): single placebo floor + NW t + marginal residual
  only. Treat the multiple-comparison across 8×4 cells informally — the short-horizon vwap_dev /
  mom_last / close_loc cluster is consistent and individually strong (t>3 marginal), not a lone
  lucky cell.
- This is a **diagnostic gate**, not a backtest and not a promotion. No canonical paths written,
  no orders, no live-tree git.
