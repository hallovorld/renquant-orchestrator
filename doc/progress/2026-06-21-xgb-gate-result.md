# XGB WF-gate result (operator P0)

STATUS:   complete (results record; XGB FAIL → NOT promoted; config reverted to known-good)
WHAT:     gated the fresh XGB (+0.053 oos_mean_ic, latest data) through the production WF gate.
RESULT:   operator XGB-to-prod P0. Verdict FAIL. Defensible facts only: XGB has
          POSITIVE aggregate real IC +0.054, PASSES the overall time-shift placebo
          + WF Sharpe floor + beats SPY 1/3; FAILs §5.2 regime-sanity IC
          (BULL_CALM, CHOPPY) + BULL_CALM trade-monotonicity. NOT promoted; never bypass.
SIGNAL:   XGB clears the overall placebo (PatchTST 60d/20d/pruned all sat ~−0.02
          and failed it), so the features contain extractable cross-sectional
          signal that XGB captures. This is an aggregate statement; it does NOT
          establish a robust regime-by-regime edge (see CAVEAT).
EVIDENCE: real_ic +0.0543, overall placebo +0.0343<thr +0.0379 PASS, WF Sharpe
          +0.94/+0.18/+0.97 PASS; regime-sanity FAIL BULL_CALM,CHOPPY; monotonicity
          FAIL BULL_CALM; VERDICT FAIL. `[VERIFIED — /tmp/xgb_gate4.log, ephemeral]`
CAVEAT:   the regime failure is NOT yet shown to be a mere measurement artifact —
          the follow-up diagnostic (#167) finds BULL_CALM (the dominant, reliable
          regime) is genuinely weak and the aggregate +0.054 is BEAR-inflated. So
          this record does NOT claim the remaining blocker is uniquely identified
          or that XGB is one diagnostic away from a pass.
NEXT:     see #167 for the regime diagnosis (bounded: gate FAIL is correct, no
          gate change). Separately, fix the GBDT-manifest relative-uri path bug
          (its own PR; broken weekly_wf_promote since 05-24). No promotion / no bypass.
