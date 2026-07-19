# AC4 migration P1 — seal the serving pair as bundle generation 1

STATUS: delivered (CODE ONLY — the live cutover is operator-gated, see NEXT)

WHAT: adds `renquant_orchestrator.bundle_seal` — the first real publication
THROUGH the transactional bundle store (renquant-artifacts#25/#26/#27 +
renquant-pipeline#206), i.e. GOAL-5 AC4 migration phase **P1 ("seal")** of
RFC RenQuant#492 (`doc/design/2026-07-17-artifact-bundle-transactionality.md`)
and the P0-P3 census (`doc/design/2026-07-18-ac4-migration-census.md` §6).
The module:
- `seal_serving_pair(store, panel_path, calibrator_path, operator, ...)`
  reads the current serving pair VERBATIM and publishes it as **generation
  1** (genesis, `parent_bundle=null`) via the artifacts store's §2.3
  PREPARE/ACTIVATE writer protocol — validator-gated (the default store is
  `create_default_store`, wiring the pipeline `bundle_contract.validate_pair`
  into writer step 6), operation-log recorded (PREPARE fsync'd BEFORE the
  ACTIVE flip, ACTIVATE bound to it), ACTIVE flipped to gen 1;
- `RunBundleProvenance` records exactly `{bundle_id, manifest_digest,
  member_digests, generation}` (RFC §2.2 run-bundle binding) for run-bundle
  replay;
- `regenerate_flat_views(resolved, flat_dir)` regenerates the flat paths as
  READ-ONLY (mode 0444) views of the active bundle's members, byte-identical
  to each member, on the pointer flip (census §6: "views are read-only,
  regenerated on pointer flip") so every existing flat-path reader keeps
  working unchanged;
- `bindings` are a VERBATIM copy of the panel's stamped WF-gate/identity
  metadata (RFC §2.7 — pair-consistency only, EXPLICITLY NOT a
  buy-admissibility assertion); `authorization` is a non-restamp-class seal
  record (RFC §2.4) with the two source digests as `inputs`.
Also: a `python -m renquant_orchestrator.bundle_seal` CLI (operator-gated live
entry) and the M9 strategy snapshot regenerated (adds `bundle_seal`).

WHY/DIR: the 104 serving pair has been mutated by four independent per-FILE
writers whose rollbacks orphaned the calibrator↔scorer binding four times
(2026-05-27/06-22/07-01/07-14→16 → 94% cash on 07-16). P0 built the
AUTHORITATIVE pair-level store; P1 is the first publication through it. This
PR makes P1 EXECUTABLE without touching production: the store is invoked as a
writer (RFC §5 boundary — renquant-artifacts OWNS the store; the orchestrator
owns run-bundle provenance + the read-only local view materialization). The
flat pair stays authoritative on the live machine until the operator runs the
cutover.

EVIDENCE:
- artifact: `src/renquant_orchestrator/bundle_seal.py` +
  `tests/test_bundle_seal.py` (12 tests) + regenerated
  `data/strategy_snapshot.json` (adds `bundle_seal`).
- prod or exp: exp — SANDBOX stores only (tmp_path + injected stub pair
  validator + injected local-mount guard/clock); NO live prod store or live
  serving pair is initialized, read, or written by any test or by this PR.
- existing data: builds on the merged store library (renquant-artifacts
  `bundle_store`/`bundle_contract_binding`, `create_default_store`,
  `publish`/`resolve_active`/`rollback_to`) + pipeline `bundle_contract`
  (#206); verified against a fresh origin/main clone of every sibling.
- best-known?: yes — full orchestrator suite green (4186 passed, 3 skipped)
  against fresh origin/main siblings; the 12 P1 tests prove: first-publication
  end-to-end (PREPARE durable before flip via step-8 kill-injection; ACTIVATE
  bound; reader serves generation 1; provenance = {bundle_id, digest, member
  digests, generation}); flat view is 0444 + byte-identical to the bundle
  member; a reader holding a resolution across a flip keeps a consistent
  generation; break-glass rollback restores prior serving byte-for-byte with
  NO artifact surgery; the seal never mutates the source pair; a rejecting
  validator aborts before any flip/view (validator-gating is load-bearing);
  the genesis guard refuses a second seal; the CLI builds the store via
  `create_default_store`.
- scope: renquant-orchestrator only; the umbrella RFC/census are merged and
  referenced, not copied; no memory binding-constraint (LONG ledger) changes.

NEXT: operator-gated machine landing (the census P1 EXECUTION) — declare the
real store location (`deploy/bundle_store_location.json`), stand up the store
(`bundle_store_init`), run `bundle_seal` against the REAL store to flip ACTIVE
to gen 1, and record the run-bundle provenance in the daily run. Until that
cutover the flat pair remains authoritative. Then P2: migrate the W1 weekly
promote / W2 monthly refresh / W3 restamp / W4 manual writers onto the
publisher and start stamping `{bundle_id, ...}` into every daily run bundle.
