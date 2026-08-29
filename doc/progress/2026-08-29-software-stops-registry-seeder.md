# Software-stops writer migration, step 1 — the registry SEEDER

STATUS: code + tests in this PR only. Nothing installed, no config flag
flipped, no live tree or `-run` checkout touched. `execution.software_stops.enabled`
stays `false`; the pager plist stays a DARK template. Two umbrella follow-ups
are named (§5) and are NOT in this PR.

## 1. Bottom line

`ensure_registry_seeded(state_root, broker, *, max_staleness_minutes)` creates
an EMPTY, schema-valid software-stop registry at exactly the path the liveness
checker resolves — once, only if absent, never overwriting — and a
`python -m renquant_orchestrator.software_stops_registry_contract seed --broker <b>`
CLI wraps it so the umbrella sell wrapper can call it unconditionally before
the runner. Broker tagging and the snapshot schema are IMPORTED from
`renquant_pipeline.software_stops`; if that module is not importable the seeder
fails closed (ImportError, exit 3) rather than re-implementing either.

Evidence: `tests/test_software_stops_registry_contract.py` 24 tests (was 9),
`tests/test_stops_liveness_pager.py` unchanged; the two files together
53 passed / 2 skipped `[VERIFIED pytest, sibling pipeline+execution src on path]`.
Full orchestrator suite on this branch: see §6.

## 2. The hole this closes

Three facts, each read from source at the pinned sibling checkouts
(pipeline `76ab129`, execution `91c7bf8`):

1. The registry treats a MISSING file as "armed, empty — created on first
   write": `renquant-pipeline/src/renquant_pipeline/software_stops.py:339-341`
   (`_load`: `if not self._path.exists(): return`). `is_armed()` (`:364-367`)
   is therefore TRUE with no file on disk.
2. The execution checker's `check()` returns OK on a missing file:
   `renquant-execution/src/renquant_execution/software_stops_liveness.py:209-213`
   ("OK: no software-stop registry ... the layer has never armed a stop").
   Only the installer-guard mode distinguishes MISSING (`validate_registry`,
   `:280-283` → `REGISTRY_MISSING`).
3. The checker composes its path as
   `registry_path_for(Path(data_root) / DEFAULT_REGISTRY_PATH, broker)`
   (`:314-336`), and the pager plist passes
   `data_root = /Users/renhao/.renquant/runtime/software-stops`
   (`deploy/com.renquant.stops-liveness.plist`, key
   `RENQUANT_STOPS_PAGER_DATA_ROOT`).

Consequence: a writer that is running against the WRONG root, or not running
at all, is indistinguishable from "nothing armed" — the file simply is not
there and both the registry and the pager read that as fine. The installer
guard (`scripts/install_stops_pager.sh:207-267`, requires `--validate-registry`
== VALID) refuses to arm in that state, which is correct but also means the
pager can never be armed until SOMETHING creates the file at the checker's
path. Step 1 is that something.

## 3. The contract (`src/renquant_orchestrator/software_stops_registry_contract.py`)

| item | where | behaviour |
|---|---|---|
| `seeded_registry_path(state_root, broker, *, registry_rel)` | `:252-275` | `Path(state_root)/registry_rel` then the PIPELINE's `registry_path_for` — step-for-step the checker's `resolve_registry_path`. Unknown broker → the pipeline's `ValueError` (allow-list is theirs). |
| `ensure_registry_seeded(...)` | `:297-369` | absent → mkdir parents, build `{version, contract, max_staleness_minutes, last_evaluated_at: null, stops: {}}` from the pipeline's `REGISTRY_VERSION`/`REGISTRY_CONTRACT`, validate with the pipeline's PUBLIC `validate_software_stop_snapshot`, write a pid-unique tmp, re-validate the BYTES on disk, publish atomically. Present+valid → no-op (byte-identical, mtime and inode unchanged). Present+corrupt → `SoftwareStopRegistryCorruptOnDisk`, file untouched. One INFO on create, DEBUG on no-op. |
| publish primitive | `:353` | `os.link(tmp, path)` — atomic like `os.replace`, but REFUSES to clobber: if the real writer creates the file between our existence check and our publish, `FileExistsError` → we re-validate theirs and return. `os.replace` would have silently overwritten the writer's first write. |
| `_pipeline_stops_module()` | `:212-249` | `importlib.import_module("renquant_pipeline.software_stops")` (the `from … import` form reads an attribute off an already-imported package and cannot observe a blocked submodule), plus a presence check for the four public names used. ImportError message says what is missing and that nothing is worked around. |
| `DEFAULT_REGISTRY_REL` / `DEFAULT_SEED_MAX_STALENESS_MINUTES` | `:184` / `:189` | local constants pinned to the pipeline's `DEFAULT_REGISTRY_PATH` / `DEFAULT_MAX_STALENESS_MINUTES` by `test_default_registry_rel_and_budget_match_pipeline_defaults` — if the owning repo moves either, orchestrator CI goes red here. |
| CLI `seed --broker <b> [--max-staleness-minutes 30] [--data-root …] [--registry-rel …]` | `:375-442` | exit 0 created (`SEEDED: <path>`) or valid-existing (`EXISTS: <path>`); 1 usage (bad broker); 2 corrupt-existing; 3 pipeline not importable. `--data-root` defaults to `software_stops_registry_root(runtime_state_root())` = `~/.renquant/runtime/software-stops`, the plist's value by convention (`test_seed_cli_default_matches_the_pager_plist_data_root` compares the host-independent suffix, not the operator's home). |

Ownership stays as Codex set it on #481: this module owns LOCATION. The seed's
CONTENT is validated by the producing repo's validator before it is published;
the seeder never re-derives the schema, and the only literal it carries
(`DEFAULT_REGISTRY_REL`) is parity-tested against the pipeline constant.

One naming note for reviewers: `software_stops_registry_path()` in this module
(`<root>/software-stops/<broker>.json`, from #481) records the convention this
repo PROPOSED for a migrated writer. The checker never adopted it — it
composes `<data_root>/data/rq105/software_stops.<broker>.json`. The seeder
follows the checker, because the checker is what the pager runs. The older
helper is left in place (tests pin it); its docstring is the historical record.

## 4. Why this is inert

- Today `execution.software_stops.enabled` is `false` in both the pinned and
  the live config (`fractional-cash-drag-deprioritized` memory, 08-24 update).
  `SoftwareStopRegistry.from_config` returns `None` when the flag is off
  (`software_stops.py:316-337`), so nothing in the live loop reads or writes
  the registry file at any path. An empty valid file sitting at the neutral
  root is read by nobody.
- With `enabled: true`, the empty seed is exactly what the registry would
  persist on its own first write with zero stops (`snapshot()` `:371-378`,
  `_persist()` `:380-395`): `_load` reads it as "armed, empty",
  `compute_staleness` reports `n_stops=0 / stale=False`, and the checker's
  `check()` says OK with "0 armed stops" — pinned by
  `test_seed_is_valid_and_ok_for_the_execution_checker` against the real
  execution checker. The only observable change is that the file EXISTS, so
  `--validate-registry` reports VALID instead of MISSING and a heartbeat that
  never arrives becomes a fact the pager can see instead of an absence it
  cannot.
- The seeder does not install, schedule, or flip anything. No launchd job,
  no plist edit, no config edit, no umbrella change.

## 5. The two umbrella follow-ups (NOT in this PR; both need their own review)

1. **Runner:** `RenQuant/backtesting/renquant_104/adapters/runner.py:233-236`
   calls `SoftwareStopRegistry.from_config(config, broker_name=…)` WITHOUT
   `repo_root`, so a relative `registry_path` resolves against the process
   cwd — i.e. the umbrella tree. Step 2 passes
   `repo_root=<neutral root>` (`~/.renquant/runtime/software-stops`, the
   same value the plist arms the pager with) so the writer stamps where the
   checker looks. `from_config` already supports the kwarg
   (`software_stops.py:321`, `:332`).
2. **Sell wrapper:** `RenQuant/scripts/intraday_sell_104.sh` (runner invoked
   with `--sell-only --intraday` at `:110`; pinned-subrepo `PYTHONPATH` already
   built at `:58` and already includes renquant-orchestrator + renquant-pipeline)
   calls `"$PYTHON" -m renquant_orchestrator.software_stops_registry_contract
   seed --broker alpaca` unconditionally before the runner. Exit 0 is the
   normal path every pass (EXISTS); a non-zero exit is a page-worthy fact
   (corrupt registry or broken pin), not a reason to skip the sell pass —
   the wrapper's handling of that exit is the review question for step 2.

Both are umbrella changes and land through the R-PIN path (pin advance +
`-run` sync as separate reviewed steps); neither is authorized by this PR.

## 6. Chain position

```
[this PR] seeder (orch)            → file exists at the checker's path
  → step 2: runner from_config(repo_root=neutral) + wrapper calls seed (umbrella)
  → SLA drill (test-fire STALE; plist prerequisite (2))
  → install_stops_pager.sh install --apply   (guard now passes: VALID, not MISSING)
  → stage-3 sign-off → fractional flip under its own LONG-ledger row (2b text: "fractional later under its own chain")
```

Test evidence (this branch, `PYTHONPATH` = src + the nine sibling `src` dirs,
`RenQuant/.venv` python 3.10.20, `-p no:cacheprovider`):

- `tests/test_software_stops_registry_contract.py tests/test_stops_liveness_pager.py`:
  53 passed, 2 skipped `[VERIFIED]` (clean `origin/main` `75274096`: 38 passed, 2 skipped).
- Without the pipeline sibling on the path: 11 passed, 13 skipped, each skip
  naming "sibling renquant-pipeline src not on the path" `[VERIFIED -rs]`.
- Full suite: clean `origin/main` = 17 failed / 6757 passed / 10 skipped;
  this branch = 17 failed / 6772 passed / 10 skipped, and the FAILED set is
  byte-identical to clean main's (`diff` of the two `FAILED` lists is empty)
  `[VERIFIED]`. The 17 are pre-existing (`test_shadow_ab_daily_script` x13,
  `test_shadow_serving_skips_leave_evidence` x2, `test_cli` x1,
  `test_goal3_public_export_resolution` x1); none is in the two files above.
- One finding while getting there: the `python -m` entry-point test first
  built the child's `PYTHONPATH` from `sys.path`, which passed in isolation
  and failed ONLY in the full run — the full-suite process carries 391
  `sys.path` entries (89 unique; many test modules `sys.path.insert` the
  same `ops/renquant104`), a 50,356-byte string under which the child exited
  0 with empty stdout. The test now derives the path from where the imported
  `renquant_*` packages actually live (comment at the test names the numbers).

No memory-tier file covers the software-stops / fractional line as a MID
workstream (it lives in LONG row 2b's text and the 08-24 memory update);
this doc is the durable record for step 1. Opening a MID workstream file for
the fractional chain is an SOP-M proposal for the operator, not done here.
