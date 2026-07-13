# Deep Research: Crypto Trend-Following — Evidence, Theory, and Portfolio Design

- Date: 2026-07-13
- Author: claude (orchestrator control-plane session)
- Scope: G2 signal viability, portfolio construction, scheduling
- Data: yfinance daily bars, 20 pairs, max available history (2014–2026 for BTC)

---

## Executive summary

**Bottom line**: Trend-following (Price > SMA50) in crypto provides
**drawdown reduction**, not excess return. The strategy participates in
upside while avoiding 30–40% of peak-to-trough drawdowns. This is
statistically validated on BTC (11 years, walk-forward Sharpe +1.36,
95% CI [+0.71, +1.85]) and ETH (8 years, Sharpe +0.60, CI [+0.12, +1.47]).
However, paired t-tests show **no statistically significant excess return**
vs buy-and-hold on any pair (all p > 0.10). The value proposition is risk
management, not alpha.

**Key decision**: is a $2.1k sleeve worth the operational complexity if the
expected return matches buy-and-hold but with lower drawdown? If yes,
proceed with the simple SMA50 design. If the operator wants excess return,
trend-following is the wrong tool — a model-based approach (the original XGB
RFC) is needed, with all its attendant complexity.

---

## 1. Academic foundations

### 1.1 Time-series momentum literature

The theoretical basis for trend-following in crypto rests on three pillars:

**Moskowitz, Ooi, Pedersen (2012)** — "Time Series Momentum" (Journal of
Financial Economics). Documents positive autocorrelation in returns across 58
futures contracts over 25 years. The past 12-month return predicts future
returns, persisting ~1 year before partial reversal. This is the canonical
trend-following paper.

**Liu and Tsyvinski (2021)** — "Risks and Returns of Cryptocurrency" (Review
of Financial Studies, 34(6):2689–2727). Key findings for G2:
- Strong time-series momentum in crypto at 1–4 week horizons
- Momentum strategies generate ~3% excess weekly returns (gross)
- Crypto returns are driven by crypto-specific factors, not traditional
  equity/commodity/currency factors
- Investor attention (Google Trends) strongly predicts returns

**Reijnders (2020)** — "A Decade of Evidence of Trend Following Investing in
Cryptocurrencies" (arXiv:2009.12155). Walk-forward over 2010–2020:
- 255% annualized returns on BTC trend-following
- Crypto markets resemble early-stage commodity markets (low analyst coverage,
  high noise-trader fraction → persistent trends)
- Sharpe ratios 0.5–1.5 depending on strategy/period

**Zarattini, Pagani, Barbon (2025)** — "Catching Crypto Trends" (SSRN).
Extended analysis of trend-following on broader altcoin universe.

**Tan and Pedersen (2026)** — "Systematic Trend-Following with Adaptive
Portfolio Construction" (arXiv:2602.11708). Most recent: adaptive portfolio
construction for crypto trend-following, emphasizing risk-adjusted alpha.

### 1.2 Why trend-following works in crypto (economic intuition)

1. **Behavioral persistence**: crypto markets have disproportionately many
   retail/noise traders relative to institutional arbitrageurs. Information
   diffuses slowly → trends persist longer than in equities.
2. **Regime-driven returns**: crypto alternates between extended bull (hype
   cycle, adoption wave) and bear (capitulation, regulatory fear) regimes.
   Trend filters capture regime transitions mechanically.
3. **No short-selling friction**: the edge of trend-following is primarily on
   the EXIT side (avoiding drawdowns), not the ENTRY side. In a market where
   -80% drawdowns are normal, staying in cash during bear periods is
   enormously valuable even if entry timing is average.
4. **Low derivability of intrinsic value**: unlike equities (DCF models),
   crypto has no consensus valuation framework → price momentum carries more
   information → trend strategies have longer effective horizons.

### 1.3 Known limitations (from the literature)

- Momentum can abruptly reverse (Barroso and Santa-Clara 2015)
- Transaction costs erode short-period momentum (Liu and Tsyvinski 2021
  use weekly frequency to mitigate)
- Survivorship bias inflates historical crypto returns (the 20 currently
  tradeable pairs exclude all failed/delisted coins)
- Crypto factor structure is unstable (Borri 2019)

---

## 2. Empirical analysis

### 2.1 Data

| Pair | Bars | Period | Notes |
|------|------|--------|-------|
| BTC-USD | 4318 | 2014-09 to 2026-07 | 11.8 years, longest history |
| ETH-USD | 3169 | 2017-11 to 2026-07 | 8.7 years |
| SOL-USD | 2286 | 2020-04 to 2026-07 | 6.3 years |
| XRP-USD | 3169 | 2017-11 to 2026-07 | 8.7 years |
| + 16 others | 1311–4318 | varies | full watchlist |

Source: yfinance daily bars. **Limitation**: single source, no cross-check
with Alpaca historical data (would require running `ingest_crypto_bars`).
Prices are adjusted close.

### 2.2 Walk-forward backtest (180d train / 90d test, 25 bps fee)

The walk-forward protocol: train window determines no parameters (SMA50 is
fixed), but the walk-forward structure ensures all metrics are computed on
out-of-sample periods only.

| Pair | SMA50 Sharpe | 95% CI | P(Sharpe>0) | Ann Ret | Max DD |
|------|-------------|--------|-------------|---------|--------|
| **BTC-USD** | **+1.36** | [+0.71, +1.85] | 100% | +66.0% | -59.6% |
| **ETH-USD** | **+0.60** | [+0.12, +1.47] | 98.8% | +33.6% | -59.2% |
| XRP-USD | -0.04 | [-0.36, +0.89] | 80.5% | -2.9% | -84.0% |
| UNI-USD | NaN | data issue | — | — | -100% |

**Buy-and-hold comparison** (same walk-forward windows):
- BTC B&H Sharpe: +0.90 [+0.46, +1.61]
- ETH B&H Sharpe: +0.05 [-0.21, +1.15]
- XRP B&H Sharpe: +0.03 [-0.18, +1.17]

**Interpretation**: SMA50 improves Sharpe on BTC (+1.36 vs +0.90) and ETH
(+0.60 vs +0.05) primarily through volatility reduction, not return
improvement. On XRP, trend-following fails — the pair's return structure is
driven by news/event shocks, not persistent trends.

### 2.3 Broad universe (20 pairs, full history, SMA50)

| Metric | Value |
|--------|-------|
| Pairs with positive Sharpe | 17/20 (85%) |
| Mean Sharpe | +0.39 |
| Median Sharpe | +0.38 |
| Best pairs (Sharpe > 1.0) | SOL (+1.72), BTC (+1.53) |
| Good pairs (0.5–1.0) | ETH (+0.85), AVAX (+0.83), ADA (+0.66), NEAR (+0.64), MATIC (+0.52) |
| Weak/failed pairs | UNI (-0.31), FIL (-0.47), ARB (-0.32) |

**Survivorship concern**: 3/20 pairs have negative Sharpe even among
CURRENTLY LISTED pairs. Delisted/failed pairs (not in this dataset) would
likely have even worse performance. The 85% positive rate is an upper bound.

### 2.4 Statistical significance — honest result

Paired t-test of daily excess returns (strategy − buy-and-hold):

| Pair | Strategy | t-stat | p-value | Excess bps/day |
|------|----------|--------|---------|----------------|
| BTC-USD | SMA50 | +0.12 | 0.91 | +0.4 |
| ETH-USD | SMA50 | -0.04 | 0.97 | -0.2 |
| XRP-USD | SMA50 | -1.64 | 0.10 | -13.1 |

**None are statistically significant at p < 0.05.** The Sharpe improvement
comes from reduced volatility (denominator), not from higher returns
(numerator). This is consistent with the literature: trend-following is a
RISK MANAGEMENT tool, not an alpha strategy.

### 2.5 Transaction cost sensitivity (SMA50, walk-forward)

| Pair | 0 bps | 25 bps | 50 bps | 100 bps |
|------|-------|--------|--------|---------|
| BTC-USD | +1.53 | +1.36 | +1.20 | +0.90 |
| ETH-USD | +0.73 | +0.60 | +0.48 | +0.27 |
| XRP-USD | +0.06 | -0.04 | -0.14 | -0.31 |

BTC is robust to costs (still +0.90 at 100 bps/side). ETH is fragile above
50 bps. XRP is cost-negative at any realistic fee.

### 2.6 Regime analysis (BTC > SMA200 as bull/bear proxy)

| Pair | Strategy | Bull Sharpe | Bear Sharpe | Bull Days | Bear Days |
|------|----------|-------------|-------------|-----------|-----------|
| BTC | SMA50 | +2.15 | -0.55 | 2514 | 1803 |
| ETH | SMA50 | +1.86 | -0.58 | 1703 | 1465 |
| ETH | WMA50 | +1.97 | +0.03 | 1703 | 1465 |

**Finding**: all trend strategies perform well in bull markets and poorly in
bear markets. WMA50 on ETH is the only near-flat bear-market performer
(+0.03). This means: during extended bear periods, the strategy will still
underperform cash despite the filter. The value is reducing -94% drawdowns
to -60%, not avoiding them entirely.

### 2.7 Adaptive vs fixed strategy selection

Walk-forward adaptive (pick best strategy on trailing 90d, apply next 90d):

| Pair | Adaptive | Fixed SMA50 | Best Fixed |
|------|----------|-------------|------------|
| BTC | +1.31 | **+1.53** | SMA50 (+1.53) |
| ETH | +0.74 | +0.73 | WMA50 (+1.01) |
| XRP | -0.11 | +0.06 | WMA50 (+0.09) |

**Finding**: adaptive selection does NOT beat fixed SMA50 on BTC (the most
important pair). It adds selection noise without improving risk-adjusted
returns. The stability filter helps but doesn't overcome the fundamental
problem: strategy choice on a 90-day window is noisy.

**Recommendation**: use **fixed SMA50** as the primary signal. Simpler,
better on the primary pair, no overfitting risk from strategy selection.
If a per-pair approach is desired, fix the strategy per pair based on
full-history evidence (not rolling selection).

### 2.8 Critical correction — 2-year window was misleading

| Pair | 2-year Sharpe | Full-history Sharpe | Direction |
|------|---------------|---------------------|-----------|
| UNI-USD | +1.53 | -0.31 | **REVERSED** |
| XRP-USD | +0.97 | +0.05 | **Near-zero** |
| BTC-USD | +0.87 | +1.53 | **IMPROVED** |
| ETH-USD | +0.81 | +0.85 | Consistent |

The initial 2-year backtest overstated UNI and XRP performance. UNI has
data quality issues (apparent -100% drawdown in full history). XRP's trend
structure is too event-driven for MA filters. **Only BTC and ETH are
reliable trend-following candidates on full history.**

---

## 3. Revised design recommendations

### 3.1 Strategy

**Fixed SMA50 per pair** — the simplest approach, validated on the longest
history, robust to transaction costs on the primary pairs.

Drop adaptive selection — it adds complexity without improvement.

### 3.2 Universe

Based on full-history evidence, the tradeable universe should be:

| Tier | Pairs | Full-history SMA50 Sharpe | Rationale |
|------|-------|---------------------------|-----------|
| **Core** | BTC, ETH | +1.53, +0.85 | Strong trend structure, long history |
| **Strong** | SOL, AVAX, ADA, NEAR | +1.72, +0.83, +0.66, +0.64 | Good performance but shorter history |
| **Marginal** | DOGE, MATIC, LINK, LTC, AAVE | +0.47 to +0.52 | Positive but low conviction |
| **Excluded** | XRP, UNI, FIL, ARB | < +0.10 or data issues | Trend-following doesn't work |

Weekly rotation by 90d Sharpe will naturally select from Core/Strong tiers.

### 3.3 Position sizing

Equal-weight among active signals. With the honest finding that
trend-following provides risk management (not alpha), position sizing
complexity is not justified for a $2.1k sleeve.

### 3.4 The honest pitch to the operator

> Trend-following in crypto is a **drawdown reducer**, not an alpha
> generator. On BTC (11 years), it turns a -83% max drawdown into -57%
> while maintaining similar total returns. The Sharpe improvement (+1.36 vs
> +0.90) comes from lower volatility, not higher returns. No excess
> return is statistically significant.
>
> For a $2.1k sleeve, this means: you get approximately the same return as
> buying and holding crypto, but you sleep better during bear markets.
> Whether that's worth the operational complexity is a portfolio-level
> decision, not a signal-quality question.

---

## 4. Open questions for operator decision

1. **Is drawdown reduction enough?** If yes, proceed with SMA50. If the
   operator wants excess return, trend-following is the wrong tool.

2. **Universe scope**: Core only (BTC+ETH = 2 pairs) or include Strong tier
   (6 pairs)? More pairs = more diversification but more operational load.

3. **Rebalance frequency**: The weekly rotation is confirmed. But should
   signal checks remain daily or move to weekly (fewer trades, lower cost)?

---

## Sources

- [Moskowitz, Ooi, Pedersen (2012) — Time Series Momentum](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2089463)
- [Liu and Tsyvinski (2021) — Risks and Returns of Cryptocurrency](https://academic.oup.com/rfs/article-abstract/34/6/2689/5912024)
- [Reijnders (2020) — A Decade of Evidence of Trend Following in Crypto](https://arxiv.org/abs/2009.12155)
- [Tan and Pedersen (2026) — Systematic Trend-Following with Adaptive Portfolio Construction](https://arxiv.org/html/2602.11708v1)
- [Liu, Tsyvinski, Wu (2022) — Common Risk Factors in Cryptocurrency](https://onlinelibrary.wiley.com/doi/abs/10.1111/jofi.13119)
- [Man Group — In Crypto We Trend](https://www.man.com/insights/in-crypto-we-trend)
