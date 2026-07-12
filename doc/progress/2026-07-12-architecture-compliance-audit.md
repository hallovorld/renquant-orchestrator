# Architecture Compliance Audit — GOAL-3

Date: 2026-07-12
Status: COMPLETE (audit phase). Remediation sequenced, not started.
PR: orchestrator (this PR)

## Summary

Full-repo architecture audit against the canonical subrepo operating model
(`RenQuant/doc/arch/subrepo-operating-model.md`). Scanned all RenQuant repos
for ownership violations, forbidden imports, hardcoded paths, and
asset-class-blocking coupling.

## Findings

19 violations identified across 6 repos. 3 previously known violations confirmed
resolved.

| Severity | Count | Key themes |
|---|---|---|
| P0 | 5 | Umbrella still owns live production path (runner.py + daily_104.sh); pipeline↔orchestrator circular import; hardcoded umbrella paths in orchestrator; orchestrator imports pipeline kernel internals |
| P1 | 8 | Duplicated broker allowlist; NYSE-only calendar/exits; no cost model in WF gate; equity-only wash-sale/fundamentals/vol/TIF/reconciliation blocking crypto (GOAL-2) |
| P2 | 6 | 274 umbrella scripts; stale config copies; copied feature code; no CI boundary lint |

Full registry: `doc/research/2026-07-12-architecture-violation-registry.md`

## Relationship to GOAL-2 (Crypto)

8 of 19 violations (V-006, V-007, V-009, V-010, V-011, V-012, V-013, V-019)
directly block crypto asset-class extension. Phase 1 remediation is sequenced
to unblock GOAL-2 first.

## Remediation plan

Four phases, prioritized by production impact and GOAL-2 unblocking:

1. **Unblock crypto + close circular deps** (V-003, V-006, V-010, V-012, V-013)
2. **Strengthen import boundaries** (V-018, V-005, V-017, V-004)
3. **Migrate production path** (V-001, V-002, V-014)
4. **Cleanup** (V-015, V-016, V-007, V-008, V-009, V-011, V-019)

No implementation in this PR — audit and registry only. Remediation PRs
reference violation IDs from the registry.

## Methodology

- Automated grep for hardcoded paths, cross-repo imports, NYSE references,
  equity-only constants
- Manual inspection of production entry points (live/runner.py, daily_104.sh)
- Reconciliation against the subrepo operating model's ownership table
- Cross-reference with crypto RFC (#453) gap analysis
