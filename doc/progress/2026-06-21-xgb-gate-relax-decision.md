# XGB deployment via designed gate opt-ins — decision record

STATUS:   in-progress (decision record + risk disclosure; execution pending operator confirm on the
          lags-SPY fact)
WHAT:     documents the legitimate (non-bypass) path to deploy XGB per the operator's "loosen the
          gate" directive — the gate's DESIGNED operator opt-ins (benchmark_required,
          regime_required, sanity_regime_ic_required, allow-pass-open-monotonicity) — the 4 relaxes
          XGB needs, and the material risk (XGB lags SPY APY 0/3; weak in BULL_CALM).
WHY/DIR:  XGB is the only model with real signal; remaining sell-only indefinitely vs trading the
          best-available model is the operator's real-money call. This is the audit-trail disclosure
          the gate's own design requires before enabling the opt-ins.
EVIDENCE: gate5: XGB passes absolute Sharpe floor + overall placebo (+0.0343<0.0379) but FAILs
          benchmark (beat SPY APY 0/3), WF-regime, regime-sanity (BULL_CALM/CHOPPY), monotonicity.
          `[VERIFIED — /tmp/xgb_gate5.log]`
NEXT:     operator decision on the lags-SPY fact -> if go: set 4 opt-ins, re-gate (passed=true),
          promote, swap prod->xgb, daily-full E2E. NOT a bypass; all reversible; logged. Then Path 1.
