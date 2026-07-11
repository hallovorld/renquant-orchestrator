# Progress: exit/entry plane coherence + durable wash-sale ledger (design)

DATE: 2026-07-11
TYPE: design PR (no runtime change)
DELIVERABLE: `doc/design/2026-07-11-exit-plane-coherence-and-wash-ledger.md`

## What

Design-first resolution of the two remaining #484 §8 fixes (5 and 6):

1. **Plane coherence for `ModelProtectionExitTask`** — decision: hybrid
   fail-direction (defer the strike evaluation to the coherent/fresher
   plane when one qualifies; fail-closed skip + CRITICAL page only when no
   plane passes the buy path's own staleness axes), identity threading via
   a stamped `ScoringPlaneIdentity` (shared `sha256_file`, train-end axis
   fields, never `trained_date`), session-grain + identity-scoped strikes,
   three-stage flag-gated rollout (telemetry → shadow+alarm → enforce).
2. **Durable broker-reconciled wash-sale ledger** — append-only,
   hash-chained, broker-fill-keyed JSONL; nightly reconciler on the merged
   umbrella #428 toolkit; owner renquant-execution (writer/reconciler),
   renquant-pipeline (pure `wash_view` gate derivation), orchestrator
   (invariant checker I-W1..6); 4-phase migration off
   `live_state.last_sell_dates` (Phases 0-1 zero-runtime-change).

## New evidence produced for this design (read-only, this session)

- **Complete `ModelProtectionExitTask` firing history** (enablement
  2026-06-11 → 07-10, 620 runs / 20 sessions): 9 exits, 9/9 ran 1→2→3/3
  with zero resets ever, 8/9 fired while the panel plane was POSITIVE on
  the name, 3/9 accrued 3 strikes in 24 minutes (vs the configured
  "3 consecutive daily evaluations"), June firings on 55-76d-stale
  per-ticker planes. Outcomes: 1 good save (EQIX), 1 clear whipsaw (NFLX),
  1 mixed, 2 leaning whipsaw, 1 leaning save, 1 flat, 2 too recent.
  D1 counterfactual: EQIX save preserved, NFLX whipsaw prevented.
- **Code-plane map**: exit mu = per-ticker plane via `ScoreModelTask`
  (task_sell.py:157-165, :508-512); panel never runs in the intraday
  `SellOnlyPipeline`; held-name staleness waiver at job_universe.py:318-324
  is what arms stale-plane exits; zero model-identity plumbing end to end.
- **live_state ownership**: umbrella legacy runner is today's writer of
  record (4 mutation sites; whole-dict replace, no locking, 3 cadences;
  RESTORE-FROM-DB + manual-rewrite erasure paths verified possible);
  renquant-execution holds the graduated parallel `live_persistence`,
  unwired.

## Method / safety

Read-only throughout: no git command in the live umbrella tree or any
primary checkout; runs DB opened only as a scratchpad copy; no production
path written. Design authored in a fresh isolated clone; worktree-only
discipline honored. Two parallel read-only sub-sweeps (firing history;
code/ownership map) merged into the design doc's §2.2 and §2.1/§3.1-3.2.

## Status / next

- PR opened for Codex + operator review — DO NOT MERGE without review; the
  review asks are enumerated in the design doc §5.
- Implementation intentionally NOT started: every stage (Stage 0 telemetry,
  wash Phase 0 backfill, …) is its own PR against the owners in design §4.
- Memory tier: mid-term workstream file added
  (`doc/memory/mid-term/exit-and-state-integrity.md`, status proposed).

## Correction (r2 — Codex review response, 2026-07-11)

Codex found two safety-contract gaps; both are now first-class in the
design, not implied:

1. **D1 coherence predicate was too permissive.** The original predicate let
   a promoted, fresher successor substitute for the admitting model based
   only on artifact freshness + a promotion record — it never checked
   whether the successor represented the SAME scoring thesis. Fixed:
   `ScoringPlaneIdentity` gains `config_schema_sha256`/`feature_recipe_version`
   fields, and the coherence predicate now requires them to match — a
   promotion to a different feature recipe (e.g. renquant-model#44's
   `vol_trend_v2`) is never coherent regardless of promotion status (§2.5).
   A pre-registered successor-vs-original counterfactual comparison is now
   a stated Stage-2 precondition, not merely implied by the shadow record.
   Separately, §2.6's "0 resets in 620 runs" claim is now explicitly split
   from policy: it is currently an INFERENCE from log timestamps, not a
   code-verified defect, and the design states exactly what code-level
   proof (scheduler/evaluation-timestamp trace; reset-branch
   reachability) is required before session-grain accrual is adopted as a
   fix rather than a guess. The 9-firing evidence table is now explicitly
   scoped as incident motivation, not the validation population — Stage 1
   advance now additionally requires a full holding-evaluation population
   replay with transaction costs (§2.6, §2.7).
2. **D2's ledger durability was asserted, not shown.** The original draft
   specified a hand-rolled append-only hash-chained JSONL file under three
   concurrent writer cadences with no single-writer lease, no atomic-
   append/fsync/rotation protocol, no recovery semantics, and no proof
   `broker_activity_id` is unique per partial fill. Per Codex's exact
   instruction, moved to a SQLite-backed transactional store instead of
   trying to hand-build those properties (§3.3) — single-writer enforcement
   and atomicity now come from the database engine (`BEGIN IMMEDIATE`
   transactions), matching the concurrency-control class already relied on
   elsewhere in this stack. Reconciliation is now explicit that conflicting
   (not merely correctable) broker facts are preserved as parallel active
   rows pending human resolution, never silently resolved by supersession
   (new I-W7, §3.4/§3.6). `wash_view`'s account scope, timezone rule, and
   30-day boundary semantics are now pinned as explicit, stated properties
   (§3.5) rather than implicit in the comparison arithmetic. The
   orchestrator checker's "alarm, never repair" role is now a stated hard
   rule (§3.6), not an implication of "monitor layer".

No section was deleted; both worked-example replays (§2.2's table, §3.1's
failure record) are preserved. All phases remain DARK — nothing in this
revision relaxes the existing staged-rollout gates (§2.7, §3.7).
