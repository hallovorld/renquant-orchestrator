# RealizedVolGate opportunity-cost: hard cap vs vol-target sizing

2026-06-25. Operator: high-vol days are opportunities too — raise the bar, don't freeze
completely. Research + experiment first, then conclude. (Trigger: 2026-06-25 daily-full
no-trade; `RealizedVolGateTask` dropped 21/97 buy candidates over the 60% annualized-vol cap.)

## Question
The buy pipeline runs a HARD `RealizedVolGateTask` (`task_risk_gates.py:48-123`, config key
`risk_gates.realized_vol.max_annualized`, default **0.60**) that **drops** any candidate whose
60-day annualized realized vol exceeds 60%, in Phase 2b — BEFORE conviction and Kelly sizing.
It is an **untested heuristic** ("Russell 2000 median ≈ 0.30, so 0.60 excludes the high tail")
— no A/B, no tuning memo, and **not regime-aware**.

But the system ALREADY controls vol downstream, harder: Kelly sizing is `f* = μ/σ²` — it shrinks
a name by the **inverse of variance** (a 60%-vol name gets ~0.25× the size of a 30%-vol name; a
120%-vol name ~0.06×), and `ApplyRealizedVolFallbackTask` feeds it realized vol **clipped to
[0.05, 1.50]**. So the sizer is willing to size names up to **150%** vol (tiny), while the gate
**forbids** anything over 60% — an internal contradiction. The hard pre-exclusion is
**double-counting risk** and discarding high-vol names the σ² sizer would have shrunk safely.
Does the gate cost alpha?

## Method (purged walk-forward, no lookahead)
- Realized `vol60_ann` per (ticker, date) = 60d rolling std of daily close returns × √252,
  from `data/ohlcv/<ticker>/1d.parquet` — matches the gate's definition. 100% panel coverage.
- OOS model score per (ticker, date) from a pooled **purged-WF XGB** (6 cuts, 60d embargo) on
  the alpha158+regime panel (`alpha158_291_fund_regime_dataset.parquet`, label `fwd_60d_excess`).
  550,442 OOS-scored rows. (Proxy ranker — not the live PatchTST; see caveats.)
- "Would-buy" set = each day's **top quintile by model score**. Split by the 60% cap:
  ADMITTED (≤60%) vs GATED (>60%). Plus a sizing sim on the daily basket.

## Results
**Top-quintile would-buy names, split by the 60% vol cap:**

| group | n | mean fwd_60d_excess | hit-rate | Sharpe (/name) |
|---|---|---|---|---|
| ADMITTED ≤60% | 90,545 | +0.065 | 0.49 | +0.057 |
| **GATED >60%** | 20,906 | **+0.350** | **0.55** | **+0.181** |

The model's high-conviction picks that the gate THROWS AWAY have a **higher hit-rate (55% vs
49%) and higher per-name Sharpe (+0.181 vs +0.057)**. (The +0.35 mean is **tail-inflated** —
high-vol = fat right tail; trust the hit-rate and Sharpe, not the raw mean.)

**Gated high-score names by regime** (is the dropped alpha real, not one regime?):

| regime | n | mean fwd | hit | Sharpe |
|---|---|---|---|---|
| BULL_CALM | 5,105 | +0.465 | 0.55 | +0.209 |
| BEAR | 2,775 | +0.671 | 0.68 | +0.513 |
| BULL_VOLATILE | 13,026 | +0.236 | 0.52 | +0.124 |

**Sizing sim — daily top-quintile basket fwd return** (the decision-relevant test):

| basket construction | days | mean basket fwd | Sharpe |
|---|---|---|---|
| (A) hard cap, equal-weight ADMITTED only | 1,909 | +0.063 | +0.259 |
| **(B) inverse-vol, ADMIT ALL (weight ∝ 1/vol)** | 1,940 | **+0.078** | **+0.342** |

Admitting the high-vol names with **inverse-vol (vol-target) sizing beats the hard cap on BOTH
return (+0.078 vs +0.063, +24% rel) AND Sharpe (+0.342 vs +0.259, +32% rel)**. The 1/vol
weighting controls the risk (high-vol names get small weights) while capturing their alpha.
Note the sim used 1/σ; the LIVE Kelly is 1/σ² (stronger shrinkage) — so the real system would
control the high-vol risk **even more** than this sim, making "admit + size down" safer still.

## Conclusion
The evidence supports the operator's thesis: the **hard >60% exclusion costs risk-adjusted
return**. The model ranks high-vol names usefully (higher hit-rate), and vol-target sizing —
which the system *already has in Kelly* — captures that alpha at a BETTER Sharpe than excluding
them. A binary "freeze" is the wrong tool when a continuous vol-aware sizer exists downstream.

## Caveats (why this is a DISCUSSION, not an auto-deploy)
1. **Tail-inflated means** — the +0.35 mean is dominated by extreme winners; hit-rate/Sharpe and
   the daily-basket Sharpe (+0.342 vs +0.259) are the trustworthy numbers (and still favor admit).
2. **Period bias** — 2016–2026 was historically kind to high-vol growth (AMD/NVDA/SMCI). The
   high-vol edge may be momentum-regime-conditional; the thin BEAR cell (+0.67) is likely period-specific.
3. **Gross of costs / constraints** — no transaction costs, PDT, concentration/sector caps, or
   borrow. Inverse-vol weights need the real Kelly + QP construction to confirm.
4. **Proxy model** — OOS scores are an XGB proxy, not the live PatchTST. Re-run with live scores.
5. **No absolute ceiling tested** — a genuinely distressed name at 150%+ vol may still warrant a
   hard ceiling; "remove the cap" ≠ "no ceiling".

## Proposed direction (to discuss; validate before any deploy)
- **Raise `risk_gates.realized_vol.max_annualized` from 0.60 to align with Kelly's clip ceiling
  (1.50, or a conservative 1.0–1.2)** and let the existing Kelly `1/σ²` sizing shrink the 60–120%
  band instead of excluding it. This removes the internal contradiction (the sizer already accepts
  up to 150%) and keeps a hard ceiling for genuinely uninvestable / distressed names. Net: "raise
  the bar, don't freeze." One-line config change — low blast radius, reversible.
- Validate properly before deploy: live-PatchTST scores, transaction costs, per-regime, confirm
  the Kelly clip + concentration caps actually bound the high-vol weights — then **shadow-test**
  (isolated `alpaca_shadow`) and only graduate if the live Sharpe holds. Do NOT curve-fit the new
  ceiling to today's specific names.
- Reproducible via `scripts/research_vol_gate_opportunity_cost.py`.
