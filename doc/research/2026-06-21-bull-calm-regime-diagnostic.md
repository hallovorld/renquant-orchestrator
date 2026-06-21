# BULL_CALM/CHOPPY regime wall — diagnostic for XGB (CORRECTED: the gate is right here)

XGB passed the WF Sharpe floor + the overall placebo + has positive real IC (+0.054) but FAILed the
gate on regime-sanity IC (BULL_CALM, CHOPPY) + BULL_CALM monotonicity (#166). This diagnoses it.

> **CORRECTION (this PR's own first draft was wrong).** I first framed the failure as "largely a
> gate-calibration sensitivity, not a model defect." Then I **directly measured the per-regime
> placebo** — and it refutes that. In BULL_CALM/CHOPPY the placebo IC **exceeds** the real IC, so
> the gate fails them **correctly**: the model's calm/choppy signal is genuinely drift-/placebo-
> entangled. Corrected finding below; trail kept because the measurement is what stopped a
> "loosen-the-gate" overclaim.

## XGB per-regime IC + placebo (gate's own regime_diagnostics + regime_shift_diagnostics)
Thresholds: n_dates>=30, mean_ic>=0.02, placebo |placebo60| <= max(0.005, 0.5*|aligned_real|).

| regime | n | mean_ic | placebo60 | bar (0.5*aligned) | verdict |
|---|---|---|---|---|---|
| BEAR | 50 | +0.335 | +0.0993 | +0.173 | PASS (placebo << real) |
| BULL_CALM | 399 | +0.0234 | +0.0266 | +0.0218 | FAIL (placebo > real IC) |
| BULL_VOLATILE | 19 | +0.0254 | +0.0170 | +0.0160 | skipped (n<30) |
| CHOPPY | 40 | +0.0256 | +0.0268 | +0.0146 | FAIL (placebo > real IC) |

`[VERIFIED -- direct measurement, gate's regime_shift_diagnostics on the fresh XGB]`

## The corrected finding
- XGB has positive real IC in every regime -- but in BULL_CALM and CHOPPY the placebo IC is LARGER
  than the real IC (0.0266 > 0.0234; 0.0268 > 0.0256). The model's ranking in calm/choppy markets
  correlates with the drift-shifted label MORE than with the real forward label.
- So the gate fails BULL_CALM/CHOPPY CORRECTLY -- the signal there is substantially slow-drift /
  placebo, not clean cross-sectional alpha. This is a MODEL property, not a calibration artifact.
- It is NOT just the 0.5x factor: even a much looser bar (placebo < 1.0*real) would still fail both.
  The placebo exceeds the real IC outright.
- Where XGB is genuinely clean: BEAR (real +0.335, placebo +0.099). Its overall +0.054 IC is real
  but carried by BEAR; calm/choppy regimes are drift-entangled.

## Honest correction of the first draft
The "gate-calibration sensitivity / loosen the regime-placebo test" reading was an OVERCLAIM -- a
hopeful story the direct placebo measurement does not support. There is NO calibration change to
make here; proposing one would have been a bypass-via-calibration. Discarded.

## What this means for the path
- No promotion, no bypass, no gate loosening. The gate is doing its job for XGB in calm/choppy.
- XGB's real, clean edge is regime-specific (BEAR). The lever is making the calm/choppy signal clean
  (feature/label work for those regimes) OR a regime-aware deployment that trusts XGB only where its
  signal is placebo-clean. Both are research, not a gate change.
- The operator's gate-doubt, for XGB specifically: the regime gate is VINDICATED, not over-strict --
  confirmed by measuring the placebo, not assuming.
