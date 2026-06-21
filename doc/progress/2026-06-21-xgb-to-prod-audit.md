# XGB → prod + pipeline rigor audit (operator P0)

STATUS:   in-progress (ledger reversal + self-audit done; retrain/swap/E2E are the next steps)
WHAT:     records the operator's 2026-06-21 decision reversing the XGB veto (XGB → prod primary,
          PatchTST → shadow), and the self-audit of the XGB pipeline's scientific rigor.
WHY/DIR:  operator P0. Self-audit verdict: pipeline is RIGOROUS (purged-WF-CV + 60d embargo,
          lagged features, honest +0.04 OOS IC, calibrator doesn't fake OOS). Supports the pivot.
EVIDENCE: train_production_model.py purged-CV + embargo (lines 470-485, 539); features shift(1)
          (build_alpha158_qlib.py); calibrator refuses to fake OOS (fit_calibrator_alpha158_fund.py
          136-141). On same features XGB OOS IC +0.04 vs PatchTST -0.025.
          `[VERIFIED — script read + training_runs.oos_mean_ic]`
NEXT:     retrain XGB latest data (back up artifact) -> swap prod kind hf_patchtst->xgb + PatchTST
          ->shadow -> daily-full E2E. Flag: whether XGB still goes through the live WF gate
          (never bypass) or the self-audit pass stands in — operator to confirm the bar.
