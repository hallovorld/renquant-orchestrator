# Two-arm shadow A/B session runner (D6-§2a prerequisite P-2)

**Date**: 2026-07-10
**Status**: BUILT + TESTED — UNINVOKED (no launchd entry, no schedule, no daily_104 change)
**Related**: PR #443 (D6 Deployment Governor RFC + preregistered replay protocol, §2a), P-1
(renquant-execution readonly-broker parameterization), the strategy-104 config-only
`shadow_b` PR (the #52 successor)

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
