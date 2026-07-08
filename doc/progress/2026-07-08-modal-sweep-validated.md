# Modal Sweep — Reconciled with #434's Runtime Fixes

**Date**: 2026-07-08
**Status**: Code reconciled + locally verified; a fresh bounded remote smoke
test is still recommended before the full 75-variant sweep (see below —
this revision downgrades the prior "Smoke test PASS, ready for full sweep"
claim, which turned out to be unreliable evidence for this reconciled code).

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
