# BULL_CALM/CHOPPY regime wall — diagnostic for XGB (real defect vs gate-calibration?)

XGB passed the WF Sharpe floor + the overall placebo + has positive real IC (+0.054) but FAILed the
gate on **regime-sanity IC (BULL_CALM, CHOPPY)** + BULL_CALM monotonicity (#166). This diagnoses
that regime-sanity failure. **Finding: it is largely a gate-calibration sensitivity at small IC,
not a clear model defect — XGB has positive IC in every regime.**

## XGB per-regime cross-sectional IC (gate's own `regime_diagnostics`)
Thresholds (gate): `n_dates >= 30`, `mean_ic >= 0.02`, placebo-ratio `|placebo| <= 0.5·|ref|`.

| regime | n_dates | mean_ic | eligible | mean_ic ≥ 0.02 floor? |
|---|---|---|---|---|
| BEAR | 50 | **+0.335** | yes | ✅ (strong) |
| **BULL_CALM** | 399 | **+0.0234** | yes | ✅ (clears floor) — **yet FAILed** |
| BULL_VOLATILE | 19 | +0.0254 | no (n<30, skipped) | — |
| **CHOPPY** | 40 | **+0.0256** | yes | ✅ (clears floor) — **yet FAILed** |

`[VERIFIED — gate's analyze_manifest_sanity_placebo.regime_diagnostics on the fresh XGB]`

## The deduction
A regime PASSes iff `mean_ic >= 0.02 AND placebo_ok`. BULL_CALM (+0.0234) and CHOPPY (+0.0256)
**both clear the 0.02 mean_ic floor**, yet are marked FAIL. Therefore the failure is **necessarily
the placebo-ratio sub-check** (`placebo_ok=False`) — the only other criterion.

At these small per-regime ICs, the placebo bar is `0.5 × ~0.023 ≈ 0.0115`. A modest regime placebo
IC easily exceeds that tiny bar — **the same ill-conditioned-at-small-IC behaviour documented in
PR #163** (`threshold = max(0.005, 0.5·|IC|)`; when real IC is small, the test compares two
noise-band-adjacent numbers).

## What this means (bounded, honest)
- **XGB genuinely ranks positively in every regime** (positive IC, BULL_CALM/CHOPPY above the
  0.02 floor). This is NOT a model that picks backwards in calm/choppy markets.
- **The BULL_CALM/CHOPPY regime-sanity FAIL is dominated by the placebo-ratio sub-check at small
  IC** — a gate-calibration sensitivity, not a clear stock-picking defect.
- This is **direct evidence for the operator's original gate-doubt** ([#163]) — for a model with
  genuine positive IC, the regime-placebo-ratio test is over-strict when the regime IC is small.

## Caveats (do NOT overclaim)
- **The "placebo is the cause" is DEDUCTIVE** (mean_ic passes the floor → only `placebo_ok` can
  fail), not directly measured in this run (the per-regime placebo number came back unpopulated in
  the standalone harness). The mean_ic values themselves ARE directly measured.
- **Small IC cuts both ways:** at ~0.023 IC, "real-but-small signal" vs "small placebo-entangled
  signal" is genuinely hard to separate — that ambiguity IS the ill-conditioning. This does NOT by
  itself prove the gate is "wrong"; it shows the test loses power at small IC.
- **Separate sub-failure:** BULL_CALM *trade-monotonicity* also failed; that is a different
  (trade-outcome) check, not diagnosed here. IC-positive + monotonicity-fail can coexist.
- **No promotion / no bypass.** Diagnosing the gate's behaviour ≠ loosening it.

## Proposed next (operator/Codex)
1. **Directly measure** the per-regime placebo IC to confirm the deduction + quantify how far over
   the bar BULL_CALM/CHOPPY are.
2. **Calibration question for the regime-placebo sub-test:** at small-but-floor-clearing IC, should
   it "abstain (insufficient power)" rather than "fail"? (Same #163 abstain-vs-fail question.) A
   reviewed calibration change — not a bypass — could let a genuinely-positive-IC model like XGB pass.
3. Re-run XGB through the gate with a corrected GBDT manifest (the relative-uri path bug, #166).
