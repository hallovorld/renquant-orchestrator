# 2026-07-20 — orch#558: preflight legacy flat views before a changed-content seal

Fixes the P0 orch#558 (F-7 / AC4 bundle-seal): `seal_serving_pair` with
`regenerate_views` could `store.publish` (PREPARE + ACTIVE flip) BEFORE
`regenerate_flat_views` discovered a legacy flat target with different bytes and
refused replacement — leaving ACTIVE pointing at the new bundle while fixed-path
readers retained the old flat pair (a split state; the orphaned-binding class).

## Fix
- New `_refuse_if_flat_pair_would_change(members, flat_dir)` mirrors
  `regenerate_flat_views`'s Phase-1 byte-identity check on the RAW member bytes.
- `seal_serving_pair` runs it BEFORE `store.publish` (when `regenerate_views`),
  so a changed-content seal raises with the store unmutated and the flat dir
  untouched — all-or-nothing across store state and the flat compat views.
- `regenerate_flat_views` keeps its own post-publish check as a final guard
  (defense in depth); behaviour is otherwise unchanged.

## Acceptance (orch#558 P1) — met
- Existing-different-pair seal raises BEFORE PREPARE/ACTIVATE/ACTIVE mutation
  (test asserts `store.read_operations()` has no PREPARE/ACTIVATE).
- Both legacy flat files remain byte-for-byte unchanged.
- Byte-identical genesis / no-op still seals.
- Missing flat directory also raises pre-publish (no PREPARE/ACTIVATE).
- SEAL-level regression tests added (not only a direct regeneration test).

## Scope (corrected per review — do NOT overclaim)
This completes **P1 SAFETY only**: a changed-content flat pair is now refused
*before* any store mutation, so no split state (ACTIVE=new bundle + old flat
pair) is ever published. **Changed-content activation remains BLOCKED** — a
seal whose members differ from the fixed-path flat pair still fails intentionally.
Any changed-content activation, artifacts pin advance, or F-7 cutover still
REQUIRES the P2/P3 pair-atomic generation-pointer publisher (deferred). This PR
does NOT unblock changed-content cutover; it makes the P1 genesis/no-op seal
all-or-nothing.

Tests: `test_bundle_seal.py` (3 new: changed-pair refusal, missing-dir refusal,
byte-identical no-op).
