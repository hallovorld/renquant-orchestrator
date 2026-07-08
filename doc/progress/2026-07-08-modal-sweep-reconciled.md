# Modal Sweep — Reconciled with #434's Runtime Fixes

**Date**: 2026-07-08
**Status**: Round 5 real bounded Modal smoke test STILL RUNNING at the time
this round was written (operator re-authorized under the standing <$10
spend policy). Interim log inspection of the in-progress run found a
SECOND, independent fundamentals-sync gap (round 4's fix was necessary but
not sufficient) — fixed in this round, not yet re-verified against a fresh
run.

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


## Round 4 (2026-07-08): real bounded smoke test FAILED -- missing fundamentals data

With cost/provenance accounting fixed (round 2) and the stale
"validated" claim removed (round 3), the operator authorized running the
actual bounded 1-variant/3-seed remote Modal smoke test round 3 asked for.

**Result: FAILED.** All 3 dispatched tasks (1 variant x 3 seeds) ran for
the full 3600s worker timeout and were cancelled by Modal's platform --
none produced a completed result. Real cost incurred: ~3 pods x
up to 3600s on 4 CPU/16GB ~= **$0.95**.

### Root cause

Remote logs (`modal app logs <app-id>`) showed, on every one of 500+
consecutive simulated backtest days:

```
Panel scoring contract failed (panel_fundamentals_missing). Cleared N buy candidate(s); buy/QP path is fail-closed for this run.
NoTradeAlert: N consecutive days with zero orders (limit=15) -- some upstream gate is blocking.
SimAdapter: panel history cache load failed -- [Errno 2] No such file or directory: '/data/data/alpha158_291_fundamental_dataset.parquet'
```

`SimAdapter._load_panel_history_cache()` (`backtesting/renquant_104/adapters/sim.py:753-778`)
resolves `panel_history_path` (default
`"data/alpha158_291_fundamental_dataset.parquet"`, not overridden in any
config this sweep uses) relative to `strategy_dir.parent.parent` -- i.e.
`repo_root` in this script's terms. `scripts/run_sweep_modal.py`'s
`local_paths` dict passed to `executor.sync_data()` only ever had
`"ohlcv"` and `"app"` labels -- **no `"data"` label at all**, so this
792 MB fundamentals dataset was never synced to the Modal Volume in the
first place. Every simulated day fail-closed on panel scoring with zero
candidates, and the worker apparently spun in that state without ever
reaching a terminal result until Modal killed it on timeout.

This is a structural gap, not a flaky/transient failure: it would recur
on every future Modal run of this sweep, deterministically, regardless of
which variant or seed runs.

### Fix

Extracted a new `stage_panel_history(repo_root, base_config) -> Path`
function (mirrors the existing OHLCV-subsetting pattern -- the full
`data/` dir is 24 GB; only the one 792 MB fundamentals file is needed, so
it is selectively staged into a temp dir rather than syncing everything).
Added `"data": str(data_staging)` to `local_paths`. With the Modal
Volume mounted at `/data` (per `modal_executor.py`), a `"data"`-labeled
sync entry lands at `/data/data/<filename>` inside the container --
exactly the path `SimAdapter` resolves to.

`stage_panel_history()` reads the same config keys `SimAdapter` reads
(`ranking.panel_scoring.panel_history_path`, falling back to
`panel_history_path`, falling back to the same hardcoded default) so a
future config override is honored identically on both the local and
Modal execution paths.

Checked for sibling gaps: the only other `"data/..."`-relative config
keys in `adapters/sim.py`/`adapters/runner.py`/`kernel/persistence.py`
are OUTPUT paths (`position_day_snapshots.parquet`, `runs.db`,
`sim_runs.db`) or short-selling-specific (`alpaca_borrow_status.json`,
not exercised -- this sweep's config has no shorting enabled and
`persistence.enabled=False` is set for every variant, per
`variant_to_request()` in `run_sweep()`). No other input-data gap found.

### Verification

- 4 new tests in `tests/test_run_sweep_modal.py::TestStagePanelHistory`,
  covering: default path staged, configured-override path staged, the
  staged file's manifest-relative-path contract
  (`build_local_manifest` genuinely produces
  `"data/alpha158_291_fundamental_dataset.parquet"`, not just "a file
  exists somewhere"), and the missing-source-file case degrading
  gracefully rather than crashing.
- All 4 confirmed to fail against pre-fix code via `git stash`
  (`ImportError: cannot import name 'stage_panel_history'`).
- Full suite: 3250 passed, 1 pre-existing unrelated failure
  (`test_parking_sleeve_cli_computes_allocation` -- confirmed passes in
  isolation; an environment/ordering flake unrelated to this change, not
  introduced by it).
- **Did NOT re-run a real Modal smoke test.** This fix is verified
  locally (source file resolution + manifest-path contract), but the
  actual remote execution path -- does the fundamentals file genuinely
  land correctly inside the container and let panel scoring succeed --
  has not been re-confirmed on Modal. That is the next required step
  before treating this PR as execution-proven, and it requires separate
  spend authorization (the failed round-4 attempt already cost ~$0.95).

## Round 5 (2026-07-08): second real smoke test found a SIBLING fundamentals gap

Operator re-authorized a fresh bounded (1-variant/3-seed) remote Modal
smoke test on round 4's fix (under the standing <$10 spend policy — no
per-run re-ask needed at this scale). That run was inspected mid-flight
(read-only `modal app logs`/`modal volume ls` on the already-running app;
no new spend triggered by this inspection).

**Confirmed round 4's fix genuinely worked**: the specific
`No such file or directory: '/data/data/alpha158_291_fundamental_dataset.parquet'`
error is completely absent from this run's logs (it appeared on every
occurrence of the failure in round 4's run; zero occurrences here).

**But `panel_fundamentals_missing` still fired on every simulated day.**
Root-caused by reading `renquant-pipeline`'s actual source (not just this
sweep script) — a SEPARATE, independent gap:

`renquant_pipeline.kernel.panel_pipeline.job_panel_scoring` (lines
~1278-1294) has an XGBoost-scorer-specific fund-feature lookup, active
whenever `scorer.feature_cols` includes `earnings_yield`/`book_to_price`/
`gross_profitability`/`roe`/`asset_growth` — true for this sweep's
`panel_ltr_xgboost` scorer (confirmed by the observed failure itself, not
assumed). It reads a SECOND file,
`renquant_pipeline...panel_pipeline._data_root.data_root() / "data" /
"sec_fundamentals_daily.parquet"` — never staged by round 4's fix (which
only covered `alpha158_291_fundamental_dataset.parquet`), so this branch
fail-closes to `panel_fundamentals_missing` regardless of the first file
now being present.

**Deeper contributing issue found**: `_data_root_cached()`'s own resolver
(`_data_root.py`) validates itself against the SAME sentinel file
(`data/sec_fundamentals_daily.parquet`) — meaning if it EVER returns a
root successfully, that root must already contain the file (by
construction). Its fallback chain (env var, else sibling-checkout /
home-dir / package-root candidates) has no candidate that plausibly
exists inside the Modal container (no bundled `RenQuant` umbrella
checkout, no `~/git/github/RenQuant` on an ephemeral container, and
`bundle.py` never copies a `data/` folder into the bundled
`renquant-pipeline` package root). The observed graceful
`panel_fundamentals_missing` (rather than an unhandled `RuntimeError` from
`_resolve()`'s own final `raise`) implies something upstream catches that
exception and reports it as this same fail-closed reason — the exact
try/except site was not traced further given time/spend constraints, but
does not change the fix: pin the resolver's *first* (env-var) candidate
explicitly rather than depend on the fragile fallback chain succeeding by
accident.

### Fix

1. `scripts/run_sweep_modal.py`'s `stage_panel_history()` (renamed in
   scope, not in name — same function) now stages BOTH
   `alpha158_291_fundamental_dataset.parquet` (792 MB) AND
   `sec_fundamentals_daily.parquet` (17.5 MB) into the same `"data"`
   staging directory, so both land at their respective
   `/data/data/<filename>` paths on the Volume. Each file is staged
   independently — one being absent locally does not block staging the
   other.
2. `modal_app.py`'s `run_variant_remote()` now sets
   `os.environ.setdefault("RENQUANT_DATA_ROOT", "/data")` at the very top
   of the function body, before any `renquant_pipeline` imports that would
   trigger `_data_root_cached()`'s lazy resolution — pinning it
   deterministically to the same root `SimAdapter` already correctly
   resolves to (`strategy_dir.parent.parent` == the Volume mount point),
   rather than relying on the local-machine-oriented fallback chain that
   has no valid candidate inside a Modal container.

### Sibling-gap re-check (broader this time)

Given this was the second gap of the exact same class found in
consecutive rounds, traced the fuller data-loading surface before
stopping:
- `job_panel_scoring.py`'s other `repo / "data" / ...`-style reads: none
  found beyond the two now-fixed files.
- `SimAdapter`/`sim/runner.py::run_backtest`'s other `data/`-relative
  reads: same set already covered by round 4's sibling check (output
  paths and shorting-specific, not exercised by this sweep's
  `persistence.enabled=False`/no-shorting config) — re-confirmed, no new
  gap found there.
- Did not exhaustively trace every OTHER scorer-kind branch in
  `job_panel_scoring.py` (e.g. `panel_linear`) since this sweep's config
  uses `panel_ltr_xgboost` specifically — noting this as a known
  incomplete area rather than claiming full coverage.

### Verification

- 2 new tests in `tests/test_run_sweep_modal.py::TestStagePanelHistory`:
  `test_sec_fundamentals_daily_is_also_staged` and
  `test_one_missing_file_does_not_block_staging_the_other`. Both confirmed
  to fail against the round-4-only code via `git stash` (targeted stash of
  just `scripts/run_sweep_modal.py` + `modal_app.py`, keeping the new
  tests) — `AssertionError: assert False` on the missing staged file.
- Full suite: 3252 passed, 1 pre-existing unrelated failure
  (`test_parking_sleeve_cli_computes_allocation`, same as every prior
  round — a stale hardcoded path dependent on other worktrees, not caused
  by this change).
- **Did NOT run a fresh real Modal smoke test on this fix.** The
  currently-running round-5 smoke test (already in flight before this
  round's investigation started) is running against the FUNDAMENTALS-FILE
  fix only, not this `RENQUANT_DATA_ROOT`/second-file fix — it was
  inspected read-only, not restarted or duplicated (no additional spend
  incurred by this round). A genuinely fresh bounded smoke test against
  BOTH fixes together is still the next required step before this PR can
  be treated as execution-proven.

## Round 6 (2026-07-08): THIRD real smoke test — round 5's fix was necessary but not sufficient; root cause is a stale bundled triple-impl, not a caching/ordering race

A third real bounded (1-variant/3-seed) Modal smoke test was run against
round 5's fix (`36b3972f`, both fundamentals files staged under `"data"` +
`RENQUANT_DATA_ROOT=/data` pinned). **Confirmed via `modal app logs`: both
prior file-not-found errors are gone** — neither
`alpha158_291_fundamental_dataset.parquet` nor `sec_fundamentals_daily.parquet`
produced a "no such file" error, and `modal volume ls renquant-sweep-data
/data` directly confirmed both files genuinely exist on the Volume at their
staged paths. **Yet `panel_fundamentals_missing` still fired on every
simulated day, same as rounds 4-5.**

Round 5's own writeup left this open: *"The observed graceful
panel_fundamentals_missing ... implies something upstream catches that
exception ... the exact try/except site was not traced further."* This
round traced it. **The hypothesis was wrong — there is no swallowed
exception and no import-order/`@lru_cache`-timing race in `modal_app.py`.**
Read `modal_app.py`'s `run_variant_remote` line-by-line: `os.environ.
setdefault("RENQUANT_DATA_ROOT", "/data")` runs before `sys.path` is even
configured (before any subrepo directory is importable), and before the
first `from sim.runner import run_backtest` / `from scripts.run_
concentration_cap_sweep import ...` — there is no earlier import in this
file or its own module-level code that could reach `renquant_pipeline`
first. In isolation, the ordering in this file is correct.

**The actual root cause: `adapters/sim.py` (bundled into the Modal image
via `bundle_subrepos()`'s `kernel`/`sim`/`adapters` copy) imports panel
scoring via `from kernel.panel_pipeline import PanelScorer` — a
DIFFERENT top-level import path than `renquant_pipeline.kernel.
panel_pipeline`, resolving to a physically SEPARATE directory:
`RenQuant/backtesting/renquant_104/kernel/panel_pipeline/` (confirmed a
real directory, not a symlink). This bundled copy's `job_panel_scoring.py`
predates the `_data_root.py` refactor entirely — it has no
`_data_root_cached()` import at all, and hardcodes
`repo = Path(__file__).resolve().parents[4]` directly (confirmed by
reading the file: 6 separate call sites, e.g. line 568-569,
`repo = Path(__file__).resolve().parents[4]; fp = repo / "data" /
"sec_fundamentals_daily.parquet"`).**

For this file bundled at `/data/app/kernel/panel_pipeline/
job_panel_scoring.py`, `parents[4]` resolves to `/` (the container
filesystem root) — completely independent of `RENQUANT_DATA_ROOT`, which
this stale copy never reads. So it looks for
`/data/sec_fundamentals_daily.parquet` (Volume-relative path
`sec_fundamentals_daily.parquet`, no directory prefix) — ONE level
shallower than where round 5 staged it (`/data/data/sec_fundamentals_
daily.parquet`, Volume-relative `data/sec_fundamentals_daily.parquet`).
This is a genuine triple-impl divergence — the same class of bug this
session's own history has hit before (calibrator/scorer fingerprint
triple-impl) — not a caching or ordering bug in the code round 5 touched.

`alpha158_291_fundamental_dataset.parquet` was unaffected by this same
issue because `SimAdapter._load_panel_history_cache()` (the consumer for
THAT file) resolves its own root via `strategy_dir.parent.parent` — a
third, independent convention that happens to already agree with round
4's staging path; only the `sec_fundamentals_daily.parquet` consumer in
the stale bundled `job_panel_scoring.py` copy has this depth mismatch.

### Fix

`sync_data.py`: `build_local_manifest` now returns
`(manifest, sources)` instead of just `manifest` — the previous
`rel_path.split("/", 1)` re-derivation of `(label, file_rel)` in
`sync_to_modal_volume`'s upload loop is ambiguous for a root-level
(no-prefix) file, since there's nothing to split on; the new `sources`
dict is built directly alongside the manifest and used as the
authoritative local-file lookup at upload time. Added `_prefixed(label,
rel)`: an empty label means no path prefix, landing a file directly at
the Volume root.

`run_sweep_modal.py`: `stage_panel_history()` now returns
`(data_staging, root_staging)` — `data_staging` unchanged (both files,
`"data"` label, for `SimAdapter`/the canonical `_data_root_cached()`
resolver); `root_staging` is a new, separate staging directory containing
ONLY `sec_fundamentals_daily.parquet` (17.5 MB — small, so duplicating it
is cheap), passed to `sync_data()` under the empty-string label
(`local_paths[""]`) so it lands at the Volume root — exactly where the
stale bundled `job_panel_scoring.py` copy's `parents[4]`-based resolution
looks. `alpha158_291_fundamental_dataset.parquet` is NOT duplicated (it's
792 MB and only needed at the one path it already correctly lands at).

Did not touch the umbrella tree (`RenQuant/backtesting/renquant_104/
kernel/panel_pipeline/job_panel_scoring.py` itself is out of bounds per
this repo's hard rule against writing to that live checkout) — the fix
is entirely on the sync/staging side, duplicating the small file to a
second path rather than patching the stale consumer's resolution logic
in place.

### Verification

- 2 tests renamed/restructured, 1 new test added in
  `tests/test_run_sweep_modal.py::TestStagePanelHistory`:
  `test_sec_fundamentals_daily_is_also_staged_at_modern_path` (existing
  assertion, renamed for clarity that this is the canonical-resolver
  path, not necessarily what's actually executing), and
  `test_sec_fundamentals_daily_is_also_staged_at_legacy_root_path` (new —
  asserts the file lands in `root_staging` and that `build_local_manifest`
  with an empty label produces `"sec_fundamentals_daily.parquet"` with NO
  `"data/"` prefix). Existing missing-file/one-file-missing tests updated
  for the new two-directory return signature.
- All new/changed assertions confirmed to fail against round-5-only code
  via targeted revert of `sync_data.py`/`run_sweep_modal.py` alone
  (keeping the new tests): 4 failures, including
  `TypeError: cannot unpack non-iterable PosixPath object` (proving the
  single-return-value signature was genuinely different before) and
  `AssertionError` on the missing root-level staged file.
- Full suite: 3253 passed, 1 pre-existing unrelated failure
  (`test_parking_sleeve_cli_computes_allocation`, same as every prior
  round, unrelated to this change).
- **Did NOT run a fresh real Modal smoke test on this fix** — the
  round-6 real smoke test (already in flight, predates this fix) was
  inspected read-only for diagnosis only; no additional spend incurred by
  this investigation/fix. A fresh bounded smoke test against this fix is
  still the next required step. Given this is now the THIRD distinct
  fundamentals-data-path issue found across three consecutive real smoke
  tests, a genuinely comprehensive trace of every consumer's resolution
  convention (rather than fixing one gap per round as discovered) may be
  warranted before further real spend, to reduce the risk of a fourth.

## Round 7 (2026-07-08): architecture investigation — is the stale kernel/panel_pipeline copy a mistake to eliminate, or genuinely load-bearing? Plus 2 more real data gaps found by tracing it fully.

Round 6 found that `adapters/sim.py` imports panel scoring via a bare
`from kernel.panel_pipeline import PanelScorer` that resolves, inside the
Modal container, to a stale bundled copy of `job_panel_scoring.py`
(`RenQuant/backtesting/renquant_104/kernel/panel_pipeline/`) rather than
the canonical `renquant_pipeline.kernel.panel_pipeline` package. This
round investigates whether that's an accidental drift to eliminate, or a
deliberate separate implementation — the "comprehensive trace" round 6
flagged as still outstanding.

### Finding: this is NOT an accidental duplicate — do not eliminate it

Directly diffed the two files: **3273 lines different** — not minor
staleness, an entirely different generation (missing the
fingerprint_dispatch unification and the `_data_root.py` refactor
entirely, missing large caching-helper sections that exist in canonical).

But `git log`/`git blame` on the bundled tree (read-only inspection only —
no writes made to the umbrella tree, per this repo's hard rule) shows a
long, continuously active, INDEPENDENT commit history for this exact
kernel — "decomposition slice 1-5" refactors, regime-specialist-ensemble
features, continuous-Kelly sizing, etc., spanning many months. This
specific file's last real commit was 2026-06-12; a sibling file in the
same directory was touched 2026-06-14 — i.e. the whole kernel tree is
actively maintained, this one file simply hasn't needed a change since a
refactor (fingerprint unification, `_data_root.py`) that happened in
`renquant_pipeline` (the live/production package) after that date and was
never backported here.

**Conclusion: `RenQuant/backtesting/renquant_104/kernel/` is the genuine,
deliberately separate backtesting/sim kernel — not a mistake.** Redirecting
`adapters/sim.py`'s import to canonical, or aliasing/deleting the bundled
copy, would risk breaking every LOCAL (non-Modal) backtest that currently
depends on this exact implementation — a much bigger, riskier change than
this PR's scope, and not something to do unilaterally mid-fix. Rounds 4-6's
approach (stage the specific files this kernel's own hardcoded
`parents[4]`-relative paths expect, leave the import alone) is confirmed
correct and the right fix given this constraint, not a lazy band-aid.

### Two more real gaps found while tracing this kernel's own file fully

Reading the stale copy's full `data/`-relative dependency surface (not
just the one path round 6 fixed) found two more:

- `data/earnings_surprise/` — read whenever the scorer's `feature_cols`
  includes any of `days_since_earnings`/`pead_signal`/`pead_quintile_rank`
  (PEAD) or `sue_signal`/`surprise_momentum`/`surprise_streak` (SUE).
- `data/news_sentiment_alpaca/` — read whenever `feature_cols` includes
  any `sentiment_*` column.

Confirmed BOTH are genuinely exercised by this sweep's actual model:
directly grepped the walk-forward manifest's `feature_cols`
(`artifacts/walkforward_v2_20260602/2024-01-01/panel-ltr.json`) and found
all of `days_since_earnings, pead_signal, pead_quintile_rank, sue_signal,
surprise_momentum, surprise_streak, sentiment_pos_share, mean_sentiment,
n_articles_log` present — this is not a theoretical/unused code path.

**Severity is lower than round 6's finding, but real**: unlike the
fund-feature check (`if not fp.exists(): _fail_closed_panel_scoring(...)`,
a hard block), this kernel's own "Feature-health check" only *warns* on
all-zero PEAD/SUE columns — it does not fail-closed the day. So the
missing dirs would NOT have caused a fourth timeout, but would have
silently zero-imputed 6-9 of the model's feature columns, producing a
misleadingly weaker/different smoke-test result than what rounds 4-6's
fixes alone would suggest — the same class of "quiet overclaim" this
session has repeatedly flagged, just manifesting as understated results
rather than an outright crash.

**Fix**: `stage_panel_history()` now also stages `data/earnings_surprise/`
and `data/news_sentiment_alpaca/` (small — ~3MB and ~4MB, confirmed via
`du -sh` locally) at both the canonical `"data"`-label path and the stale
kernel's Volume-root path, same dual-staging pattern as
`sec_fundamentals_daily.parquet`. Caught and fixed my own initial path
mistake before committing: first attempt nested these under an extra
`"data"` subdirectory inside the staging dir, which would have doubled up
with the `"data"` LABEL itself and landed one level too deep
(`/data/data/data/...` instead of `/data/data/...`) — corrected to flat
staging, matching the existing file-staging pattern, and verified via the
manifest-path test below before trusting it.

**Verification**:
- 3 new tests in `TestStagePanelHistory`:
  `test_earnings_surprise_and_sentiment_dirs_staged_at_modern_path`,
  `test_earnings_surprise_and_sentiment_dirs_staged_at_legacy_root_path`,
  `test_missing_earnings_surprise_dir_does_not_raise`.
- Confirmed 2 of the 3 fail against pre-fix code (`FileNotFoundError`
  reading the staged file) via targeted `git stash` of only
  `run_sweep_modal.py`, keeping the new tests — the third passes
  vacuously pre-fix (old code never touches these dirs at all, so
  "missing dir doesn't raise" was trivially true).
- Full suite: 3256 passed, 1 pre-existing unrelated failure
  (`test_parking_sleeve_cli_computes_allocation`, same as every prior
  round).
- **Did NOT run a fresh real Modal smoke test** — round 6's real smoke
  test (predates this fix, and round 6's own fix) was still in flight at
  the start of this investigation; not touched or duplicated. No
  additional spend incurred by this round's investigation/fix.

This is now 4 real rounds of fixes to the same general area (Modal
container data-availability for the sim kernel). All 4 have been
genuinely distinct, well-understood, cheaply-fixable data-staging gaps —
not evidence of an unbounded/open-ended problem — but a fresh real smoke
test against ALL FOUR fixes together is now the single most informative
next step before considering the full 75-variant sweep.
