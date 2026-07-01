# shadow scorer (PatchTST) freshness — design PR

STATUS:   design for review (no code/config in this PR). Describe → discuss → PR to Codex → then implement per-repo.
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
NEXT:     Phase 1 shadow freshness monitor (observe-only) + last-successful-retrain timestamp → Phase 2 (re)install the
          weekly scheduled job + run the §4 manual refresh/promote remediation → Phase 3 automated retrain→served-pin
          promote (atomic, re-stamped against the pinned config) → Phase 4 confirm the 35d breach default + wire the
          untrustworthy-comparison annotation. Resolve §6 open questions (ceiling, promote autonomy, data-vintage
          dependency, cadence) in discussion.
