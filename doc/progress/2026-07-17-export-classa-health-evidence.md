# rq105 export: replace the absolute row floor with class-A health evidence

STATUS: delivered
WHAT: `ops/renquant105/export_batch_scores.py` rejected the legitimate
light-signal 2026-07-16 session (5 candidate rows, 100% covered, real buys
placed) because of the absolute MIN_ROWS=25 floor — starving the whole
rq105 class-A chain (scheduler aborted `aborted_class_a_unavailable`).
Replaced the floor with independent run-health evidence (`_health_gaps`):
`run_bundle.panel_contract.ok is True`, `pipeline_flags.buy_blocked/
skip_buys are False` (a sell-only/containment run never ran the buy funnel
its frozen vector represents), and `training_cutoff` +
`model_content_sha256` present (the G4 provenance chain). MIN_ROWS drops
to a bare non-empty sanity check; the existing fingerprint-gap and
0.9-coverage checks are unchanged.
WHY/DIR: task #64 / GOAL-5 follow-through — the floor's original job
(excluding the pre-operational 2026-04-23..27 cluster) is now done by
three stronger evidence checks; the ops-layer degradation sentinel
independently alarms on thin-candidate streaks.
EVIDENCE: real-DB proof — the 2026-07-16 run EXPORTS (rc=0, 5/5, 100%);
both probed April-cluster runs fail all four health gaps. Module tests
43/43 (new admit/reject matrix incl. the sell-only-guard-run rejection);
full suite 4000 passed.
NEXT: live verification = the next 06:25 PT firing after deploy.
