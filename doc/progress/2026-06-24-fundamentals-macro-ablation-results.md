# #58 ablation executed — fundamentals/macro/analyst don't earn their keep (with caveats)

STATUS:   evidence PR (research doc). No production/model change. Executes the approved
          plan #184 — PARTIAL by necessity (fundamentals arm only; sentiment/PEAD deferred).
WHAT:     5-seed, per-(regime×WF-window) placebo-clean ablation of alpha158+fund vs
          alpha158-only, + the macro (structural) and analyst (yfinance / FMP) answers.
          Doc: doc/research/2026-06-24-fundamentals-macro-ablation-results.md.
RESULT:   fundamentals practical-null in ALL regimes (Δ BULL_CALM +0.0054±0.0209, BEAR
          +0.0081±0.0306, BULL_VOL −0.0075±0.0199; none clear ±0.01 or the ≥5/6-window sign
          rule). Macro=0 for selection (not in scorer). Analyst: yfinance negative all
          regimes; FMP revision plan-locked (free covers ~30%, HTTP 402) + inside noise.
WHY-DIR:  answers the operator's "which data is truly valuable?" with pre-registered method.
          The 5-seed/per-window rule CORRECTED a spurious 3-seed "robust −0.0075±0.0014"
          (artifact of averaging windows before the seed sd) → really ±0.0199 noise.
CAVEATS:  (1) sentiment/PEAD LOGO arms NOT runnable — dataset lacks those columns (deferred,
          not concluded). (2) Does NOT license retiring the fundamentals pipeline: this
          dataset (built 2026-05-08) predates the #398/#401 refresh, so a null indicts the
          bundle's current value, not the signal — rule #2 needs a rerun on refreshed data.
          (3) underpowered (~3–4 windows/regime); a null bounds the effect <~0.01, not zero.
NEXT:     no model change. If we want a fundamentals-RETIRE decision: build a refreshed panel
          (+ sentiment/PEAD columns) and rerun C−B / A−D1. Otherwise the conclusion stands:
          model is ~entirely alpha158 technical; honest lever = calibration + cost-aware
          construction + entry filter, not adding weak non-technical alpha.
