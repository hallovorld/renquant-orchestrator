# Architecture compliance registry & remediation roadmap (GOAL-3)

STATUS: audit synthesis — registry + remediation GUIDANCE only; implementation
explicitly out of scope (operator mandate 2026-07-10)
DATE: 2026-07-10
METHOD: four parallel read-only cluster audits (A: umbrella, B: pipeline+common,
C: execution/base-data/model/artifacts, D: orchestrator+strategy), every claim
[VERIFIED] by diff/grep with file:line evidence — full reports committed under
`doc/research/evidence/arch_audit_2026_07/`. This document is the synthesis,
written personally by the coordinating session; the cluster reports are the
evidence base and controlling detail.

## 1. Executive verdict

The multi-repo architecture is REAL at the contract layer (order-status vocab
single-sourced, boundary AST tests, active==golden mechanically CI-tested,
model repo fully clean) — and INCOMPLETE at the operational layer: the umbrella
is not yet a deprecated pin consumer. Three unpinned umbrella layers trade real
money daily (live/ broker stack, RunnerAdapter dispatch, all 18 launchd plists),
and the single most dangerous structural defect is that **promotion evidence and
live trading run different code**.

## 2. Systemic findings (cross-cluster themes)

### T1 — Dual-home kernel divergence: evidence vs. live split [P0]
The kernel "copy-not-move" lift was never cut over. 113 files now differ
(baseline 73 on 07-04, i.e., actively worsening). Umbrella `live/runner.py`
imports the umbrella kernel copy; sim / WF-gate / promote ALSO run the umbrella
kernel; the pinned pipeline kernel (ahead: exits 138 diff-lines, sizing 342,
preflight 308) is what the native/orchestrator path runs. Consequence: **the
WF gate promotes models on code the live path does not execute.** Every other
finding is secondary to this one. (Evidence: audit A §A5/F-3, audit B §1.)

### T2 — The umbrella is load-bearing, not deprecated [P0→P1]
- All 18 launchd plists invoke umbrella scripts (A §A10/A12)
- Orchestrator itself hardcodes 13 umbrella paths in `scheduled_jobs.py`, the
  pin manifest in `repos.py:33`, the umbrella venv in the Makefile (D §7)
- ~15.4k LOC of training code lives umbrella-side and WRITES production every
  Sunday, while renquant-model holds a diverged parallel implementation (A §A6)
- Cheapest large win [VERIFIED]: `scheduled_jobs.py` already registers native
  replacement jobs with cutover commands — the launchd cutover needs no new
  design, only staged execution (A §10).

### T3 — The duplicated-contract bug class (the fingerprint family, generalized)
The triple-implementation fingerprint incident was not an accident; it is a
pattern. Currently live instances:
- Tax conventions ×3 (rotation 0.50/0.32 cliff; QP 0.30/0.15 bridge; flat 0.30
  in selection) — the same sell is costed differently per leg (B §4)
- NYSE calendar ×7 parallel implementations, incl. a real settlement bug
  (`t2_settlement.py:48` weekday-only — holiday weeks compute wrong dates) —
  while `renquant_common.market_calendar` sits built and unimported (B §7)
- Promotion-gate thresholds mirrored model↔backtesting by comment discipline
  only; `acceptance_entry_ic.py`/`challenger.py`/`triple_barrier.py`
  byte-identical ×2–3 (C §5)
- `MIN_FRACTIONAL_NOTIONAL_USD` duplicated with NO mechanical parity test (C §4)
- `compute_parent_intent_id` ×2 pipeline↔execution (B §3)
- Umbrella `live/` twins ×6 vs execution repo, 4 diverged, authority split by
  path, no drift guard (C §3)
Rule extracted for the ledger: **a contract that exists in two repos without a
mechanical parity/drift test is a latent production incident.**

### T4 — Registry/record ownership bypassed
renquant-artifacts' registry holds exactly one fixture; all real promotion
records live umbrella-side (promote-bak files, artifacts/ dumps, 6.8 GB incl.
full subrepo copies) (C §1, A §8).

### T5 — Policy/code misplacement (both directions)
- Execution repo contains a full trading strategy (`igv_short_*`: hardcoded
  entry/TP/SL levels + decision state machine + live option orders) — alpha
  decisions in the broker-adapter repo (C §2)
- strategy-104 contains orphaned kernel sizing code (`parking_sleeve.py`, 227
  lines, zero importers, third divergent sleeve copy) (D §5)
- A latent kernel-logic cluster is growing inside the orchestrator, all
  shadow/dark-gated today: `parking_sleeve.py` sizing, `entry_timing_policy.py`,
  and the 1,954-line `intraday_live_executor.py` incl. a live submit path —
  must migrate (→pipeline, →execution) BEFORE any 105 §9.4 arming (D §2)
- Duplicated gate re-implementations in orchestrator harnesses instead of
  imports (D §3)

### T6 — Fingerprint gates fail-open on the real path [P1]
The bridge (the ACTUAL daily production entry) is fail-open by default on
subrepo pin drift (`runtime_paths.py:216-238` via `live_bridge.py:254`); the
bridge run bundle is flag-gated; `native_live_run.py` has no fingerprint gate
at all. The fail-closed `daily.py` gate is exercised only by a smoke fixture.
This contradicts the orchestrator's own CLAUDE.md ("do not silently continue
without strategy/data/artifact fingerprints") on the one path that matters
(D §6).

### T7 — Governance is mechanical only where it was made mechanical
active==golden: CI-tested ✓. Progress-doc gate: filename check ✓. Everything
else is honor-system: unknown config keys silently ignored everywhere
(`extra="allow"`), 5 dead top-level keys, a 100+-key silent-default surface in
the pipeline kernel including gate strictness itself; memory-tier updates
un-enforced; ~62 unclassified research scripts in orchestrator scripts/ with 9
fitting models locally (D §8-9).

## 3. Violation registry

The controlling registry is the union of the four cluster reports' numbered
findings (A1–A14; B's 10 findings; C's 10; D's 10 — each with file:line,
target owner, S/M/L size, and risk grade). Headline rows:

| ID | Violation | Owner → Target | Size | Risk |
|---|---|---|---|---|
| T1/A5/F-3 | Dual-home kernel; gate evidence ≠ live code | umbrella → pipeline | L | P0 |
| A10/A12 | launchd layer on umbrella scripts | umbrella → orchestrator | M | P1 (cheap win) |
| A6 | 15.4k LOC training umbrella-resident + diverged model twin | umbrella → model | L | P1 |
| C3 | live/ broker twins ×6, 4 diverged, no drift guard | umbrella → execution | M | P1 (latent HIGH) |
| D6 | fail-open fingerprints on bridge/native path | orchestrator | M | P1 |
| C1 | artifacts registry bypassed | umbrella → artifacts | L | P2 |
| B4 | tax conventions ×3 | pipeline → common | M | P2 |
| B7 | calendar ×7 + settlement holiday bug | pipeline → common | M | P2 (has real bug) |
| C2 | igv_short strategy in execution | execution → strategy/pipeline | M | P2 (gated) |
| D2 | latent kernel cluster in orchestrator (incl. 105 executor) | orchestrator → pipeline/execution | L | P2 (gates 105 arming) |
| B5 | training pipelines inside pipeline repo | pipeline → model | M | P2 |
| C5/C4 | comment-synced thresholds/floors, no parity tests | model/backtesting/execution → common + pin tests | S | P2 |
| D5 | strategy-104 orphaned kernel code | strategy-104 → delete | S | P3 |
| B8 | ~4.3k lines replay/e1-e3 harness in pipeline | pipeline → backtesting | S | P3 |

(Sub-findings, small items, and the correctly-owned inventory — what must NOT
be migrated, e.g. promote_pin/rollback history, paper_broker+agent_breaker
protective features pending ports — are in the cluster reports.)

## 4. Remediation roadmap (sequenced; guidance only)

**R0 — Tripwires first (S, days, zero behavior change).** Before moving any
code, make drift VISIBLE: mechanical parity/hash tests for every T3 instance
(live/ twins vs execution files, $1 floor, thresholds, intent-id, tax
constants); extend the boundary AST tests to base-data/artifacts; unknown-key
warning counter (not yet strict) on config load. Rationale: every migration
below is then protected by an alarm instead of review vigilance.

**R1 — launchd cutover (M, ~week).** Flip the 18 plists to the already-
registered native orchestrator jobs one leg at a time (shadow-compare each leg
per the D6-§2a paired-bundle pattern before cutting the next). Kills T2's
operational core with no new design. Prereq for R2 (removes umbrella-script
consumers of the umbrella kernel).

**R2 — Kernel cutover (L, staged, the P0).** Per-module: pin-parity shims in
the umbrella kernel that IMPORT the pinned pipeline module and assert
golden-vector equality in shadow for N sessions, then delete the local copy.
Order by blast radius: exits → sizing → preflight → runner stems. The WF
gate/sim/promote chain moves to the pinned kernel in the SAME slice as live
(never let evidence and live diverge again — that is T1's lesson). Progress
metric: the 113-file diff count, published per slice, must go DOWN
monotonically to zero.

**R3 — Broker stack unification (M).** Execution repo is the owner. Port the
two umbrella-only protective features (paper_broker Z9 stop-sim, agent_breaker
G2 caps) INTO renquant-execution first, THEN retire the twins behind the R0
parity alarms. The #454/#26 pattern (owner implementation + umbrella
delegating call-site with fallback) is the proven migration shape.

**R4 — Training migration (L).** Reconcile the diverged umbrella↔model
factories (diff-audit first slice), then move the Sunday tournament to
renquant-model invoked via pins; umbrella keeps only the schedule shim until
R1 retires it. Do not attempt in one PR; the 07-02 fractional staging pattern
(stages, flag-off, certification marker unchanged) applies.

**R5 — Fingerprint fail-closed (M, behavior change → pre-registration gate).**
Bridge pin-drift default flips to fail-closed with an explicit, logged, alarmed
override env; run bundle always-on; native_live_run gains the same gate. This
is a behavior change on the production path: shadow the fail-closed verdicts
for N sessions first (count would-have-blocked days), then flip via the gate.

**R6 — Single-source contracts (M).** Tax → one implementation in common
(rotation's is canonical; QP/selection import it); calendar → adopt
`renquant_common.market_calendar` at the 7 sites (fixes the settlement bug as
a side effect — add the holiday regression test FIRST so the bug-fix is
visible); thresholds/metrics dedupe → common. Each site-flip is a small PR
gated by the R0 parity tests.

**R7 — Registry adoption + placement hygiene (P2/P3).** Promotion records
write to renquant-artifacts (promote_pin gains a dual-write stage, then
cutover); igv_short strategy content moves to a strategy repo (or is retired —
operator decision, it is a manual position-manager); orchestrator's latent
kernel cluster migrates before 105 arming; strategy-104 orphan deleted; scripts/
placement policy written (research vs production classification).

**Sequencing dependencies:** R0 → (R1 ∥ R6) → R2 → R3/R4; R5 independent after
R0; R7 last except the 105-arming prerequisite. Interaction with in-flight
programs: GOAL-1's D6 experiment runs on the pinned kernel via the native path
(unaffected); GOAL-2's crypto RFC REQUIRES the execution-repo ownership shape
(R3) and the always-open calendar (R6's calendar single-sourcing is its
prerequisite); both goals' pins ride R2's parity discipline.

## 5. Enforcement recommendations (make the architecture self-defending)

1. Twin-file drift CI: hash-parity job across the known twin sets; failure
   blocks merge in BOTH repos (extends the #181 allowlist-parity pattern).
2. Boundary AST tests in every repo (model's per-family pattern is the
   template; base-data and artifacts currently have none).
3. Config strictness ratchet: unknown-key counter → warn → fail, one config
   section per release; dead keys deleted with the same PR discipline.
4. A "migration exception" label with expiry (the #454 time-bounded exception
   worked because it was explicit; make expiry mechanical — CI warns when an
   exception file is older than its declared sunset).
5. The kernel-diff counter (T1) published in the weekly ops summary until zero.

## 6. Non-goals

No implementation in this PR. No priority override of GOAL-1/GOAL-2 in-flight
work. No retirement of protective features without ports (paper_broker,
agent_breaker, legacy kernel/models.py scorers are LIVE dependencies). The
QP shadow path is retained per the Governor RFC's disposition.
