# Modal Sweep — Reconciled with #434's Runtime Fixes

**Date**: 2026-07-08
**Status**: Code reconciled + locally verified; a fresh bounded remote smoke
test is still recommended before the full 75-variant sweep (see below —
this revision downgrades the prior "Smoke test PASS, ready for full sweep"
claim, which turned out to be unreliable evidence for this reconciled code).

## Round 2 (2026-07-08): fix cost/provenance undercounting + preflight mismatch

Codex's re-review of the reconciled code (round 1 above) found two more
blocking issues, both about the per-seed fan-out changing execution
semantics (1 pod per variant → 1 pod per (variant, seed)) without the
cost/provenance accounting or the preflight cost gate being updated to
match.

### Issue 1 — variant cost undercounted by ~seeds_per_variant x

`ModalExecutor.execute_batch`'s aggregation loop took `max(elapsed_seconds)`
across a variant's per-seed pods and charged cost once from that single
max value. With 3 separate pods actually running (and billing) per
variant, this understated real spend by roughly 3x — e.g. pods taking
300s/600s/200s reported a variant cost as if only ONE 600s pod ran,
silently discarding the other 500s of billed compute.

**Fix**: `modal_executor.py`'s aggregation now tracks `total_worker_seconds`
as a running SUM across every pod's `elapsed_seconds` for that variant
(seeded from the first pod's own elapsed time, then added to on each
subsequent pod). `BacktestResult.elapsed_seconds` is now populated from
that sum, not a max — so it represents *total billed compute-seconds*
for the variant, not any single pod's wall-clock duration. `peak_memory_mb`
correctly stays a max (independent pods don't share memory, so the
worst single pod's footprint is the right resource-sizing signal, unlike
elapsed time which genuinely sums for billing purposes).

For per-pod provenance (worker_id/started_at/finished_at/checksum),
`modal_app.py`'s worker now stamps these fields onto each `seed_data`
entry (in addition to the existing pod-level `result_obj` fields), so
`BacktestResult.per_seed[i]` carries genuine per-pod identity/timing —
not just whichever pod's response the executor happened to aggregate
first. The variant-level `worker_id`/`started_at`/`finished_at`/
`result_checksum` fields are documented in code as representative-only
(first-arrival), not authoritative for every pod — `per_seed[i]` is the
authoritative source per pod.

### Issue 2 — preflight cost gate modeled the old 1-pod-per-variant plan

`preflight()` computed `_estimate_cost_usd(30.0) * 75` — a stale
75-pods-at-30s-each model from before the per-seed fan-out redesign,
even though the actual plan is now `n_variants x n_seeds_per_variant`
pods (~225-228 for the full grid + A/A variant). At the old (wrong)
inputs this projected ~$0.20 — nowhere near the ~$9-$100+ real range
depending on true per-pod duration — meaning the safety gate meant to
catch unreasonable spend was silently modeling roughly 1/28th of the
real dispatch and would never fire.

**Fix**: `preflight()` now takes required `n_variants`/`n_seeds_per_variant`
keyword args and computes `n_pods = n_variants * n_seeds_per_variant`
before projecting cost — no hardcoded pod count. `run_sweep_modal.py`'s
call site now derives real values from the frozen grid constants
(`len(ENTRY_CAPS) * len(DRIFT_BUFFERS) * len(TOPUP_THRESHOLDS)` = 75,
+1 for the A/A resplit variant, or `args.max_variants + 1` in smoke
mode) and `len(FROZEN_SEEDS)` — cheaply, without materializing the full
75-variant config-file grid just to count it. `LocalExecutor.preflight`
and the `BacktestExecutor` protocol gained the same optional params for
interface consistency (local execution has no real cost concern).

The per-pod time estimate used for the projection is now a named
constant, `DEFAULT_SECONDS_PER_POD_ESTIMATE = 5558.0` (93 min) — the
only real data point available (the original smoke test's cached-run
worker time), used conservatively as a per-pod figure even though the
per-seed design likely runs faster per pod than that 3-seeds-serial
number. This is a deliberately non-optimistic placeholder pending a
fresh smoke test on this code; it is NOT a validated per-seed-pod
timing. At this conservative estimate, the full-grid projection now
correctly exceeds the $20 preflight threshold — this is intended: the
gate should require a human decision (or a real, better number) before
authorizing full-sweep spend, not silently wave it through.

### Verification

- `tests/test_cloud_modal.py::TestModalExecutor::test_preflight_cost_scales_with_actual_pod_count`
  — proves preflight's projected cost scales linearly with
  `n_variants * n_seeds_per_variant`; confirmed failing pre-fix
  (`TypeError: got an unexpected keyword argument 'n_variants'`).
- `tests/test_cloud_modal.py::TestPerSeedCostAggregation::test_variant_cost_is_sum_not_max_of_per_seed_pods`
  — dispatches 3 fake per-seed pod results (300s/600s/200s) through the
  real `execute_batch` aggregation path (fake Modal SDK with a working
  `app.run()` + controllable `.map()`) and asserts the resulting
  `BacktestResult.elapsed_seconds` is 1100 (sum), not 600 (max);
  confirmed failing pre-fix (`600.0 == 1100.0` assertion failure) via
  `git stash` on `modal_executor.py` alone.
- Full suite: 3246 passed, 3 skipped, 1 pre-existing unrelated failure
  (`test_parking_sleeve_cli_computes_allocation`, reproduces on clean
  `main`).
- **Still NOT performed**: a fresh real Modal smoke test. Per the
  reviewing feedback, even a bounded 1-2 variant smoke test should wait
  until this accounting fix lands — which it now has in this revision —
  but no cloud dispatch was run as part of this round.

## What this is

This PR (per-seed fan-out) and #434 (7 runtime-failure fixes) were built
concurrently on top of each other's absence: #434 branched from main and
fixed real, previously-discovered Modal runtime failures; this PR also
branched from main (before #434 merged) and built a different, genuinely
useful per-seed fan-out redesign — but its branch never had #434's fixes
in its history, and its own diff never touched the files those fixes live
in (`bundle.py`, `modal_app.py`, `sync_data.py` — only `modal_executor.py`
changed here). This revision merges #434's branch into this one and
reconciles the two.

## Why the prior "smoke test PASS" claim needed re-checking

The original smoke-test result recorded below (APY 15.1%, Sharpe 1.47,
A/A +0.0000, 93 min, $0.12/variant) was real — but it ran against the OLD,
pre-#434 code path (`build_image()`'s `copy_local_dir` image-baking
approach, `bundle.py`'s `("kernel", "sim")`-only bundle list, no Volume
path fix). That code combination is materially different from what a
production sweep needs: `sim/runner.py::run_backtest`'s default
(non-snapshot) path does an unconditional `from adapters.sim import
SimAdapter` — and pre-#434's `bundle.py` never bundled `adapters/` or
`training_panel/` at all. Whether the original smoke test's 1-variant run
somehow avoided this import, or ran against a differently-patched local
environment, is unresolved — but it should not be trusted as validating
the reconciled code, which is why this revision does NOT carry that claim
forward as proof for the merged result.

## What was reconciled

1. **From #434** (`fix/modal-executor-runtime`, commits `9130575a`
   `a871989e` `f444e49e` `ea7b18c9` `75e51875`):
   - `bundle.py`: bundles `adapters/`, `training_panel/`,
     `scripts/run_concentration_cap_sweep.py`, `scripts/__init__.py` (not
     just `kernel/`, `sim/`).
   - `sync_data.py`: Volume path no longer double-prefixed (`vol.batch_upload`
     writing to `/{rel_path}`, not `/data/{rel_path}` under a Volume
     already mounted at `/data`).
   - `modal_app.py`: module-scope `run_variant_remote` worker (Modal
     references it by name rather than pickling a closure — avoids
     `DeserializationError` when `renquant_orchestrator` isn't installed
     in the container), plus the previously-missing pip deps (`cvxpy`,
     `pydantic`, `ngboost`, `lightgbm`).
   - `RENQUANT_MODAL_TIMEOUT_SECONDS`/`RENQUANT_MODAL_RETRIES` env-var
     handoff so `ModalExecutor`'s caller-supplied timeout/retries still
     reach the decorator despite it being module-scope (decorator-time-only
     in Modal's SDK — no per-call override exists).

2. **From this PR** (`feat/modal-per-seed-fanout`, `b13b15b6`):
   - Per-seed fan-out: one Modal task per `(variant, seed)`, not one task
     per variant running all seeds — better parallelism, less GIL
     contention within a pod.
   - Resource upgrade: `WORKER_CORES` 1→4, `WORKER_MEM_GIB` 4→16.
   - Executor-side aggregation of per-seed task results back into a
     per-variant `BacktestResult` (max elapsed/memory, merged curves).
   - Walk-forward manifest path resolution against the Volume-mounted
     artifacts copy (`/data/artifacts/<manifest-filename>`), for the case
     where the config's `walkforward.manifest_path` was a local path
     from wherever the sweep was launched.

   The now-module-scope `run_variant_remote` (in `modal_app.py`) was
   adapted to run ONE seed per invocation (this PR's granularity) instead
   of #434's original multi-seed-per-task; the duplicate worker this PR
   had defined directly in `modal_executor.py` (`_remote_worker` +
   a nested per-call `@app.function`) was removed — there is now exactly
   one worker definition, at module scope, in `modal_app.py`.

## A real bug found and fixed during reconciliation

Combining #434's added bundle dirs with a naive per-subdirectory sys.path
strategy (mirroring this PR's original worker, which did
`sys.path.insert("/app/kernel")`, `.../sim`, `.../scripts` individually)
is itself broken: `from adapters.sim import SimAdapter` requires
`adapters`'s **parent** directory on `sys.path` to resolve `adapters` as
a top-level package — inserting `/app/adapters` itself does not make
`adapters` importable; it exposes what's *inside* `adapters/` as
top-level names instead.

Caught via a real (non-synthetic) local check: built a genuine bundle
from this machine's actual subrepos via `bundle_subrepos()`, then tried
`from adapters.sim import SimAdapter` using the worker's proposed
sys.path entries — got `ModuleNotFoundError: No module named 'adapters'`.
Fixed by relying solely on `app_root` (`/data/app`) itself being on
`sys.path` — already inserted at the top of the worker, from #434 — and
removing the incorrect `adapters`/`training_panel` (and redundant
`kernel`/`sim`/`scripts`) per-subdirectory insertions. Re-verified the
same real-bundle check afterward: `adapters.sim.SimAdapter`,
`sim.runner.run_backtest`, and `scripts.run_concentration_cap_sweep` all
import cleanly with just `app_root` + the subrepo `src/` dirs on path.

Added `tests/test_cloud_modal.py::TestBundle::
test_worker_sys_path_setup_resolves_top_level_bundled_packages`, which
builds a real bundle with synthetic `adapters`/`sim` packages and asserts
the worker's actual sys.path strategy resolves the import chain in a
subprocess — confirmed this test fails under the wrong
(subdirectory-insertion) approach and passes under the fix.

## Verification actually performed

- Full test suite: 3244 passed, 3 skipped, 1 pre-existing unrelated
  failure (`test_parking_sleeve_cli_computes_allocation`, confirmed
  reproducing identically on clean `main`).
- Local, real-bundle import verification (see above) — HIGH confidence
  the specific `adapters`/`training_panel`/`scripts` import chain that
  broke the original reconciliation attempt now resolves correctly.
- **NOT performed**: a fresh real Modal remote smoke test on this
  reconciled code. The original smoke test's numbers (APY/Sharpe/cost
  below) are preserved here for the record but must NOT be read as
  validating this revision — they ran against different code. A small
  (1-2 variant) bounded remote re-verification of this reconciled code is
  recommended before committing to the full 75-variant / ~$9 sweep, given
  local testing cannot fully substitute for the real container/Volume/
  image-build environment.

## Original smoke-test record (superseded context, not current evidence)

Incumbent smoke test (1 variant, 3 seeds) on Modal, run against pre-#434
code:

| Metric | Value |
|--------|-------|
| APY | 15.1% |
| Sharpe | 1.47 |
| Max DD | 7.3% |
| Turnover | 2.00x ann |
| Cost | 20.0 bps |
| A/A Sharpe lift | +0.0000 (PASS) |
| Worker time | 5558s (93 min) on 4 CPU / 16 GB |
| Cost | $0.12/variant |

Findings from that run: seeds 42/43/44 produced identical results
(deterministic pipeline); cold start (image build + Volume cache) adds
~4h on a first run, ~93 min on cached runs. Full-sweep cost/time
projection (75 variants × 3 seeds, 225 pods, ~31 min wall-clock, ~$9) is
plausible order-of-magnitude but should be re-confirmed once a fresh
smoke test on this reconciled code exists.
