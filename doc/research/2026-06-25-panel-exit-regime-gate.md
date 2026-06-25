# CrossSectionalPanelExit: valuable in stress regimes, mis-fires in BULL_CALM

2026-06-25. Trigger: the 2026-06-25 SHADOW run exited AMZN on `panel_conviction`
(`CrossSectionalPanelExit`) at a −2.35% loss; prod (XGB) held it. Theory + data teardown +
a regime-gated fix to **validate**. Research/decision evidence — the rule lives in
renquant-pipeline; NO change here.

## The rule (renquant-pipeline `task_panel_conviction_xs.py`)
- **AND-rule**: exit a held name if `panel ≤ bottom-20%ile threshold` AND `mu ≤ mu_sell_ceiling
  (0.0)`. **OR-bypass**: `mu ≤ mu_strong_sell_ceiling (−0.05)` alone. σ-blind; pre-QP; overrides QP.
- AMZN: `panel=−0.200 ≤ thr=−0.176` (5th-lowest of 19), `mu=−0.0008 ≤ 0` → **AND-rule** fired
  (OR-bypass did not). Exited purely for ranking bottom-20% with a **near-zero** μ.

## Today's internal contradiction (run log)
`QP_HOLDING_SOLVE AMZN target_w=+0.0261` — the μ/σ² optimizer wanted to **KEEP** AMZN at 2.6%;
`QP_TRADE_SUPPRESSED [preexisting_exit]` — the σ-blind rule **overrode** it. AMZN is the
**lowest-vol holding** (σ=0.156 vs MU 0.494) — the ballast a Markowitz/Kelly book keeps.

## Empirical (1) — XGB proxy (549k OOS rows) — and its CORRECTION
The XGB-proxy fwd-return-by-percentile looked *flat* in the bottom (AMZN zone ≈ middle), which
suggested "exiting captures ~0 alpha." **That was a proxy artifact** — see (2). The XGB proxy
has weaker loser-discrimination than the live PatchTST, so it understated the bottom's
underperformance. The proxy's one robust signal was the **regime split** (below).

## Empirical (2) — LIVE PatchTST pt07 seed44 (the actual shadow scorer) — DEFINITIVE
Using the live model's real OOS val_preds (`(date, pred, label)`, 20,016 rows, 2020–2022
covid+inflation-peak cuts), cross-sectional percentile of the REAL `pred`:

| pctile band | n | mean fwd | 95% CI | hit>0 |
|---|---|---|---|---|
| deep bottom 0–10 | 1948 | −0.096 | [−0.130, −0.061] | 0.42 |
| **AMZN zone 10–20** | 1948 | **−0.088** | [−0.126, −0.048] | 0.43 |
| 20–40 | 3978 | −0.059 | [−0.087, −0.030] | 0.43 |
| middle 40–60 | 4041 | −0.003 | [−0.032, +0.026] | 0.46 |
| 60–80 | 3978 | +0.073 | [+0.039, +0.104] | 0.48 |
| **top 80–100** | 4123 | **+0.200** | [+0.164, +0.239] | 0.52 |

**Monotonic and predictive** — the real PatchTST bottom-20% genuinely underperforms. Decision
delta (AMZN-zone vs the median name you'd hold) = **−0.086, CI [−0.124, −0.046] → exit IS
justified** *in aggregate on these cuts*. **So the "zero-alpha exit" headline is RETRACTED** —
the rule has real value where the scorer discriminates losers.

## The regime split SURVIVES the live model (the actual issue)
AMZN-zone (bottom 10–20%) forward return by regime, REAL PatchTST:

| regime | n | mean fwd | 95% CI |
|---|---|---|---|
| **BULL_CALM (today)** | 260 | **+0.026** | **[−0.073, +0.123] ← CI incl 0; leans POSITIVE** |
| BEAR | 546 | −0.220 | [−0.287, −0.143] |
| BULL_VOLATILE | 1142 | −0.051 | [−0.103, −0.001] |

Even on the live scorer, the bottom-20% **predicts underperformance in BEAR / BULL_VOLATILE but
NOT in BULL_CALM** (mean even leans positive). AMZN was exited in **BULL_CALM** — the one regime
where this signal does not hold. The aggregate "exit is justified" is **driven by the stress
regimes** that dominate these cuts (coverage: BULL_VOL 11,646 / BEAR 5,670 / BULL_CALM 2,700).

## Theory (why)
A low-IC long-ranker's edge is strongest at the **top** (winners, +0.200) and weakens toward the
bottom; in **calm** regimes cross-sectional dispersion compresses and the bottom-rank carries no
forward information (mean-reverts), while in **stress** regimes the bottom genuinely leads losers.
The current rule is **σ-blind, forced-quantile (1-in-5 always flagged), and regime-agnostic**, so
in BULL_CALM it dumps low-σ ballast (AMZN) the μ/σ² optimizer wants to keep.

## Proposal (validate further → renquant-pipeline PR; NOT now)
1. **Regime-gate the AND-rule**: fire `bottom-20% AND mu≤0` only in BEAR / BULL_VOLATILE; in
   BULL_CALM require the OR-bypass (`mu ≤ −0.05`) or defer to the QP. (Both proxy AND live model:
   BULL_CALM bottom-20% CI includes 0.)
2. **Don't let the σ-blind rule override the QP** when QP wants to keep the name (exit only when
   QP also targets ~0, e.g. CRWD today).
3. Tighten `mu_sell_ceiling` from 0 toward `mu_strong` (−0.05).

## Caveats (honest)
- The **aggregate** value of the rule is REAL (live-PatchTST decision delta is significantly
  negative); I retract the earlier "captures zero alpha" claim.
- The **BULL_CALM** finding (not predictive) is the actionable one, but the live-model BULL_CALM
  sample is small (n=260, wide CI) because these OOS cuts are covid+inflation (stress-heavy).
  **Confirm with PatchTST OOS scores from BULL_CALM-dominant periods** before a pipeline change.
- Survivorship-biased panel; shadow-test the regime-gated exit vs the current rule first.
- Repro: `scripts/research_panel_exit_predictiveness.py` (XGB proxy) + the live-PatchTST cut on
  `artifacts/patchtst_doe_hf/pt_07_cut*_seed_44/*val_preds.parquet`.
