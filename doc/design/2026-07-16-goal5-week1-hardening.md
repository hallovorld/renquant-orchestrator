# GOAL-5 week-1 hardening: detect, drift, containment (AC1-3)

Date: 2026-07-16
Goal: GOAL-5 P0 — systemic prevention of the 2026-07-16 incident class
(book drained to 94% cash across 3 silently fail-closed sessions).

## Incident layers → deliverables

| Incident layer | Root pattern | Deliverable | AC |
|---|---|---|---|
| 3 days of zero candidates + swallowed calibrator Traceback + weekly-wf-promote exit 1, all unnoticed | silence ≈ health | `ops/renquant104/rq104_degradation_sentinel.py` (PR #527) | AC1 |
| 07-15 launchd containment swap invisible; orchestrator-run 130 commits behind with 6 un-upstreamed hotfixes | run surface ≠ reviewed surface | `ops/run_surface_drift_check.py` + `ops/launchd_manifest.json` baseline (PR #528) | AC2 |
| the containment left no record, no expiry, no owner | out-of-band changes invisible to the next operator | CONTAINMENT PROTOCOL in CLAUDE.md (this PR) | AC3 |

Companion month-1 work (task #66): AC4 transactional artifact bundles
(kills the 4x-recurring calibrator binding-orphan class), AC5 integration
preflight as a pin-merge CI gate (would have caught orch#524's namespace
gap pre-deploy), AC6 governed-override design rule for HARD capital gates.

## AC drill plan (delivery = demonstrated detection, not merged code)

- **AC1**: (done, in PR #527 evidence) `rq104_degradation_sentinel.py
  --as-of 2026-07-15` against the prod DB (read-only) reproduces the
  incident alarm — zero-candidate streak + swallowed Traceback — i.e. the
  operator would have been paged on day 2. Post-deploy: one live scheduled
  firing on a healthy day must stay silent.
- **AC2**: (done, in PR #528 tests) the exact containment (daily104 →
  /tmp wrapper) replayed against the committed manifest alarms; live drill
  post-deploy = benign one-char manifest edit → next firing alarms →
  revert.
- **AC3**: drill = simulate a containment (task + record + intentionally
  NO manifest update) → verify the drift scan alarms daily until lifted,
  and the task expiry is visible. Protocol text is prompt-level compliance;
  the drift scan is its mechanical backstop (same split as the existing
  CLAUDE.md enforcement note).

## Deploy (operator-gated landing)

Load `deploy/com.renquant.rq104-degradation-sentinel.plist` (15:00 PT) and
`deploy/com.renquant.run-surface-drift.plist` (07:00 PT), then add both to
`ops/launchd_manifest.json` in the same reviewed change.
