# 2026-07-03 — M6 stage-2 design: fingerprint migration + live-artifact re-stamp plan

Docs-only design PR (`doc/design/2026-07-03-m6-stage2-fingerprint-migration.md`).
Successor to #244 (stage-1 contract) and renquant-common#21 (0.9.1 shims, which
name this stage-2 as their removal point). Trigger: renquant-pipeline#160 reverted
the #159 v1 cutover for lack of a migration plan for already-stamped production
artifacts — this is that plan.

## What was measured (read-only, live umbrella tree, 2026-07-03)

- Prod panel-LTR, both shadow-lane artifacts, and the 43 WF fold scorers carry
  **no stamped `model_content_fingerprint` at all** — identity is recomputed at
  every read; the active calibrator binding holds only because both sides
  currently recompute under the same 0.8.1 semantics.
- v1 ≠ legacy hash on every live artifact; no unclassified keys under the v1
  tables on the current inventory.
- Live venv: renquant-common **0.8.1**. On fleet convergence to 0.9.1 (D1 chain),
  with today's merged code: the weekly calibrator refit arms a daily fail-close,
  and `weekly_wf_promote` breaks immediately (the WF loader's recompute is the
  bare name = v1; its calibrator match is fail-CLOSED — corrects the
  "fail-soft = survivable" premise).

## The plan (see design §3)

Step 0 legacy pre-stamp (unblocks safe venv convergence, zero code) → step 1
version-dispatched verification behind `accept_legacy_stamps` flag (+ common
0.9.2 table additions) → step 2 v1 re-stamp run (gated on live pin-align + venv
evidence) → step 3 census green (orchestrator script, coverage-exercised window)
→ step 4 flag flip → step 5 common 0.10 shim removal (grep + census gated).
Dual-accept is version-DISPATCHED (one acceptable hash per artifact), reconciling
the task's dual-accept window with stage-1 §2c's no-OR rule.

## Follow-ups (implementation PRs, not in this PR)

1. Umbrella re-stamp tool PR + step-0 run (operator grant) — BEFORE the live venv
   converges on 0.9.x.
2. common 0.9.2 (OPERATIONAL_KEYS for migration stamp fields).
3. pipeline stage-2 code PR + strategy-104 flag PR.
4. orchestrator census script PR.
5. common 0.10 shim removal, last.
