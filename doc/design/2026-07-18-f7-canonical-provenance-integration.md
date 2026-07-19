# Design: wiring F-7 canonical run-intent provenance into production (governed)

Task ref: #55 (was "G3/F-7 provenance publisher contract redesign", parked;
UNPARKED by artifacts#29 landing the registry side). Date: 2026-07-18.
Status: RFC — design review required before ANY implementation.
Owner: drafted personally per design-review policy.

## 1. The gap this closes

The F-7 canonical-provenance **registry** is fully built and merged in
`renquant-artifacts` (canonical_registry.py + validation.py, artifacts#29,
squash 0b67302f) but is **entirely UNWIRED in production** — verified across
all repos on `main`:

- **No producer** calls `write_canonical_run_intent` /
  `register_canonical_publication` anywhere (grep: 0 call sites in any repo).
- **No validator** calls `validate_artifact_manifest` /
  `ArtifactManifestContext` in the orchestrator or umbrella daily run (grep:
  0 call sites). The registry validation is a library capability nothing in
  production invokes.

That is the literal meaning of artifacts#29's "**fails closed until the
integration exists**": the prod canonical artifact (the 104 panel scorer +
its calibrator) is published today with NO verifiable run-intent provenance,
and the registry that would verify it has no caller. There is also **no
parent F-7 design doc** — canonical_registry.py references
`doc/design/2026-07-16-f7-canonical-provenance.md` but that file does not
exist on any repo's `main`; this RFC is the authoritative integration design.

**What #29 already gives us (the contract to build against):**
- `write_canonical_run_intent(...)` — atomic write of `run_intent.json`
  (producer, code-pins + config/data fingerprints, `producer` allow-listed),
- `verify_canonical_run_intent(path, ...)` — intrinsic + producer-allowlist
  verification,
- `build_canonical_provenance_reference(run_intent_path, artifact_digest)` —
  computes `run_intent_digest` from the actual bytes (never caller-supplied),
- `CanonicalPublicationSnapshot` + `verify_canonical_publication_snapshot(...)`
  — the pinned-registry trust anchor (exact HEAD + clean + origin remote +
  tracked `INDEX.json` + indexed-entry digest),
- `validate_artifact_manifest(manifest, *, canonical_publication_snapshot,
  require_provenance)` — the admission gate, which PRESERVES #30's
  `PROVENANCE_REQUIRED_AFTER` enforcement window.

## 2. Non-negotiable constraint: this is a fail-closed gate on the daily
canonical-training surface — it MUST be governed, never a flag-day

The surface being wired is the one GOAL-5 exists to protect and the site of
the 2026-07-16 book-drain incident class. artifacts#24 already demonstrated
the failure mode: an unconditional provenance requirement broke
backtesting/model/orch CI (fixed by #30's governed window). This integration
therefore adopts, as a HARD design rule, the same governed rollout #30/the
`ARTIFACT_DIGEST_REQUIRED_AFTER=2026-09-01` precedent use:

1. **Opt-in first.** The producer write and the admission validation ship
   behind `RQ_REQUIRE_CANONICAL_PROVENANCE` (default OFF). With it off,
   behaviour is byte-identical to today (no new gate).
2. **Then a dated enforcement window.** A `CANONICAL_PROVENANCE_REQUIRED_AFTER`
   date (proposed ≥ the artifacts `ARTIFACT_DIGEST_REQUIRED_AFTER` 2026-09-01,
   so the two F-7 windows close together, not staggered) after which absent
   provenance fails closed — with the pre-window tolerance emitting the same
   `_MISSING_PROVENANCE_WARNING` shape #30 established.
3. **Consumer suites in review (the #24 lesson).** The PR that introduces the
   admission gate MUST run the backtesting / model / orchestrator suites
   against the tightened contract and attach the results — never defer that
   to pin-advance.
4. **No flag-day.** At no point does merging or a default config make the gate
   mandatory without a window + opt-in escape.

## 3. Design

### 3.1 Producer (umbrella-owned)
The single reviewed entrypoint that PUBLISHES the prod canonical pair (the
WF-gate promote step that writes `artifacts/prod/panel-rank-calibration.json`
+ the scorer) calls, in one atomic sequence BEFORE the publish becomes
visible: `write_canonical_run_intent` (recording the code pins + config/data
fingerprints of THIS training run) → `register_canonical_publication`
(binding the run-intent digest to the artifact digest in the registry
`INDEX.json`). Implementation must pin the EXACT promote entrypoint (candidate:
the WF-gate promote in the weekly retrain chain) — named at build time, not
guessed here. The producer is the trust anchor precisely because its code is
reviewed and its evidence is re-verifiable against the environment.

### 3.2 Snapshot supply + admission gate (orchestrator-owned)
The daily-run artifact admission (the hydration path the AC4 census §3.4 maps:
`native_context_hydration` / `model_bundle` / `native_live_context` /
`intraday_session_inputs`) resolves `CanonicalPublicationSnapshot` from the
PINNED registry subrepo checkout and calls `validate_artifact_manifest(...,
canonical_publication_snapshot=snapshot, require_provenance=<window>)` before
admitting the prod canonical scorer. This is the currently-absent validator
call site; it is INTRODUCED here (behind §2's opt-in/window).

### 3.3 AC4 P2 coordination (the reason this is one design, not two)
AC4 P2 records **bundle-generation** provenance (`{bundle_id, manifest_digest,
generation}`) into run bundles at the SAME hydration surface. #55 records
**run-intent** provenance (which reviewed run produced the artifact). They must
not double-wire or contradict on that surface. RECOMMENDATION: #55's admission
gate lands AFTER AC4 P1's live seal cutover (bundle generations live), so the
run-intent reference binds to a bundle generation rather than a bare flat
path — one coherent provenance record, not two. This couples #55's sequencing
to the operator's AC4 P1-seal cutover decision (open question §5).

## 4. Phasing + the deployment gate
- **P-a** producer wiring (umbrella, opt-in OFF) — no behaviour change.
- **P-b** admission validation (orchestrator, opt-in OFF) — no behaviour change;
  consumer suites run in review.
- **P-c** flip `RQ_REQUIRE_CANONICAL_PROVENANCE` on in SHADOW / dated window.
- **P-d** artifacts pin advance past 0b67302f — OPERATOR-gated
  ([[artifacts-pin-gate-f7-canonical-snapshot]]): only after P-a/P-b land +
  consumer suites verified green, else the #24 flag-day break recurs.

## 5. Open question for the operator (sequencing, not a blocker to this RFC)
Should #55's admission gate (§3.2) be sequenced AFTER the AC4 P1-seal live
cutover (recommended — binds run-intent to a bundle generation, one coherent
record), or proceed independently on the flat pair now (faster, but re-wires
when AC4 P2 lands)? This RFC is draftable + reviewable either way; only the
implementation ordering depends on the answer.

## 6. Acceptance (for the eventual implementation, not this RFC)
- AC-1 producer: the prod-canonical promote entrypoint writes a verifiable
  run_intent + registers the publication; `verify_canonical_run_intent`
  passes on the real record; a tampered digest fails.
- AC-2 admission: `validate_artifact_manifest` with the pinned snapshot admits
  a well-formed prod canonical manifest and REJECTS a dirty/absent snapshot;
  with the window open + provenance absent it WARNS (not raises).
- AC-3 governance: opt-in OFF == byte-identical today; consumer suites
  (backtesting/model/orch) green in the gate-introducing PR.
- AC-4 no-flag-day: a test forces `CANONICAL_PROVENANCE_REQUIRED_AFTER` past
  and proves the window semantics; another proves pre-window tolerance.

## 7. Known open design gaps (adversarial self-review — resolve before impl)

These are named honestly rather than hand-waved; each must be closed in the
implementation-design round (not this RFC).

### 7.1 The producer may be a PAIR published by TWO jobs
artifacts#29 binds the canonical publication as the scorer + calibrator
**pair**. But the scorer (WF-gate promote, weekly) and the calibrator
(`monthly_calibrator_refresh`, monthly) are published on DIFFERENT cadences
by DIFFERENT entrypoints. So "one atomic sequence writes run_intent + registers
the publication" (§3.1) is not obviously realizable — there may be no single
pair-publishing entrypoint. RESOLUTION options: (a) route both through one
pair-publishing entrypoint (this is exactly AC4's pair-atomic bundle seal —
a THIRD AC4 coordination point, arguing #55 should ride AC4's bundle
generation as the pair unit); (b) a run-intent that spans the pair with a
two-phase register. Must be decided before producer impl.

### 7.2 The produce -> commit -> pin -> validate registry cycle
`register_canonical_publication` MUTATES the registry `INDEX.json`, but
`verify_canonical_publication_snapshot` requires a CLEAN, pinned checkout.
There is therefore a commit -> push -> subrepo-pin cycle between publication
and validation, and #29's own follow-up named the missing piece: a
"protected, review-gated publisher for registry commits." The hard sub-problem
is that an AUTOMATED daily producer cannot have a human review each registry
commit. RESOLUTION options: (a) the producer writes to a staging ref that a
review-gated bot promotes; (b) the registry INDEX is append-only +
content-addressed so any commit is trivially machine-verifiable and the
run-intent's re-verifiable evidence (code pins + fingerprints vs the actual
environment) IS the "review". RECOMMEND (b) — it matches #29's stated trust
model ("evidence re-verifiable against the environment", no per-run PR). This
publisher design is a prerequisite of the pin advance (§4 P-d).

### 7.3 AC4 coupling must not become a deadlock
§3.3/§5 recommend #55's gate land AFTER the AC4 P1-seal cutover — but that is
operator-gated and unscheduled; naive coupling stalls #55 on it. MITIGATION
(supersedes the §5 framing): build the #55 producer + admission (opt-in OFF)
INDEPENDENTLY now — they are byte-identical-to-today with the flag off — and
gate ONLY the enforcement-window flip (P-c) on AC4 so the provenance binds to
a bundle generation rather than a bare flat path. This decouples the
buildable, review-able work from the operator-gated sequencing, so neither
blocks the other. The operator's §5 answer then only affects WHEN P-c flips,
not whether P-a/P-b can proceed.
