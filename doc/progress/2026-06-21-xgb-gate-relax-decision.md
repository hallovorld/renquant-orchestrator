# XGB gate opt-ins — inventory + risk disclosure (NOT an adopted relax-and-promote path)

STATUS:   complete (neutral inventory + risk disclosure). The "relax all four checks →
          passed=true → promote" path is documented but explicitly NOT adopted as a
          deployment decision on this evidence.
WHAT:     inventories the gate's DESIGNED operator opt-ins (benchmark_required,
          regime_required, sanity_regime_ic_required, allow-pass-open-monotonicity),
          records which checks XGB fails, and discloses the material risk (XGB lags
          SPY APY 0/3; weak in BULL_CALM). It does NOT record a settled decision to
          manufacture passed=true by relaxing all four.
WHY/DIR:  the operator asked to loosen the gate so the only model with signal can
          trade. Relaxing four independent checks after seeing the failed result is a
          major change to the acceptance bar, not a small toggle — so this is a
          disclosure/inventory, and the deployment question stays governed by the
          bounded diagnosis (#167) and a downstream conviction floor, not by this doc.
EVIDENCE: gate5: XGB passes absolute Sharpe floor + overall placebo (+0.0343<0.0379)
          but FAILs benchmark (beat SPY APY 0/3), WF-regime, regime-sanity
          (BULL_CALM/CHOPPY), monotonicity. `[VERIFIED — /tmp/xgb_gate5.log]`
DECISION: do NOT treat "4 relaxes → passed=true" as good enough on its own. If XGB is
          deployed, opt-in use must be paired with (a) the bounded #167 finding
          (BULL_CALM weak, aggregate BEAR-inflated) and (b) a downstream economic
          conviction floor (mu_floor, renquant-pipeline #140) so the book only buys
          well-separated names — not "everything the relaxed gate now admits".
