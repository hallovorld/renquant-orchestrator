# model freshness governance — design PR

STATUS:   design for review (no code/config in this PR). Describe → discuss → PR to Codex → then implement per-repo.
REVISION: R5 (round-5) — addresses Codex's round-4 review on head `c02655d7`, which ACKNOWLEDGED R4 resolved B3 (the
          fail-closed replay-feasibility audit + committed held-out confirmation + prospective-logging fallback) and left
          ONE remaining blocker: point-in-time eligibility lacks an explicit ARTIFACT-AVAILABILITY timestamp. Prior: R4
          (head `c02655d7`) added the §5.0 Phase-0 audit; R3 (head `68e2ab01`) split selection from confirmation +
          per-source SLA; R2 reworked round-1 on head `183764a5`. This revision also MERGES `origin/main` (weekly-APY CI
          fix #211) so the shared `test` check reruns green.
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
CODEX-R5: ONE remaining blocker resolved (docs-only, §5.0/§5.4 edit). Codex round-4 acknowledged R4 resolved B3. BLOCKER:
          point-in-time eligibility lacked an explicit ARTIFACT-AVAILABILITY timestamp — §5.0 admitted a candidate on
          `data cutoff <= simulated date` ALONE, which is necessary but NOT sufficient: a model trained/registered July 1
          on a May 31 cutoff was NOT available to a June 15 decision, yet that predicate admits it → BACKFILLS a
          later-created artifact into an earlier date (look-ahead). FIX: (1) §5.0(i) now enumerates immutable
          `artifact_created_at` / `registry_available_at` fields for EVERY candidate + the gate verdict's `observed_at`,
          recorded at creation from a write-once source; (2) new §5.0(i-a) eligibility predicate — a candidate is eligible
          at simulated time `t` IFF all data-cutoff axes (§2) AND `artifact_created_at`/`registry_available_at` AND gate
          `observed_at` are `<= t` (cutoff alone is explicitly insufficient); (3) the predicate is applied to EVERY arm
          in §5.4 — current-prod-hold, newest-eligible, best-recent fallback, AND the rollback identity — so no arm can
          reference an artifact created after `t`; (4) §5.0(ii) coverage matrix reports a MISSING availability timestamp
          as its own missingness class and FAILS CLOSED (excludes/flags the candidate) rather than inferring it from a
          filesystem mtime or git commit ancestry. Header REVISION + §5-intro round-5 note updated to match.
CODEX-R4: ONE prior blocker resolved (docs-only, §5 rewrite). Codex round-3 acknowledged R3 fixed both prior blockers.
          (B3) REGISTRY FEASIBILITY NOT ESTABLISHED — §5 assumed a point-in-time registry (per breach date: complete
          then-knowable candidate set, artifact bytes + recipe/data fingerprints + cutoffs, gate result + failure class,
          subsequent OOS outcomes) whose EXISTENCE + COVERAGE were never audited; reconstructing from artifacts surviving
          today = SURVIVOR BIAS, regenerating with current code/data = LOOK-AHEAD + RECIPE DRIFT, and a selection/confirmation
          split cannot fix biased/MISSING INPUT history. FIX: (1) new §5.0 Phase-0 replay-FEASIBILITY audit MUST PASS
          (fail-closed) BEFORE any pre-registration — enumerate exact required fields + IMMUTABLE sources; date-by-date
          candidate/artifact COVERAGE + MISSINGNESS broken down by ARM and by FAILURE CLASS (missingness correlated with
          failure class = biased sample, not just thin); fixed MINIMUM independent-breach-event + 60d-OOS floor; FAIL CLOSED
          if the untouched confirmation window lacks enough complete/unbiased events. (2) §5.6 honest fallback — if historical
          coverage insufficient, do PROSPECTIVE SHADOW LOGGING first (accrue a clean write-once point-in-time registry going
          forward); do NOT claim the historical replay can authorize 28d/10d from incomplete/survivor-biased history; Pillar 3
          stays DEFERRED, Phase-1 monitor+cadence ship regardless. (3) §5.2 now COMMITS to a temporally-later HELD-OUT
          CONFIRMATION span as the policy-authorizing design (confirms ONE FIXED 28d/10d policy); nested/rolling DEMOTED to a
          SECONDARY robustness check of the ADAPTIVE SELECTOR, explicitly NOT policy-authorizing (choice fixed BEFORE prereg
          freeze). Rollout Phase 3 split into 3a (feasibility audit) → 3b (experiment only if 3a passes, else §5.6).
CODEX-R3: TWO blockers resolved (docs-only, §2/§3/§5 rewrites). (B1) SELECTION-BIAS — R2 chose 28d/10d AND gated them on the
          SAME shadow replay; §5 rebuilt as a two-stage protocol: pre-registered candidate grid (fast ceiling {21,28,35,45},
          window {5,10,15}, slow-axis P-FUND-FRESHNESS params) + ALL selection inside an inner/selection stage + verdict read
          ONLY from a temporally-later UNTOUCHED confirmation span (5.2a) OR nested/rolling OUTER folds (5.2b) + simultaneous
          confidence bounds / DSR-style multiplicity haircut across the grid; 28d/10d are labelled SELECTION-STAGE OUTPUTS,
          the authorizing verdict comes only from the confirmation/outer stage. (B2) PER-SOURCE FRESHNESS — one universal
          raw-age ceiling is invalid for heterogeneous feeds (a point-in-time quarterly value can be >28d old yet CURRENT; a
          fresh backfill timestamp does NOT make an overdue filing current). §2/§3 replaced with PER-SOURCE SLA: each
          actually-used feed judged on its own contract (reporting period, available_at, expected-next-update, failed-harvest);
          28d ceiling binds ONLY the FAST axis (OHLCV/price-derived/retrain cutoff), SLOW axis (quarterly fundamentals/
          estimates) "current" iff latest-expected filing present + on-SLA; model's BINDING status = worst actually-used
          source, not one global age. Reconciled with the pipeline's existing P-FUND-FRESHNESS split (daily-feed
          max_feed_stale_days=20 vs quarterly-availability filing_lag_days=45 / max_quarters_behind=1) — governance REUSES
          those two dimensions rather than inventing a third number; §5 replay evaluates the source-specific policies, not one
          global age.
CI-NOTE:  Codex (round-5) again requires the required checks green before merge. The previously-RED required `test` check was
          the weekly-APY LOOK-AHEAD failure, fixed in PR #211 (`fix/weekly-apy-monitor-time-dependent`), now MERGED to `main`.
          This revision MERGES `origin/main` into the branch (disjoint change: this branch = docs, #211 = src/tests → clean
          merge, no conflicts) so the shared `test` check reruns against the fixed code. This PR itself remains docs-only and
          touches no code / config / broker / risk / sizing.
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
NEXT:     Phase 1 (monitor + timeout fix + Action P0 re-audit) → Phase 2 (WF-gate repair) → Phase 3a (§5.0 replay-feasibility
          audit; fail-closed) → Phase 3b (point-in-time shadow experiment ONLY if 3a passes, else §5.6 prospective logging
          first) → Phase 4 (shadow-first fallback, only if the non-inferiority gate clears) → Final (flip
          `model_staleness_days` 60→28). Resolve §8 open questions along the way.
