# Progress: G2 Crypto Trend-Follow Portfolio Design (v3)

- Date: 2026-07-13
- Branch: `design/crypto-trend-portfolio`
- Goal: G2 — Alpaca crypto trading sleeve

## What changed

Rewrote the G2 crypto design from "adaptive per-pair strategy selection" (v2)
to **fixed SMA50 trend filter** (v3), driven by deep end-to-end research.

### Deep research conducted

Walk-forward backtests (180d train / 90d test) with bootstrap 95% CI, 1000
resamples, on max available history (BTC: 11.8 years, ETH: 8.7 years). Seven
analyses:

1. **Walk-forward with CI**: BTC SMA50 Sharpe +1.36 [+0.71, +1.85], ETH +0.60
2. **Transaction cost sensitivity**: BTC robust at 100 bps (+0.90)
3. **Regime analysis**: all strategies fail in bear; bull Sharpe +2.15
4. **Statistical significance**: NO excess return vs B&H (all p > 0.10)
5. **Drawdown reduction**: BTC MaxDD -83% → -57% (31% reduction)
6. **Adaptive vs fixed**: adaptive LOSES to fixed SMA50 (+1.31 vs +1.53)
7. **Broad universe**: 17/20 (85%) pairs positive, mean Sharpe +0.39

### Key design changes (v2 → v3)

- **Signal**: adaptive per-pair selection → fixed SMA50 (simpler, empirically better)
- **Universe**: 20 pairs → 16 pairs (XRP/UNI/FIL/ARB excluded as trend fails)
- **Value proposition**: reframed from "alpha" to "drawdown reduction" (honest)
- **Academic backing**: Moskowitz-Ooi-Pedersen, Liu-Tsyvinski, Reijnders, Tan-Pedersen

### Deliverables in this PR

- `doc/design/2026-07-13-crypto-trend-portfolio.md` — updated design (v3)
- `doc/research/2026-07-13-crypto-trend-following-deep-research.md` — full research memo

## Operator decision needed

The research shows trend-following provides **drawdown reduction, not excess
return**. No excess return is statistically significant. The question for the
operator is: is a $2.1k sleeve that delivers the same return as buy-and-hold
but with -30% less drawdown worth the operational complexity?

## Status

Design ready for review. Implementation blocked on operator go/no-go (per
the "crypto回测数据很差的话就没必要做了" gate).
