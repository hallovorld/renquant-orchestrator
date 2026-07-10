# Two-arm shadow A/B session runner (D6-§2a prerequisite P-2)   (PR #451)

STATUS:    in-progress
WHAT:      Implements the §2a two-arm shadow session runner
           (`renquant_orchestrator shadow-ab`) as pure code + tests, enforcing
           the frozen P-2 review contract mechanically and failing closed on
           every contract violation. UNINVOKED — no launchd entry, no
           schedule, no daily_104 change.
WHY/DIR:   Prerequisite P-2 for orchestrator#443's D6-§2a breadth-lever
           shadow A/B (now MERGED). Depends on P-1 (renquant-execution
           readonly-broker parameterization, execution#26, MERGED) and P-1b
           (pipeline ALLOWED_BROKERS entries, pipeline#181, MERGED); the
           strategy-104 config-only `shadow_a`/`shadow_b` PR (#53, MERGED)
           is done too. This PR (P-2) is the last prerequisite before arming.
EVIDENCE:  n/a (code-structure/contract-enforcement PR; no model/data claim)
NEXT:      Codex review of this revision (account-snapshot sealing +
           digest coverage — see "Paired-world sealing fix" below). Once
           approved: arming is a separately-gated step.

## Bottom line

`renquant_orchestrator shadow-ab` (new `src/renquant_orchestrator/shadow_ab_runner.py`)
implements the §2a two-arm shadow session runner as pure code + tests. It enforces the
frozen P-2 review contract mechanically and fails closed on every contract violation.
Nothing installs or schedules it — arming is a later, separately gated step after #443
merges and the P-1 / pipeline-allowlist / config-only prerequisites land.

## What it enforces (frozen §2a P-2 contract)

- **Same-world rule**: both arms must resolve IDENTICAL model / calibrator /
  data-manifest shas BEFORE anything runs; a mismatch aborts the session with neither
  arm invoked (exit 3).
- **Per-session bundle** (both arms, every §2a field): config sha256, unified
  `model_content_sha256`, calibrator sha, broker-state tag, strategy/pipeline/execution
  pin shas, data/feature manifest sha, and the invoking orchestrator commit. Model and
  calibrator fingerprints delegate to the ONE shared `renquant_common.model_fingerprint`
  implementation (never a bespoke re-hash; triple-impl incident history), resolved
  through the single `artifact_resolver` authority.
- **Paired invalidation**: either-arm failure (or a shared-input failure) marks the
  session invalidated in BOTH arms (exit 4); a clean arm paired with a failed arm is
  excluded entirely. Running excluded-pair vs attempted-pair counters are persisted.
- **Config-hash drift = VOID**: the first real session freezes both arms' config hashes
  (plus the world fingerprints) in `shadow_ab_freeze.json`; any later session whose
  config hash drifts exits 5 with the `SHADOW-AB VOID` marker and runs neither arm.
  Non-config drift against the freeze excludes the pair (bounded missingness), not VOID.
- **Preflight symmetry**: one shared env template (`SHADOW_PREFLIGHT_ENV`) and one
  shared command template for both arms; `assert_preflight_symmetry` rejects any delta
  beyond exactly (config path, tag, arm output dir) before anything runs — a tag-keyed
  preflight special case is structurally impossible.
- **Frozen tags**: `alpaca_shadow_a` / `alpaca_shadow_b` only; legacy `alpaca_shadow`
  (the untouched daily_104 Step-4 ops shadow), swapped, equal, or novel tags are
  rejected.
- **Prod-state protection**: `--output-root` must live outside the umbrella runtime
  tree; notifications require a dedicated shadow ntfy topic (the live `renquant` topic
  is rejected); arms run sequentially, never concurrently, and both consume the same
  session-shared market/account snapshot files.

## Assembly (per the §2a scope note, decided in this PR's review)

Arms are invoked through an injectable CommandRunner boundary; the default assembly is
the orchestrator-native, pipeline-owned chain — `native-live-context` →
`native-live-inference` → `native-live-run` — which never imports umbrella
`live.runner` (the §2a execution plan retired the bridge/live.runner route for this
experiment; `live_bridge.py` and daily_104 Step-4 stay untouched on the legacy ops
path). The broker-state tag is threaded into the native run (`--broker-name`,
`--live-state-broker-name`, arm-isolated `runs.<tag>.db`), so until the pipeline
`ALLOWED_BROKERS` allowlist entries and P-1's readonly-broker parameterization merge,
downstream state resolution fails closed by design.

## Tests

`tests/test_shadow_ab_runner.py` (23 tests) mocks the pipeline invocation boundary and
covers: same-world abort, both-arms paired invalidation, config-drift VOID,
frozen-world mismatch (invalidated, not VOID), §2a bundle completeness per arm,
preflight/env symmetry (+ rejection of tag-keyed asymmetry), sequential arm ordering on
shared inputs, tag validation (legacy/swapped/equal/novel), live-topic rejection,
umbrella-tree output-root rejection, symmetric notifications, plan-only inertness, CLI
wiring, and exclusion-counter accumulation. Full `make test` green.

## Explicitly NOT in this PR

- No launchd/schedule install, no invocation from any script (P-2 is a prerequisite;
  arming is gated on #443 + P-1 + the pipeline allowlist + the config-only shadow_b PR).
- No umbrella change of any kind; no change to `live_bridge.py` or daily_104 Step-4.
- No pipeline/execution internals — those repos own their pieces (P-1, allowlist).

## Post-#443-merge fixes (Codex review on #451, 4 points)

Codex reviewed this PR against the frozen r7 protocol (before #443's final r8/r9
rounds) and found the code didn't yet enforce the contract it claimed to. All four
points addressed now that #443 has merged:

1. **Decision-snapshot digest** (r7 point 1): `SPEC_2A_ARM_FIELDS` grows an 8th
   field, `decision_snapshot_digest`. `native_live_context.compute_decision_snapshot_digest()`
   is the ONE shared digest formula (never reimplemented at two call sites — the
   `model_content_sha256` triple-impl incident history is exactly the failure mode this
   avoids): it hashes the market snapshot content (covers as-of/universe/prices/
   corporate-actions) + model/calibrator identity + a fixed starting-state-convention
   marker + the session date. `run_shadow_ab_session` computes this digest ONCE before
   either arm's plan is built and threads it into BOTH arms' `native-live-context`
   invocation via new `--decision-snapshot-digest`/`--model-content-sha256`/
   `--calibrator-content-sha256`/`--session-date` flags.
   `native_live_context.build_native_live_context()` independently RECOMPUTES the
   digest from what it actually loaded and raises `DecisionSnapshotMismatchError` on a
   mismatch — consumption-side verification, not just parameter threading. A mismatch
   fails that arm's command (nonzero exit), which the EXISTING either-arm-failure path
   already invalidates in BOTH arms (no new pairing logic needed).
2. **Freeze payload / drift checks** (Codex review on #451, point 2): `_freeze_payload`
   now includes `subrepo_pins` and `orchestrator_commit`; `_frozen_world_mismatches`
   checks them against the frozen-at-start values (same bounded-exclusion semantics as
   model/calibrator/manifest drift — a pin or code change mid-experiment invalidates the
   session-pair, it does not silently pass).
3. **Treatment-key isolation** (point 3): new `treatment_key_violations()` flattens both
   arms' configs to dotted-path key/value maps (dropping `_reason` annotation keys, which
   the protocol explicitly permits) and asserts the diff set is EXACTLY
   `ranking.panel_scoring.buy_floor_std_mult` — not "distinct config paths." Catches both
   an accidental extra delta and a missing treatment delta. Negative test included
   (`test_run_aborts_when_config_diff_has_an_extra_delta`), per Codex's explicit ask.
4. **No umbrella-layout fallback** (point 4): new `default_experiment_strategy_dir()`
   resolves the PINNED `renquant-strategy-104/configs` dir via `default_github_root()`
   and fails closed (`ShadowABContractError`) if it doesn't exist — no silent fallback to
   `repo_root / "backtesting" / "renquant_104"`. `repo_root` itself is unchanged (it's a
   legitimate, separate safety check in `validate_output_root` and an artifact-resolution
   fallback, not the umbrella-coupling bug).

Tests: `tests/test_shadow_ab_runner.py` grew from 23 to 39 (treatment-key isolation x4,
decision-snapshot digest x3, pin/commit drift x3, no-umbrella-fallback x3, plus fixture
updates for the new required `build_arm_plan` params). `tests/test_native_live_context.py`
unaffected (new params are optional, backward compatible). Full suite: 3310 passed, 3
skipped, 1 pre-existing failure unrelated to this PR (`test_parking_sleeve_cli_
computes_allocation`, a worktree-path artifact in a file this PR never touches — confirmed
via `git diff --stat` showing zero changes to that file).

## Paired-world sealing fix (Codex review on #451, "paired-world proof is still incomplete")

Codex's next review found the point-1 fix above real but incomplete: the digest covered
only the market snapshot + model/calibrator + date, never the account snapshot, and
nothing MATERIALIZED (immutably copied) either snapshot before either arm consumed it —
a caller could mutate the account file after the freeze, or (in principle) a future
caller could pass genuinely different account snapshots per arm while the market-only
digest looked identical.

Fixed both halves:

- **`native_live_context.compute_decision_snapshot_digest()`** gains a required
  `account_snapshot` parameter, included in the canonical digest alongside the market
  snapshot. `STARTING_STATE_CONVENTION`'s docstring is corrected: the RULE (each arm
  reads its own prior-EOD state) is shared, but that never meant the account snapshot's
  CONTENT was excluded from integrity checking — it now is, per-arm.
- **New `native_live_context.seal_json_snapshot()`**: loads a JSON snapshot and writes a
  canonical immutable copy to a dedicated path. `run_shadow_ab_session` now seals both
  the market and account snapshots into `<session_dir>/sealed_market_snapshot.json` /
  `sealed_account_snapshot.json` BEFORE computing the digest or building either arm's
  plan, and both arms are handed the SEALED paths, never the original caller-supplied
  ones — a mutation of the original after sealing has zero effect on what either arm
  reads. (Plan-only mode does no sealing — no writes are permitted under `output_root`
  in that mode — and reads the given paths directly instead, which requires them to
  already exist; an auto-generated account snapshot that hasn't been materialized yet is
  a plan-only caller error now, not a silent gap, since it never worked correctly before
  either.)
- **`build_native_live_context()`** already loaded the account snapshot for its own
  payload; it now also feeds that same loaded dict into its digest recomputation, so
  consumption-side verification catches a mutated/mismatched account file exactly the
  same way it already caught a mutated market file — no new CLI flags needed.
- The one existing case where an account snapshot needs auto-generation
  (`account_snapshot_json=None`) is now run EAGERLY (before the digest, not deferred to
  the later shared-steps batch) so real content exists to seal — the single call site
  that used to defer this is unchanged in the explicit-path case (by far the common one;
  every existing test uses it).

Tests: `tests/test_shadow_ab_runner.py` grew from 39 to 43 — a module-level
account-only-difference test proving two otherwise-identical inputs with different
account content get different digests, a module-level mutation test on
`build_native_live_context` proving a post-freeze account mutation fails closed, and two
session-level integration tests (digest changes with account content;
sealed copies survive a post-hoc mutation of the originals). One existing test
(`test_arms_run_sequentially_and_consume_same_inputs`) updated to assert both arms
reference the SEALED paths, not the originals. Full suite: 3314 passed, 3 skipped, the
same 1 pre-existing unrelated failure (confirmed reproducible across 3 repeated full-suite
runs; an earlier single run showed 5 additional failures that did not reproduce in
isolation or in 3 subsequent full-suite runs — a flaky/ordering artifact, not a real
regression, since the unmodified branch also passes those 5 tests both in isolation and
across repeated full-suite runs).
