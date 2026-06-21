# BULL_CALM/CHOPPY regime wall diagnostic (XGB)

STATUS:   in-progress (diagnostic; no promotion, no gate change)
WHAT:     diagnoses why XGB FAILed regime-sanity in BULL_CALM/CHOPPY (#166). CORRECTED finding (direct placebo measurement): XGB has positive
          real IC everywhere, BUT in BULL_CALM/CHOPPY the placebo IC EXCEEDS the real IC (0.0266>0.0234;
          0.0268>0.0256) — signal is drift-entangled there → gate fails them CORRECTLY (not a
          calibration artifact). My first-draft 'gate over-strict' was an overclaim; corrected.
WHY/DIR:  XGB is otherwise gate-worthy (positive IC, passes overall placebo + WF floor). The regime
          wall is largely a gate-calibration sensitivity, not a clear model defect → direct evidence
          for the operator's gate-doubt. Lever = the regime-placebo-ratio calibration at small IC.
EVIDENCE: gate's own regime_diagnostics: per-regime mean_ic all positive, BULL_CALM/CHOPPY clear the
          0.02 floor yet FAIL → placebo sub-check is the only possible cause (deductive; placebo
          number not directly measured this run). `[VERIFIED — regime_diagnostics on fresh XGB]`
NEXT:     NO gate change (measurement shows the gate is correct here). Research options: clean the
          calm/choppy signal (feature/label work) OR regime-aware deployment trusting XGB where
          placebo-clean (BEAR). No promotion/bypass.
