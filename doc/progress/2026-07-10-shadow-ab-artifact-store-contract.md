# 2026-07-10 — run-manifest artifact_store contract (shadow-ab precheck fix, r2)

## What happened

The D6-§2a two-arm experiment was armed today. A manual `launchctl kickstart`
preflight — run through the real launchd path precisely to catch this class
before the first counted session — aborted at precheck (exit=3, pair
invalidated):

```
precheck_failure: artifact unresolvable (fail-closed):
'../../artifacts/patchtst_shadow/pt07_strict_trainfit_embargo60_20260522/seed_44/hf_patchtst_all_seed44_model.pt'
tried ['<repo_root>/.subrepo_runtime/artifacts/...', '/Users/renhao/git/artifacts/...']
```

Prod configs author artifact refs as **umbrella-layout parent walks** (the
strategy dir two levels below the store). The manifest pins the strategy
checkout under `.subrepo_runtime/repos/`, where that walk resolves to nothing;
the resolver failed closed, as designed.

## r1 (rejected) and r2 (this PR)

r1 rebuilt the umbrella geometry with a symlink shim. Codex review: blocked —
the shim "restores the deprecated umbrella as a runtime artifact owner"; the
contract belongs at the **producer/manifest boundary**, and CI failed (the
script fixtures have no artifact store). Accepted in full; the shim is gone
(the wrapper is untouched by this PR).

r2 — the explicit contract, orchestrator-only, all additive/opt-in:

1. **Run manifest** may declare `artifact_store: {path}` — WHERE the store is,
   instead of any checkout reconstructing umbrella geometry. The §2a runner
   validates the schema at load, requires the directory to exist at precheck
   (fail-closed), and records it in the session bundle + sealed snapshot.
2. **`artifact_resolver`** gains store-addressed semantics: a relative ref
   whose first component after stripping LEADING `..` segments is `artifacts`
   resolves against the declared store FIRST (`source="artifact_store"`);
   interior `..` disqualifies (fail-safe); no store declared → byte-identical
   behaviour.
3. **Threading**: the runner passes `--artifact-store` into both arm steps;
   `native-live-context` uses it for consumption-side sha verification (same
   anchors as the precheck — the divergent-resolution incident class);
   `native-live-inference --hydrate-pipeline-context` uses it to
   **rewrite the in-memory config's panel model/calibrator refs to resolved
   absolute paths** before the kernel sees the config, because the pipeline's
   `LoadScorerTask` joins relative refs lexically against `_strategy_dir`
   (umbrella geometry again). Identity safety: the paired-world config sha is
   computed from RAW file bytes at precheck (unchanged); artifact identity is
   separately enforced via `model_content_sha256`; `artifact_path` is NOT in
   `renquant_common.config_consistency._model_relevant_fields`, so P-CONFIG-FP
   is unaffected `[VERIFIED against renquant-common source]`.

## Evidence

- 13 new tests (resolver store contract ×9, runner manifest/threading ×5
  incl. pinned-checkout integration with NO umbrella geometry, hydration
  rewrite ×2); affected suites: my branch passes everything main passes plus
  the new tests — the 16 failures in the local sandbox are identical on
  pristine origin/main (missing sibling `renquant_artifacts` on PYTHONPATH)
  `[VERIFIED by stash/rerun control]`.

## Landing (after merge, operator-granted steps)

1. Orchestrator pin bump (promote_pin dry-run → apply → verify).
2. Add to `/Users/renhao/renquant-shadow-ab/run_manifest.json`:
   `"artifact_store": {"repo": "renquant-artifacts", "path": "store"}` plus
   the renquant-artifacts pin at the #13 merge commit (superseding the r2
   free-path form — see the r3 section below). Blob identity remains
   sha-stamped per artifact; freeze drift VOIDs the pair. No freeze exists yet
   (`freeze_created: false`), so amending the manifest before the first valid
   session is protocol-clean.
3. `launchctl kickstart` re-preflight; a full valid pair (exit=0) is the
   acceptance evidence before the first counted session (2026-07-11 14:35 PT).

## r3 (Codex on r2: bind the store to a pinned owner)

r2's `artifact_store: {path}` was still an untyped directory that could point
back at the deprecated umbrella tree. r3 closes it:

- `artifact_store` must be `{"repo": <manifest repo name>, "path": <relative
  subdir>}`. A bare path, an unknown repo, an absolute subdir, or a `..`
  segment are all load-time contract errors.
- The store root resolves INSIDE the named repo's checkout only AFTER
  `verify_run_manifest` proves that checkout is at the pinned commit with a
  CLEAN tree — commit binding by construction (test: tampering with the store
  repo's tree aborts the session before either arm). The bundle records
  {repo, path, root, commit}.
- The blobs got a pinned subrepo owner: renquant-artifacts PR #13 adds
  `store/` with fingerprint-verified byte-copies (model + sidecars +
  calibrator; the calibrator's only committed home had been the umbrella
  strategy dir — audit T1 divergence made visible). Landing pins that commit
  in the experiment manifest: `artifact_store: {"repo": "renquant-artifacts",
  "path": "store"}`.
