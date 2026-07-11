# R-PIN Stage 1 — deployment-manifest schema + neutral state root + `deploy-pin capture`

Date: 2026-07-11
Design: `doc/design/2026-07-11-deployment-pin-authority-migration.md` (§5.1, §5.2, §7.1, §9 Stage 1)
Stage: 1 of 5 — additive, zero consumer change. The on-disk umbrella lock
remains the pin authority; the manifest is an unverified shadow record
consumed by nothing (§8 stage-1 row).

## What shipped

1. **`src/renquant_orchestrator/deployment_manifest.py`** — the shared
   manifest module:
   - Deployment-manifest **schema v1** loader/verifier: PORTABLE repo
     identity only (`remote/branch/commit/role/status`, unknown keys
     rejected — `local_path`/`test_command` mechanically cannot enter the
     authority document), monotonic `generation` (int ≥ 1),
     `artifact_store {repo, path}` (#464 binding), `deployment.verify`
     restricted to the code-owned profile ALLOWLIST (v1: exactly
     `readonly-e2e`, structured args validated per profile),
     `evidence_ref` in `store://` form (null only in the pre-seal
     `captured` state — see "one schema note" below), `supersedes_sha256`
     chaining (null only for generation 1). A mechanical portability sweep
     rejects any host-path string value anywhere in the document.
   - **Neutral state root (§5.2)**: `RENQUANT_DEPLOY_STATE_ROOT` (default
     `~/.renquant/deploy/`) with `deployment-manifest.json`,
     `runtime-inventory.json` (repo → checkout path, verified
     HEAD == manifest commit at read), FORWARD-ONLY
     `expected-generation.json` (atomic write; refuses any decrease and
     any same-generation content rewrite), `receipts/` layout.
   - **§7.1 predicate helpers** (pure, consumed by Stages 3-4):
     steady-state, normal record-first apply (predecessor exactness;
     generation-skip named), emergency lane (remote steady-state equality
     — forked-epoch refusal), plus `classify_generation` (less ⇒
     stale/replayed, greater ⇒ torn apply).
   - **Shared conventions lifted from `shadow_ab_runner`** (design §2.3,
     the fingerprint-triple lesson): the injectable git probe, the
     exists/HEAD/clean checkout-verification core, `artifact_store`
     schema validation, and resolve-and-contain store-root resolution now
     live HERE; `shadow_ab_runner` imports them back. Behavior-invariant:
     `tests/test_shadow_ab_runner.py` passes UNMODIFIED (identical checks,
     identical fail-closed message strings).

2. **`src/renquant_orchestrator/deploy_pin.py`** + `renquant-orchestrator
   deploy-pin capture`: reads the DEPLOYED truth — the on-disk lock AND
   the actual `.subrepo_runtime` clone HEADs — and FAILS CLOSED on any
   disagreement (all disagreements listed; a lock commit that is only a
   prefix of the clone HEAD is also a refusal). On agreement emits the
   portable manifest + host inventory to the state root. DRY-RUN by
   default; `--write` persists (manifest → inventory → forward-only epoch
   record, so a crash between writes is a detectable torn state) and
   re-verifies the written pair read-only. Re-capture advances the
   generation and chains `supersedes_sha256`; a torn state root
   (manifest/epoch-record mismatch) is refused, never extended.
   NO mirror, NO apply, NO authority semantics (Stages 3-4).

3. Tests: `tests/test_deployment_manifest.py` (schema good/malformed,
   generation rules, portability, inventory verification against real git
   fixtures, forward-only record incl. the greater-than torn case, §7.1
   predicates) and `tests/test_deploy_pin.py` (agreement, disagreement
   fail-closed on real git fixtures, dry-run-writes-nothing, write +
   re-verify, epoch advance, torn-root refusal, CLI dispatch).
   `data/strategy_snapshot.json` regenerated (new subcommand + modules).

## One schema note for review

§5.1 shows `deployment.state: "deployed"`. This implementation adds ONE
extra state, `captured`: a capture emitted before the verification
evidence is sealed into renquant-artifacts. `evidence_ref` may be null
ONLY in that state; a `deployed` record REQUIRES the sealed `store://`
reference, so the durable first-manifest commit (the follow-up PR) cannot
land unsealed. Alternative was a placeholder `store://` value, which would
have validated silently — rejected as a footgun.

## Stage-1 gate (from the design) and landing step

- Gate: capture output matches the on-disk lock AND clone HEADs exactly
  (the command itself fails closed otherwise, and `--write` re-verifies
  read-only, emitting the resolved map as PR evidence); `make test` green.
- Rollback: delete a file no one consumes yet.
- Landing (operator/main session, NOT this PR): run
  `renquant-orchestrator deploy-pin capture --write` on the host, then a
  follow-up PR commits the first manifest to
  `deploy/deployment-manifest.json` with `evidence_ref` sealed to
  renquant-artifacts (`store://`, the #13/#14 mechanism) — recording
  today's §2.2 deployed state durably for the first time.

## Verification

- New tests + full repo suite run against real git fixtures; suite result
  identical to the origin/main baseline modulo the pre-existing
  sandbox-environment failures (twin-parity sibling-layout checks and
  shadow-ab daily-script env tests, identical set on origin/main at
  `354d184e`).
- [VERIFIED 2026-07-11] the production lock and all 9 runtime clone HEADs
  currently AGREE (read-only inspection), so the landing capture is
  expected to pass its fail-closed gate as of today.
