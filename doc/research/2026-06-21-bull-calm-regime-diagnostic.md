# BULL_CALM/CHOPPY regime wall — diagnostic for XGB

XGB passed the WF Sharpe floor + the overall placebo + has positive aggregate real
IC (+0.054), but FAILed the gate on regime-sanity IC (BULL_CALM, CHOPPY) +
BULL_CALM monotonicity (#166). This note diagnoses why, and lands on a single
bounded stance.

## Bounded conclusion (current, reliable)
- **BULL_CALM is the only per-regime read with enough data to trust** (425 dates).
  There, XGB is **weak**: real IC **+0.0149** (below the 0.02 floor) and the
  shift-60 placebo (+0.0229) **exceeds** the real IC. This is reliable because
  BULL_CALM is the dominant regime by sample size.
- **BEAR/CHOPPY cannot be validated**: intrinsically rare (50/40 dates over ~2
  years, with 60d-overlapping labels → a handful of independent observations).
  The BEAR real IC of +0.347 is implausibly high for cross-sectional equity and
  is not a claim this analysis can stand behind in either direction.
- **The aggregate +0.054 is correct arithmetic but BEAR-inflated**, i.e. carried
  by that rare, unvalidatable regime. So it is a **misleading deployment signal**
  for the regime XGB would mostly operate in.
- **The gate's regime-sanity FAIL is therefore correct** — it catches that XGB's
  edge is not robust where it would trade. **No promotion, no bypass, no gate change.**

## Evidence — per-regime IC + placebo, with power
Gate's own `regime_diagnostics` + `regime_shift_diagnostics` (shift 60). Thresholds:
n_dates>=30, mean_ic>=0.02, placebo |placebo60| <= max(0.005, 0.5*|aligned_real|).
Power read = recent-50% OOS window (534 dates):

| regime | n_dates | real_ic | placebo60 | reliability |
|---|---|---|---|---|
| BEAR | 50 | +0.347 | +0.098 | RARE — implausible magnitude, cannot validate |
| **BULL_CALM** | **425** | **+0.0149** | +0.0229 | **RELIABLE — weak, below floor, placebo > real** |
| BULL_VOLATILE | 19 | +0.023 | +0.019 | rare (n<30, skipped) |
| CHOPPY | 40 | +0.026 | +0.029 | rare — cannot validate |

`[VERIFIED — gate's regime diagnostics on the fresh XGB; power read over 534 OOS dates]`

Supporting check (operator flagged "clean only in BEAR violates common sense"):
per-regime label self-autocorr `corr(label_t, label_{t+60})` is HIGHER in BEAR
(+0.183) than BULL_CALM (−0.049)/CHOPPY (+0.008) — the opposite of what would
explain a calm/choppy placebo inflation, which is part of why the BEAR number is
treated as unvalidatable rather than as a clean edge.

## Path to deploy XGB (both research, neither a bypass)
1. **Strengthen the BULL_CALM cross-sectional signal** (feature/label work) — the
   hard fix, and the one that matters because BULL_CALM is where it would trade.
2. **Regime-aware deployment** — trade only where the signal is validated, accept
   rarer trading.

## Process trail (superseded — not current claims)
While iterating I drafted two framings that the measurement above retired; recorded
so the reasoning is auditable, but they are **not** the conclusion:
- *"The gate is over-strict / this is calibration sensitivity at small IC."*
  Retired: directly measuring the per-regime placebo showed it exceeds the real IC
  in BULL_CALM/CHOPPY, so a calibration loosen would have been a bypass.
- *"XGB's clean edge is BEAR-specific."* Retired: the BEAR IC is on too small/rare
  a sample to validate; the only reliable per-regime statement is that BULL_CALM
  is weak. The defensible result is the aggregate +0.054 **with** the caveat that
  it is BEAR-inflated and not a robust calm-market edge.
