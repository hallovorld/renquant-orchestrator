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
seal-20260711`, **merged** as `26999f941b319178c5441c4816d666a9b5eda715`,
currently `renquant-artifacts` main HEAD) seals, read-only against the real
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

## Update — P0 follow-up: the checkout-identity gap (Codex, second round)

Codex's second-round comment (issue comment, not a formal review — posted
after the `state=deployed` push above landed) named a STRONGER provenance
gap than the byte-tamper check the first round asked for: the committed
manifest pins `renquant-artifacts` at `c71edf7f...`, but the sealed evidence
bundle was added LATER by `renquant-artifacts#21`. `deploy-pin verify`
resolved the evidence through whichever sibling checkout happened to be
currently on disk (via `runtime_paths.default_github_root` +
`STORE-MANIFEST.json`), not through any revision recorded in — or bound to
— the deployment record itself. A sibling checkout that has since advanced
past the sealed revision (main moving on) can still pass every existing
check: `STORE-MANIFEST.json`'s content-hash entry travels WITH the checkout
and stays internally consistent, so byte-tamper detection sees nothing
wrong, yet the command proves nothing about what the DEPLOYED pin actually
contained or could resolve at the time it was recorded. Codex asked for one
explicit model, either (A) advance the actual `renquant-artifacts` pin
through the normal record-first procedure and capture a new generation
whose PINNED commit contains the evidence, or (B) bind `evidence_ref` to an
immutable artifacts commit + content hash and reject any sibling checkout
whose HEAD differs from it.

**Chose (B).** Option (A) requires bumping the LIVE production
`renquant-artifacts` pin (`c71edf7f...` is the currently-deployed
production pin, mid an active live two-arm trading experiment) — a
live-tree/production-pin mutation outside this repo's scope to execute
without direct operator authorization, and unrelated to what this PR is
actually recording (this record documents deployed state; it does not
itself decide to move the artifacts pin). (B) is a pure code-and-schema
fix with zero live-tree side effects and directly closes the gap Codex
named: evidence is external audit material, not something that requires
the pin itself to advance.

**Schema** (`deployment_manifest.py`): new required field
`deployment.verify.evidence_repo_commit` — the exact 40-hex commit of the
`artifact_store` sibling checkout the sealed `evidence_ref` was resolved
from. The two fields travel together: `evidence_repo_commit` must be a
full-sha string whenever `evidence_ref` is sealed (non-null), and must be
null in the pre-seal `captured` state (whenever `evidence_ref` is null) —
one may never be present without the other. Deliberately NOT tied to
`repos["renquant-artifacts"].commit` (the pin): an evidence bundle sealed
by a PR that lands after the pinned commit is legitimate and must remain
schema-valid; the two fields are independent by design.

**Capture-side** (`deploy_pin.py`, `run_capture` /
`build_deployment_manifest_payload`): whenever `--evidence-ref` is
supplied, the capture now resolves the `artifact_store` sibling checkout's
ACTUAL current HEAD (`git rev-parse HEAD`, same
`runtime_paths.default_github_root` sibling-checkout convention `deploy-pin
verify` already used) and stamps it as `evidence_repo_commit` —
automatically derived, never a new user-facing flag (a user-suppliable
value would reopen exactly the "can be edited without proving it was
observed" hole this whole follow-up is about). Fails closed (nothing
written) if that sibling checkout is missing or unreadable — a capture
supplying `--evidence-ref` must never silently emit a null
`evidence_repo_commit`.

**Verify-side** (`deploy_pin.py`, `resolve_evidence_bundle_path`): BEFORE
reading or trusting anything from the resolved sibling checkout, its
ACTUAL current HEAD must equal `deployment.verify.evidence_repo_commit`
exactly, and the checkout must be CLEAN
(`deployment_manifest.check_checkout_state`, `require_clean=True` — a dirty
checkout risks an uncommitted local edit to the evidence bundle defeating
the `STORE-MANIFEST.json` tamper check too). Failing this raises
`DeployPinError` with a message naming both the actual checkout HEAD and
the declared `evidence_repo_commit`, and stating explicitly that a
checkout not at that exact revision "cannot prove the evidence was
resolved from the deployment-recorded revision, regardless of content-hash
agreement." The existing `STORE-MANIFEST.json` content-hash check still
runs afterward — it catches a DIFFERENT failure mode (a self-inconsistent
seal: the checkout's own committed hash entry not matching its own bundle
bytes), which checkout-identity alone cannot see.

**Real record updated**: `deploy/deployment-manifest.json` now carries
`deployment.verify.evidence_repo_commit =
"26999f941b319178c5441c4816d666a9b5eda715"` — `renquant-artifacts#21`'s
merge commit, which is also (verified this session, read-only, via a fresh
disposable `git clone` — the live production sibling checkout was never
touched) the exact current `renquant-artifacts` main HEAD. Rebuilt via
`build_deployment_manifest_payload` (not hand-edited); every other field is
byte-identical (diffed) apart from `generated_at` (rebuild-timestamp
provenance, same convention as the prior update). Re-ran `deploy-pin
verify --manifest deploy/deployment-manifest.json --github-root
<disposable clone>` against this real bundle: passes (`state: deployed`,
all three digests matching); confirmed the new checkout-identity check
actually fires by adding one empty commit to the disposable clone and
re-running — correctly rejected with `checkout-identity gap` before any
STORE-MANIFEST/digest check ran.

**Tests** (`tests/test_deploy_pin.py`, `tests/test_deployment_manifest.py`):
schema tests for the `evidence_ref`/`evidence_repo_commit` pairing
(required-together, full-sha shape, and the exact pre-#21-pin-vs-post-#21-
evidence case — schema-valid when they differ); a capture-side test
injecting a recording `git_probe` to prove `evidence_repo_commit` is
stamped from the real resolved sibling HEAD; a fail-closed capture test
when the sibling checkout can't be resolved; and on the verify side,
`test_verify_rejects_checkout_identity_mismatch` (the core regression test:
HEAD moved on, bundle bytes untouched — must reject) and
`test_verify_rejects_dirty_sibling_checkout` (`require_clean=True`). The
four existing verify fixtures were upgraded from plain directories to REAL
committed git checkouts (this file's stated philosophy: exercise real git
state, never mocks) so the new checkout-identity check has something
legitimate to pass against. Full `deploy_pin` + `deployment_manifest` suite
green (98 passed).
