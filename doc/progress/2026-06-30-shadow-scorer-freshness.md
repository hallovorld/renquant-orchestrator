# shadow scorer (PatchTST) freshness — design PR

STATUS:   design for review (no code/config in this PR). Describe → discuss → PR to Codex → then implement per-repo.
REVISION: r2 (2026-06-30) — addresses Codex's ONE blocking point on r1 (head c771eab6): "cadence +
          automatic promotion do NOT make stale INPUT DATA fresh" — r1 would have churned the served
          pin to a new artifact carrying the SAME 2026-02-10 (~140 data-day) information set, resetting
          operational timestamps without repairing data freshness (the trained_date-vs-data-cutoff
          error #210 §2 prevents). r2 fixes it: (1) upstream POINT-IN-TIME PANEL REFRESH is now a
          PREREQUISITE of the shadow retrain/promote, not a name-only/out-of-scope dependency (§3.1,
          §6 Q3); (2) the promote FAILS CLOSED unless every recipe-required source is on its
          source-specific SLA (reuse #210 §2/§3) AND effective_train/selection_cutoff ACTUALLY ADVANCE
          — a justified no-advance retrain is LABELED non-fresh and does not reset the freshness clock
          (§3.1, §3.4); (3) new §3.4 VALIDATED-PROMOTE gate — rc=0 is insufficient: artifact load +
          smoke inference, schema/recipe/config-FP parity (reconciled with panel_scorer_config_mismatch
          re-stamp, §3.3), non-degenerate outputs, resource bounds, minimum shadow-quality sanity floor,
          else keep the old pin; (4) §2 states the BLAST RADIUS — shadow moves no capital but shares the
          inference + reporting paths, so a broken artifact can still fail the daily run or corrupt
          champion-challenger evidence → the gate is not optional; (5) §3.2 re-keys the monitor's
          `healthy` state to the served artifact's BINDING DATA CUTOFF + a successful VALIDATED promote
          (per-source SLA), NEVER "last successful retrain". Docs-only; merged origin/main (PR #211
          weekly-APY CI fix) to keep `test` green. Re-requested review from haorensjtu-dev.
WHAT:     fills the SHADOW-PANEL cell of #210's freshness matrix ({prod,shadow}×{panel,per-ticker}). Proposes (a) a
          reliable, MONITORED weekly retrain cadence for the shadow HF-PatchTST scorer — restore the scheduled launchd job
          + add the missing retrain→served-pin PROMOTE step; (b) a shadow freshness MONITOR reusing #210's tiered
          data-cutoff monitor, with a deliberately more-lenient 35d breach ceiling (non-trading); (c) a reconcile with the
          shadow config-fingerprint fail-closed (re-stamp = config drift, retrain = data drift; a fresh promote must stamp
          against the pinned config so it does not reintroduce panel_scorer_config_mismatch).
WHY/DIR:  PatchTST is SHADOW (prod primary is XGB since 06-23, #210 §0), so this is a champion–challenger / model-monitoring
          concern, NOT live-trading risk — but a 39d-stale challenger makes every prod-vs-shadow delta meaningless. Frozen
          for TWO compounding reasons: (1) the retrain job has NO scheduled launchd entry (unowned cadence, last MANUAL run
          2026-06-16), and (2) even when it runs it writes the WF corpus (latest cutoff 2026-03-09), NOT the config-pinned
          served snapshot — so the served bytes stay at 2026-05-22 ("merged is not deployed"). #210 covers prod-panel +
          per-ticker; NONE of the three model populations has a reliably-running monitored refresh cadence — this RFC
          completes the set.
EVIDENCE: (all read-only, live umbrella tree, 2026-06-30) `launchctl list | grep renquant` → retrain-panel104 /
          conditional-retrain104 / retrain-alpha158-linear / monthly-meta-label-retrain / weekly-wf-promote present, NO
          weekly-retrain-patchtst. `logs/weekly_retrain_patchtst/` = 3 files (06-07, 06-08 rc=0, 06-16 rc=0 last) — nothing
          in ~2 weeks since. Served artifact
          `artifacts/patchtst_shadow/pt07_strict_trainfit_embargo60_20260522/seed_44/hf_patchtst_all_seed44_model.pt`:
          model.pt mtime 22 May, trained_date=2026-05-22 (~39d), effective_train_cutoff_date=2024-11-13,
          effective_selection_cutoff_date=2026-02-10 (~140 data-days). Pinned `strategy_config.shadow.json`:
          panel_scoring.kind=hf_patchtst + fixed artifact_path=…/pt07…20260522/… (retrain does not advance it).
          config_fingerprint=sha256:f8fb2259b2bf1537 + `…metadata.json.bak.20260625-restamp` (the 06-25 re-stamp event).
          NOTE: parent investigation cited last-run 06-08; ground-truth is 06-16 — both manual, no scheduled cadence
          either way.
COMPLEMENT: reuses #210 (`doc/design/2026-06-30-model-freshness-governance.md`) — its data-cutoff freshness key, tiered
          observe-only monitor, ownership split, and staged/reversible rollout — applied to the shadow scorer; does NOT
          duplicate #210's ceiling/replay machinery. The 35d shadow ceiling is a cheap observe-only monitor-tier default,
          NOT a trading gate, so it does not need #210's §5 point-in-time replay authorization.
SCOPE:    this PR = RFC + this progress note ONLY. Implementation (umbrella launchd plist + retrain/promote script,
          strategy-104 shadow config, pipeline/orchestrator monitor) is follow-up per-repo PRs AFTER discussion. No
          broker/risk/sizing change; never bypass branch protection. The immediate remediation (one manual retrain +
          promote + (re)install the scheduled job) is SPECIFIED in §4 but explicitly NOT executed here.
OWNERSHIP: shadow retrain script + launchd schedule = umbrella ops; recipe/promote mechanics = backtesting/model;
          freshness policy + tiers + artifact_path pin = strategy-104 config; monitor + run-bundle provenance = pipeline/
          orchestrator.
NEXT:     Phase 1 shadow freshness monitor (observe-only) keyed on the served artifact's BINDING DATA CUTOFF +
          validated-promote status (cadence-lapse alert = parallel liveness track) → Phase 2 (re)install the weekly
          scheduled job (cadence) → Phase 3 wire the upstream point-in-time PANEL REFRESH prerequisite ahead of retrain +
          the §3.4 validated-promote gate (fail-closed unless per-source SLA on-SLA AND cutoffs advance) → Phase 4 automated
          retrain→VALIDATED served-pin promote (atomic, re-stamped against the pinned config) + run the §4 manual
          remediation → Phase 5 confirm the 35d data-cutoff breach default + wire the untrustworthy-comparison annotation.
          Resolve §6 open questions (ceiling, promote autonomy, panel-refresh ownership/sequencing, cadence) in discussion.
