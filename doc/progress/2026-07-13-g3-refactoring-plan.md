# 2026-07-13 G3 redefined: incremental architecture refactoring

## Summary

G3 scope changed from one-shot audit (DONE — orch #492 merged) to incremental
safe refactoring using the architecture violation registry as the roadmap.

## What changed

- G3 redefined per operator directive: "从简单的部分重构代码，使他们 align with
  multi repo and pipeline architecture"
- Phased plan written: `doc/design/2026-07-13-g3-refactoring-plan.md`
- Acceptance criteria defined (4 measurable ACs per governance process)
- Governance doc §8 updated to reflect new G3 scope
- Phase A (tripwires/parity tests) is the starting point — zero behavior change

## Phase plan

| Phase | Scope | Risk | ETA |
|-------|-------|------|-----|
| A | Tripwires + parity tests (R0) | ZERO — read-only tests | ~1 week |
| B | Single-source contracts (R6, B4, B7, C4, C5) | LOW — same values | ~2 weeks |
| C | Dead code + misplaced code cleanup | ZERO — unused code | ~1 week |
| D+ | Larger migrations (R1-R5) | M-L — separate design docs | Future |

## Acceptance criteria (goal-level)

| AC | Criterion | Current | Target |
|----|-----------|---------|--------|
| AC-1 | Zero regressions | N/A (no changes yet) | 0 new failures per PR |
| AC-2 | Violation count monotonic decrease | 7 systemic (T1-T7) | Net decrease per phase |
| AC-3 | No unregistered behavior change | N/A | 100% shadow coverage |
| AC-4 | Operator phase-exit review | N/A | ACK before next phase |

## Evidence

- Violation registry: `doc/design/2026-07-10-architecture-compliance-registry.md`
- Refactoring plan: `doc/design/2026-07-13-g3-refactoring-plan.md`
- Governance §8 updated for G3 redefinition
- Test baseline: 3902 passed, 1 failed (pre-existing `test_live_twin_parity_manifest_current`)
