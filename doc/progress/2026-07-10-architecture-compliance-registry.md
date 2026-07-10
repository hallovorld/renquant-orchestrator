# Architecture compliance registry — audit synthesis (GOAL-3)

**Date**: 2026-07-10
**Status**: Audit deliverable (registry + remediation guidance; NO implementation)

## Bottom line

Four parallel cluster audits (umbrella / pipeline+common / exec+data+model+
artifacts / orchestrator+strategy; 1,065 lines of file:line evidence committed
as appendices) synthesized into 7 systemic findings and a sequenced R0-R7
remediation roadmap. Headline: promotion evidence and live trading run
DIFFERENT kernels (113 diverged files, worsening); the umbrella is still
load-bearing (18 launchd plists, 15.4k LOC training, 13 hardcoded orchestrator
paths); the triple-implementation bug class has 6 live instances (tax ×3,
calendar ×7 with a real settlement-date bug, etc.). Cheapest big win: launchd
cutover to already-registered native jobs.

## Changes

- `doc/design/2026-07-10-architecture-compliance-registry.md` — synthesis:
  systemic findings T1-T7, violation registry, R0-R7 roadmap, enforcement
  recommendations (written personally by the coordinating session)
- `doc/research/evidence/arch_audit_2026_07/audit_{A,B,C,D}*.md` — the four
  cluster reports (evidence base, controlling detail)
