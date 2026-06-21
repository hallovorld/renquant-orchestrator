# XGB WF-gate result (operator P0)

STATUS:   in-progress (results record; XGB FAIL → NOT promoted; config reverted to known-good)
WHAT:     gated the fresh XGB (+0.053 oos_mean_ic, latest data) through the production WF gate.
WHY/DIR:  operator XGB-to-prod P0. Verdict FAIL, but narrow: XGB has POSITIVE real IC +0.054,
          PASSES placebo (first model this session) + WF Sharpe floor + beats SPY 1/3; FAILs only
          BULL_CALM/CHOPPY regime sanity + BULL_CALM monotonicity. Confirms features have signal
          XGB extracts (PatchTST doesn't). Not promoted; never bypass.
EVIDENCE: real_ic +0.0543, placebo +0.0343<thr +0.0379 PASS, WF Sharpe +0.94/+0.18/+0.97 PASS;
          Sanity FAIL regime-sanity BULL_CALM,CHOPPY; monotonicity FAIL BULL_CALM; VERDICT FAIL.
          `[VERIFIED — /tmp/xgb_gate4.log, ephemeral]`
NEXT:     diagnose the BULL_CALM/CHOPPY regime wall (real defect vs measurement) — now the ONLY
          blocker for a model that otherwise has edge. Fix the GBDT-manifest relative-uri path bug
          (its own PR; it has broken weekly_wf_promote since 05-24). No promotion / no bypass.
