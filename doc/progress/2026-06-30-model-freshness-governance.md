# model freshness governance — design PR

STATUS:   design for review (no code/config in this PR). Describe → discuss → PR to Codex → then implement per-repo.
REVISION: R2 (round-2) — reworked to address Codex `CHANGES_REQUESTED` on head `183764a5`.
WHAT:     proposes a freshness-governance contract — a data-cutoff-keyed staleness monitor (NOT just `trained_date`), a
          28-day hard ceiling on BOTH production models, a reliable/monitored retrain cadence, a DEFERRED best-of-recent
          fallback bounded to infra-failures + an OOS floor, and a WF-gate REPAIR so the strict path can re-validate the
          active primary.
WHY/DIR:  "no buys" has TWO independent freshness root causes. (A) Per-ticker tournament retrain TIMES OUT
          (`parallel_ticker_timeout_seconds=600`, only 67/142 finish) → cadence frozen since late April →
          `trained_date` 61d > 60d `model_staleness_days` → universe zeroes → 0 candidates. (B) The weekly WF-promote
          that would re-validate the ACTIVE PRIMARY panel scorer chronically fails → the live primary is frozen at 05-18
          with no standing WF evidence.
R2-FIX:   R1 rested on a FACTUALLY STALE premise (claimed PatchTST primary since 06-05, GBDT vestigial/sell-only). CORRECTED:
          pinned `strategy_config.json` has `panel_scoring.kind="xgb"`; the XGB/GBDT `panel-ltr.alpha158_fund` (trained 05-18)
          is the OPERATOR-DIRECTED live PRIMARY as of 06-23 (`_2026_06_23_xgb_promotion`, reversing the 06-05 PatchTST
          promotion); PatchTST is now SHADOW (`LoadScorerTask: loaded xgb` + `ApplyShadowScoringTask: shadow hf_patchtst`).
          The 06-23 switch was a CONFIG-KIND directive, NOT a gate pass; `promotion_status="gated_buys"` is a STALE stamp.
          → WF-gate section reframed from "retire the vestigial GBDT promote" to "REPAIR the gate to re-validate the PRIMARY".
CODEX-6:  (1) premise corrected + Action P0 production-state re-audit; (2) freshness keys on DATA cutoff / event_time /
          available_at / fingerprints, stale feeds BLOCK a fresh stamp; (3) fallback splits infra vs quality failures —
          bypasses ONLY enumerated infra failures AND only after an independently recomputed OOS economic floor;
          substance/leakage/placebo/recipe-mismatch/unknown stay FAIL-CLOSED; (4) best-of-10d pre-registered per model family
          OR marked DEFERRED — panel (1 scorer) vs tournament (142 tickers) are DIFFERENT populations, separate rules;
          (5) 28d/10d + "stale-is-safer" claim gated behind a point-in-time SHADOW REPLAY + pre-registered non-inferiority
          gate; (6) remediation triggers BEFORE the ceiling; atomic promote / concurrent-retrain / partial-completion /
          per-ticker coverage floor / rollback / run-bundle provenance; OWNERSHIP split (WF semantics→backtesting/model,
          policy→strategy, admission→pipeline, coordination→orchestrator; umbrella scripts do NOT own model selection).
RESHAPE:  near-term shippable = Phase 1 (observable monitor + measured timeout/cadence repair). Fallback DISABLED/deferred
          behind Action P0 + the shadow experiment + a pre-registered selection policy + a non-inferiority gate. Operator's
          core intent ("fresh beats stale when the retrain failed for a MECHANICAL reason") PRESERVED but NARROWED to
          infra-only + OOS floor + shadow validation (RFC §7 states the narrowing + why). 28d ceiling + best-of-recent kept
          as north star, staged safely.
EVIDENCE: `logs/daily_104/2026-06-30.log` (0 candidates / 0 tickers); RL/RF artifact mtimes ~2026-04-22; pinned
          `renquant-strategy-104/configs/strategy_config.json` `panel_scoring.kind="xgb"` + `_2026_06_23_xgb_promotion` /
          `_2026_06_23_role`; live-run scorer trace (xgb primary + hf_patchtst shadow); GBDT reject timeline — recipe-fp
          FIXED 05-27→06-04 (candidate+manifest both hash `cfdd6cb8`), Fix-1 sim per-bar path FileNotFoundError, Fix-2
          scorer-kind parity (direction to re-confirm under pinned xgb), Fix-3 placebo ceiling structurally unsatisfiable
          (~+0.04 embargo floor), Fix-4 substance (0/3 cuts beat SPY, ΔSharpe −0.72) = gate working correctly.
SCOPE:    this PR = RFC + this progress note ONLY. Cross-repo implementation (pipeline / strategy-104 config / umbrella
          scripts) is follow-up per-repo PRs AFTER the design is discussed. No broker/risk/sizing change.
NEXT:     Phase 1 (monitor + timeout fix + Action P0 re-audit) → Phase 2 (WF-gate repair) → Phase 3 (point-in-time shadow
          experiment) → Phase 4 (shadow-first fallback, only if the non-inferiority gate clears) → Final (flip
          `model_staleness_days` 60→28). Resolve §8 open questions along the way.
