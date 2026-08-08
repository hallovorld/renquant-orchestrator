# The pocket layer in return space — rotation loses, styles are directional-only, and cash drag dominates everything

Operator direction (2026-08-08): the goal is a pocket×style capital-allocation
machine judged in RETURN space (net return, drawdown, costs), not
cross-sectional IC. This record is the return-space foundation: every pocket
question answered on the deepest data available, with one visible correction.

Derivation: `data/2026-08-08-pocket-layer-derivation.py` — PROVENANCE ONLY. It
reads the machine-local OHLCV tree (`RenQuant/data/ohlcv/`, 114 names loaded,
1910 trading days 2019-01-02..2026-08-07) and the pinned `sector_map`. TR
returns via `renquant_model_common.total_return.total_return_close` — the
production primitive, not a reimplementation. Numbers below are
`[VERIFIED — script output, 2026-08-08 session]` unless tagged otherwise.

## 1. VISIBLE CORRECTION — the sector-rotation gradient was a sparse-sample mirage

An earlier same-day probe on the label table's sparse date axis (27 evaluable
dates) showed top-1 trailing-momentum rotation at +68.6% annualized and a
clean monotone gradient. **The full 1910-day OHLCV series reverses it:**

| strategy (2024-01..now, daily rebalance, 20 bps/switch) | gross ann | net ann | Sharpe | maxDD |
|---|---|---|---|---|
| universe equal-weight, fully invested | **+33.9%** | **+33.9%** | **2.20** | −18.1% |
| equal-sector | +31.1% | +31.1% | 2.29 | **−15.1%** |
| rotation top-1 (58 switches/yr) | +15.6% | **+4.1%** | 0.41 | −27.2% |
| rotation top-2 (56 switches/yr) | +24.4% | +13.2% | 0.89 | −25.0% |

2019-onward: same shape (top-1 net **−3.2%**). Trailing-momentum pocket
rotation loses to simply holding the diversified book — before costs — and
whipsaw (58 switches/yr) is the mechanism. The 27-date gradient was noise on
n_eff ≈ 1.4. **The rotation line is closed.**

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

Live book, last 63 trading days (2026-05-10..08-07)
`[VERIFIED — live_state_snapshots, best row per date]`:

```
mean cash 78.3%   median 80.6%   min 40.0%   max 94.7%
book $10,962      annual drag at the measured universe return (+33.9%/yr):
                  ≈ $2,911 / year  ≈ 27% of the book
```

In the same window the fully-invested universe ran Sharpe 2.20 with an −18%
max drawdown. **No pocket routing, style switch, or expert family measured
tonight moves returns by a fraction of what sitting 78% in cash costs.** In
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
