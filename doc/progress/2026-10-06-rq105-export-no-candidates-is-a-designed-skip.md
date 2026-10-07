# 2026-10-06 — rq105 export: a completed run with ZERO candidates is a designed skip (the sell-only shape #1128 could not see)

STATUS:   delivered, awaiting review — zero reviews at head.
WHAT:     `ops/renquant105/export_batch_scores.py`: when `_select_source_run`
          finds no qualifying run, `_completed_runs_without_candidates` checks
          for the positive evidence of an empty funnel — ≥1 completed live run
          on the expected prior session, every one contract-clean
          (`panel_contract.ok is True`), and not one `role='candidate'` row
          with a non-null `panel_score` across them. That is a designed skip
          (exit 3, sidecar `reason="no_candidates"`). No completed run, a
          non-clean run, or a thin-but-non-empty roster all stay exit 1.
          `rq105_liveness_check._DESIGNED_SKIP_REASONS` admits the new reason
          and names it in the OK line; `run_shadow_serving.sh` wording
          generalised. 4 exporter tests + 1 liveness test.
WHY/DIR:  root cause of every `rq105 export FAILED rc=1` → `serving SKIPPED`
          → `🚨 rq105 DOWN` page since 2026-09-29. #1128 keyed the designed
          skip on `pipeline_flags.buy_blocked/skip_buys`, but the sell-only
          FALLBACK (preflight P-WF-GATE/P-REGIME-IC hard-fail) records
          `buy_blocked=False skip_buys=False` and persists zero candidate rows,
          so the source-run query returns nothing and the buy-gated branch is
          never reached. rq105 is downstream of 104's buy admission: a session
          where 104 admitted nothing has no class-A vector by construction;
          104's own zero-candidate sentinel owns that alarm.
EVIDENCE: see §4(b) below.
  artifact:      ops/renquant105/export_batch_scores.py, ops/renquant105/rq105_liveness_check.py, ops/renquant105/run_shadow_serving.sh, tests/ (159 passed across the four rq105 suites on this branch).
  prod or exp:   exp — ops-script change; effective at the next 06:15 export after merge + -run sync. Reads the DB read-only; writes only the sidecar under data/rq105/ that #1128 already defined.
  existing data: runs.alpaca.db [VERIFIED read-only 2026-10-06 14:1x PDT]: 2026-10-02 35 completed live runs / 0 candidate rows, 2026-10-05 36 / 0, 2026-10-06 35 / 0, every bundle `panel_contract.ok=True`, `pipeline_flags={buy_blocked: False, skip_buys: False}`, `wf_gate_provenance.passed=False promotion_basis=freshness_fallback_rfc210`; 2026-09-28 (last FULL day) 69 candidate rows. Export log 2026-10-06: `no qualifying completed live run for the expected prior session 2026-10-05`. No persisted sell-only marker exists in the run bundle or `gate_verdicts` (0 rows for 10-05) — the pipeline knows `run_mode` in preflight but does not record it; this fix therefore keys on the OBSERVABLE (contract-clean completed run, zero rows), not on a flag that is not written.
  best-known?:   yes — anti-vacuity: the sell-only test fails against the deployed main exporter (1 failed) and passes here; the three negative tests pass on both (they pin that the three non-designed shapes stay exit 1).
  scope:         orchestrator ops + tests only; no data/config/artifact touched.
NEXT:     merge + -run sync; pipeline should eventually persist `run_mode` into
          the run bundle so the exporter can say "sell-only" rather than
          "zero candidates" — a pipeline-repo change, not taken here. The
          pages this leaves standing are 104's: model freshness BREACH / STALE-
          MODEL / preflight ERROR / silent-refusal, all one fact (no servable
          artifact since 09-29) awaiting the operator's RFC#210 decision.
