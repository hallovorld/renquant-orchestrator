# Progress — dawn-preflight `live.runner` import fix (GOAL-5 AC5/AC1)

**Date:** 2026-07-21. **Type:** ops monitor bugfix (1-line parity).

## STATUS:
The `com.renquant.rq104-dawn-preflight` job has been failing (last exit 1, current
— ran 2026-07-21 06:05) with `ModuleNotFoundError: No module named 'live'` →
"funnel never reached a decision line." A #524-class cross-repo import gap **in the
AC5 guard itself**. NOT a live-trading outage: the real 13:55 daily run works
(produces candidates); only the dawn readonly probe was broken.

## WHAT:
`ops/renquant104/dawn_funnel_preflight.sh`: add `cd "$REPO_DIR"` (umbrella root)
before `python -m live.runner`, matching the real daily wrapper.

## WHY/DIR:
`live/` is at the umbrella ROOT (`RenQuant/live/runner.py`), not in any subrepo, so
`-m live.runner` needs the umbrella on the module search path. `daily_104.sh:275`
resolves it via `cd "$REPO_DIR"`; the preflight ran from `OPS_DIR` with a
subrepo-only PYTHONPATH (line 20) → `live` unresolvable → fail-closed before any
decision. The fix makes the readonly probe resolve `live` exactly as production
does. All preflight paths are absolute ($REPO_DIR/$OPS_DIR/$LOG), so changing cwd
is side-effect-free.

## EVIDENCE:
Reproduced + fixed by direct import test:
- BEFORE (cwd=OPS_DIR, subrepo-only path): `import live.runner` → `ModuleNotFoundError: No module named 'live'`.
- AFTER (cwd=umbrella root): `import live.runner` → OK.
`[VERIFIED — before/after import test on the live venv]`

## NEXT:
- Deploy to `renquant-orchestrator-run` after merge (the run checkout is what
  launchd executes); next 06:05 dawn-preflight should reach a decision line.
- The other forwarded launchd nonzero exits were classified (2026-07-21): run
  -surface-drift = the README drift I already cleaned (self-resolves); scorer
  -identity/weekly-apy/tournament-retrain = STALE last-exit statuses, not current
  failures. This preflight was the only current genuine one.

---

## ADDENDUM 2026-07-22 — true read-only probe (`--preflight`), codex CR on #565

**Problem (codex):** `--broker readonly-alpaca --once` only constrains BROKER
writes. `live.runner --once` can STILL open/create the runs DB, allocate a run
id, persist `live_state`, run the score-distribution DB writer, and emit ntfy —
so it was NOT a safe read-only operational probe.

**Fix (two repos):**
- **Umbrella** (`RenQuant`, branch `feat/runner-preflight-mode`): added a
  `--preflight` (dry-run) mode to `live/runner.py`. It drives the same funnel to
  the decision line but GUARANTEES zero of: DB/state persistence, order
  placement, promotion, notification. Enforcement (single chokepoints, not
  scattered ifs), verified by mapping every side-effect surface:
  - `RunnerAdapter.commit()` is the sole write chokepoint (every
    `broker.place_order` / `record_*` / `save_live_state_atomic` / L6-sidecar /
    trade-log write lives there) — dry-run never calls it; commit() also refuses
    + flips the guard if ever entered (defense in depth).
  - The adapter opens NO runs DB in preflight (`ctx._db is None` ⇒
    `ScoreDistributionJob` no-ops and `data/runs_*.db` is never created); meta
    -label parquet capture is forced off.
  - Every ntfy send is intercepted at the single send chokepoint
    (`_post_ntfy_with_retries`) by a process-wide `PreflightGuard` and suppressed.
  - Emits `preflight_attestation: {persisted,notified,promoted,ordered,
    reached_decision}` — self-attesting (a boundary that is actually hit flips
    its flag). `reached_decision:true` ONLY after `pipeline.run()` completes; any
    preflight-contract failure ⇒ `reached_decision:false` (fail closed, alerts
    the daily-killer 8h early).
- **Orchestrator** (this PR #565):
  - `ops/renquant104/dawn_funnel_preflight.sh`: invoke `--preflight` (dropped
    `--once`); kept the `cd "$REPO_DIR"` import fix. After the run, FAIL CLOSED
    (exit 1 + alert) unless the runner attested a clean probe, BEFORE the content
    analyzer even runs.
  - New `ops/renquant104/dawn_preflight_attest.py`: parses the terminal
    `preflight_attestation:` line and passes only when persisted/notified/
    promoted/ordered are all false AND reached_decision is true. Missing line
    (crash/hang/truncation) or any true mutation flag ⇒ fail closed.

**Evidence `[VERIFIED]`:** umbrella preflight tests
(`test_runner_preflight_dry_run.py` 6, `test_runner_preflight_adapter.py` 3,
`test_runner_preflight_fail_closed.py` 3) green; a real-adapter test proves
`--preflight` construction opens no `runs*.db` under an isolated path and
`commit()` refuses + flips the guard. Orch verifier tests
(`test_dawn_preflight_attest.py` 11, `test_dawn_funnel_analyze.py` 7) green.
Cross-module check: the exact line the runner emits passes the orch verifier
when clean and fails closed when a boundary is hit or no decision is reached.
