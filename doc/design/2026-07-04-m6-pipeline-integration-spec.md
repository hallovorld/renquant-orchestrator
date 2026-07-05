# M6 stage-2: pipeline integration specification

DATE: 2026-07-04
STATUS: SPEC (as-built documentation of the step-1 code + remaining migration steps)
PARENT: `doc/design/2026-07-03-m6-stage2-fingerprint-migration.md` (the stage-2 plan)
BLOCKS: step-2 v1 re-stamp run, step-4 flag flip, step-5 shim removal (common 0.10)

## Purpose

The M6 stage-2 migration plan (parent doc) describes the full five-step sequence
for moving the fleet from the legacy 0.8.1 fingerprint semantics onto the
schema-v1 API (`stamp()`/`verify()`). Step 1 of that plan -- the
version-dispatched verification code -- lives entirely in the pipeline repo.
This document is the pipeline integration specification: it enumerates every
file changed, the dispatch logic at each fail-closed check, the dual-stamp
resolution in `PanelScorer.load`, the config key contract, and the test fixtures
that pin the behavior.

Modeled on `doc/design/2026-07-04-s5-decision-ledger-pipeline-integration.md`.

## Version boundary (pipeline commit this spec describes)

This is a pinned-subrepo orchestration repo — every cross-repo behavioral claim
below only holds for a specific pipeline checkout state. That state:

- **Pipeline commit**: `0dfc070cec82bb27089909f28eb764730ccdd844`
  (`feat(fingerprint): M6 stage-2 step-1 — schema-version-dispatched
  verification behind accept_legacy_stamps`), `renquant-pipeline` package
  version `0.4.0`. This is the single commit that introduced/last-touched all
  five files section 1 documents (`fingerprint_dispatch.py`, `panel_scorer.py`,
  `job_panel_scoring.py`, `walk_forward/loader.py`,
  `tests/test_model_content_sha256_shared.py`) — verified via
  `git log --oneline -- <file>` on each, all five resolve to this same commit
  as their most recent touch. As of this doc's date, `renquant-pipeline`
  `origin/main` HEAD (`0b47bf57564006c8c63ace7a626cc37f1d54b196`, PR #175) sits
  strictly after this commit but does not modify any of these five files, so
  the described behavior is still current against `origin/main` at time of
  writing.
- **Orchestrator-run pin expectation**: `renquant-orchestrator`'s
  `pyproject.toml` currently pins `renquant-pipeline>=0.1.0` (an open range,
  not a strict lock — this repo's local dev/CI wiring runs against the sibling
  checkout via `PYTHONPATH` rather than an installed pinned package; see
  `pytest.ini_options.pythonpath` in `pyproject.toml`). There is no
  machine-checkable lock file pinning this specific commit today. An operator
  or reviewer wanting to confirm "does my checkout match what this spec
  describes" should check that their local `renquant-pipeline` checkout is at
  or after commit `0dfc070c` on the files listed above (`git log --oneline -1
  -- <file>` should show `0dfc070` unless a later commit has since touched it,
  in which case this spec is stale for that file and needs re-anchoring).

**Re-anchoring note**: this version boundary is a snapshot in time. If
`renquant-pipeline`'s pin (or sibling checkout) moves past a commit that
touches any of the five files above, the line-range references and described
dispatch behavior in this doc must be re-verified against the new commit
before being treated as current — do not assume this spec stays accurate
across a pipeline pin bump without re-checking.

## Current state (as-built, 2026-07-04)

Step-1 code has been implemented. The following table records the as-built state
of every component.

| Component | File | Status |
|-----------|------|--------|
| `fingerprint_dispatch` module | `kernel/panel_pipeline/fingerprint_dispatch.py` | Implemented (the ONE dispatch layer) |
| `PanelScorer.load` dual-stamp | `kernel/panel_pipeline/panel_scorer.py:150-166` | Implemented (calls `resolve_scorer_stamp_metadata`) |
| Daily fail-closed check | `kernel/panel_pipeline/job_panel_scoring.py:2217-2289` | Migrated to dispatch claims |
| WF fold scorer claim | `kernel/walk_forward/loader.py:414-443` | Migrated (`_scorer_claim_for_entry`) |
| WF fold fail-closed check | `kernel/walk_forward/loader.py:449-490` | Migrated to dispatch claims |
| WF loader init | `kernel/walk_forward/loader.py:206-229` | Accepts `accept_legacy_stamps` param |
| Is-identity test | `tests/test_model_content_sha256_shared.py` | Rewritten with v1 + legacy pins |
| Config key | strategy-104 `ranking.panel_scoring.fingerprint.accept_legacy_stamps: true` | Declared |

## 1. Files changed (sites 1-4, 9 from parent doc section 2a)

### 1a. `kernel/panel_pipeline/fingerprint_dispatch.py` (NEW, the dispatch layer)

This module is the ONE place the pipeline decides how a scorer/calibrator
identity pair is compared during the M6 migration window. Both fail-closed
binding checks route through it. Hash logic is IMPORTS ONLY from
`renquant_common.model_fingerprint` (the triple-impl lesson, parent doc
section 5 row 3).

Key exports consumed by the two fail-closed check sites:

| Export | Purpose |
|--------|---------|
| `IdentityClaim` | Dataclass: one side's declared scorer identity under exactly one schema (`v1` or `legacy`) |
| `build_claim()` | Classifies a schema_version + v1_value + legacy_values into a single-schema claim |
| `match_claims()` | Compares an identity pair within ONE schema; returns `MatchVerdict` (matched, route, reason) |
| `accept_legacy_stamps()` | Reads the config flag (section 2 below); default `True` during the window |
| `log_verify_telemetry()` | The step-1 divergence-telemetry line (one per verify); step-3 census criterion (e) counts legacy-route acceptances from these lines |
| `resolve_scorer_stamp_metadata()` | Stamps both identities into in-memory scorer metadata + telemetry (section 4 below) |
| `scorer_claim_from_payload()` | Identity claim for a scorer read from disk (WF), replacing the bare-name recompute |
| `normalize_fingerprint()` | Legacy route: strip `sha256:` prefix + lowercase |
| `fingerprints_match()` | Legacy route only: exact OR 12-char-prefix match |
| `any_fingerprints_match()` | Legacy route only: cross-product match over lists |

Internal helpers (not exported):

| Helper | Purpose |
|--------|---------|
| `_v1_digests_equal()` | v1 route: exact full-digest equality, never a prefix match |
| `_legacy_recompute_from_path()` | Legacy (0.8.1) content recompute via the deprecated shim; telemetry + unstamped-fallback only |
| `_v1_recompute()` | v1 recompute via `model_content_sha256()`; returns `(digest, error)` |

Imports from `renquant_common.model_fingerprint` (pinned by `test_dispatch_module_uses_the_shared_objects`):

```
FINGERPRINT_SCHEMA_VERSION, FingerprintError, MismatchError,
UnclassifiedKeyError, VersionGapError, artifact_sha256,
model_content_sha256, model_content_sha256_from_path, stamp, verify
```

### 1b. `kernel/panel_pipeline/panel_scorer.py` (MODIFIED -- site 1)

**What changed.** After `stamp_artifact_metadata` (the 0.8.1 shim) computes
the legacy in-memory identity at line 150, a new call at line 161-166 invokes
`fingerprint_dispatch.resolve_scorer_stamp_metadata()` to stamp BOTH
identities (legacy + v1) into the in-memory metadata and log the divergence-
telemetry line.

**Import surface.** The v1 API (`stamp`, `verify`, `FINGERPRINT_SCHEMA_VERSION`)
is re-exported alongside the legacy shims (`stamp_artifact_metadata`,
`model_content_sha256_from_path`, `_MUTABLE_ARTIFACT_KEYS`,
`_PREDICTIVE_CONTENT_HINTS`) -- this module is the pipeline's single import
surface. The is-identity test (`test_v1_api_reexports_are_the_shared_objects`)
pins that these are the same objects as `renquant_common.model_fingerprint`,
not re-implementations.

### 1c. `kernel/panel_pipeline/job_panel_scoring.py` (MODIFIED -- site 2)

**What changed.** `_assert_calibrator_matches_scorer` (the strict daily buy
path, the 2026-05-27/06-22/07-01 incident site) was migrated from the
heterogeneous list-OR matcher to the version-dispatched claim comparison.

The function now:
1. Builds a scorer `IdentityClaim` via `build_claim()` from the active
   scorer metadata: `fingerprint_schema_version` (if present) selects v1
   route, otherwise legacy route with multi-key identity values.
2. Builds a calibrator `IdentityClaim` via `build_claim()` from calibrator
   metadata: `scorer_fingerprint_schema_version` (if present) selects v1.
3. Reads the flag via `accept_legacy_stamps(ctx.config)`.
4. Calls `match_claims(scorer, calibrator, accept_legacy=...)` which
   dispatches within one schema only.
5. Logs telemetry via `log_verify_telemetry()`.
6. Raises `ValueError` on `verdict.matched == False` (fail-closed), with
   the dispatch route and reason in the error message.

**Helper.** `_fingerprint_values()` (line 2186) collects legacy multi-key
identity values from metadata -- the same eight key names as the pre-dispatch
behavior. This feeds the `legacy_values` parameter of `build_claim()`.

### 1d. `kernel/walk_forward/loader.py` (MODIFIED -- sites 3 and 4)

**Site 3 (fold scorer identity, formerly line 158).** The bare
`model_content_sha256` recompute (which silently followed the venv's
renquant-common version -- the #160 problem) was replaced by
`_scorer_claim_for_entry()` (line 414), which dispatches on the fold
artifact's OWN stamp:

- **v1-stamped fold:** `scorer_claim_from_payload()` calls `verify()` against
  the payload (fail-closed: `MismatchError`/`VersionGapError`/
  `UnclassifiedKeyError` are `ValueError` subclasses); the ONE acceptable
  value is the declared stamp. No recompute needed -- verify proves the stamp
  is faithful.
- **Versionless (legacy) fold:** stamped identity keys + the explicit LEGACY
  shim recompute + the whole-file hash. The venv-coupled bare recompute is
  replaced by the explicit legacy shim, so semantics no longer silently change
  when renquant-common versions change.
- **Unstamped fold (dev/test state only; production is census-enforced post
  step-0):** BOTH recomputes (legacy shim + v1) + stamped identity keys + file
  hash. Dies at flag-off.

**Site 4 (fold fail-closed check).** `_assert_calibrator_matches_entry()`
(line 449) was migrated to the same dispatch pattern as site 2:
`_scorer_claim_for_entry()` + `_calibrator_claim()` + `match_claims()` +
`log_verify_telemetry()`.

**Constructor.** `WalkForwardModelLoader.__init__` accepts an
`accept_legacy_stamps` parameter (default: resolved from config via
`accept_legacy_stamps(None)` which returns `True`). Callers with a config
dict should pass the resolved value.

### 1e. `tests/test_model_content_sha256_shared.py` (REWRITTEN -- site 9)

**What changed.** The test file was rewritten from is-identity pins on the
four SHIM names to:

| Test | What it pins |
|------|-------------|
| `test_v1_api_reexports_are_the_shared_objects` | `panel_scorer.model_content_sha256 is shared.model_content_sha256` (and `stamp`, `verify`, `artifact_sha256`, `FINGERPRINT_SCHEMA_VERSION`) |
| `test_dispatch_module_uses_the_shared_objects` | `fingerprint_dispatch.model_content_sha256 is shared.model_content_sha256` (and all v1 API + legacy shim + all error classes) |
| `test_legacy_shim_reexports_are_the_shared_objects` | `panel_scorer.stamp_artifact_metadata is shared.stamp_artifact_metadata` (+ `model_content_sha256_from_path`, `_MUTABLE_ARTIFACT_KEYS`, `_PREDICTIVE_CONTENT_HINTS`) -- REMOVE at step 5 |
| `test_pipeline_entry_point_matches_shared_function_on_fixture_payload` | `panel_scorer.model_content_sha256(payload) == shared.model_content_sha256(payload)` |
| `test_frozen_v1_vector` | Frozen v1 test-vector: `sha256:0f6dc00a...` for the reference payload |
| `test_frozen_legacy_vector_survives_until_step5` | Frozen legacy test-vector: `sha256:a64b2824...` via the deprecated shim (writes to tmp, catches `DeprecationWarning`) |
| `test_the_two_schemas_are_pinned_to_differ` | v1 != legacy on the same payload (an accidental re-unification = semantics silently moved) |

## 2. Config key contract

**Key:** `ranking.panel_scoring.fingerprint.accept_legacy_stamps`

**Location:** `renquant-strategy-104/configs/strategy_config.json`, nested
under the existing `ranking.panel_scoring` section.

**Current value:** `true` (declared 2026-07-03; the reader's default is also
`true`, so merging this changed no behavior -- it declares the migration
window in policy).

**Semantics:**

| Value | Behavior |
|-------|----------|
| `true` (or absent/malformed ancestor) | Migration window: both v1 and legacy verification routes exist. Each artifact is verified under the ONE schema its stamp declares. |
| `false` | Post-flip strictness (step 4): only v1-stamped identity pairs verify. A versionless stamp fails closed with the "re-stamp under v1" remedy (`VersionGapError` semantics). |

**Resolution path in code:**
`fingerprint_dispatch.accept_legacy_stamps(config)` walks
`config["ranking"]["panel_scoring"]["fingerprint"]["accept_legacy_stamps"]`,
returning the default (`True`) at any missing or non-Mapping ancestor.

**Consumers:**
1. `job_panel_scoring.py:_assert_calibrator_matches_scorer` -- reads via
   `_accept_legacy_stamps(getattr(ctx, "config", None))`.
2. `walk_forward/loader.py:WalkForwardModelLoader.__init__` -- resolved
   at construction time (callers pass the value or `None` for default).

**Step-4 flip:** a strategy-104 config PR sets the value to `false`. Rollback
is a config revert (one PR; artifacts still carry both stamps). The flip is
GATED on the step-3 census green window (parent doc section 3 step 4).

## 3. Version-dispatched verification logic

The two fail-closed checks (`_assert_calibrator_matches_scorer` in
`job_panel_scoring.py` and `_assert_calibrator_matches_entry` in
`walk_forward/loader.py`) both route through `fingerprint_dispatch.match_claims()`.

### 3a. Claim construction

Each side's identity is classified into exactly one schema by `build_claim()`:

```
schema_version is None        -> SCHEMA_LEGACY claim
                                 values = all legacy identity strings
schema_version == 1           -> SCHEMA_V1 claim
                                 values = (the ONE v1 digest,)
schema_version == <other int> -> ValueError (version-gap remedy)
schema_version is bool/str/.. -> ValueError (never coerced)
```

For the **scorer** side:
- `job_panel_scoring.py` reads `meta["fingerprint_schema_version"]` and
  `meta["model_content_fingerprint"]` from the active scorer metadata
  (populated by `PanelScorer.load` -> `resolve_scorer_stamp_metadata`).
  Legacy values come from `_fingerprint_values(meta)`.
- `walk_forward/loader.py` reads the fold artifact's payload directly via
  `scorer_claim_from_payload()`, which dispatches on
  `payload["fingerprint_schema_version"]` and calls `verify()` for v1-stamped
  artifacts (fail-closed).

For the **calibrator** side:
- Both sites read `metadata["scorer_fingerprint_schema_version"]` and
  `metadata["scorer_model_content_fingerprint"]` from the calibrator object.
  Legacy values come from the multi-key list
  (`scorer_model_content_fingerprint`, `scorer_artifact_fingerprint`,
  `scorer_artifact_sha256`).

### 3b. Dispatch rules (match_claims)

```
accept_legacy=false AND either side is not SCHEMA_V1:
    -> MatchVerdict(matched=False, route="version-gap", ...)

scorer.schema != calibrator.schema:
    -> MatchVerdict(matched=False, route="cross-schema", ...)
    (A v1 mismatch can never hide behind a passing legacy hash)

both SCHEMA_V1:
    -> exact full-digest equality (no prefix, no multi-key list)
    -> MatchVerdict(route="v1", ...)

both SCHEMA_LEGACY:
    -> any_fingerprints_match (cross-product, 12-char-prefix acceptance)
    -> MatchVerdict(route="legacy", ...)
```

### 3c. Four dispatch cases (fixture coverage)

The test suite (existing + needed) must cover all four outcomes:

| Case | Scorer stamp | Calibrator declaration | Flag | Expected |
|------|-------------|----------------------|------|----------|
| v1/v1 match | v1 (schema_version=1) | v1 (scorer_schema_version=1) | any | `matched=True, route="v1"` |
| legacy/legacy match | versionless | versionless | `true` | `matched=True, route="legacy"` |
| cross-schema never-match | v1 | versionless (or vice versa) | `true` | `matched=False, route="cross-schema"` |
| flag-off VersionGapError | versionless | versionless | `false` | `matched=False, route="version-gap"` |

Additional edge cases pinned:

| Case | Expected |
|------|----------|
| v1/v1 mismatch (different digests) | `matched=False, route="v1"` |
| legacy/legacy no overlap | `matched=False, route="legacy"` |
| v1 stamp fails `verify()` (corrupt) | `ValueError` (MismatchError) at claim construction, before match |
| Future schema version (e.g. 2) | `ValueError` at claim construction |
| Bool/string schema version | `ValueError` at claim construction |
| Empty values (missing fingerprint) | `ValueError` at the caller (missing identity = fail-closed) |

## 4. PanelScorer.load dual-stamp resolution

`PanelScorer.load` (for XGBoost artifacts) performs two fingerprint operations
in sequence:

### 4a. Legacy stamp (line 150)

```python
meta = stamp_artifact_metadata(
    {k: v for k, v in payload.items() if k != "booster_raw_json"},
    path,
    payload=payload,
)
```

`stamp_artifact_metadata` is the 0.8.1 shim imported from
`renquant_common.model_fingerprint`. It computes the legacy identity:
- If the artifact carries a stamped `model_content_fingerprint`, it preserves
  it via `setdefault` (stamped-value precedence).
- If unstamped, it recomputes under 0.8.1 semantics and stamps.

### 4b. Dual-stamp enrichment (lines 161-166)

```python
from renquant_pipeline.kernel.panel_pipeline.fingerprint_dispatch import (
    resolve_scorer_stamp_metadata,
)
meta = resolve_scorer_stamp_metadata(
    meta, payload, path, context="PanelScorer.load",
)
```

`resolve_scorer_stamp_metadata` performs:

1. **v1 stamp verification (v1-stamped artifacts only).** If
   `payload["fingerprint_schema_version"]` is present, calls `verify()`
   against the payload -- fail-closed (`MismatchError`/`VersionGapError`/
   `UnclassifiedKeyError` are `ValueError` subclasses). A v1-stamped artifact
   whose content does not reproduce its own stamp is corrupt.

2. **v1 recompute.** Calls `model_content_sha256(payload)` (the v1 hasher).
   On success: stores the digest under
   `meta["model_content_fingerprint_v1_recompute"]` (telemetry-only key,
   never read by any verifier). On `FingerprintError`: stores the error
   detail under `meta["model_content_fingerprint_v1_recompute_error"]`.

3. **Legacy recompute.** Calls `model_content_sha256_from_path(path)` (the
   0.8.1 shim, `DeprecationWarning` silenced). Stores the digest under
   `meta["model_content_fingerprint_legacy_recompute"]` (telemetry-only).

4. **Divergence-telemetry log line.** Logs one structured line per load with:
   `context`, `artifact`, `stamped_schema` (v1/legacy/unstamped),
   `stamped_value`, `legacy_recompute`, `v1_recompute`,
   `stamp_eq_legacy`, `stamp_eq_v1`, and any v1 error.

The telemetry keys (`META_V1_RECOMPUTE`, `META_LEGACY_RECOMPUTE`,
`META_V1_RECOMPUTE_ERROR`) are distinct from every key `_fingerprint_values()`
collects, so the v1 recompute can never leak into a legacy-route identity list.

## 5. Test fixtures needed

### 5a. Existing coverage (test_model_content_sha256_shared.py)

Seven tests are already implemented (section 1e table). These pin:
- Is-identity of all imports (v1 API, dispatch module, legacy shims)
- Frozen test-vectors for both schemas on the same reference payload
- The two schemas are pinned to differ

### 5b. Dispatch unit tests (fingerprint_dispatch)

Tests for `build_claim`, `match_claims`, `accept_legacy_stamps`,
`resolve_scorer_stamp_metadata`, and `scorer_claim_from_payload` should
cover:

| Fixture | What it proves |
|---------|---------------|
| `build_claim` with `schema_version=None` | Returns `SCHEMA_LEGACY` claim with all legacy values |
| `build_claim` with `schema_version=1` + v1_value | Returns `SCHEMA_V1` claim with exactly one value |
| `build_claim` with `schema_version=1` + no v1_value | Raises `ValueError` (malformed stamp) |
| `build_claim` with `schema_version=2` | Raises `ValueError` (version gap) |
| `build_claim` with `schema_version=True` | Raises `ValueError` (bool is not int for this purpose) |
| `match_claims` v1/v1 match | `MatchVerdict(matched=True, route="v1")` |
| `match_claims` v1/v1 mismatch | `MatchVerdict(matched=False, route="v1")` |
| `match_claims` legacy/legacy match | `MatchVerdict(matched=True, route="legacy")` |
| `match_claims` legacy/legacy no overlap | `MatchVerdict(matched=False, route="legacy")` |
| `match_claims` cross-schema | `MatchVerdict(matched=False, route="cross-schema")` |
| `match_claims` flag-off + versionless | `MatchVerdict(matched=False, route="version-gap")` |
| `match_claims` flag-off + both v1 | Still matches normally (flag only blocks legacy) |
| `accept_legacy_stamps` with nested config | Returns the value at the nested path |
| `accept_legacy_stamps` with `None`/missing | Returns `True` (default) |
| `resolve_scorer_stamp_metadata` on unstamped payload | Stamps both recomputes as telemetry keys |
| `resolve_scorer_stamp_metadata` on v1-stamped payload | Verifies stamp (pass) + stamps telemetry |
| `resolve_scorer_stamp_metadata` on v1-stamped corrupt payload | Raises `MismatchError` |
| `scorer_claim_from_payload` v1-stamped | `IdentityClaim(schema="v1", values=(stamp,))` |
| `scorer_claim_from_payload` legacy-stamped | `IdentityClaim(schema="legacy", values=(...))` with legacy shim recompute |
| `scorer_claim_from_payload` unstamped | `IdentityClaim(schema="legacy", values=(...))` with both recomputes |

### 5c. Integration test: end-to-end daily path

A test that constructs a v1-stamped scorer artifact and a v1-declared
calibrator, loads the scorer via `PanelScorer.load`, and runs
`_assert_calibrator_matches_scorer` -- should pass on the v1 route with
zero legacy-route acceptances in telemetry.

A parallel test with legacy-stamped scorer + versionless calibrator
verifying on the legacy route (with `accept_legacy_stamps=true`).

### 5d. Integration test: WF loader path

A test that constructs a fold manifest + fold artifacts (v1-stamped and
legacy-stamped), constructs matching calibrators, and runs the WF loader's
`_assert_calibrator_matches_entry` through the dispatch. Should verify both
routes and cross-schema rejection.

### 5e. Step-5 removal checklist (for the test PR)

When step-5 lands (common 0.10 shim removal), the test PR must:
- Remove `test_legacy_shim_reexports_are_the_shared_objects`
- Remove `test_frozen_legacy_vector_survives_until_step5`
- Remove all legacy-route test fixtures (they test dead code post-0.10)
- Verify `test_the_two_schemas_are_pinned_to_differ` can be removed (only
  one schema exists post-0.10)

## 6. Integration checklist

### Step-1 (pipeline code -- DONE)

- [x] `fingerprint_dispatch.py` module: dispatch layer with `match_claims`,
      `build_claim`, `accept_legacy_stamps`, `resolve_scorer_stamp_metadata`,
      `scorer_claim_from_payload`
- [x] `panel_scorer.py`: `PanelScorer.load` calls `resolve_scorer_stamp_metadata`
      for dual-stamp enrichment after `stamp_artifact_metadata`
- [x] `job_panel_scoring.py`: `_assert_calibrator_matches_scorer` uses
      `build_claim` + `match_claims` dispatch (daily buy path)
- [x] `walk_forward/loader.py`: `_scorer_claim_for_entry` replaces bare-name
      recompute; `_assert_calibrator_matches_entry` uses dispatch claims
- [x] `walk_forward/loader.py`: `WalkForwardModelLoader.__init__` accepts
      `accept_legacy_stamps` parameter
- [x] `test_model_content_sha256_shared.py`: rewritten with v1 API is-identity
      pins + frozen test-vectors + schemas-differ pin
- [x] strategy-104 config: `ranking.panel_scoring.fingerprint.accept_legacy_stamps: true`
      declared

### Step-2 (v1 re-stamp run -- PENDING, gated on step-1 merged + deployed)

- [ ] Verify step-1 code merged AND pinned on the live machine (pin-align +
      venv `renquant-common >= 0.9.2`)
- [ ] Dry-run `restamp_model_content_fingerprint.py` over the FULL artifact
      inventory (any `UnclassifiedKeyError` aborts into a common-table PR)
- [ ] Write run: v1 re-stamp all scorer artifacts (prod + shadow + WF folds)
- [ ] Write run: re-declare all calibrator scorer identities to v1
- [ ] Re-run `stamp_walkforward_fingerprints.py` on affected manifests
- [ ] Verify census green (all v1 stamps present, recomputes match)

### Step-3 (observation window -- PENDING, gated on step-2)

- [ ] Census runs in the daily run bundle during the window
- [ ] Telemetry shows ZERO legacy-route acceptances over the window
- [ ] Window minimum: 7 consecutive daily-full runs + 1 weekly calibrator
      refit + 1 `weekly_wf_promote` cycle (every section 2a site exercised)
- [ ] Any manual re-stamp during the window restarts it

### Step-4 (flag flip -- PENDING, gated on step-3 green)

- [ ] Strategy-104 config PR: `accept_legacy_stamps: false`
- [ ] Verify: a versionless stamp now fails closed with the re-stamp remedy
- [ ] Rollback plan: flip the flag back (one config PR)

### Step-5 (shim removal -- PENDING, gated on ALL of step-4 criteria)

- [ ] Census green including zero-legacy telemetry window AFTER step 4
- [ ] Zero-legacy-callers grep clean across every repo main + umbrella tree
- [ ] renquant-common 0.10: remove the four shim names + `_legacy_*` engine
- [ ] Pipeline: bump common cap to `>=0.10`
- [ ] Pipeline: remove legacy-route test fixtures (section 5e)
- [ ] The #21 removal contract is discharged

## 7. Prerequisite: renquant-common 0.9.2

Step-1 code imports from `renquant_common.model_fingerprint` and assumes these
names exist. The 0.9.2 release (parent doc section 3 step 1 bullet 5) must
classify the migration stamp fields (`model_content_fingerprint_legacy_081`,
`restamp_provenance`) into `OPERATIONAL_KEYS` -- otherwise the first v1
`stamp()` of a step-2 dual-stamped artifact raises `UnclassifiedKeyError` on
the very fields the migration added. Table change requires model-repo review
per the stage-1 ownership contract.

## Safety

- Hash logic is IMPORTS ONLY from `renquant_common.model_fingerprint` -- no
  re-implementation in the pipeline. The is-identity test
  (`test_dispatch_module_uses_the_shared_objects`) pins this structurally.
- The dispatch module never raises on a plain mismatch -- callers own their
  fail-closed `ValueError` messages. The dispatch provides the route + reason
  for those messages and for telemetry.
- Telemetry-only keys (`META_V1_RECOMPUTE`, `META_LEGACY_RECOMPUTE`) are
  distinct from every key `_fingerprint_values()` collects, so a v1 recompute
  can never leak into a legacy-route identity list.
- No production data paths are written by the pipeline code changes. All
  artifact mutation is in the umbrella re-stamp tool (step-0 and step-2),
  outside this spec's scope.
- The flag's default is `True` (the safe direction -- legacy-stamped
  population verifies unchanged). The `False` flip is a deliberate,
  reviewable strategy-config PR.
