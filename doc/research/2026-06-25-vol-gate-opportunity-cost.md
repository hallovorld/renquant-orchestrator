# RealizedVolGate: EXPLORATORY diagnostic on the hard 60% vol cap

2026-06-25. Trigger: the 2026-06-25 daily-full no-trade — `RealizedVolGateTask` dropped
21/97 buy candidates over the 60% annualized-vol cap. Operator: high-vol is opportunity too;
raise the bar, don't freeze — but with theory + rigorous data. **This is EXPLORATORY evidence
only — NOT a config proposal.** An earlier version of this PR over-claimed a "regime-aware
rule"; that claim is withdrawn (it was based on a calendar split, not the regime label, and
does not survive proper uncertainty). Superseded after Codex review.

## 1. Theory (kept honest)
- **Kelly / Merton:** optimal weight `f* = μ/σ²` — vol enters sizing **continuously**; there is
  no binary admission threshold in optimal theory. A hard cap forces `f*=0` above a line.
- **Low-volatility anomaly / BAB** (Ang 2006; Baker 2011; Frazzini–Pedersen 2014): high
  idiosyncratic-vol / high-beta names earn **lower risk-adjusted** returns. This is the real
  theoretical case FOR penalising vol — but as a *continuous* penalty (which Kelly `1/σ²`
  already is), not specifically a 60% admission line.
- **Moreira–Muir (2017)** studies **portfolio-level** volatility TIMING (scale the whole book by
  1/σ_portfolio). It is **NOT** direct evidence about a **cross-sectional single-security**
  admission gate. Cited only as background on vol-scaling — explicitly NOT as support for this
  gate change.

## 2. Survivorship caveat — up front, and it dominates
The panel is **291/291 names that all survive to 2026** (zero delistings). The high-vol names
that blew up are MISSING, biasing high-vol returns UP. A raw "high-vol wins" reading therefore
**contradicts the well-replicated low-vol anomaly**, which is itself a sign the data is
survivorship-contaminated. So everything below is an **upper-bound diagnostic**, not deployable
evidence. No robustness op here removes survivorship.

## 3. Method
Monthly rebalance; top-quintile by OOS model score (pooled purged-WF **XGB proxy — NOT the live
PatchTST**; omits the Kelly μ numerator, QP, concentration caps, daily rebalance, and the live
gate ordering); weight ∝ 1/σ² (clip [.05,1.5]); forward 1-mo **excess** vs SPY from OHLCV;
turnover cost Σ|Δw|·(5bps+20bps·vol). **5 non-overlapping purged test folds (60d embargo; fold
boundaries do not share a date).** Vary ONLY the cap. Sliced by the **actual market regime
label** (verified uniform across names per date), with sample counts; paired block-bootstrap CIs;
TRUE-exclusion vs winsorization robustness. Pure helpers are unit-tested in
`tests/test_research_vol_gate.py`.

## 4. Results
**Overall cap sweep (92 months, net of cost, excess vs SPY):**

| cap | Sharpe | annRet | maxDD | CVaR5 | median mo |
|---|---|---|---|---|---|
| **0.60 (current)** | +0.20 | +1.5% | −15.2% | −4.8% | +0.0012 |
| 0.80 | +0.65 | +4.9% | −13.1% | −3.9% | +0.0028 |
| 1.00 | +0.70 | +5.3% | −13.8% | −3.9% | +0.0037 |
| 1.50 | +0.71 | +5.4% | −14.0% | −3.8% | +0.0037 |
| ∞ | +0.71 | +5.3% | −14.0% | −3.8% | +0.0037 |

Point estimate: relaxing the cap *raises* the Sharpe and does NOT raise vol/drawdown (the 1/σ²
sizing keeps high-vol names tiny). BUT — see the uncertainty below.

**By ACTUAL regime — Sharpe by cap (n months):**

| regime | 0.6 | 0.8 | 1.0 | 1.5 | ∞ |
|---|---|---|---|---|---|
| BULL_CALM (n=42) | +0.27 | +0.44 | +0.45 | +0.45 | +0.45 |
| BULL_VOLATILE (n=47) | +0.36 | +0.78 | +0.85 | +0.83 | +0.83 |
| **BEAR (n=3)** | — unmeasurable — | | | | |

Relaxing helps in both BULL regimes; **BEAR has only 3 months → no regime-level conclusion is
possible.** (My earlier "the cap helps in the 2022 bear" was a *calendar-period* artifact, not a
regime result — withdrawn.)

**Paired block-bootstrap CI (2000 reps, 3-mo blocks) — monthly return delta vs cap 0.6:**

| comparison | Δ mean / mo | 95% CI |
|---|---|---|
| 1.0 − 0.6 | +0.0032 | **[−0.0002, +0.0080]** |
| 0.8 − 0.6 | +0.0028 | [−0.0001, +0.0073] |
| ∞ − 0.6 | +0.0032 | [−0.0003, +0.0081] |

**Every CI includes zero.** The relaxation's benefit is a positive point estimate but is **NOT
statistically significant** at 95% on this sample.

**Robustness (top-1% winner months):** true-exclude Sharpe ≈ winsorize (0.6: +0.11 vs +0.10;
1.0: +0.61 vs +0.60) — but **neither removes survivorship** (both keep only 2026 survivors).

## 5. Honest conclusion (exploratory)
- The point estimates are *consistent with* the theory that, given a downstream `1/σ²` sizer, a
  hard 60% admission cap is conservative — relaxing raised Sharpe without raising drawdown.
- BUT this is **not significant** (bootstrap CIs include 0), BEAR is **unmeasurable** by regime,
  the panel is **survivorship-biased** (upper bound), and the ranker is a **proxy**, not the live
  PatchTST in the live sizing/QP/gate stack. **No config change is supported by this evidence.**
- I withdraw the prior "60% is the worst point" and "1.0/0.6 regime rule" claims.

## 6. What a real decision needs (before ANY config PR)
Pre-register per-regime hypotheses + acceptance/risk bars → re-run with **live PatchTST** scores
and the **real Kelly μ/σ², QP, concentration caps, daily rebalance, and live gate order** → use a
**point-in-time universe including delisted outcomes** → report paired net-return, drawdown/CVaR,
and turnover deltas **with uncertainty** → **shadow-test** the chosen rule before production.
Repro: `scripts/research_vol_gate_opportunity_cost.py`.
