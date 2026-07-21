# Progress — AC6 gate design rule (governed override path)

**Date:** 2026-07-20
**Goal:** GOAL-5 P0 AC6 (month-1). **Type:** repo-contract rule (docs + PR template).

## What
Codifies GOAL-5 AC6: every PR that adds/tightens a HARD capital-admission gate
must document a **governed override path** (identity / expiry / binding +
override provenance in the run bundle). Artifacts, this PR + two companions:
- `doc/design/2026-07-20-ac6-gate-design-rule.md` — the rule: scope of "HARD
  capital-admission gate", the three required override properties, the
  provenance-in-run-bundle sub-requirement, enforcement + reviewer heuristic.
- `.github/pull_request_template.md` — a new checklist item making it a review
  gate (this repo's instance of the rule, not fleet-wide).
- Companion (different repo): `hallovorld/RenQuant#522` — adds the rule as
  Universal Rule 7 in the umbrella architecture contract, the actual canonical
  cross-repo home (open, pending review).
- Companion (this repo): `renquant-orchestrator`#564 — tracks the remaining
  per-repo rollout (R2) and the run-bundle validator work (R4).

## Why this direction
The 07-16 book-drain incident happened because a HARD gate had **no governed way
to lift it** → the only override was undocumented hand-surgery on live files. AC6
moves the override path to design time so the emergency path (AC3) is unnecessary.
The provenance-in-bundle clause **requires future gate PRs to close**, under R3,
the specific gap the 07-16 adversarial re-review flagged (#203 MED: override
provenance not in the run bundle) — this PR adds no schema, producer, or
validator itself; see the design doc's disposition of `LiveRunBundle` vs. the
daily `run_bundle.json` for what R4 has to reconcile.

## Scope guard
Rule targets *whether the system may act* (hard blocks), explicitly **excludes**
pure sizing/economic ranking. True kill-switches are allowed but must say so.

## Status / next (revised per second codex review round)
- Docs-only; no code. `EVIDENCE: provisional orchestrator-local rule + PR-template
  item added; companion umbrella PR opened` `[VERIFIED — template diff + rule doc
  + hallovorld/RenQuant#522 present]`.
- **AC6 is PARTIALLY met, not met/enforced fleet-wide.** This PR is R0: a
  **provisional, orchestrator-local** rule + its PR-template instance — it is
  explicitly **not** "the canonical rule" while its only source lived here.
  The canonical cross-repo source is now `RenQuant` `doc/arch/subrepo-operating-model.md`
  Universal Rule 7 (companion PR `hallovorld/RenQuant#522`, open/pending review,
  not yet merged). A checklist in one repo's template is manually attestable and
  does not govern gate PRs in `renquant-pipeline`/`renquant-execution`/
  `renquant-strategy-104`/`renquant-model`, nor mechanically enforce
  provenance-in-run-bundle.
- **AC6 completes only with the rollout** (rule §Enforcement): R1 canonical home
  in the umbrella arch contract (PR open, `hallovorld/RenQuant#522`); R2 the same
  checklist in every gate-owning repo, grep-grounded to `renquant-pipeline`
  (primary, 85 hits), `renquant-execution` (10 hits), `renquant-strategy-104`
  (config-only, 0 code hits but in scope), `renquant-model` (7 hits, lower
  confidence — verify before wiring); R3 provenance as a per-gate acceptance
  criterion in the interim; R4 the shared run-bundle validator + hard-block lint
  (the mechanical close — see design doc for the existing `LiveRunBundle` schema
  vs. the unvalidated daily `run_bundle.json` it would need to reconcile).
  Tracked in `renquant-orchestrator`#564 (the prior `#66` reference in an earlier
  revision was a stale link to an unrelated merged evidence PR — corrected here).
- Remaining GOAL-5 month-1 also: AC5 full-funnel closer (#521, umbrella).
