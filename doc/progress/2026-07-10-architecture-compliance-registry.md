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

## r1 update (2026-07-10, same day) — first Codex review, P0 sequencing bug

Codex found a real bug in the R1/R2 sequencing: R1 (flip launchd to the
already-registered native orchestrator jobs) could silently double as a live
kernel cutover, since T1 established that the "native/orchestrator path" this
flip targets already runs the PINNED kernel while WF-gate/sim/promote evidence
(R2's job to migrate) would still be on the umbrella kernel — meaning R1 alone
would re-create the evidence≠live split in the opposite direction rather than
closing it. "Shadow-compare each leg" was not a sufficient acceptance rule.

Fixed:
- Froze a kernel-identity invariant (`(pipeline_repo_sha,
  kernel_module_content_hash)`, reusing `renquant_common.model_fingerprint.
  model_content_sha256` and the Governor RFC's decision-snapshot-digest
  discipline) gating every R1/R2 cutover step: no live cutover without a
  matching identity tuple on both the run bundle and the WF/sim/promote
  evidence, verified by a pre-registered golden-vector/shadow comparison,
  persisted in both records, fail-closed on mismatch.
- Rescoped R1 to launchd→native-scheduler changes that PROVABLY preserve
  kernel identity (still the umbrella kernel, just invoked differently); any
  leg that would change kernel identity is deferred to R2.
- R2 now explicitly states: the first native execution cutover for each
  module IS an R2 slice, bundled with the corresponding evidence-path cutover
  in the same slice, always.
- Added a "temporary migration mechanism governance" section covering every
  shim named in R1-R5 (owner, expiry — calendar or measurable milestone,
  telemetry, fail-closed retirement past expiry).
- R5's override mechanism corrected from a static "explicit override env" to
  an expiring, operator-authorized incident token/record.

## Changes

- `doc/design/2026-07-10-architecture-compliance-registry.md` — synthesis:
  systemic findings T1-T7, violation registry, R0-R7 roadmap, enforcement
  recommendations (written personally by the coordinating session); r1
  update above corrects the R1/R2 sequencing and shim governance
- `doc/research/evidence/arch_audit_2026_07/audit_{A,B,C,D}*.md` — the four
  cluster reports (evidence base, controlling detail)
