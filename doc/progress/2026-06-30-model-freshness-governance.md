# model freshness governance — design PR

STATUS:   design for review (no code/config in this PR). Describe → discuss → PR to Codex → then implement per-repo.
WHAT:     proposes a freshness-governance contract — 28-day hard ceiling on BOTH production models, a tiered
          staleness monitor, a reliable/monitored retrain cadence, a best-of-last-10-days fallback auto-promote,
          and WF-promote cleanup (Fix-1/2/3) so the strict path can pass a good model.
WHY/DIR:  "no buys" has TWO independent freshness root causes. (A) Per-ticker tournament retrain TIMES OUT
          (`parallel_ticker_timeout_seconds=600`, only 67/142 finish) → cadence frozen since late April →
          `trained_date` 61d > 60d `model_staleness_days` → universe zeroes → 0 candidates. (B) The weekly GBDT
          WF-promote chronically fails but is VESTIGIAL (panel scorer switched to PatchTST 2026-06-05; GBDT is a
          never-gate-passed sell-only fallback that reached prod via STAMP ops, not promotion).
EVIDENCE: `logs/daily_104/2026-06-30.log` (0 candidates / 0 tickers); RL/RF artifact mtimes ~2026-04-22;
          GBDT reject timeline — recipe-fp FIXED 05-27→06-04 (candidate+manifest both hash `cfdd6cb8`, MATCH),
          Fix-1 sim per-bar path FileNotFoundError, Fix-2 PatchTST-kind vs GBDT-artifact parity fail, Fix-3
          placebo ceiling structurally unsatisfiable (~+0.04 embargo floor), Fix-4 substance (0/3 cuts beat SPY,
          ΔSharpe −0.72 on the clean 06-11→14 runs = gate working correctly). `[VERIFIED — prior investigation]`
SCOPE:    this PR = RFC + this progress note ONLY. Cross-repo implementation (pipeline / strategy-104 config /
          umbrella scripts) is follow-up per-repo PRs AFTER the design is discussed. No broker/risk/sizing change.
NEXT:     resolve §6 open questions (fallback metric; 28d/10d numerics; retire vs re-kind the GBDT promote; gate
          panel admission on staleness), then implement in phases — monitor + timeout fix first (Phase 1),
          WF-gate cleanup (Phase 2), shadow-first fallback (Phase 3), then flip `model_staleness_days` 60→28.
