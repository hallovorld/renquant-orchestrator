# Live-tree sync drill runbook — ops doc PR

STATUS:   ops runbook (docs only; operator-executed by design — agents never run git
          mutations in the live tree).
REVISION: r1.
WHAT:     `doc/ops/live-tree-sync-drill.md` — R7's remaining slice (S11 named it the open
          deliverable): the safe sequence for bringing the behind-with-overlapping-dirt live
          umbrella checkout up to origin/main. Snapshot (status/diff/stash-list to dated
          files) → classify dirt into the four S11 classes (code-residue-already-upstream /
          code-hotfix-NOT-upstream=HALT-and-PR-first / live-stamped-artifacts-keep /
          data-churn-keep) → stash+ff-only-merge+pop (never reset/checkout/clean) → verify
          (the runner.py self._config canary, make doctor, watch the next intraday tick) →
          never-list with case law (06-25 clobber, 06-26 18-FAIL discovery lag, 06-17
          rawlabel overwrite, #412 agent near-miss).
WHY/DIR:  #231 Term PROCESS / floor tier-2: the undisciplined floor's only remaining
          documented hole was the absence of a written safe-landing sequence — the 06-25
          incident happened precisely because the recovery was improvised. Timing windows
          (post-daily-run, outside market hours), ff-only semantics, and the class-2 HALT
          rule encode the lessons as procedure.
EVIDENCE: S11 inventory (2026-07-02, PR #241) for the current dirt classes; incident case
          law from the memory records (dates in-doc).
NEXT:     Codex review; the lander uses this runbook for the pending sync (which also clears
          the "pins NOT deployed" WARN); the runbook is referenced from the M9 generated-
          snapshot follow-up so doc and procedure stay linked.
