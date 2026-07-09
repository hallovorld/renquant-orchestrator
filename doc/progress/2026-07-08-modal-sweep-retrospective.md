# Retrospective: Modal sweep — 7 rounds of avoidable failure

**Date**: 2026-07-08
**Scope**: PR #435 (per-seed fan-out + data contract)
**Cost**: ~$2.25 in wasted Modal compute (rounds 4-6), ~6 hours of agent time,
operator attention/frustration across 7 review cycles.

## What happened

A single feature (cloud backtest sweep on Modal) took 7 rounds of smoke tests,
each uncovering a NEW missing data dependency that should have been caught
before ANY cloud money was spent.

| Round | Failure | Root cause |
|-------|---------|------------|
| 4 | `alpha158_291_fundamental_dataset.parquet` missing | Never staged to Volume |
| 5 | `sec_fundamentals_daily.parquet` missing | Sibling file, same class as round 4 |
| 6 | Same file, wrong path depth | `Path(__file__).resolve().parents[4]` vs Volume symlink |
| 7 | Finally built the data contract that should have been round 1 | — |

Every failure was the SAME class: a data file the pipeline reads was not
staged to the container. This was entirely predictable by reading the code.

## Why it happened — three root causes

### 1. Did not trace the full dependency surface before spending money

The agent treated smoke tests as the DISCOVERY mechanism — "run it, see what
breaks, fix that one thing, run again." This is the opposite of engineering:
the correct approach is to enumerate all dependencies deterministically
(read the code, list every file read), verify them locally, THEN confirm with
a single smoke test.

**The data contract (`verify_staged()` + `verify_remote()`) that finally
fixed this in round 6 should have been the FIRST deliverable, not the
sixth.**

### 2. Did not respect multi-repo boundaries

The pipeline reads files through 3 DIFFERENT code paths:
- `renquant_pipeline._data_root.data_root()` → `RENQUANT_DATA_ROOT` env var
- `SimAdapter._load_panel_history_cache()` → `strategy_dir.parent.parent`
- `job_panel_scoring.py` (kernel copy) → `Path(__file__).resolve().parents[4]`

The agent treated these as "the pipeline reads fundamentals" (singular) instead
of understanding that the multi-repo architecture means MULTIPLE independent
implementations exist for the SAME logical operation, each with its own
resolution path. This is a direct consequence of not reading the actual code
paths before building the staging logic.

**Lesson**: in a multi-repo system, "bundle the code and data" is not one
task — it requires tracing every import path in every copy of shared logic
to find ALL resolution strategies.

### 3. Reactive fix-per-round instead of systematic enumeration

Each round fixed exactly the ONE file that failed, without asking "what ELSE
does this same code path read?" or "are there OTHER code paths that read
similar files?" Round 5 found a second fundamentals file — but only because
round 4's fix made the pipeline proceed far enough to hit the next gap.
A systematic grep for `data/` or `parquet` in the bundled code would have
found ALL of them in round 4.

## What was wasted

- **~$2.25** in Modal compute on runs that were structurally guaranteed to fail
- **~6 hours** of agent context windows debugging one-file-at-a-time
- **6 review cycles** of operator attention on a PR that could have been 2 cycles
- **Credibility**: the PR title went from "validated" → "pending" → "still
  failing" → finally "PASS" — each title change eroding trust

## Process changes to prevent recurrence

### For this agent (Claude)

1. **Dependency-first, not smoke-first.** Before ANY cloud/remote execution,
   enumerate ALL file reads in the target code path. Produce a manifest.
   Verify the manifest locally. Only THEN spend money to confirm.

2. **Multi-repo = multi-path.** When bundling code from N repos, trace
   EVERY import path that touches shared resources. Grep for ALL file I/O
   in the bundled tree, not just the one that failed last time.

3. **Systematic sibling check.** When fixing a missing file, immediately ask:
   "what OTHER files does this same function/module read?" and "are there
   OTHER callers of this same file through DIFFERENT paths?" Fix them all
   in one round.

4. **No overclaiming.** A PR title says "validated" ONLY when a fresh test
   on the current HEAD has passed. "Pending" is the honest default.

### For the codebase (Codex review gates)

5. **Any PR that adds remote/cloud execution MUST include a deterministic
   preflight contract** — a function that enumerates and locally verifies
   every required file before any remote call. This is now enforced by
   `data_contract.py` for Modal sweeps; the pattern should be extended to
   any future remote execution surface.

6. **Cost-gate accuracy.** The preflight cost estimate must use measured
   (not theoretical) rates. The initial estimate was 1.7× too high because
   it used Modal's published rates for a different resource configuration
   than actually allocated.

### For the operator-agent contract

7. **Standing agreement with Codex**: when reviewing a PR that adds remote
   execution, require the preflight contract as a blocking review criterion
   (not just "does it pass tests"). This is the mechanical gate that
   prevents the reactive-discovery anti-pattern.

## What went right

- The data contract pattern (`verify_staged` + `verify_remote`) is genuinely
  useful and reusable. It should have been built first, but it IS the right
  solution.
- Per-seed fan-out works correctly and produces reproducible results.
- The A/A test (Sharpe lift = +0.0000) confirms pipeline determinism.
- Total cost of the successful run was $0.30 — the infrastructure is
  cost-effective once it works.
