# S-TC: standing transfer coefficient measurement

DATE: 2026-07-05

## What

Promote the POC transfer coefficient measurement (`scripts/poc_transfer_coefficient.py`,
3 rounds of Codex review) to a schedulable standing measurement module.

## Changes

- `src/renquant_orchestrator/tc_measurement.py` — new module:
  - `compute_buy_side_tc()` — core computation per run (admission taxonomy from POC round 3)
  - `run_measurement()` — batch: find un-measured canonical runs, compute, persist
  - `main(argv)` — CLI entry point with `--runs-db`, `--ledger-db`, `--dry-run`
  - Persists to `tc_metrics` table in `decision_ledger.db` (append-only, WAL, idempotent)
- Job runner: `tc_measurement` registered in `_MODULE_JOBS` + `scheduled_jobs` inventory
- Tests: 10 new tests covering classification, computation categories (measured,
  no_deployment, zero_dispersion, insufficient population), end-to-end persistence,
  idempotency, dry-run, empty DB
- Strategy snapshot regenerated for the new source module
- `doc/roadmap-backlog.json`: mark `s2-wire-gate-ledger` done (code-complete across all
  repos — pipeline #176 + orchestrator #133 + DecisionLedgerWriteTask registered in
  pp_inference.py; config enablement is a separate operational step)

## Sprint status note

Cross-repo scan (2026-07-05) confirms ALL engineering code for SHORT-tier items is merged
with flags OFF across all 9 repos. Remaining work is config enablement + operational
verification, not code.

## Round 2 (Codex review)

STATUS: fixed, pushed, awaiting re-review.

WHAT: `main()`'s default `--runs-db` resolution fell back to
`os.environ.get("RQ_ROOT", str(Path.home() / "git/github/RenQuant")) / "data/runs.alpaca.db"`
— a repo/workstation path assumption unrelated to this repo's actual runtime-path
authority. For a daily standing job (not an ad hoc script) this risked silently
pointing at the wrong tree on a different machine.

WHY-DIR: replaced the `RQ_ROOT`/home-dir fallback with
`DEFAULT_RUNS_DB = default_data_root() / "data" / "runs.alpaca.db"` — the exact
convention already used by `transfer_coefficient.py`, `m4b_conviction_replay.py`,
`sign_laundering_harness.py`, `gate_calibration_diagnostic.py`, and
`attribution/ledger.py`. `main()` now does `args.runs_db or DEFAULT_RUNS_DB`, so
an explicit `--runs-db` still overrides, but the silent default routes through
the canonical `runtime_paths.default_data_root()` authority (honors
`RENQUANT_DATA_ROOT` / `RENQUANT_REPO_ROOT` / `RENQUANT_GITHUB_ROOT`) instead of
a hard-coded path. Also corrected the module docstring, which still described
a third, different hard-coded path (`~/renquant-data/...`) that never matched
either the old or new code.

EVIDENCE: added `TestDefaultRunsDbResolution` (2 tests) — one asserts
`DEFAULT_RUNS_DB == default_data_root() / "data" / "runs.alpaca.db"`, the other
spawns a fresh subprocess with `RENQUANT_DATA_ROOT` set before import and
confirms `DEFAULT_RUNS_DB` resolves to that root (proving genuine derivation,
not a value that merely looks similar — a module-level constant computed at
import time can't be tested by patching env vars post-import). Both fail
against the pre-fix code (`ImportError: cannot import name 'DEFAULT_RUNS_DB'`)
and pass after. Full module suite 15/15; full repo suite 2990/2992 (2
pre-existing unrelated failures in `test_bundle_consistency_ci_gate.py`,
confirmed reproducing on clean `origin/main`).

NEXT: awaiting fresh Codex review at the current head.

## Round 3 (Codex review)

STATUS: fixed, pushed, awaiting re-review.

WHAT: two issues in `run_measurement()`:
1. Persistence was keyed by `run_id` (the `tc_metrics` PRIMARY KEY), not
   `run_date`. If day D was measured under run A, and a later rerun B became
   the new canonical `max(created_at)` run for the same `run_date`, the job
   appended B's row without removing A's — leaving two measured rows for one
   trading day, double-counting that day in the rolling `tc_mean`/`tc_se`.
2. `--dry-run` still opened `decision_ledger.db` read-write, enabled WAL, and
   called `_ensure_table()` (`CREATE TABLE IF NOT EXISTS` + index) — which
   creates the file on first run even though nothing is meant to be
   persisted. This violated the advertised "compute but don't persist"
   contract, and mattered because dry-run is exactly what rehearsals/safety
   checks rely on.

WHY-DIR: for a standing metric feeding a rolling summary, one canonical row
per trading day is the whole point of the "canonical daily run" concept —
letting a superseded run's row survive silently corrupts every downstream
read of `tc_mean`. And a "dry-run" that mutates the target file on disk is a
dry-run in name only.

EVIDENCE:
- Fix 1: `run_measurement()` now reads existing rows keyed by `run_date` (not
  just `run_id`) via `_existing_metrics_rows()`. For each canonical run, if
  `run_date` was already measured under a DIFFERENT (older) `run_id`, that
  date is marked stale — its row is `DELETE`d before the new one is inserted
  (`INSERT OR REPLACE`). Reproduced the bug directly before fixing: seeded
  run A for `2026-07-01`, measured, then seeded a later run B for the same
  date and re-measured — pre-fix left 2 rows for the day; post-fix leaves
  exactly 1 (run B's).
- Fix 2: added `_read_existing_metrics_readonly()`, which opens the ledger
  via SQLite's `mode=ro` URI — this genuinely cannot create or alter the
  file (an OperationalError is caught and treated as "nothing measured yet"
  when the file doesn't exist). `run_measurement()` now takes this read-only
  path entirely when `dry_run=True`; the read-write connection, WAL pragma,
  and `_ensure_table()` call are only reached on the real (non-dry-run)
  path. The rolling `tc_mean`/`tc_se` for the dry-run summary is computed in
  Python from (existing rows minus superseded dates) + newly-computed
  results, so dry-run still reports an accurate preview without any second
  ledger touch. Reproduced directly: ran `--dry-run` against a temp dir with
  no `ledger.db` — pre-fix, the file existed afterward; post-fix, it does
  not.

New tests: `test_rerun_supersedes_prior_canonical` (seeds run A for a date,
measures, seeds a later run B for the same date, measures again, asserts
exactly one row survives and it's B's) and
`test_dry_run_never_creates_ledger_db` (asserts the ledger file does not
exist before or after a `--dry-run` invocation that has real work to do).
Both confirmed to FAIL against the pre-fix code (isolated via `git stash` on
`tc_measurement.py` only) and pass after. Full module suite 17/17; full repo
suite 3135/3135 (no failures — the 2 previously-known unrelated
`test_bundle_consistency_ci_gate.py` failures are gone too).

NEXT: awaiting fresh Codex review at the current head.
