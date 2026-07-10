# native-live-context paired-world verification (first real §2a session repro fix)

**Date**: 2026-07-10
**Status**: VERIFIED — the exact failed session command now passes end-to-end
**Related**: #451 (P-2 two-arm shadow runner, merged), #443 (D6 §2a protocol)
**Repro**: `/Users/renhao/renquant-shadow-ab/2026-07-10/shadow_ab_session_bundle.json`
(first real two-arm session: both arms exited 2, session paired-invalidated, exit 4)

## Bottom line

The two-arm runner invokes its arm steps as `python -m renquant_orchestrator
<subcommand> ...`, which routes through the TOP-LEVEL `cli.py` — and `cli.py` never
gained the paired-world flags that `build_arm_plan` emits. The module-level
`native_live_context.main()` accepted them (merged with #451), but the `cli.py`
subparser rejected the whole invocation with `unrecognized arguments:
--decision-snapshot-digest ...` (exit 2) — so the consumption-side half of the §2a
contract never executed, and every real session would fail closed at arm step 1.
A second latent break: `native-live-run` (arm step 3) had NO `cli.py` subcommand at
all. Both fixed; the exact failing command from the repro bundle now exits 0 with
`decision_snapshot_verified` + `config_artifact_shas_verified` [VERIFIED, replayed
against the real session's sealed files and the real PatchTST/calibrator artifacts].

## What changed

1. **`cli.py` `native-live-context`**: accepts + threads `--decision-snapshot-digest`,
   `--model-content-sha256`, `--calibrator-content-sha256`, `--session-date` (and the
   runner's resolution anchors, below). Optional — absent flags leave every existing
   caller byte-identical (pinned by test).
2. **`cli.py` `native-live-run`**: new subcommand wiring the existing
   `native_live_run.main`, declaring EXACTLY the surface `build_arm_plan` emits and no
   more (the module's live-commit flags stay off the top-level CLI).
3. **Consumption-side artifact verification** (`verify_config_artifact_shas`): with the
   paired-world args present, the context now also verifies the frozen model/calibrator
   shas against the artifacts it ACTUALLY resolves from the strategy config it loaded —
   via the single `artifact_resolver` authority and the single unified
   `renquant_common` fingerprint (`default_model_fingerprint_from_path`, now shared:
   `shadow_ab_runner` delegates to it instead of holding a second copy — triple-impl
   lesson). Any inconsistency (unresolvable ref, sha mismatch, calibrator
   declared-vs-frozen asymmetry) exits nonzero.
4. **Clear nonzero exit**: `native_live_context.main()` catches
   `DecisionSnapshotMismatchError` and exits 2 with a `PAIRED-WORLD MISMATCH: ...`
   stderr line — that nonzero arm exit is what triggers the runner's both-arms
   invalidation.
5. **Anchor threading** (found by replaying the repro): the context initially resolved
   artifacts from (config-parent, default repo root) while the runner had resolved with
   its own `--strategy-dir` — the replay failed with "model artifact unresolvable"
   because the armed config's `../../artifacts/...` ref only resolves from the runner's
   anchor. `build_arm_plan` now threads `--strategy-dir` (+ `--repo-root`) into the
   context command so BOTH sides resolve through EXACTLY the same anchors — divergent
   resolution order between two call sites is the incident class `artifact_resolver`
   exists to kill. Defaults (config parent + default repo root) apply when absent.
6. **Shared ref extraction**: `panel_artifact_refs()` added to `native_live_context`;
   `shadow_ab_runner.resolve_arm_fingerprints` now uses it (producer and consumer read
   the SAME config keys or the verification proves nothing).

## Does native-live-inference / native-live-run need the same args?

Checked against `build_arm_plan`'s actual emissions:
- `native-live-inference`: emits only `--context-json`/`--output-json` — surface
  already matched; nothing added.
- `native-live-run`: subcommand was MISSING entirely; added with exactly the nine
  emitted flags (`--inference-json --execution-output-json --output-json --broker-name
  --run-id --strategy-dir --runs-db --live-state-broker-name
  --live-state-contract-output-json`).
- `native-live-account-snapshot` (shared fetch step): already matched.
- New regression pin `test_every_runner_emitted_command_parses_and_dispatches_through_cli`
  drives EVERY runner-emitted command through `cli.main` with dispatch stubs — this
  test alone would have caught today's incident class.

## Tests

`tests/test_native_live_context.py` +8 (CLI accept+verify happy path; digest mismatch
nonzero + clear message; model-sha-vs-artifact mismatch nonzero (digest deliberately
consistent so only the artifact check can catch it); calibrator declared-but-not-frozen
nonzero; absent-args legacy byte-identical pin; anchor pins x2; `panel_artifact_refs`
fail-closed). `tests/test_shadow_ab_runner.py` +1 (runner-emissions CLI contract) and
1 updated (happy-path context test now carries a resolvable config). Full suite:
3353 passed, 3 skipped.
