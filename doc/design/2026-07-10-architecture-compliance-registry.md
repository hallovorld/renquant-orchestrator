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

**Kernel-identity invariant (frozen HERE, gates every R1/R2 cutover step —
CORRECTED, Codex review round 1, 2026-07-10):** the R1 draft below let a
scheduler change silently double as a kernel cutover. Freezing this now so
that mistake cannot recur.

- **Identity tuple**: `(pipeline_repo_sha, kernel_module_content_hash)` —
  the pinned `renquant-pipeline` commit SHA plus a content hash of the
  kernel module tree, computed with the SAME `model_content_sha256`-style
  convention this project already uses in exactly one place
  (`renquant_common.model_fingerprint.model_content_sha256`, per audit B
  §1 — the single surviving implementation after the fingerprint-triple
  incident; reused here, not reinvented) and the same "compute once,
  independently re-verify at every consumption point" discipline the
  merged Deployment Governor RFC's decision-snapshot digest already
  established (`doc/design/2026-07-09-governor-prereg-replay-protocol.md`,
  "Paired-world input synchronization").
- **The rule**: no production live cutover — meaning any change to WHICH
  KERNEL COPY live actually executes — is permitted unless BOTH (a) the
  originating decision/run bundle and (b) the corresponding WF-gate/sim/
  promote evidence carry the IDENTICAL identity tuple, AND (c) that tuple
  has passed a pre-registered golden-vector/shadow comparison: the same
  frozen set of historical inputs run through both the live-consumed
  kernel and the evidence-consumed kernel, asserting byte-identical (or an
  explicitly pre-registered tolerance-bounded) output on every vector.
  "Shadow-compare each leg" alone (the R1 draft's acceptance rule) is NOT
  this comparison — it checks behavioral similarity on live shadow
  traffic, not kernel-identity equality against a frozen reference set.
- **Persistence, fail-closed**: the matched identity tuple and the
  golden-vector comparison's pass/fail result are stamped into BOTH the
  promotion record (artifacts-side) AND the live run bundle. A mismatch at
  either side FAILS CLOSED — blocks the cutover if not yet executed,
  blocks promotion/live continuation if discovered after — never a
  logged-and-continue warning.

**R1 — launchd cutover (M, ~week) — RESCOPED (Codex review round 1):** the
draft above proposed flipping the 18 plists to "the already-registered
native orchestrator jobs" as a scheduler-only change. That is false for any
plist whose native replacement is the native/orchestrator path T1 already
identified as running the PINNED kernel — flipping launchd to invoke it
would be a live kernel cutover disguised as a scheduling change, landing
before R2 has moved WF-gate/sim/promote onto that same kernel, and would
re-create T1's evidence≠live split in the opposite direction (evidence
stale, live current) rather than closing it.

R1's scope is therefore restricted to launchd→native-scheduler changes that
DEMONSTRABLY preserve the existing execution implementation: verified via
the kernel-identity tuple above — the native replacement job, at cutover
time, must resolve to the SAME identity tuple the umbrella-script path
resolved to immediately before the flip (i.e., still the umbrella kernel
copy, invoked through a different scheduling mechanism). Any leg whose
native replacement would instead resolve to a DIFFERENT identity tuple is
explicitly OUT of R1's scope — its cutover is deferred to R2, where it is
bundled with the corresponding evidence-path cutover in the same slice (see
below). R1's acceptance test per leg is therefore: (1) kernel-identity match
against pre-flip, checked mechanically, not asserted; (2) shadow-compare
per the D6-§2a paired-bundle pattern, retained as a secondary behavioral
check. Kills T2's operational (scheduling) core with no new design; does
NOT by itself remove any umbrella-kernel consumer — that is R2's job.

**R2 — Kernel cutover (L, staged, the P0).** Per-module: pin-parity shims in
the umbrella kernel that IMPORT the pinned pipeline module and assert
golden-vector equality in shadow for N sessions, then delete the local copy.
Order by blast radius: exits → sizing → preflight → runner stems. **The
first native execution cutover for each module — the point where live
starts consuming a DIFFERENT kernel identity than before — IS an R2 slice,
and the WF-gate/sim/promote chain for that module moves to the SAME
identity in the SAME slice, always** (never let evidence and live diverge
again, in either direction — that is T1's lesson, generalized per the
kernel-identity invariant above). This absorbs any launchd leg R1 deferred
for exactly this reason. Progress metric: the 113-file diff count,
published per slice, must go DOWN monotonically to zero.

**R3 — Broker stack unification (M).** Execution repo is the owner. Port the
two umbrella-only protective features (paper_broker Z9 stop-sim, agent_breaker
G2 caps) INTO renquant-execution first, THEN retire the twins behind the R0
parity alarms. The #454/#26 pattern (owner implementation + umbrella
delegating call-site with fallback) is the proven migration shape. **Every
umbrella-delegating call-site left behind by this pattern is a temporary
migration shim (governance fields below) — not a permanent second home.**

**R4 — Training migration (L).** Reconcile the diverged umbrella↔model
factories (diff-audit first slice), then move the Sunday tournament to
renquant-model invoked via pins; umbrella keeps only the schedule shim until
R1 retires it. Do not attempt in one PR; the 07-02 fractional staging pattern
(stages, flag-off, certification marker unchanged) applies. **The schedule
shim is a temporary migration shim (governance fields below).**

**Temporary migration mechanism governance (applies to every shim in R1–R5:
the R1 umbrella-invoking scheduler wrapper, R2's pin-parity shims, R3's
umbrella-delegating call-sites, R4's schedule shim, R5's override token
below — CORRECTED, Codex review round 1):** none of these may be an
undated, unowned bridge. Each MUST declare, at the point it is introduced:
- **Owner**: a named role (operator — the same accountability convention
  already used for every capital-risk freeze elsewhere in this project's
  design docs), not "the team" or unspecified.
- **Expiry**: either a calendar date or an explicit MEASURABLE migration
  milestone (e.g. "R2's exits-module diff count reaches 0"), whichever the
  shim's own removal condition actually depends on — a milestone-based
  expiry where one exists (most of these do; they retire when their
  specific R-stage slice completes) rather than a generic calendar date.
- **Telemetry**: an observable signal that the shim is still in use (a
  counter, a log line, or a per-run stamp — reusing whatever this
  project's existing observability convention is, not a new one) so its
  continued necessity is visible, not assumed.
- **Fail-closed retirement**: what happens if the shim is still present
  past its expiry — it must FAIL CLOSED (block the path it bridges) at
  that point, not continue silently. A shim past expiry is a stopped
  migration, not a permanent architecture decision, and must surface as
  such.

**R5 — Fingerprint fail-closed (M, behavior change → pre-registration gate).**
Bridge pin-drift default flips to fail-closed; run bundle always-on;
native_live_run gains the same gate. **Override mechanism, CORRECTED
(Codex review round 1): NOT a static "explicit override env" that, once
set, permanently disables the check.** The override requires an EXPIRING,
operator-authorized incident token/record: a specific, time-bounded,
logged authorization tied to a named incident (not a standing environment
variable), which automatically expires and must be re-authorized for any
further use — governed by the same owner/expiry/telemetry/fail-closed
fields above. This is a behavior change on the production path: shadow the
fail-closed verdicts for N sessions first (count would-have-blocked days),
then flip via the gate.

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
   exception file is older than its declared sunset) — this is the general
   mechanism the R1–R5 "temporary migration mechanism governance" fields
   above (owner/expiry/telemetry/fail-closed retirement) instantiate for
   every shim named in this roadmap; the CI warning should escalate to a
   fail-closed block, not stay a warning, once a shim's declared expiry
   passes (per that section).
5. The kernel-diff counter (T1) published in the weekly ops summary until zero.

## 6. Non-goals

No implementation in this PR. No priority override of GOAL-1/GOAL-2 in-flight
work. No retirement of protective features without ports (paper_broker,
agent_breaker, legacy kernel/models.py scorers are LIVE dependencies). The
QP shadow path is retained per the Governor RFC's disposition.
