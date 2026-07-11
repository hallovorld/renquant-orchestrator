# Modal run guardrails: enforceable spend cap + pre-registered workload identity

Date: 2026-07-11
Scope: `src/renquant_orchestrator/cloud/modal_executor.py`,
`modal_app.py`, `executor.py`, `scripts/run_sweep_modal.py`, tests.
Prerequisite named by Codex's #450 review (2026-07-11 03:21Z, points 1–2)
and by the merged experiment plan's "BLOCKING PREREQUISITE" section
(`doc/design/2026-07-11-modal-bounded-run-experiment-plan.md`).

**Merging this PR authorizes NO Modal run.** It only makes the approval
boundary mechanically enforceable; any actual bounded run still requires
the operator to set the dollar ceiling and approve a concrete workload
manifest at execution time.

## What is enforced now

1. **Spend cap (fail-closed).** `ModalExecutor.preflight` gained a
   REQUIRED keyword `approved_cost_cap_usd` — no default, so a cap-less
   call is a `TypeError`; a non-positive/NaN/inf cap is a `ValueError`.
   The gate is `min(HARD_COST_SAFETY_GATE_USD = $20, approved cap)`: the
   tighter bound always governs (tests prove both directions). The cap +
   effective gate + projection are recorded in the report's details on
   pass AND fail.
2. **Dispatch token, not honor system.** A passing preflight issues an
   immutable `DispatchApproval` (cap, effective gate, projection, pod
   count, manifest sha, nonce). `execute_batch` now takes
   `preflight=<report>` and refuses to dispatch when it is absent, failed,
   or was issued by a different executor instance (nonce check). The
   guard runs before any modal_app import.
3. **Pre-registered workload identity.** `WorkloadManifest` (JSON, loaded
   via `WorkloadManifest.load`) REQUIRES: exact variant identifiers with
   per-variant `config_sha256` + literal seed integers, bundle
   fingerprint, volume name + content-coupled volume commit, data-manifest
   sha, walk-forward artifact sha, data interval start/end, region, and
   image-spec fingerprint. Unknown region or unresolved image/Volume
   identity fails at load (`WorkloadManifestError`) — abort, not post-hoc
   note. Preflight cross-checks the manifest against the executor config,
   synced data, current bundle, and planned variant/seed counts. At
   dispatch, every request is re-verified against the manifest (variant
   registered, config sha, seed set, interval, volume commit, plus a
   fresh bundle-fingerprint recompute); ANY mismatch raises
   `WorkloadMismatchError` before anything reaches Modal. Batches may be
   a SUBSET of the manifest (incumbent-first batch, resume) but never a
   deviation.
4. **Evidence stamping.** The manifest sha + cap are echoed into every
   pod's request JSON (`dispatch_metadata`), stamped onto each aggregated
   `BacktestResult.workload_manifest_sha256`, and written as
   `dispatch_approval.json` next to `results.db` in the sweep output dir.
5. **Runner surface.** `run_sweep_modal.py`:
   `--write-workload-manifest PATH --region R` captures the CURRENT plan
   (local-only: content-coupled volume commit computed without any Modal
   call) for operator approval; `--workload-manifest` +
   `--approved-cost-cap-usd` are hard usage requirements for
   `--preflight`/`--execute`/dry-run (`parser.error` otherwise). The
   request builder was extracted to module level
   (`build_backtest_request`) so capture and execution fingerprint
   byte-identical `config_json` through one code path;
   `incumbent_turnover` rides on the request, not in the config, so
   post-incumbent candidates keep their pre-registered fingerprints.
6. **Region is requested, not just recorded.** `modal_app` bakes
   `RENQUANT_MODAL_REGION` into the `@app.function` decorator (same
   env-var mechanism as timeout/retries; conflict-on-reimport check
   extended). `IMAGE_SPEC` in `modal_executor.py` is the single source of
   truth for the image definition; a test asserts modal_app's baked build
   inputs match it, so the manifest's image fingerprint cannot drift from
   what runs.

## Evidence

- `[VERIFIED]` Full suite in the feature worktree: **3431 passed, 9
  failed, 3 skipped**. The 9 failures (8 in
  `tests/test_shadow_ab_daily_script.py`, 1 in `tests/test_twin_parity.py`)
  are byte-identical on a pristine `origin/main` worktree in the same
  environment — pre-existing worktree-env-sensitivity (these tests depend
  on primary-checkout git/manifest state), not this change.
- `[VERIFIED]` Guardrail test files: `tests/test_cloud_modal.py` +
  `tests/test_run_sweep_modal.py` + `tests/test_cloud_executor.py` = 78
  passed (42 on baseline `origin/main` → 36 net-new), covering: cap
  missing → TypeError; unresolved cap → fails closed (no fallback to the
  $20 gate); cap above gate → hard gate binds; cap below gate → cap
  binds; projected > cap → preflight fails, no token; dispatch without
  token / failed report / foreign report → refused; variant added, seed
  changed, config drift, bundle drift, off-interval, wrong volume commit
  → `WorkloadMismatchError` before dispatch; happy path records cap +
  manifest sha in dispatch metadata and results; manifest loader rejects
  unknown region / unresolved image/Volume / count-like variants /
  duplicate names / non-integer seeds; writer round-trips and refuses
  unresolved plans; `run_sweep` threads the token into BOTH batches.
- `[GUESS]` Whether the operator's Modal workspace plan supports
  `region=` at `@app.function` is unverified (no Modal calls permitted).
  Installed SDKs (1.2.6 system / 1.5.1 venv) accept the kwarg
  [VERIFIED by signature inspection]. If the plan rejects it, dispatch
  fails loudly — fail-closed, matching the plan's abort-on-unresolved
  rule.

## Deliberately out of scope

- No production parameter/estimator changes: `MODAL_CPU_RATE`,
  `DEFAULT_SECONDS_PER_POD_ESTIMATE`, and the $20 literal's VALUE are
  untouched (the literal is only named `HARD_COST_SAFETY_GATE_USD`).
  #450's estimator/constants questions stay in their own PR.
- No dollar ceiling proposed — OPERATOR TO SET, per the design doc.
- `ResultStore` schema unchanged (evidence goes to the
  `dispatch_approval.json` sidecar + per-result field) to avoid a SQLite
  migration in a guardrail PR.

## 2026-07-11 round-2 addendum: --execute hard-blocked, no unilateral signing design

Codex round-2 (2026-07-11T04:20:37Z): the cap + manifest above are still
self-service — any caller with Modal credentials can generate a manifest,
choose a cap, pass preflight, and dispatch; the dispatch token is
self-issued by that same caller. That does not meet the standing rule
that an agent cannot self-authorize a Modal run. Codex asked for either a
real cryptographically-signed operator-authorization artifact (verified
against a key the execution agent cannot access) or, as an interim,
unconditionally hard-blocking `--execute` so this PR's useful local-only
work can merge without granting dispatch capability.

Deliberately did NOT design the signing scheme — deciding where the
private key lives and what tool/workflow signs the artifact is a
trust-boundary decision about the execution agent's own constraints, not
something the agent that control exists to constrain should invent
unilaterally. Flagged to the operator for input on the signing mechanism.

Implemented the interim hard block instead:

- `run_sweep_modal.py::main`: `--execute` now unconditionally fails closed
  (clear error, `return 1`) immediately after CLI argument validation —
  before ANY bundling/staging/sync work, not just before dispatch. A
  second `if not args.execute` further down (kept as a normal conditional,
  not a bare assert, so static analysis doesn't read Step 6+ as dead code)
  is a structural backstop.
- Also found and fixed a bigger pre-existing gap while implementing this:
  Step 4 (`executor.sync_data(...)`) ran UNCONDITIONALLY — even for a
  plain `--preflight` or no-flag dry run, before any `--execute` check —
  and genuinely called the real Modal API (`modal.Volume.from_name`,
  `vol.batch_upload`). This predates #463 entirely (present since the
  original `feat(cloud): Modal executor...` commit on `main`). New
  `sync_data.local_data_manifest()` computes a byte-identical `DataManifest`
  (same `commit_id`/`files`/`total_bytes`) from local file content only,
  with zero `modal` import; `sync_to_modal_volume` now calls it internally
  too (single source of truth), and `run_sweep_modal.py`'s Step 4 uses it
  directly instead of the real-upload path. No code path in this script
  reaches Modal now, regardless of flags.

Tests: `test_execute_is_disabled_pending_authorization_and_no_live_guard`
+ `test_execute_disabled_error_precedes_manifest_load` (block fires before
any file I/O — a deliberately nonexistent/malformed manifest path proves
it); `test_local_data_manifest_makes_no_modal_calls` (sentinel `modal`
module in `sys.modules` that raises on any attribute access — proves
structurally that Step 4's replacement never touches it);
`test_local_data_manifest_commit_id_matches_a_real_sync` (same commit_id
as the pre-refactor computation, so the identity a manifest is validated
against didn't silently change). All 4 confirmed meaningful via
stash-revert against the pre-fix code. Full guardrail suite (`test_cloud_
modal.py` + `test_run_sweep_modal.py`): 75 passed.

## 2026-07-11 round-3 addendum: block moved into the library, not just the CLI

Codex round-3 (2026-07-11T04:45:20Z): the CLI block is UX, not a safety
gate — any in-repo Python caller can construct a `ModalExecutor` directly
and call `execute_batch()`/`sync_data()`, bypassing `run_sweep_modal.py`
entirely. Both public methods still imported/accessed Modal, and
`execute_batch` still accepted a self-issued preflight report. Moved the
block into the one place both methods share:

- New `ModalExecutor._require_modal_execution_enabled()` — unconditionally
  raises `ModalExecutionDisabledError`, called as the FIRST line of both
  `execute_batch()` and `sync_data()`, before any other guardrail logic
  (dispatch-approval check, workload-mismatch check, `modal_app` import,
  the real `sync_to_modal_volume` upload). A passing, self-issued
  `preflight` report does not bypass it — that self-issued-authorization
  gap is exactly what round-3 rejected. A dedicated method (not a bare
  `raise` inline) so re-enabling this later is a one-line change in one
  place, and so neither method's body reads as statically unreachable
  dead code in the meantime.
- Existing guardrail tests (dispatch-approval nonce, workload-mismatch
  checks, cost-cap math, partial-failure handling — all still real, valid
  logic that must keep working the moment this block lifts) now
  explicitly monkeypatch `_require_modal_execution_enabled` to a no-op via
  the shared `_passing_preflight` fixture, so they keep exercising that
  logic rather than being blocked by the new guard.
- New `TestModalExecutionDisabled` class proves the guard itself: calling
  `execute_batch()` with a genuinely PASSING, self-issued preflight report,
  and calling `sync_data()`, both raise `ModalExecutionDisabledError`
  before touching Modal — proven structurally via a sentinel `modal`
  module in `sys.modules` that raises `AssertionError` on any attribute
  access. Confirmed meaningful via stash-revert (ImportError against the
  pre-fix code, since `ModalExecutionDisabledError` is new).

Full guardrail suite: 77 passed (2 new). Broader suite: 2991 passed / 14
failed (identical failures to round 2 — same pre-existing env issues,
unrelated).
