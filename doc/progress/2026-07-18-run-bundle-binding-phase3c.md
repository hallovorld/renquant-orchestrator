# Run-bundle binding fields — phase 3 PR-C (GOAL-5 AC4)

Date: 2026-07-18
Spec: RFC "transactional artifact bundles for the 104 serving pair"
(RenQuant#492, `doc/design/2026-07-17-artifact-bundle-transactionality.md`
§2.2 run-bundle binding, §5 ownership: renquant-orchestrator "resolves
the registered bundle at run time and records `{bundle_id,
manifest_digest, member digests, pointer_generation}` in each run bundle
(the existing provenance surface)"). Companion phase-3 PRs:
renquant-artifacts PR-A (seam binding) and renquant-common PR-B (contract
fixture promotion).

## The provenance surface

The orchestrator's daily run-bundle persistence is
`src/renquant_orchestrator/daily.py::PersistDailyRunBundleTask` — it
assembles the canonical `run_bundle.json` (manifests, fingerprints,
decision trace, orders, stage trace) for every full run. That is where
the §2.2 binding block now lives.

## Delivered

- `src/renquant_orchestrator/serving_bundle_provenance.py` (new):
  `serving_bundle_provenance(resolved=None)` builds the run bundle's
  `serving_bundle` block:
  - `resolved=None` (the CURRENT reality — **no production bundle store
    is deployed**; migration is gated on the RFC §3 census, NOT on this
    phase) → the explicit marker `{"bundle_store": "not_deployed"}`. A
    stated fact, distinguishable forever from field-absence (runs
    predating this PR) and from a silently-lost resolution.
  - a resolved bundle (duck-typed against the renquant-artifacts
    `ResolvedBundle`/`PublishResult` shape; no store import) → all four
    §2.2 fields: `bundle_id`, `manifest_digest`, `member_digests`
    (per-member `{sha256, bytes}`), `pointer_generation`. Fail-closed:
    ANY missing/malformed piece raises `ValueError` — a half-recorded
    binding cannot honor the §2.2 replay guarantee, so it is never
    persisted. `generation=None` (a resolution that bypassed the ACTIVE
    pointer) is refused for the same reason.
- `daily.py`: `DailyRunContext` gains optional
  `resolved_serving_bundle: Any | None = None`;
  `PersistDailyRunBundleTask` records
  `bundle["serving_bundle"] = serving_bundle_provenance(...)`. With the
  default `None` this is a single additive key in `run_bundle.json` —
  **the daily run's behavior is UNCHANGED until the census-gated
  migration deploys a store and wires a real resolution in.**
- `data/strategy_snapshot.json` regenerated via the repo's own
  `scripts/generate_strategy_snapshot.py --update` (module census gained
  `serving_bundle_provenance`; the doc-alignment test enforces this).

## Verification

16 new tests (`tests/test_serving_bundle_provenance.py`; both paths at
both layers) + updated `tests/test_daily.py` (context field census, the
not-deployed marker in the canonical bundle-contents test). Full suite:
4039 passed, 3 skipped (baseline before this change: 4023 passed, 3
skipped on the same interpreter). [VERIFIED]

- helper: explicit marker for `None` (and for the no-arg call);
  resolved path records exactly the four fields, JSON-serializable;
  mapping-style and attribute-style member digests both accepted;
  10 fail-closed cases (missing/empty bundle_id, missing manifest/
  digest, empty member map, member missing sha256/bytes, generation
  None/str/bool).
- persistence: `PersistDailyRunBundleTask` writes the marker by default
  and the four fields when a resolved bundle is supplied.

## Interpretation recorded (reported, not improvised)

- §2.2 names the field `pointer_generation`; §5's summary says
  `generation`. This PR records the §2.2 normative name
  (`pointer_generation`) since §2.3's pointer format is what it binds to.
- Refusing `generation=None` (archive-lookup resolutions) for the DAILY
  binding is an interpretation of §2.2's "pointer_generation" being
  REQUIRED: a daily run always serves via ACTIVE, so a pointer-less
  resolution in the daily path indicates a wiring bug, not a valid state.

## Not in this PR

- Actually resolving a bundle in the daily job (needs a deployed store —
  RFC §3 census first) and supplying the GC `is_referenced` query from
  the run-bundle archive (that query becomes meaningful only once run
  bundles carry `bundle_id`s, i.e. after migration).
- Any change to production paths, schedules, or the live tree.
