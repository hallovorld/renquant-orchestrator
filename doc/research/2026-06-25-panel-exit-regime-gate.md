# CrossSectionalPanelExit: the AND-rule fires on noise in BULL_CALM

2026-06-25. Trigger: the 2026-06-25 SHADOW run exited AMZN on `panel_conviction`
(`CrossSectionalPanelExit`) at a −2.35% loss. Prod (XGB) held it. This is the external
+ empirical teardown of WHY, and a proposal to **validate** a regime-gated fix (NOT a
pipeline change — the rule lives in renquant-pipeline; this is research/decision evidence).

## The rule (renquant-pipeline `task_panel_conviction_xs.py`)
- **AND-rule**: exit a held name if `panel ≤ bottom-20%-percentile threshold` AND `mu ≤
  mu_sell_ceiling (0.0)`. Threshold = `sorted(scores)[round(N·0.20)]` of today's cross-section.
- **OR-bypass**: `mu ≤ mu_strong_sell_ceiling (−0.05)` alone (strong-negative μ).
- It is **σ-blind**, runs **pre-QP**, and **overrides** the QP optimizer.

AMZN 2026-06-25: `panel=−0.200`, `thr=−0.176` (5th-lowest of 19), `mu=−0.0008`. The **AND-rule**
fired (`−0.200 ≤ −0.176` AND `−0.0008 ≤ 0`); the OR-bypass did NOT (`−0.0008` is not `≤ −0.05`).
So AMZN was exited purely for ranking in the bottom ~20% with a **near-zero** μ.

## Today's internal contradiction (from the run log)
`QP_HOLDING_SOLVE AMZN target_w=+0.0261` — the μ/σ²-aware optimizer wanted to **KEEP** AMZN at
2.6%; `QP_TRADE_SUPPRESSED [preexisting_exit]` — the σ-blind exit rule **overrode** it. AMZN is
the **lowest-vol holding** (σ=0.156 vs MU 0.494, CRWD 0.258) — the low-risk ballast a Markowitz/
Kelly book wants to keep. The rule dumped it, concentrating the book in higher-σ names.

## Empirical test (purged-WF XGB proxy, 549k OOS rows, bootstrap CIs)
Forward 60d excess return by cross-sectional score percentile:

| pctile band | n | mean fwd | 95% CI | hit>0 |
|---|---|---|---|---|
| deep bottom 0–10 | 54k | −0.023 | [−0.031, −0.014] | 0.46 |
| **AMZN zone 10–20** | 55k | **−0.037** | [−0.045, −0.030] | 0.46 |
| 20–40 | 110k | −0.040 | [−0.045, −0.035] | 0.45 |
| **middle 40–60** | 110k | **−0.037** | [−0.043, −0.032] | 0.45 |
| 60–80 | 110k | −0.012 | [−0.018, −0.006] | 0.46 |
| **top 80–100** | 111k | **+0.118** | [+0.110, +0.126] | 0.50 |

**The alpha is entirely in the TOP.** 0–80th percentile is uniformly negative and statistically
indistinguishable — the **AMZN zone (10–20) ≈ the middle (40–60)**. Being in the bottom 20% does
NOT predict worse forward returns than being mid-pack.

**Decision delta — exit-zone fwd MINUS the median name you'd hold instead:**

| zone | fwd − median | 95% CI | verdict |
|---|---|---|---|
| AMZN zone | **+0.0001** | **[−0.007, +0.007]** | exit captures **~0 alpha** (CI incl 0) |
| deep bottom | +0.0145 | [+0.006, +0.024] | actually better than median |

→ Exiting an AMZN-zone name and redeploying to a median name has **zero expected forward
benefit** — you pay cost + realize the loss for nothing.

**And today is the worst regime for this signal:**

| regime | AMZN-zone mean fwd | 95% CI |
|---|---|---|
| **BULL_CALM (today)** | **−0.0036** | **[−0.014, +0.007] ← CI incl 0: NOT predictive** |
| BEAR | −0.322 | [−0.354, −0.288] |
| BULL_VOLATILE | −0.046 | [−0.055, −0.036] |

The bottom-20% signal predicts underperformance in BEAR / BULL_VOLATILE but is **pure noise in
BULL_CALM** — the exact regime AMZN was exited in.

## Theory (why)
1. **A long-ranker's bottom is not a short signal.** A low-IC LTR concentrates its edge in
   picking winners (top +0.118); its loser-discrimination ≈ 0 (the whole bottom is flat).
   Using its bottom for EXITs uses the model where it is weakest (a known equity-LTR asymmetry).
2. **Forced quantile + σ-blind + weak μ gate.** "Bottom 20%" is relative — 1-in-5 holdings is
   always flagged regardless of regime; `mu ≤ 0` is near-always-true in PatchTST's all-negative
   space (neutral ≈ −0.198). The AND-rule degrades to "dump the bottom-20% by rank, ignoring
   risk" — contradicting the μ/σ² optimizer it overrides.
3. **Cost / option value.** Exiting a μ≈0, low-σ name at a loss needs the forgone return + cost
   to be justified; the decision-delta shows the justification is statistically zero.

## Proposal (to VALIDATE in shadow, then a renquant-pipeline PR — not now)
1. **Regime-gate the AND-rule**: only fire `bottom-20% AND mu≤0` in BEAR / BULL_VOLATILE; in
   BULL_CALM require the OR-bypass (`mu ≤ −0.05`) or defer to the QP. (BULL_CALM bottom-20% CI
   includes 0.)
2. **Don't let the σ-blind rule override the QP**: exit only when the QP also wants out
   (`target_w ≈ 0`, e.g. CRWD today), not when QP wants to keep the name (AMZN).
3. **Tighten `mu_sell_ceiling`** from 0 (near-useless filter) toward `mu_strong` (−0.05).

## Caveats
XGB **proxy**, not the live PatchTST + calibrator μ — the directional findings (long-ranker
asymmetry, regime-conditioning, flat bottom) are robust to the proxy, but the exact thresholds
must be re-confirmed with **live PatchTST scores**. Survivorship-biased panel. The rule change
must be **shadow-tested** (regime-gated exit vs current) before any renquant-pipeline deploy.
Repro: `scripts/research_panel_exit_predictiveness.py`.
