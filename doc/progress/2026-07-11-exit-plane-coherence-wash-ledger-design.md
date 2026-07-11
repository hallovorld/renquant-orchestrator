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
