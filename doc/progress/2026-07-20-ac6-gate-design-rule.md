# Progress — AC6 gate design rule (governed override path)

**Date:** 2026-07-20
**Goal:** GOAL-5 P0 AC6 (month-1). **Type:** repo-contract rule (docs + PR template).

## What
Codifies GOAL-5 AC6: every PR that adds/tightens a HARD capital-admission gate
must document a **governed override path** (identity / expiry / binding +
override provenance in the run bundle). Two artifacts:
- `doc/design/2026-07-20-ac6-gate-design-rule.md` — the rule: scope of "HARD
  capital-admission gate", the three required override properties, the
  provenance-in-run-bundle sub-requirement, enforcement + reviewer heuristic.
- `.github/pull_request_template.md` — a new checklist item making it a review
  gate (the AC6 acceptance = "enforced via review checklist").

## Why this direction
The 07-16 book-drain incident happened because a HARD gate had **no governed way
to lift it** → the only override was undocumented hand-surgery on live files. AC6
moves the override path to design time so the emergency path (AC3) is unnecessary.
The provenance-in-bundle clause closes the specific gap the 07-16 adversarial
re-review flagged (#203 MED: override provenance not in the run bundle).

## Scope guard
Rule targets *whether the system may act* (hard blocks), explicitly **excludes**
pure sizing/economic ranking. True kill-switches are allowed but must say so.

## Status / next (revised per codex review)
- Docs-only; no code. `EVIDENCE: canonical rule + orchestrator PR-template item
  added` `[VERIFIED — template diff + rule doc present]`.
- **AC6 is PARTIALLY met, not met/enforced fleet-wide.** This PR is R0: the
  canonical rule + its orchestrator instance. A checklist in one repo's template
  is manually attestable and does not govern gate PRs in strategy/pipeline/
  execution/model, nor mechanically enforce provenance-in-run-bundle.
- **AC6 completes only with the rollout** (rule §Enforcement): R1 canonical home
  in the umbrella arch contract; R2 the same checklist in every gate-owning repo;
  R3 provenance as a per-gate acceptance criterion in the interim; R4 the shared
  run-bundle validator + hard-block lint (the mechanical close). Tracked in #66.
- Remaining GOAL-5 month-1 also: AC5 full-funnel closer (#521, umbrella).
