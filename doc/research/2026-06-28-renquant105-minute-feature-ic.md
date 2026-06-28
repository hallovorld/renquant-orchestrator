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

---

# Monetization under faithful costs — does the short-horizon signal CLEAR cost?

- **Added:** 2026-06-27 (same as-of pin `2026-06-26`). Extends #206.
- **The question (the decisive one, separate from IC):** the 1–3d marginal IC above is
  real, but **does ~0.02–0.03 marginal IC clear realistic round-trip cost at 1–3d
  turnover?** We build the actual cross-sectional portfolio and charge **faithful**
  turnover costs — exactly like the PEAD faithful-cost fix.
- **Reproduce:** `scripts/minute_signal_costtest.py --as-of 2026-06-26 --out /tmp/minfeat2_out`
  (cache-first: reuses #206's `minbars.parquet` WITHOUT Alpaca credentials; reuses
  sighunt's daily `bars.parquet` for forward returns). Writes `costtest_summary.csv`,
  `costtest_perperiod.csv`, `costtest_by_year.json`, `costtest_manifest.json`.

## Method (faithful)

- **Signal:** standardized minute features, PIT as-of each day's close, **entered next
  session**. `vwap_dev` (primary) AND an **equal-weight combo** of {vwap_dev,
  intraday_mom_last, close_loc}, each rank-standardized cross-sectionally per date.
  Feature construction is the **identical #206 code path** (same `build_features`).
- **Portfolios** (cross-sectional, equal-weight): top-decile (10%) and top-quintile
  (20%) **LONG-ONLY** (the monetizable leg under our shorting mandate); top-minus-bottom
  decile **L/S** (dollar-neutral, reported with the shorting-mandate caveat). Rebalanced
  at **1-day AND 3-day** frequency, **non-overlapping** holding periods.
- **Faithful cost:** one-way turnover = `Σ|w_t − w_{t−1}| / 2` from ACTUAL weight changes
  each rebalance; cost per rebalance = `one_way_turnover × round_trip_bps`. **Base 11 bps**
  round-trip; sensitivity **5 / 20 bps**. Net = gross − cost.
- **Breakeven** = round-trip cost (bps) at which net edge = 0 = `gross_per_period /
  one_way_turnover × 1e4`.

## Net economics — read per-period bps + net Sharpe (NOT the annualized headline)

> **Honest-framing note:** these are high-Sharpe SHORT-horizon series. Geometric
> annualization of a +30–110 bps/period return over 252 (1d) or 84 (3d) periods produces
> absurd-looking numbers (e.g. "+240% ann"); they are arithmetically correct but
> **meaningless to quote** — the trustworthy quantities are **per-period bps**, **net
> Sharpe**, and the **breakeven cost**. (Annualized figures are in `costtest_summary.csv`
> for completeness; do not headline them.)

Per-period economics at the **base 11 bps** round-trip (gross/net in bps per rebalance):

| signal | portfolio | step | gross bps | **net@11 bps** | one-way turn | **net Sharpe** | hit | **breakeven RT (bps)** |
|---|---|--:|--:|--:|--:|--:|--:|--:|
| vwap_dev | long-decile | 1d | +58.1 | **+48.9** | 0.84 | **3.71** | 0.62 | **69.5** |
| vwap_dev | long-decile | 3d | +112.8 | **+103.5** | 0.84 | **2.62** | 0.67 | **134.0** |
| vwap_dev | long-quintile | 1d | +37.3 | **+28.9** | 0.76 | **2.97** | 0.60 | **48.9** |
| vwap_dev | long-quintile | 3d | +89.4 | **+81.1** | 0.75 | **2.67** | 0.66 | **118.4** |
| vwap_dev | **L/S decile** | 1d | +39.5 | **+30.2** | 0.84 | **4.09** | 0.60 | **46.8** |
| vwap_dev | **L/S decile** | 3d | +59.8 | **+50.5** | 0.85 | **2.80** | 0.62 | **70.6** |
| combo | long-decile | 1d | +48.2 | **+38.4** | 0.89 | **3.60** | 0.60 | **54.4** |
| combo | long-decile | 3d | +99.8 | **+90.1** | 0.88 | **2.66** | 0.65 | **113.5** |
| combo | long-quintile | 1d | +33.9 | **+25.2** | 0.79 | **3.00** | 0.59 | **42.8** |
| combo | long-quintile | 3d | +72.5 | **+63.9** | 0.78 | **2.36** | 0.64 | **92.8** |
| combo | **L/S decile** | 1d | +30.6 | **+20.8** | 0.89 | **3.65** | 0.58 | **34.4** |
| combo | **L/S decile** | 3d | +54.5 | **+44.8** | 0.89 | **2.79** | 0.61 | **61.6** |

L/S = `0.5×top − 0.5×bottom` (dollar-neutral, gross 2). The **top-minus-bottom decile
spread** (the standard quote) is 2× the L/S row: vwap_dev **+78.9 bps/period gross →
+60.4 net@11** (1d), **+119.6 → +101.0 net@11** (3d).

**Cost sensitivity (net Sharpe @ 5 / 11 / 20 bps round-trip):** every cell stays strongly
positive even at 20 bps. E.g. vwap_dev L/S 1d net Sharpe 4.78 / 4.09 / 3.06; long-decile 3d
2.75 / 2.62 / 2.43. **No cell flips negative anywhere in the 5–20 bps band** — breakevens
(47–134 bps) are 4–12× the base cost.

## Stability — net@11 bps by year (per-period bps, net Sharpe)

| cell | 2024 | 2025 | 2026 (part) |
|---|--:|--:|--:|
| vwap_dev L/S 1d | +33.1 bps (Sh 5.3) | +21.7 (Sh 3.1) | +41.7 (Sh 4.2) |
| vwap_dev L/S 3d | +66.5 bps (Sh 3.9) | +28.5 (Sh 1.8) | +66.6 (Sh 2.7) |
| vwap_dev long-decile 1d | +49.2 bps (Sh 4.2) | +39.1 (Sh 3.0) | +70.8 (Sh 4.3) |
| combo L/S 1d | +22.4 bps (Sh 4.7) | +8.9 (Sh 1.7) | +42.7 (Sh 5.5) |
| combo long-decile 3d | +96.3 bps (Sh 3.1) | +61.5 (Sh 2.1) | +150.5 (Sh 3.3) |

**Every full year (2024, 2025, 2026-to-date) is net-positive in every cell.** The only
negative cells are the 2023 stub (n=5 days, the 22-Dec start) and are statistically empty.
2025 is the weakest year (combo L/S 1d Sh 1.7) but still positive. **The edge survives
across the three regimes in-sample.**

## The honest beta caveat (don't over-claim the long-only number)

The **long-only legs carry market beta**: over this 2024–26 window the universe equal-weight
1d return is **+13.1 bps/day (~rally beta)**. So of vwap_dev long-decile's +58 bps/day gross,
~13 bps is just being long a ripping tech tape and ~45 bps is the cross-sectional tilt. **The
market-neutral L/S decile is the clean alpha read** (+30 bps/day net@11, no beta) — and it is
the one constrained by our shorting mandate. The long-only leg monetizes, but part of its
return is beta you could get from the index; size/attribute it accordingly.

## Verdict — does it MONETIZE? **Yes, decisively, in-sample at every tested cell.**

1. **At 1d rebalance** — high turnover (~0.84 one-way, ~11 names/day traded on a 13-name
   decile), BUT the per-period edge is large enough that it is **NOT cost-killed**: vwap_dev
   long-decile net **+48.9 bps/period @11 bps, Sharpe 3.71**, breakeven **69.5 bps** (6× the
   base cost). Market-neutral vwap_dev L/S net **+30.2 bps, Sharpe 4.09**, breakeven 46.8 bps.
2. **At 3d** — turnover per *rebalance* is barely lower (~0.84; the decile reshuffles almost
   fully over 3 days) BUT each period earns ~2× the return, so **cost-per-day is far lower** →
   breakevens jump to **70–134 bps**. Net Sharpe is a touch lower (2.6–2.8) but cost headroom
   is much larger. **Clears 11 bps net comfortably, long-only AND L/S.**
3. **It clears net-of-cost at ALL tradeable (horizon, cost) cells with positive net Sharpe AND
   regime stability** → on this evidence the short-horizon minute signal is **a genuine
   short-horizon product candidate**, NOT a cost-killed null. The decisive number: **vwap_dev,
   market-neutral L/S, net of 11 bps round-trip = +30 bps/period (1d) / +50 bps/period (3d),
   Sharpe ~4 / ~2.8, breakeven 47 / 71 bps, positive every full year.**

This is the OPPOSITE of the PEAD/fundamentals economics nulls: there the IC died under faithful
cost; here the IC is real **and** the economics clear cost with multiples of headroom.

## What this does NOT prove (do not over-claim)

- **In-sample, 2.5y, single regime, 15-min bars, current-watchlist survivorship.** A net Sharpe
  of ~4 on a 1d signal over one strong-tape regime is a *candidate*, not a deployable book. The
  decisive next gates are **out-of-sample / walk-forward**, a **proper CPCV/DSR** on the
  portfolio (not just the IC), and **execution realism beyond a flat bps** (impact at the
  implied ~11 names/day, borrow for the short leg, queue/fill on a *next-session* entry).
- **Flat round-trip bps is a simplification.** 11 bps is a reasonable large-cap base, but real
  cost is name- and size-dependent; we report 5–20 bps precisely because the point estimate is
  uncertain. The signal clears the whole band, which is the robust claim.
- **Shorting mandate binds the L/S leg.** Our operating model defaults to NO short (very high
  bar); the cleanly-monetizable, beta-free L/S read is therefore **not directly deployable** as
  a long/short book today. The **long-only** leg is deployable but carries the beta noted above.
- **PDT / next-session entry / a different product.** A 1–3d minute sleeve is a *separate*
  product from the multi-day PatchTST primary — same conclusion as #206's IC section.
- **No CPCV/FWER/DSR** (lean mandate). Single faithful-cost portfolio + year-by-year stability +
  cost-sensitivity band. The multiple-cell consistency (12 cells, all net-positive, two signals,
  two horizons) is the informal robustness, not a formal multiple-testing correction.

**Bottom line:** the short-horizon minute signal is **real AND monetizable** net of faithful
11 bps cost — the cleanest "this clears cost" result in the renquant-105 alpha hunt so far. It
is a genuine **short-horizon (1–3d) product candidate** (best cell: vwap_dev, 3d, breakeven
~134 bps). It is **not** yet a deployable book (needs OOS/CPCV/execution realism) and it remains
a **different product** from the multi-day PatchTST primary, with the long-only leg carrying
rally beta and the clean L/S leg constrained by the shorting mandate.
