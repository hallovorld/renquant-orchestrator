# 2026-07-11 — R-PIN Stage 1: the first durable deployment record

`deploy/deployment-manifest.json` = the output of `deploy-pin capture --write`
run on the production host at ~11:07 PT against the on-disk lock and the
materialized `.subrepo_runtime/repos` clone HEADs (all 9 agreed; fail-closed
capture passed on the first run — [VERIFIED] the Stage-1 gate). Generation 1,
state `captured` (the design's pre-seal state: evidence_ref is sealed by a
follow-up once the e2e evidence bundle lands in renquant-artifacts store/).

This closes the §2.2 gap from the merged R-PIN design: the deployed pin
state (including today's strategy-104 f01c0259 sleeve-shadow pin, base-data
1bdfeb6f, orchestrator fb3b69ff with the write-containment fix, artifacts
c71edf7f store) now has a reviewed, versioned record for the first time.
Every future pin change records here FIRST (record-first, §7).

## Update — evidence sealed, `state` flips to `deployed`, `deploy-pin verify` added

Codex posted CHANGES_REQUESTED: the record asserted host state while
`evidence_ref` and `artifact_store.path` were empty, with neither an exact
source-lock digest nor a materialized-runtime-inventory digest/capture
attestation sealed — "a list of commit hashes can be edited without proving
it was the lock and clone set observed on the production host at the
stated time." Also: CI was red on a known-flaky shadow-AB test (rerun
requested separately; green by the time this landed).

**Evidence bundle** — `renquant-artifacts#21` (`evidence/deploy-pin-verify-
seal-20260711`, open, pending review) seals, read-only against the real
production host in this sealing session:

- the source-lock identity digest, recomputed from a fresh read of the
  production `subrepos.lock.json` (plus its raw file sha256)
- the materialized-runtime-inventory identity digest, recomputed from live
  `git rev-parse HEAD` reads of all 9 `.subrepo_runtime` clones (plus the
  raw `runtime-inventory.json` sha256)
- proof all three digests — lock, inventory, and this manifest's own
  `repos` field — are **identical** [VERIFIED this session]
- capture-tool command/implementation-commit provenance, with an explicit,
  non-fabricated caveat: the deployed-orchestrator-pin commit (`fb3b69ff`)
  is NOT an ancestor of the commit that merged `deploy_pin.py` itself
  (`90a6e8bb`) — expected (an ad hoc tool run from a fresher local checkout
  against the still-older pinned lock), not glossed over
- the capture timestamp (`2026-07-11T17:42:15Z`) and the only recorded
  `readonly-e2e` verification output — no separate log file exists on the
  host, so none is fabricated

**Manifest rebuild** — `deploy/deployment-manifest.json` was rebuilt via
`build_deployment_manifest_payload` (not hand-edited), with the
originally-committed `repos`/`generation`/`deployed_by`/`deployed_at`/
`supersedes_sha256` passed through unchanged (byte-diffed to confirm no
drift beyond the intended fields):

| field | before | after |
|---|---|---|
| `deployment.verify.evidence_ref` | `null` | `store://experiments/deploy-pin-verify-seal-20260711/RUN-LOCK.json` |
| `deployment.state` | `captured` | `deployed` (the code's own logic: state flips once `evidence_ref` is non-null) |
| `artifact_store.path` | `""` | `"store"` — required for the ref to actually resolve (`STORE-MANIFEST.json` keys and every existing `store://` consumer are relative to `<repo>/store/`, confirmed against `renquant-artifacts`' own `store/README.md` + `test_no_large_artifacts.py`); the empty value was a latent gap Codex's review correctly flagged |
| `generated_at` | `2026-07-11T17:42:15Z` | rebuild timestamp — this is document-generation provenance, distinct from `deployment.deployed_at` (unchanged, still anchored at capture time) |

**`deploy-pin verify`** (new subcommand, `src/renquant_orchestrator/deploy_pin.py`):
loads + schema-validates a manifest, resolves `deployment.verify.evidence_ref`
to the sealed bundle via the sibling-checkout convention
(`runtime_paths.default_github_root` + the #464 `artifact_store`
resolve-and-contain binding), checks the bundle's content sha256 against
the store's own `STORE-MANIFEST.json` (tamper check), then cross-checks the
bundle's `lock_identity_digest`/`inventory_identity_digest` both equal
`repo_identity_digest(manifest["repos"])` recomputed from the manifest's
own recorded commits — FAILS CLOSED (`DeployPinError`, nonzero exit) on a
null `evidence_ref`, a missing/unresolvable bundle, a content-hash tamper,
or a digest mismatch. `repo_identity_digest` / `manifest_repo_identity_entries`
live in `deployment_manifest.py` (shared, not a third hand-copy).

Verified end-to-end against the real sealed bundle (read-only, via
`--github-root` pointed at an isolated scratch sibling root — the real
`.subrepo_runtime`/lock/`~/.renquant/deploy` paths were never re-touched):
`deploy-pin verify --manifest deploy/deployment-manifest.json` returns
`state: deployed` with all three digests matching; a deliberately
tampered manifest (rewritten `repos["renquant-model"].commit`) is
correctly rejected with `exit=1` and an "identity digest mismatch" message.

**Tests** (`tests/test_deploy_pin.py`): `test_verify_accepts_matching_evidence_bundle`,
`test_verify_rejects_lock_inventory_digest_mismatch`,
`test_verify_rejects_null_evidence_ref`,
`test_verify_rejects_missing_artifact_store_sibling`,
`test_verify_rejects_store_manifest_content_tamper` — all against synthetic
fixtures, never real host state. Full `deploy_pin`/`deployment_manifest`/
`shadow_ab_runner`/`repos` suites green (162 passed) plus a full-repo run
(3602 passed, 5 skipped, 16 failed — all pre-existing local-environment
failures unrelated to this diff: native-context/live-inference/price-
snapshot paths that depend on real production checkouts not present in
this sandbox; none touch `deploy_pin`/`deployment_manifest`; CI's `test`
job is green).
