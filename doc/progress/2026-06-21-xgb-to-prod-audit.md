# XGB → prod directive + pipeline rigor audit (operator P0)

STATUS:   complete as a record of (a) the operator directive and (b) the self-audit.
          The prod swap is NOT recorded as effected/settled: XGB FAILED the WF gate
          (#166), so this does not assert XGB cleared the production bar.
WHAT:     records the operator's 2026-06-21 directive to lift the XGB pitch-veto
          (pursue XGB → prod primary, PatchTST → shadow) and the self-audit of the
          XGB pipeline's scientific rigor.
WHY/DIR:  operator P0. Self-audit verdict: the training pipeline is RIGOROUS
          (purged-WF-CV + 60d embargo, lagged features, honest +0.04 OOS IC,
          calibrator doesn't fake OOS). That validates the pipeline's METHOD; it is
          NOT a production-readiness verdict on the model.
EVIDENCE: train_production_model.py purged-CV + embargo (lines 470-485, 539); features
          shift(1) (build_alpha158_qlib.py); calibrator refuses to fake OOS
          (fit_calibrator_alpha158_fund.py 136-141). On same features XGB OOS IC +0.04
          vs PatchTST -0.025. `[VERIFIED — script read + training_runs.oos_mean_ic]`
OUTCOME:  XGB was retrained on latest data and gated (#166): positive AGGREGATE IC,
          passes overall placebo + WF floor, but FAILED regime-sanity (BULL_CALM/
          CHOPPY) + BULL_CALM monotonicity → NOT promoted by the gate. The bounded
          regime read is #167 (BULL_CALM weak, aggregate BEAR-inflated).
NEXT:     production use, if pursued, is at operator real-money discretion behind the
          downstream conviction floor (mu_floor, pipeline #140) — NOT a gate pass and
          not a bypass. Durable goal: strengthen the calm-market signal (Path 1).
