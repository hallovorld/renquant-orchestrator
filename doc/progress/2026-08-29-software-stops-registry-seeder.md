# Software-stops registry — BOOTSTRAP step: seeder + readiness classification; installer requires READY

STATUS: code + tests in this PR only. Nothing installed, no config flag
flipped, no live tree or `-run` checkout touched. `execution.software_stops.enabled`
stays `false`; the pager plist stays a DARK template. The umbrella follow-ups
are named (§6) and are NOT in this PR.

Revision 2 (after Codex CHANGES_REQUESTED on #1078, 2026-08-29T07:54:11Z): the
first revision called a seed "closing the hole". It does not. A seed is
schema-VALID with `last_evaluated_at: null`, and the execution checker reports
a valid zero-stop registry as OK whether or not a writer ever touched it — so
after one `seed` command a missing or broken writer was indistinguishable from
a healthy one, and the first revision's test pinned that false-ready state.
This revision keeps the seeding primitive as BOOTSTRAP, adds an
orchestrator-side READINESS classification, and makes the installer require
READY. The "seed reads OK" test is gone; its replacement asserts a seed is
VALID and explicitly NOT ready.

## 1. Bottom line

- **Seed = locatable, not ready.** `ensure_registry_seeded()` creates an
  empty, schema-valid registry at the canonical path once, never overwriting.
  `registry_readiness()` classifies that seed `NOT_READY_UNINITIALIZED`.
- **READY = a real writer heartbeat at the canonical path within budget.**
  Verified end-to-end with real modules: seed alone → installer refuses; ONE
  `SoftwareStopRegistry.evaluate()` on the same root → READY → the same
  installer command passes (`tests/test_stops_liveness_pager.py:1499`).
- **The landing gate requires READY.** `scripts/install_stops_pager.sh
  install --apply` now requires VALID (execution CLI) AND READY (this
  classifier). Any manifest/install/software-stops enablement evidence must
  cite READY; VALID is bootstrap and proves nothing about the writer.

## 2. The hole, restated precisely

Read from source at the pinned siblings (pipeline `76ab129`, execution
`91c7bf8`):

1. Registry `_load` treats a MISSING file as "armed, empty"
   (`renquant-pipeline/src/renquant_pipeline/software_stops.py:339-341`);
   `is_armed()` (`:364-367`) is TRUE with no file.
2. Execution `check()` returns OK on a missing file (`software_stops_liveness.py:209-213`)
   AND on a valid file with zero stops regardless of heartbeat (`:228-232`,
   "0 armed stops"). Only `validate_registry` distinguishes MISSING (`:280-283`),
   and it stops at schema validity.
3. The checker composes `registry_path_for(Path(data_root)/DEFAULT_REGISTRY_PATH, broker)`
   (`:314-336`); the plist passes `data_root = ~/.renquant/runtime/software-stops`.

So neither "file exists" nor "file is VALID" says a writer is evaluating this
path. Readiness has to be a separate classification keyed on the heartbeat,
at the canonical path, and the installer has to require it.

## 3. The contract (`src/renquant_orchestrator/software_stops_registry_contract.py`)

| item | where | behaviour |
|---|---|---|
| `seeded_registry_path(state_root, broker, *, registry_rel)` | `:263-286` | `Path(state_root)/registry_rel` then the PIPELINE's `registry_path_for` — the checker's `resolve_registry_path` step for step. Unknown broker → the pipeline's `ValueError`. |
| `ensure_registry_seeded(...)` | `:308-381` | BOOTSTRAP. Absent → mkdir parents, seed `{version, contract, max_staleness_minutes, last_evaluated_at: null, stops: {}}` from the pipeline's constants, validated by the pipeline's PUBLIC `validate_software_stop_snapshot` before AND (bytes on disk) after the write; published with `os.link` (atomic AND refuses to clobber a writer that wins the race). Present+valid → no-op (bytes/mtime/inode unchanged). Present+corrupt → `SoftwareStopRegistryCorruptOnDisk`, untouched. |
| `registry_readiness(path, *, max_staleness_minutes=30, now=None)` | `:424-517` | the landing-gate classification. `NOT_READY_UNSEEDED` no file at `path` (`:460`); `NOT_READY_CORRUPT` unreadable / fails the pipeline validator (`:468`), or a heartbeat that is present but unparseable (`:491-493`), or more than the budget in the future (`:498-500`); `NOT_READY_UNINITIALIZED` valid, `last_evaluated_at` null (`:482-484`); `NOT_READY_STALE` heartbeat older than the effective budget (`:505-507`); `READY` otherwise (`:513`). Age arithmetic = the pipeline's `compute_staleness` (never re-derived). Effective budget = `min(caller, file's own)` (`:481`) — a file cannot loosen the caller's bar. `n_stops` is reported, never decisive. |
| `READINESS_EXIT` | `:396-402` | 0 READY only; 10 UNSEEDED, 11 UNINITIALIZED, 12 STALE, 13 CORRUPT (distinct). |
| `_pipeline_stops_module()` | `:222-260` | `importlib.import_module("renquant_pipeline.software_stops")` + presence check for `registry_path_for`, `validate_software_stop_snapshot`, `compute_staleness`, `REGISTRY_VERSION`, `REGISTRY_CONTRACT`. Not importable → ImportError, nothing written, CLI exit 3. |
| CLI `seed --broker <b> [--max-staleness-minutes 30] [--data-root …]` | `:523-604` | exit 0 `SEEDED:`/`EXISTS:` (both print "bootstrap only; run `readiness`"), 1 usage, 2 corrupt-existing, 3 import. |
| CLI `readiness --broker <b> [--data-root …] [--max-staleness-minutes 30] [--now ISO]` | `:607-621` | prints the verdict line; exits per `READINESS_EXIT`; 3 on import failure; 1 usage. `--data-root` defaults to `~/.renquant/runtime/software-stops` (the plist's value by convention). |

Ownership stays as Codex set it on #481: this module owns LOCATION and, now,
the orchestrator-side READINESS classification for arming. Schema stays the
pipeline's; the checker stays execution's. The two literals here
(`DEFAULT_REGISTRY_REL`, `DEFAULT_SEED_MAX_STALENESS_MINUTES`) are parity-tested
against the pipeline's constants.

## 4. The installer gate (`scripts/install_stops_pager.sh`)

- `registry_readiness_probe()` (`:229-238`): plain subprocess of
  `python -m renquant_orchestrator.software_stops_registry_contract readiness
  --data-root <plist value> --broker <plist value|alpaca>` on the pinned
  PYTHONPATH — same round-6/7 rules as the VALID step (inputs from `$PLIST_SRC`
  only; no in-process import of execution/pipeline).
- `guard_registry_before_apply()` (`:264-338`): execution `--validate-registry`
  must be VALID (unchanged), THEN readiness must exit 0 (`:314-323`). Every
  other readiness exit (10/11/12/13, 3 import, crash) is `GUARD FAIL` →
  installer exit 3, nothing copied, launchctl never called.
- `preview_registry_readiness()` (`:240-262`): `install` (dry-run) prints the
  verdict `--apply` would enforce, or "could not be evaluated -- <reason>"
  when the pinned inventory is not resolvable on this machine; never fails
  (dry-run stays echo-only).

## 5. Tests (all `tmp_path`; nothing touches `~/.renquant`)

`tests/test_software_stops_registry_contract.py` (34 tests; 9 on main):
- seeder: create / idempotent / populated-valid untouched / corrupt untouched /
  import fails closed / path == execution `resolve_registry_path` for 3 brokers /
  CLI exit codes / `python -m` subprocess / plist parity.
- `test_seed_is_schema_valid_bootstrap_but_NOT_ready` (`:311`): execution
  `validate_registry` → VALID; `registry_readiness` → UNINITIALIZED.
- readiness (`:347-475`): UNSEEDED; seed → one REAL writer pass
  (`SoftwareStopRegistry.from_config(..., repo_root=<data root>)` +
  `evaluate()`, `_writer_pass` `:332`) → READY at the seeded path, writer and
  seeder agree on the path; STALE at budget+1; budget = tighter of caller/file;
  CORRUPT untouched (bad JSON and wrong version); unparseable / future
  heartbeat → CORRUPT, small skew within budget → READY; wrong root → UNSEEDED
  at the canonical path even though the other root is READY; stop count never
  decides; CLI exit codes 10/11/0/12/13 + usage + import failure.

`tests/test_stops_liveness_pager.py` (42 tests; 39 on main — 3 new, 1 renamed; fixtures reworked):
- hermetic fixtures now carry a stub pinned pipeline module
  (`_STUB_PIPELINE_STOPS_MODULE` `:499`) with the REAL path layout
  (`data/rq105/software_stops.<broker>.json`) and heartbeat arithmetic; the
  exec stub composes its path through it, so both stubs and the real chain
  resolve one path. All hermetic registry fixtures moved to that layout.
- `..._passes_with_zero_armed_stops_and_a_fresh_heartbeat` (`:1189`),
  `..._refuses_when_registry_is_seeded_but_uninitialized` (`:1208`),
  `..._refuses_when_registry_heartbeat_is_stale` (`:1223`); the ambient-decoy
  test's decoy is now VALID and READY (still ignored). Both dry-run tests assert
  the readiness preview line.
- real-sibling (skip only in an isolated worktree; run in CI and beside the
  siblings): the VALID real-chain test now writes a fresh heartbeat and asserts
  READY; `test_install_apply_real_chain_seed_alone_refused_then_one_writer_pass_passes`
  (`:1499`) is the requested regression: seed → `install --apply` refused with
  `NOT_READY_UNINITIALIZED`, nothing armed; `from_config` + `evaluate()` on the
  same root → READY → the same `install --apply` passes with `GUARD OK … READY`.

Evidence `[VERIFIED pytest, RenQuant/.venv py3.10.20, -p no:cacheprovider]`:
- the two files, from a checkout beside the real siblings: **76 passed, 0 skipped**
  (main: 38 passed / 2 skipped). From the isolated scratchpad worktree: 73 passed /
  3 skipped (the three real-sibling tests, each naming the reason).
- full suite from the sibling-adjacent checkout: **5 failed, 6814 passed, 2 skipped**; clean `origin/main` (`ef27bb80`, #1077) run the same way = **5 failed, 6786 passed, 2 skipped**, and the FAILED set is byte-identical (empty `diff` of the two FAILED lists). The failures are pre-existing and measure live state on this machine, not this branch (tests/test_goal3_public_export_resolution.py x1; tests/test_ops_audit_acks_ledger.py x1; tests/test_shadow_serving_skips_leave_evidence.py x2; tests/test_twin_parity.py x1: e.g. the twin-parity tripwire reports the umbrella's `live/broker.py` sha drifted from the pinned manifest; the live audit ledger carries an `ACK_EXPIRED`). None is in the two files above. (Note: the failure set differs from an isolated-worktree run, where 17 fail — `test_shadow_ab_daily_script` x13 etc. — because those tests resolve sibling checkouts relative to the repo; that set was byte-identical to clean main too, measured on the previous revision.)

## 6. Follow-ups (NOT in this PR; each needs its own review)

1. **Umbrella runner:** `RenQuant/backtesting/renquant_104/adapters/runner.py:233-236`
   calls `SoftwareStopRegistry.from_config(config, broker_name=…)` without
   `repo_root`, so a relative `registry_path` resolves against the process
   cwd. Pass `repo_root=<neutral root>` (`~/.renquant/runtime/software-stops`)
   so the writer stamps where the checker and the readiness classifier look.
   `from_config` supports the kwarg (`software_stops.py:321`, `:332`).
2. **Umbrella sell wrapper:** `RenQuant/scripts/intraday_sell_104.sh` (runner
   at `:110`; pinned PYTHONPATH at `:58` already includes orchestrator +
   pipeline) calls `... software_stops_registry_contract seed --broker alpaca`
   unconditionally before the runner. A non-zero exit is a page-worthy fact,
   not a reason to skip the sell pass.
3. **Enablement evidence:** the arming step and any `enabled: true` flip must
   cite `readiness` → READY at the plist's data root, observed while the loop
   is running. VALID is not evidence.

Chain position:

```
[this PR] bootstrap: seeder + readiness classification + installer requires READY
  → umbrella: runner from_config(repo_root=neutral) + wrapper calls seed
  → observe READY at the canonical path (readiness CLI) during a live loop
  → SLA drill (test-fire STALE)
  → install_stops_pager.sh install --apply  (guard: VALID and READY)
  → stage-3 sign-off → fractional flip under its own LONG-ledger row
```

No MID memory file covers the software-stops / fractional line (it lives in
LONG row 2b's text); this doc is the durable record. Opening a MID workstream
file is an SOP-M proposal for the operator, not done here.
