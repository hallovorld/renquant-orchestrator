# 2026-07-11 — R-PIN Stage 1: the first durable deployment record

`deploy/deployment-manifest.json` = the output of `deploy-pin capture --write`
run on the production host at ~11:07 PT against the on-disk lock and the
materialized `.subrepo_runtime/repos` clone HEADs (all 9 agreed; fail-closed
capture passed on the first run — [VERIFIED] the Stage-1 gate). Generation 1,
state `captured` (the design's pre-seal state: evidence_ref is sealed by a
follow-up once the e2e evidence bundle lands in renquant-artifacts store/).

This closes the §2.2 gap from the merged R-PIN design: the deployed pin
state (including today's strategy-104 f01c0259 sleeve-shadow pin, base-data
1bdfeb6f, orchestrator fb3b69ff with the write-containment fix, artifacts
c71edf7f store) now has a reviewed, versioned record for the first time.
Every future pin change records here FIRST (record-first, §7).
