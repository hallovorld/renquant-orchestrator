# renquant105 milestone M1 — model + validation (the make-or-break gate)

2026-06-27. Part of the renquant105 suite. **This is the GO/NO-GO milestone.** Per the
feasibility analysis (§A of the master spec) the PRIOR is that M1 FAILS — that is an
acceptable, honest outcome, not a project failure.

## Objective + scope
Train an intraday model (GBDT primary + PatchTST shadow) on triple-barrier labels and
**validate it net-of-cost** with CPCV / Deflated-Sharpe / PBO / placebo. Offline only —
no shadow run, no orders. The output is a single decision: does a placebo-clean,
cost-clearing intraday edge exist at this size/data, yes or no.

## Requirements
**Functional:**
- F1.1 Triple-barrier label builder (σ-scaled profit/stop + time barrier = max hold);
  horizon menu {30min, 2hr, open→close}; **separate overnight from intraday**.
- F1.2 **Embargo = label horizon IN BARS, rounded to a session boundary** + overnight-gap
  purge (the single most important leakage fix — getting it wrong reproduces the
  inflated-IC bug).
- F1.3 Train GBDT (`rank:pairwise`) primary + PatchTST/PatchTSMixer ranker shadow on the
  M0 intraday panel.
- F1.4 **Lean-style cost model** calibrated to Alpaca/IEX (spread + slippage + IEX
  adverse-selection; impact ≈ 0 at this size) — every metric reported **net of it**.
- F1.5 **CPCV** harness (distribution of OOS Sharpes), **Deflated Sharpe** fed the real
  trial count, **PBO** (CSCV), shuffled-label + time-shift **placebo** — all **gating**.
- F1.6 **Trials ledger** (count every variant/retrain → DSR's N).
**Non-functional:** reproducible; deseasonalized targets (intraday U-shape); average-
uniqueness weighting on overlapping labels.

## Deliverables
Intraday model artifacts (GBDT + PatchTST) + calibrator + WF-gate metadata; the
Alpaca/IEX cost model; the **validation report** (CPCV OOS-Sharpe distribution, DSR,
PBO, placebo deltas, net-of-cost Sharpe, IC + decay) with the trial count.

## Metrics / KPIs
OOS rank IC (placebo-clean), net-of-cost Sharpe, Deflated Sharpe, PBO, hit-rate on the
cost-clearing subset, cost-as-%-of-gross-alpha, IC decay half-life.

## Acceptance criteria (the GO bar — ALL must pass)
| Criterion | Threshold |
|---|---|
| OOS rank IC @ trading horizon | ≥ **+0.03**, placebo-clean (above the shuffled-label floor by a clear margin) |
| Net-of-cost Sharpe (CPCV) | ≥ **1.0** |
| Deflated Sharpe | **> 0** at the true trial count |
| PBO | **< 20%** |
| Net-PnL block-bootstrap 95% CI | lower bound **> 0** (block ≥ label horizon) |
| Sample | ≥ **40–80** clean dates (N_eff deflated by overlap) |

## Expected outcome (预期) + kill condition
**Honest prior (§A): FAIL.** Expected net-Sharpe band −2.0 to +0.5 (centered negative);
single-bar edge ~1 bp vs ~11 bps cost. **KILL CONDITION:** if the GO bar is not cleared,
**STOP — intraday alpha trading stays OFF**, and the project falls back to the
defensible residual (execution-timing + risk on the daily book; master spec §0). Do NOT
ship a cost-negative book. A pass (improbable) unlocks M2.

## Dependencies / inputs
M0 (clean intraday panel); `renquant-common` CPCV / purged-CV / WF tooling; the cost
model; the trials ledger.

## Risks (FMEA subset)
Overfitting (multiple-testing across ~70–81 prior PatchTST trials → DSR mandatory);
overlapping-label leakage (purge/embargo in bars); the IEX adverse-selection penalty
(1–3 bps/leg) eating the entire net edge → may need SIP before a fair test.

## Effort
~3–5 weeks (label design + cost model + CPCV harness + train + the validation report).
The validation discipline, not the training, is the work.
