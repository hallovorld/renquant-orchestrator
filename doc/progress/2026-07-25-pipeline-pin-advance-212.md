# 2026-07-25 — pipeline pin advance: deploy the P-STATE-FILE fix (#212) to live

STATUS:    EXECUTED (operator-authorized machine landing, one grant, this batch only)
WHAT:      Umbrella `subrepos.lock.json` renquant-pipeline pin advanced
           `d32f7017ff05` → `9c5f48e653fb` via `scripts/promote_pin.py bump --apply`
           (atomic lock write + `subrepo_assemble --sync` materialization).
WHY/DIR:   Deploys the merged pipeline#212 fix — P-STATE-FILE had SOFT-failed the
           LiveStateV2 schema check against the live book on every run since
           2026-07-11 (a staged fail-close under the strict flip).
DELTA DEPLOYED (full list, 4 commits):
  9c5f48e  merge #212 (MonitorStateV2 accepts funnel_integrity_history)
  56737dd  the #212 fix itself
  05eaf8f  #211 shadow-scorer health record (shadow-side, additive)
  a871166  #209 decision-schedule record-validation API (additive)
EVIDENCE:
  artifact:      umbrella subrepos.lock.json (renquant-pipeline.commit = 9c5f48e653fb…);
                 .subrepo_runtime/repos/renquant-pipeline at 9c5f48e (verified)
  prod or exp:   PROD machine landing, operator-authorized 2026-07-25 ("授权")
  existing data: pre-deploy dry-run diff reviewed; promote-bak backup created by the tool
  best-known?:   promote_pin.py is the house's atomic/verified/reversible pin path
  scope:         "P-STATE-FILE check on the DEPLOYED runtime against the real
                 live_state.alpaca.json: PASS — LiveStateV2 valid, 4 holdings,
                 7 funnel-history records, 0 quarantined keys. Next daily-full
                 (Monday 13:55 PT) is the live confirmation."
REVERT (literal):
  cd /Users/renhao/git/github/RenQuant && .venv/bin/python scripts/promote_pin.py revert --apply
  # or: scripts/promote_pin.py bump --subrepo renquant-pipeline \
  #       --commit d32f7017ff052faae16668850e6c1b3be1359f08 --apply
KNOWN RESIDUE (pre-existing, NOT introduced here; left untouched, no grant):
  - drift scan: runtime/renquant-model has 1 uncommitted README.md change
  - drift scan: orchestrator-run HEAD ade07dd7 behind expected 1242c96e (orchestrator
    pin advance is a SEPARATE landing needing its own grant)
  - umbrella working tree carries the long-standing dirty artifact set; the lock +
    snapshot changes from this promotion are uncommitted there (umbrella lock
    commits blocked by Codex #460)
  - `deploy/deployment-manifest.json` (the R-PIN Stage-1 authority document,
    doc/progress/2026-07-11-r-pin-first-durable-record.md:14 "every future
    pin change records here FIRST") was NOT advanced by this landing — it
    still records `renquant-pipeline.commit = 289b919908fc…` at generation 1
    (2026-07-11). CORRECTION (Codex #578 review): an earlier draft of this
    doc wrongly claimed the manifest already served as the durable surface
    for this move; it does not — this doc is an informal stage-1 note only.
    Advancing the manifest requires `deploy-pin capture --write
    --evidence-ref store://…` against the current on-disk lock (already at
    `9c5f48e653fb`, agreeing with the materialized `.subrepo_runtime` clone
    HEAD) plus a sealed readonly-e2e evidence bundle landed in
    renquant-artifacts — a SEPARATE landing needing its own grant, tracked
    here until done.
NEXT:      watch Monday's daily-full for "preflight ✓ P-STATE-FILE [HARD] loaded
           live_state.alpaca.json (LiveStateV2 valid…)"; then the strict flip can
           proceed on its own schedule. Separately: land the deployment-manifest.json
           R-PIN follow-up above.
