# RealizedVolGate: theory + rigorous test of the hard 60% vol cap

2026-06-25. Trigger: the 2026-06-25 daily-full no-trade — `RealizedVolGateTask` dropped
21/97 buy candidates over the 60% annualized-vol cap. Operator: high-vol is opportunity too;
raise the bar, don't freeze — but **with theory and rigorous data, not a hot take**. This is a
research/discussion PR (NO behavior change). It supersedes an earlier, weaker version that
leaned on a survivorship-biased mean.

## 1. Theory — what should govern high vol: a binary gate, or sizing?
- **Kelly / Merton optimal sizing:** the optimal weight is `f* = μ/σ²`. Risk enters
  **continuously** through the variance denominator; there is **no binary admission threshold**
  in optimal theory. A hard cap forces `f*=0` above a line — a discontinuity theory doesn't ask for.
- **Moreira & Muir (2017, J. Finance), "Volatility-Managed Portfolios":** scaling exposure DOWN
  when realized vol is high (∝ 1/σ²) RAISES Sharpe and alpha out of sample. Direct support for
  "size high-vol names down, don't exclude them."
- **The countervailing force — the low-volatility anomaly** (Ang, Hodrick, Xing, Zhang 2006;
  Baker–Bradley–Wurgler 2011; Frazzini–Pedersen "Betting Against Beta" 2014): high idiosyncratic-vol
  / high-beta names earn **lower risk-adjusted** returns. This is the real theoretical case FOR
  penalising vol — but it argues for a continuous penalty (which Kelly `1/σ²` already is), not a
  specific 60% line.
- **Where a hard cap IS justified:** Kelly assumes thin tails; high-vol names have fat tails and
  noisier μ/σ estimates, and can gap (earnings/distress). That argues for a **tail/leverage
  ceiling + fractional Kelly** (both already present: fractional=0.3, vol clip [0.05, 1.50]),
  not an admission gate well below the sizer's own 1.50 clip.

**Synthesis / hypothesis:** with a `1/σ²` sizer downstream, a hard cap *well below* the sizer's
clip is redundant in calm/bull regimes (the sizer already shrinks high-vol names) and should only
bind where the low-vol anomaly bites — **in stress/bear regimes**. So the right design is a
**regime-aware** cap, not a single 60% line. The current gate is **not** regime-aware
(`risk_gates.realized_vol.max_annualized = 0.60`, uniform; an untested "2× Russell median" heuristic).

## 2. Honest data caveat up front — survivorship
Our panel is **291/291 tickers that all survive to 2026** — zero delistings. The high-vol names
that blew up are MISSING, which biases high-vol returns UP. That my raw data shows high-vol
*winning* (contradicting the low-vol anomaly) is itself a red flag. So the test below does NOT
trust the mean; it (a) weights by `1/σ²` (the live sizer), (b) reports drawdown/CVaR/Sortino,
(c) nets transaction costs scaled by vol, (d) **drops the top-1% monthly winners** to kill the
survivor tail, and (e) splits by sub-period incl. the 2022 bear.

## 3. Method
Monthly rebalance; each month take the **top quintile by OOS model score** (pooled purged-WF XGB,
6 cuts/60d embargo, 550k OOS rows); weight **∝ 1/σ²** with the live clip [0.05, 1.50]; forward
1-month **excess** return vs SPY from OHLCV; turnover cost = Σ|Δw|·(5bps + 20bps·vol). Vary ONLY
the cap C ∈ {0.6, 0.8, 1.0, 1.2, 1.5, ∞}. (Proxy ranker, not live PatchTST — see caveats.)

## 4. Results
**Cap sweep (net of cost, excess vs SPY):**

| cap | ann ret | ann vol | **Sharpe** | Sortino | maxDD | CVaR5 | median mo | hit |
|---|---|---|---|---|---|---|---|---|
| **0.60 (current)** | +1.5% | 7.5% | **+0.20** | +0.29 | −15.2% | −4.8% | +0.0012 | 0.53 |
| 0.80 | +4.9% | 7.5% | +0.65 | +1.17 | −13.1% | −3.9% | +0.0028 | 0.58 |
| 1.00 | +5.3% | 7.5% | **+0.70** | +1.25 | −13.8% | −3.9% | +0.0037 | 0.60 |
| 1.20 | +5.2% | 7.4% | +0.70 | +1.23 | −14.0% | −3.8% | +0.0037 | 0.59 |
| 1.50 | +5.4% | 7.6% | +0.71 | +1.26 | −14.0% | −3.8% | +0.0037 | 0.59 |
| ∞ | +5.3% | 7.5% | +0.71 | +1.26 | −14.0% | −3.8% | +0.0037 | 0.59 |

- The **60% cap is the worst point** — Sharpe **+0.20 vs +0.70** at cap ≥1.0. The improvement
  **saturates near 1.0** (no gain beyond).
- It is **NOT a risk-for-return trade**: portfolio vol is flat (~7.5%) and maxDD/CVaR are FLAT-to-
  BETTER when relaxing — because the `1/σ²` sizer keeps high-vol names tiny. The cap removes names
  without removing risk → it just loses diversification and return.

**Robustness — drop the top-1% monthly winners (kills the survivor tail):**

| cap | Sharpe | ann ret | maxDD | median mo |
|---|---|---|---|---|
| 0.60 | +0.10 | +0.8% | −18.0% | +0.0006 |
| 1.20 | +0.60 | +4.4% | −14.9% | +0.0027 |
| ∞ | +0.61 | +4.6% | −15.0% | +0.0027 |

The relaxed cap STILL dominates after removing survivor moonshots, and the **median** month favours
it too — so the result is not a handful of biased tails.

**Sub-periods (Sharpe by cap) — the theoretically-expected regime split:**

| period | 0.6 | 0.8 | 1.0 | 1.2 | 1.5 | ∞ |
|---|---|---|---|---|---|---|
| ≤2019 | 1.59 | 1.63 | 1.63 | 1.64 | 1.64 | 1.64 |
| 2020 | 0.25 | 2.35 | 2.61 | 2.65 | 2.63 | 2.68 |
| **2022 (bear)** | **−0.26** | −0.57 | −0.67 | −0.71 | −0.72 | −0.72 |
| 2023–26 | −0.41 | 0.01 | 0.13 | 0.14 | 0.15 | 0.15 |

Relaxing helps in calm/recovery (huge in 2020) but **the cap HELPS in the 2022 bear** (−0.26 capped
vs −0.72 uncapped). This is exactly the low-vol anomaly biting in stress — theory and data agree.

## 5. Conclusion (theory + data)
- The hard 60% cap **costs large risk-adjusted return in non-bear regimes** and does NOT buy risk
  reduction (the `1/σ²` sizer already controls vol/drawdown). This survives costs, drawdown, and
  the survivor-tail drop. Improvement saturates near a cap of **~1.0** (≈ the Kelly clip), so there
  is no case for "no ceiling."
- **But the cap is protective in bear** (2022). So the right fix is **regime-aware**, not uniform.

## 6. Proposal (to discuss; validate before any deploy)
- Make `risk_gates.realized_vol.max_annualized` **regime-aware**: relax to **~1.0** in
  BULL_CALM / BULL_VOLATILE (let the `1/σ²` sizer manage vol), keep **~0.6** in BEAR (low-vol
  anomaly protection). Reversible config-shaped change; keep a hard ceiling (~1.5) everywhere.
- **Validate before deploy:** re-run with **live PatchTST** scores (not the XGB proxy), confirm
  Kelly clip + concentration caps actually bound the high-vol weights live, then **shadow-test**
  (isolated `alpaca_shadow`) and graduate only if the live Sharpe holds. Do NOT curve-fit the
  per-regime cap to specific names.

## 7. Caveats (still live)
Survivorship is mitigated (drop-top-1%, median) but NOT eliminated — true delisted busts are
absent, so the high-vol edge is still an upper bound. 2022 is a single bear episode (small n).
Proxy ranker, not live PatchTST. Monthly rebalance simplifies the live daily/QP construction.
Repro: `scripts/research_vol_gate_opportunity_cost.py`.
