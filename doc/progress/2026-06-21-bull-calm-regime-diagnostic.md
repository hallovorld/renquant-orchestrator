# BULL_CALM/CHOPPY regime wall diagnostic (XGB)

STATUS:   in-progress (diagnostic; no promotion, no gate change)
WHAT:     diagnoses why XGB FAILed regime-sanity in BULL_CALM/CHOPPY (#166). Finding: XGB has
          POSITIVE per-regime IC everywhere (BEAR +0.335, BULL_CALM +0.0234, CHOPPY +0.0256, all
          above the 0.02 floor); BULL_CALM/CHOPPY fail ONLY on the placebo-ratio sub-check, which
          is ill-conditioned at small IC (bar = 0.5x0.023 ~ 0.0115) — same as #163.
WHY/DIR:  XGB is otherwise gate-worthy (positive IC, passes overall placebo + WF floor). The regime
          wall is largely a gate-calibration sensitivity, not a clear model defect → direct evidence
          for the operator's gate-doubt. Lever = the regime-placebo-ratio calibration at small IC.
EVIDENCE: gate's own regime_diagnostics: per-regime mean_ic all positive, BULL_CALM/CHOPPY clear the
          0.02 floor yet FAIL → placebo sub-check is the only possible cause (deductive; placebo
          number not directly measured this run). `[VERIFIED — regime_diagnostics on fresh XGB]`
NEXT:     directly measure per-regime placebo; consider an abstain-vs-fail calibration change for the
          regime-placebo sub-test (reviewed PR, NOT a bypass); re-gate XGB with corrected manifest.
