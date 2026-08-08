# The pocket layer in return space — rotation loses, styles are directional-only, and cash drag dominates everything

Operator direction (2026-08-08): the goal is a pocket×style capital-allocation
machine judged in RETURN space (net return, drawdown, costs), not
cross-sectional IC. This record is the return-space foundation: every pocket
question answered on the deepest data available, with visible corrections.

Derivation: `data/2026-08-08-pocket-layer-derivation.py` — PROVENANCE ONLY. It
reads the machine-local OHLCV tree (`RenQuant/data/ohlcv/`, 114 names loaded,
1910 trading days 2019-01-02..2026-08-07), the pinned `sector_map`, and the
live snapshot table (`RenQuant/data/runs.alpaca.db::live_state_snapshots`,
opened read-only) for the cash window. TR returns via
`renquant_model_common.total_return.total_return_close` — the production
primitive, not a reimplementation. Numbers below are
`[VERIFIED — script output, 2026-08-08 session]` unless tagged otherwise.
Review-r1 corrections are listed visibly in §5.

## 1. VISIBLE CORRECTION — the sector-rotation gradient was a sparse-sample mirage

An earlier same-day probe on the label table's sparse date axis (27 evaluable
dates) showed top-1 trailing-momentum rotation at +68.6% annualized and a
clean monotone gradient. **The full 1910-day OHLCV series reverses it:**

| strategy (2024-01..now, daily rebalance, 20 bps per full-book one-way turn) | gross ann | net ann | Sharpe | maxDD |
|---|---|---|---|---|
| universe equal-weight, fully invested | **+33.9%** | **+33.9%** | **2.20** | −18.1% |
| equal-sector | +31.1% | +31.1% | 2.29 | **−15.1%** |
| rotation top-1 (37 one-way turns/yr) | +15.6% | **+8.2%** | 0.41 | −27.2% |
| rotation top-2 (30 one-way turns/yr) | +24.4% | +18.5% | 0.89 | −25.0% |

Costs are charged on FULL-BASKET one-way turnover (entry/exit weights
included), so second-slot changes in top-2 are charged at their weight
(corrected in review r1 — §5). 2019-onward: same shape (top-1 net **−1.8%**).
Trailing-momentum pocket rotation loses to simply holding the diversified
book — before costs — and whipsaw (37 full-book turns/yr, 86 basket changes)
is the mechanism. The 27-date gradient was noise on n_eff ≈ 1.4. **The
rotation line is closed.**

## 2. Pocket × style, full daily data (2024-01..now, within-pocket top/bottom-3 vs own-pocket EW)

| pocket × style | ann | vs pocket EW | adj t |
|---|---|---|---|
| ai_chip × momentum | **+71.2%** | **+16 pp** | +0.19 |
| ai_chip × reversal | +31.0% | **−24 pp** | −0.26 |
| giant_tech × reversal | +26.9% | −1 pp | +0.03 |
| giant_tech × momentum | +25.4% | −2 pp | −0.03 |

The SIGN pattern matches the operator's intuition precisely: chips are a trend
pocket (momentum beats reversal by ~40 pp/yr there; reversal in chips is
poison), giant_tech is style-indifferent. **No cell clears any significance
bar** (all |t| < 0.3 after n_eff adjustment). These magnitudes are policy
inputs the operator may act on; they are not statistical conclusions, and the
multiple-comparison caveat (4 cells shown, more implied) applies in full.

## 3. The convergent finding: cash drag dominates every pocket question

Live book, last 63 snapshot dates (2026-05-12..08-07)
`[VERIFIED — script output §LIVE-CASH WINDOW; best row per date = max portfolio_value]`:

```
mean cash 77.3%   median 79.9%   min 39.9%   max 94.7%
book $10,962      annual drag at the LONG-RUN universe return
                  (+33.9%/yr, 2024-01..now — a long-run proxy, not same-window):
                  ≈ $2,872 / year  ≈ 26% of the book
```

Over exactly those 63 cash dates the fully-invested universe ran **+40.2%
annualized, Sharpe 3.04, maxDD −2.8%** `[VERIFIED — script output]` — so the
long-run +33.9% anchor is the conservative choice for the drag estimate; at
the same-window rate the drag would be ≈ $3,406/yr (≈ 31% of the book).
**No pocket routing, style switch, or expert family measured
tonight moves returns by a fraction of what sitting 77% in cash costs.** In
the operator's own return-space judgement, capital deployment (G-E, task #24:
wash-sale mass block, integer-share floor, anti-high-price tilt — all three
already measured) is the P0.

## 4. Standing state of the pocket×style machine

* Rotation: closed (§1).
* Within-pocket styles: directional magnitudes recorded (§2), statistically
  unresolved; any activation is a policy call, and the honest instrument is a
  SHADOW lane, not a backtest claim.
* Expert families: the library holds two families (XGB ×2, momentum clocks
  ×2). Value/reversal families do not exist yet; §2's giant_tech row shows no
  urgency to build them for that pocket.
* The §10 gate machinery and the bt#110 emitter remain the confirmation path
  for any future pocket×style candidate that graduates from policy to claim.

## 5. Corrections (review r1, 2026-08-08) — visible per LONG #10

1. **Same-window claim removed.** v1 stated the universe ran "Sharpe 2.20 /
   maxDD −18% in the same window" as the cash measurement; those figures are
   the 2024-01..now long-run numbers, not the cash window. The benchmark is
   now computed over exactly the 63 snapshot dates (+40.2% ann / Sharpe 3.04 /
   maxDD −2.8%), and the drag estimate's +33.9% anchor is explicitly labelled
   a long-run proxy (conservative vs the same-window rate).
2. **Top-K rotation cost model corrected.** v1 charged 20 bps per first-pick
   switch (`idxmax`), which missed second-slot/basket-membership changes in
   top-2 AND inflated the switch count via warmup-NaN rows. Costs are now
   charged on full-basket one-way turnover with entry/exit weights. Net
   figures moved: top-1 +4.1% → +8.2%, top-2 +13.2% → +18.5% (2024-01..now);
   2019-onward top-1 −3.2% → −1.8%. Every corrected variant still loses to
   the fully-invested universe (+33.9% net) — the §1 conclusion is unchanged.
3. **Cash stats re-measured inside the committed derivation.** v1's cash
   figures (mean 78.3%, window "2026-05-10..") came from an ad-hoc session
   query outside the script. The committed script now computes them
   deterministically (best row per date = max portfolio_value): mean 77.3%,
   median 79.9%, min 39.9%, max 94.7%, window 2026-05-12..08-07; drag
   ≈ $2,911 → ≈ $2,872/yr at the long-run anchor.
