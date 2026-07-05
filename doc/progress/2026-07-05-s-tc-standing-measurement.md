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
