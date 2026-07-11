# 2026-07-11 — shadow-ab write containment (self-poisoning fix)

## Incident

The first VALID §2a pair (02:15 PT) itself poisoned the next session: the
kernel's `AdmissionShadowLoggerTask` defaults its JSONL to
`config["_strategy_dir"]/logs/` — on the arm path that is the
MANIFEST-PINNED strategy checkout. The 04:5x sanity kickstart (run
deliberately after amending the manifest's base-data pin) precheck-aborted:

```
run manifest verification failed: renquant-strategy-104: working tree DIRTY (1 path(s), e.g. '?? logs/')
```

Session N's arms dirty the tree AFTER session N's own verification passed →
session N+1 fails closed. Stray `logs/admission_shadow.jsonl` (58k, 02:00
timestamp) archived to the experiment root
(`archive/strayed-arm-logs-*/`) as evidence; tree restored clean for today's
14:35 PT counted session (arms only dirty post-verify, so today is safe
even without this PR deployed).

## Fix

1. **Containment**: the runner threads `--log-containment-dir <arm_dir>`
   into each arm's inference step; hydration redirects every known
   strategy-dir-relative kernel writer in-memory (`admission_shadow.path`,
   `sleeve.log_path` when present) to the arm's own directory. Same
   identity-safety argument as the #464 artifact rewrite: config sha is
   frozen from raw file bytes; these keys are not in the P-CONFIG-FP
   projection. Arm configs untouched (no VOID).
2. **Self-healing backstop**: post-arms, the runner re-scans every manifest
   repo; an untracked `logs/` (the known byproduct pattern) is QUARANTINED
   into the session dir with a bundle warning (evidence preserved, next
   session unblocked); anything else dirty is reported and left in place —
   the next precheck fails closed on it, by design.

## Evidence

- 2 new tests (arm commands carry the containment dir pointing at the arm
  dir; quarantine moves logs/ + preserves evidence + leaves unrelated dirt
  in place with a warning). Affected suites green except the 6 pre-existing
  sandbox-baseline failures (verified identical on origin/main earlier
  tonight).
