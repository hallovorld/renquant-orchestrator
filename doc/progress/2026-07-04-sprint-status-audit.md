# Sprint checklist status audit — 2026-07-04

DATE: 2026-07-04 (revised per operator review — honest merged/open boundary)

## Sprint checklist (operator 2026-07-03~07-06)

Status key:
- MERGED = on main, CI green, code landed
- OPEN = PR exists, under review or with requested changes — NOT counted as complete
- IN FLIGHT = agent/branch work not yet PR'd

### 1. Experiment framework (expkit)

**MERGED** (#287): `expkit/{prereg,evaluation,stats,evidence,__init__}.py` (1303 lines, 52 tests)
All 6 capabilities: prereg freeze, placebo diff, block bootstrap + small-n exact,
dual control, evidence manifest, breadth replay.

**OPEN** (#312): `expkit/replay.py` — replay-experiment orchestration extracted from
the M4-b burst script (290 lines, 17 tests). Under review.

### 2. 105 intraday session

**MERGED**: core infrastructure landed across multiple PRs:
- #289: entry-timing policy module (1083 lines, 29 tests)
- #291: Stage-2 live executor — quadruple arming gate, canary envelope, order state book (1941 lines, 33 tests)
- #298: canary allowlist enforcement + loss budget + session ceiling (campaign A4)
- #290: C1 PIT feature builder scheduling

Software stops: landed in earlier sprint tick.

**Not yet PR'd**: LiveSessionRunner deferred per codex review (design cost ahead of
§9.4 economic-authorization decision — intentional scope boundary, not missing work).

### 3. 106 C1/PIT feature pipeline

**MERGED**: PIT scheduling (#290), compliance audit findings (#296)

**OPEN** (#303): mirror-drift inventory + CI freeze-line. Under requested changes.

Status: PIT launchd plists + wrapper scripts + liveness checker exist in merged code.
C1 inventory module built but not yet merged.

### 4. 107 governance skeleton

**MERGED**:
- #292: decision-ledger attribution engine — 5-leg decomposition (MARKET+SIGNAL+SIZING+TIMING+COST)
- #294: risk-budget ledger — 4-budget statement (DD/β/concentration/sleeve)
- #305: transfer coefficient measurement — TC = corr(kelly, qp)
- #307: hardcoded path fixes for attribution/risk-budget modules

**OPEN**:
- #308: QP-status diagnostic (TC root cause). Under requested changes.
- #309: QP feasibility fix design doc. Under requested changes.
- #310: rq-tc CLI entrypoint. Under requested changes.
- #313: D-group r2 path fixes for TC/attribution/ledger. Under review.

### 5. S-FRAC stages 1-3

Design merged (#254). Stage 0 in umbrella. Stages 1-3 need pipeline+execution
+strategy changes. Multi-repo — not orchestrator-only.

### 6. M6 fingerprint unification

**MERGED**: #286 (fingerprint census), #299 (stage-2 call-site inventory)

**IN FLIGHT**: B4+B7 agent (score-sha + manifest writer unification). No PR yet.

### 7. M4-b harness

**MERGED** (#288): scripts/m4b_floor_replay.py (1537 lines, 47 tests)

**OPEN** (#312): expkit/replay.py promotion (de-duplicates stats into reusable library).

## Compliance campaign items (merged)

- A4 canary enforcement: #298 MERGED
- B3 parent-intent dedup: #300 MERGED
- B5 NYSE calendar: #302 MERGED
- B6 ntfy dedup: #301 MERGED
- D-group paths r1: #307 MERGED

## Summary

| Item | Merged | Open PRs | Gap |
|------|--------|----------|-----|
| Expkit | #287 (core) | #312 (replay) | replay under review |
| 105 | #289/#291/#298 | — | LiveSessionRunner deferred by design |
| 106 C1/PIT | #290 | #303 | C1 inventory under review |
| 107 skeleton | #292/#294/#305 | #308-310/#313 | TC extensions under review |
| S-FRAC 1-3 | — | — | multi-repo blocked |
| M6 | #286/#299 | — | B4+B7 agent in flight |
| M4-b | #288 | #312 | replay promotion under review |

**Honest count: 4/7 items have substantial merged code on main. 3 items have
open PRs or are in flight. Nothing is fully "done" until merged + CI green.**
