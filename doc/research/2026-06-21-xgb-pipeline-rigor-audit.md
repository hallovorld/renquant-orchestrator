# XGB (panel-LTR alpha158_fund) pipeline rigor audit — for XGB-to-prod (operator P0)

Operator directed (2026-06-21): pursue XGB → prod primary, PatchTST → shadow, retrain XGB on latest
data, **self-audit the pipeline's scientific rigor**, and if it passes, run daily-full once to
validate E2E. This is the self-audit. **Verdict: the training pipeline's METHOD is rigorous; the
+0.04 OOS IC is honest.** This validates the method, **not** production-readiness: the fresh XGB
subsequently **FAILED the WF promotion gate** (#166 regime-sanity + monotonicity; #167 BULL_CALM
weak, aggregate BEAR-inflated). The operator lifted the XGB pitch-veto (LONG #3); that is a decision
to reconsider XGB, not a verdict that it cleared the bar.

## What was audited (the scientific-validity questions)

| check | finding | evidence |
|---|---|---|
| **Features look-ahead-free?** | ✅ features use **lagged** data (`shift(1)` before rolling) — feature at date t uses ≤ t-1 | `build_alpha158_qlib.py` (`c.shift(1)`, `v.shift(1)`), `build_alpha158_fund_panel.py:286` SUE `shift(1)` |
| **Label leakage?** | ✅ `fwd_60d_excess` = forward(ticker) − forward(SPY); strictly **future**, never mixed into features | `LABEL="fwd_60d_excess"`; train uses rows only up to `current_date − 60d` (complete labels) |
| **OOS protocol honest?** | ✅ **purged walk-forward CV** — each fold trains only on dates strictly before the val fold, with a **60-day embargo** (= the label horizon, so no train label overlaps val features) | `train_production_model.py:470-485`, `--cv-embargo-days 60` |
| **Is the +0.04 IC real OOS?** | ✅ `oos_mean_ic` = mean per-fold IC from that **purged CV**, not in-sample | `train_production_model.py:539` |
| **Cross-sectional IC computed right?** | ✅ per-date `spearman(pred, label)` then averaged | `:432-458` |
| **Training look-ahead via cutoff?** | ✅ `--train-cutoff` filters `date < cutoff` with an additional cutoff-embargo | `:270-283` |
| **Calibrator honesty?** | ✅ the calibrator script **explicitly refuses to pretend its fit-window IC is OOS** | `fit_calibrator_alpha158_fund.py:136-141` |

## Verdict
**The XGB pipeline is scientifically sound.** Purged + embargoed walk-forward CV is exactly the
right protocol for cross-sectional time-series ML at a 60d horizon (it is *stricter* than what the
old PatchTST single-split path used). The recorded `oos_mean_ic ≈ +0.04` is an honest OOS number,
not an in-sample or calibrator-fit artifact.

## Implication (the lead from #163, now on firmer ground)
On the **same alpha158 features**, XGB's honest purged-OOS IC is **+0.04** while PatchTST's recorded
OOS IC is **−0.025**. The features contain extractable cross-sectional signal; the PatchTST extractor
fails to capture it. This is *consistent with* the operator's directive to run XGB as prod primary
while PatchTST (the weaker extractor here) moves to shadow for continued development.

## Remaining caveats (honest, before live)
1. **Gate vs train-IC:** +0.04 is the model's purged-CV OOS; it is **not** the same as passing the
   live WF *promotion* gate (placebo / monotonicity / regime sanity). XGB to prod should still go
   through the WF gate — never bypass — unless the operator's "self-audit pass" explicitly stands
   in for it. *(Flagging the tension; operator to confirm the bar.)*
2. **Data recency:** the training panel currently maxes at 2026-03-24; "retrain on latest data"
   should refresh the panel if newer source data exists.
3. **The prod swap touches live money** (config `panel_scoring.kind` hf_patchtst → xgb). Done
   deliberately, backed up, after this audit, with the E2E daily-full validation the operator asked for.

## Outcome (the P0 sequence was run)
1. Retrained XGB on latest data (artifact backed up). ✅
2. Gated it through the production WF gate → **FAILED** (regime-sanity + monotonicity); **NOT
   promoted** — see #166. The config swap was applied then reverted to git-known-good; live config clean.
3. Regime failure diagnosed (bounded) in #167: BULL_CALM weak, aggregate BEAR-inflated, gate correct.

So the rigor audit stands (method is sound), but it does **not** clear XGB for production. Any
production use is operator real-money discretion behind the `mu_floor` conviction gate (pipeline
#140), not a gate pass. Durable goal: strengthen the calm-market signal (Path 1).
