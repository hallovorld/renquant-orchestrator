# G4 re-registration step 2 — canonical shadow job, immutable records, admission ledger, run-bundle fields

Date: 2026-07-18
Normative: model#61 v4 (`experiments/ensemble_phase0/DESIGN_AMENDMENT_v4_executable_next_open_evaluation.md`)
§2/§3/§5; step-1 contract `renquant_pipeline.decision_schedule` (pipeline#209,
merged) and the three step-2 requirements recorded in its approval review.

## What

v4 §5 step 2 — "the orchestrator's canonical job, immutable decision/fill
records, and run-bundle fields; prove duplicate/watermark/fill failure
behavior" — as machinery only. **SHADOW ONLY: no orders are placed anywhere**
(the declared order set is an intent record; zero broker imports, enforced by
test). **The job is NOT scheduled**: no launchd entry, no
`ops/launchd_manifest.json` change; scheduling/activation is a later governed
step and Phase 0 stays BLOCKED per the amendment.

1. `src/renquant_orchestrator/g4_shadow_job.py` — canonical job (write side):
   - `resolve_session_window(T)` — the orchestrator-owned calendar resolution
     the step-1 contract delegates to the caller: close(T)/open(T+1) from
     `renquant_common.market_calendar` into the contract's `SessionWindow`.
     Early-close aware (half days close 13:00 ET).
   - `equal_weight_scores` — the L1 arm's frozen equal-weight combination
     (v4 §3); fail-closed on universe mismatch / non-finite scores. No model
     internals: expert scores are inputs.
   - `build_arm_record` / `run_g4_shadow_session` — per-arm immutable v4 §2
     records: immutable `decision_session=T`; declared watermark COMPUTED from
     the manifested input snapshots; complete input/artifact/universe manifest
     (universe = required manifested input `"universe"`); frozen
     `calendar_id`/`price_source_id`; declared order set pinned to open(T+1);
     `job_id` minted via the contract's `job_identity` (never `hash_jsonable` —
     step-1 approval, observation 1); `decision_digest` recomputed over the
     FULL decision content so a divergent duplicate can never carry an
     identical digest (observation 2). Records validated against
     `validate_arm_record` with the byte-level watermark hook before the job
     returns; both arms must be exactly the frozen registered pair.
   - `G4EvidenceStore` — append-only, digest-named, write-once persistence
     (0o444, exclusive hard-link publish). Re-run with identical inputs =
     byte-identical = no-op admissible retry; a retry differing ONLY in the
     volatile `run_bundle_timestamp` keeps the first record and logs the
     attempt; any other overwrite raises `G4EvidenceIntegrityError` with the
     original bytes intact; divergent decisions land side-by-side under their
     own digest-names, never resolved by latest-commit.
2. `src/renquant_orchestrator/g4_admission.py` — session admission ledger
   (read side): `admit_g4_session(store, expected_session=...)` executes
   admission over the evidence dir via the step-1
   `validate_session_records` and records failure classification with
   `B_idio`/`B_shared` budget ATTRIBUTION (labels only — budget sizes,
   cumulative counting and the terminal NO-GO stay with the future pilot
   runner per v4 §2 r2). Ledger entries persist append-only
   (digest-named; identical verdicts collapse, changed verdicts side-by-side).
   Each entry carries an explicit `registration_bound` flag and a derived
   `series_eligible` (see the P0-1/P0-2/P1-4 revision below): `admissible`
   is step-2 machinery integrity only; `series_eligible` (False for every
   unregistered session) is what a future enrollment caller must consult.
3. Run-bundle fields: `DailyRunContext.g4_session_admission` (default `None`)
   + `run_bundle["g4_session"]` via `g4_session_bundle_block` — additive and
   absent-tolerant exactly like #547 (`serving_bundle`) and #549
   (`smalln_ledger`): the literal `"absent"` while the job is unscheduled,
   the verdict summary once a runner supplies an entry. Daily behavior
   otherwise unchanged.

## The three step-1 approval requirements

- **(a) documented-outage qualifier** (tightened per review P0-3, see the
  revision section below): a session the contract classifies `shared` charges
  `B_shared` ONLY when every failed arm's declared-failure record carries ≥1
  STRUCTURED `failure.outage_evidence` reference of the required shape
  `{kind, ref, observed_at}` — `kind` in the closed vocabulary
  `{venue_halt, calendar_anomaly, data_vendor_outage, infra_shared}`, `ref` a
  non-empty incident/task/URL string, `observed_at` ISO-8601 UTC; all three
  required — and NO reference anywhere in the session violates that shape.
  Otherwise the charge DEGRADES to `B_idio`: reason
  `shared_outage_evidence_malformed` on any shape violation (fail-closed —
  one bad reference poisons the whole charge),
  `shared_outage_undocumented` when an arm simply carries none. The
  contract's own classification is preserved in `pipeline_failure_class`.
  `build_failure_record` fail-fasts on malformed references at write time;
  admission independently re-validates whatever bytes are on disk.
- **(b) early-close adversarial test**: `resolve_session_window` tested on the
  2026-11-27 half day against a deterministic calendar AND the real NYSE
  calendar (13:00 ET close, next open Monday); end-to-end proof that a
  14:30 ET watermark — admissible on a normal day (control test) — fails
  closed on the early-close day at BOTH the job and the admission surface.
- **(c) expected-session parameter**: `admit_g4_session` requires
  `expected_session`; a session with no evidence at all is a detected,
  ledgered failure (`missing_session`, charged `B_idio`), and a record
  claiming a different session inside T's directory is a binding integrity
  failure.

## Interpretations recorded (reported, not improvised)

- **Universe manifest**: the step-1 record schema has no dedicated universe
  field; v4 §2's "complete input/artifact/universe manifest" is encoded by
  REQUIRING a manifested input named `"universe"`, so its digest is pinned in
  `input_manifest` and covered by the watermark recomputation.
- **Missing session → `B_idio`**: both arms silently absent is a job failure;
  per the contract's pinned semantics a symmetric ADMISSION failure is never a
  documented shared outage, and v4 §2 lists job crash/missing arm under
  `B_idio`.
- **`run_bundle_timestamp` is the only volatile field**: v4 §2 makes the
  timestamp evidence-only, so a wall-clock retry (identical decision + input
  digests) is admissible with first-write-wins; byte-identity of a true re-run
  is proven with an injected timestamp.
- **Fill records**: v4 §5 step 2 names "decision/fill records". The §3
  open(T+1) fill/price COLLECTION (marked value, cost components, cash
  reconciliation) needs the price-source plumbing and is NOT in this PR; fill
  FAILURE behavior is implemented per §2 as the declared-failure kinds
  (`fill`/`valuation` asymmetric → `B_idio`; `price_source` symmetric →
  shared, subject to (a)) and proven by test. Collection is the follow-up
  before v4 §5 step 4.

## Tests

`tests/test_g4_shadow_job.py` (34) + `tests/test_g4_admission.py` (37) +
`tests/test_daily.py` updates: duplicate/divergent retry (side-by-side, never
latest-commit), byte-identical re-run, timestamp-only retry, overwrite refusal
with bytes preserved (immutability), stale-digest/wrong-identity/non-shadow
refusal at write, late watermark (byte-level recompute mismatch + after-close),
unresolvable input digest fails closed, missing arm, missing session,
shared-with-documentation (`B_shared`) vs shared-without (degrades, `B_idio`),
one-armed documentation degrades, the full structured-evidence shape battery
(P0-3 revision: both directions, each missing field, unknown kind, empty ref,
non-ISO/non-UTC/naive `observed_at`, legacy plain string, poisoned mixed set,
non-list carrier, builder fail-fast), asymmetric crash/fill/valuation,
early-close day (fake + real NYSE calendar + normal-day control), session
binding mismatch, tampered-in-place record, unreadable evidence, ledger
append-only, run-bundle absent marker + real-entry forwarding through
`PersistDailyRunBundleTask`. `data/strategy_snapshot.json` regenerated via the
repo script (module census). Full suite green — counts in the PR body.

## Revision 2026-07-18 — review response (P0-3)

The 2026-07-18 CHANGES_REQUESTED review's P0-3 (adjudicated meritorious by
the independent verification comment) is fixed in this revision:
`outage_evidence` previously accepted ANY non-empty string, so a `B_shared`
charge was self-declarable (attach `"x"` to both arms and escape the
idiosyncratic integrity budget). Every reference is now the STRUCTURED shape
described under requirement (a) above, validated at BOTH surfaces:
`build_failure_record` (fail-fast caller error) and `admit_g4_session`
(fail-closed degrade to `B_idio` with reason
`shared_outage_evidence_malformed` on any violation, including the legacy
plain-string format). Tests cover both directions (well-formed structured →
`B_shared`; malformed → degrade) and each missing-field case (`kind`, `ref`,
`observed_at`), plus unknown kind, empty ref, non-ISO / non-UTC / naive
`observed_at`, legacy plain string, a malformed reference alongside a
well-formed one (poisons the charge), a non-list carrier, and the builder's
fail-fast. Shape validation is deliberately the extent of THIS PR — it does
not resolve or hash the referenced incident; see PP-1 below.

## Revision 2026-07-18 (r2) — review response (P0-1 / P0-2 / P1-4)

The standing review's P0-1 (frozen identifiers optional at admission),
P0-2 (calendar resolution not digest-bound into the record), and P1-4
(complete-input manifest not mechanically specified) share one root: they
ask for **pilot-registration** properties from **step-2 machinery**. On
the merits, per the merged normative sources, those properties do not
belong to this PR:

- **P0-1.** v4 §4's two-stage start freezes the registration-bound
  identifiers ONLY at the pilot-registration commit (§5 step 4), which is
  out of step-2 scope. The values to bind against **do not exist yet**.
  The step-1 contract (`decision_schedule.py:487-501`) checks the frozen
  `calendar_id`/`price_source_id` against `expected_*` ONLY when supplied,
  and pipeline#209's approving review explicitly ACCEPTED that optionality.
  Making the orchestrator strictly require them now would make it stricter
  than the merged contract it wraps and demand nonexistent values.
- **P0-2.** The frozen v1 record schema (`QUALIFYING_RECORD_FIELDS`)
  carries `calendar_id` + `orders_scheduled_for`, NOT a resolved
  close/next-open/calendar-digest; `SessionWindow` is a caller-resolved
  validation input, never persisted. pipeline#209's approving review
  accepted this caller-resolves seam (pinned semantics 5) and set step-2's
  only calendar obligation as an early-close adversarial test — delivered
  (2026-11-27, fake + real NYSE + normal-day control). Digest-binding the
  resolved window INTO the record + `decision_digest` is a **contract-level
  schema change to the merged pipeline#209 seam**, not an orchestrator
  patch — a legitimate follow-up (PP-3), not a step-2 defect.
- **P1-4.** The required-input set (beyond the mandatory `universe`)
  belongs to the pilot-registration frozen job spec (v4 §4 freezes
  universe + artifact IDs). Machinery requiring `universe` as the minimum
  matches §2's explicit "input/artifact/universe manifest" (PP-4).

**What DID change (the honest, minimal fix that fully answers the
review).** The review's operative concern is that `admit_g4_session`
returned an *admissible* verdict (`ok=True`) with unbound IDs — evidence a
later caller could misclassify without a code change. That is now closed
by an EXPLICIT unbound return (codex's own offered option (a)): every
ledger entry carries `registration_bound` (True iff both frozen IDs were
supplied) and a derived `series_eligible = ok and registration_bound`.
`admissible` is scoped in code + docstring to "records pass step-2
machinery integrity"; `series_eligible` — FALSE for every unregistered
(current) session — is the single boolean an enrollment caller must
consult. When the pilot runner DOES supply the frozen IDs, the contract
binds them in-record (`frozen_identifier_mismatch`) and `series_eligible`
follows `admissible`. Additive/absent-tolerant, no contract change, no
behavior change to any bound path; +4 tests (unbound integrity-only,
bound series-eligible, frozen-identifier-mismatch binds-but-fails,
missing-session carries the fields). This makes the machinery honestly
self-describe as NOT-yet-series-admissible rather than deferring the point
to prose alone.

## PRE-PILOT hardening requirements (named, pinned — NOT implemented here)

These MUST be resolved (implemented or explicitly waived by the operator)
BEFORE the pilot-registration commit that freezes budgets and admits real
evidence into any `B_idio`/`B_shared` counting. Sources: the 2026-07-18
independent adversarial verification (probes A2b/A7) and the standing
review's P0-3 residual.

- **PP-1: content-addressed / verified outage evidence.** P0-3's shape fix
  forces a claimant to commit to a checkable category, pointer, and time —
  but the referenced incident is still not resolved or hashed. Before pilot
  registration, outage evidence must be content-addressed through the store
  (`store_input` already exists for exactly this write path) or carry an
  operator-verified provenance digest, so a `B_shared` charge is backed by
  bytes, not a well-formed claim.
- **PP-2: keyless-local store trust boundary (probes A2b/A7).** The
  evidence store's integrity guarantees hold against accidental and
  programmatic corruption (the designed threat: every in-place tamper,
  overwrite, race, and stale-digest probe fails loudly), but NOT against a
  deliberate local adversary with unlink+rewrite capability on the evidence
  root: (A2b) forge record content, RECOMPUTE `decision_digest` over the
  forged content, rewrite the file — admission passes clean because the
  digest is self-certified by the same bytes it protects; (A7) flip ONLY
  `execution_mode` in place — it is outside `decision_digest_of` and
  enforced at write time, not re-checked at admission. Proposed direction
  (either suffices; decide at pilot registration): **(i)** HMAC the record
  digests with a key held OUTSIDE the evidence root (operator-held or
  run-bundle-side), so recomputing a digest requires the key an
  evidence-root adversary does not have; or **(ii)** a store-root ownership
  assertion (dedicated uid/read-only bind mount) that removes the
  unlink+rewrite capability from every non-runner principal. Cheap
  complements regardless of choice: admission cross-check of the file-name
  digest prefix against record content, re-check `execution_mode == shadow`
  at admission, and cross-check `attempts.jsonl` logged digests against the
  records present.
- **PP-3: digest-bound calendar resolution (review P0-2).** The resolved
  close(T)/open(T+1) window is currently a caller-resolved validation input
  (the pipeline#209-accepted seam), so a calendar revision could alter the
  historical window during re-admission (the original verdict is immutable
  and lands side-by-side, but reproducibility is not yet guaranteed).
  Before pilot registration, persist the resolved close/open (and calendar
  source/version) as an immutable, digest-bound object — either as an
  additional manifested input (the `universe` pattern, orchestrator-only,
  covered by watermark recomputation) or as a pipeline-contract v2 record
  field. The latter is a contract-level change and must go through the
  pipeline repo, not an orchestrator patch.
- **PP-4: required-input-set specification (review P1-4).** Beyond the
  mandatory `universe`, the full set of required input names/digests
  (score inputs, market/price snapshots) belongs to the pilot-registration
  frozen job spec; admission must reject a session missing any required
  snapshot or whose declared source identity differs. If all consumers
  need the schema it belongs in the shared pipeline contract, with the
  orchestrator enforcing it at runtime.

## Not in this PR

- Scheduling/activation of the job (launchd, manifest) — later governed step;
  Phase 0 remains BLOCKED (no pilot registration, no budgets frozen, no data
  collection authorized).
- Open(T+1) fill/price collection and the §3 executable return computation.
- Model-side backfill/PIT consumption (v4 §5 step 3) and the pinned umbrella
  integration run (step 4).
- The PRE-PILOT hardening requirements above (PP-1..PP-4) — named and
  pinned here, deliberately not implemented in a review-response revision.
