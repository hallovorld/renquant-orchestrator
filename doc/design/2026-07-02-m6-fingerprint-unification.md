# M6/R2: content-fingerprint unification — the measured divergence and the shared contract

STATUS: design for review (docs only; implementation lands as renquant-common + per-repo
migration PRs after discussion). Task M6/R2 of the unified plan (#231 Term PROCESS).
DATE: 2026-07-02

## 1. The divergence, measured (not asserted)

Three recurring fail-closed no-trade incidents (05-27, 06-22, 07-01) trace to
`model_content_sha256` disagreeing across repos. Inventory (read-only, 2026-07-02):

| Site | Semantics | Mechanism |
|---|---|---|
| **pipeline** `kernel/panel_pipeline/panel_scorer.py:108` | **SUBTRACTIVE**: hash payload minus `_MUTABLE_ARTIFACT_KEYS` denylist (`metadata`, `wf_gate_metadata`, `artifact_path`, `artifact_sha256`, `artifact_fingerprint`, `model_content_fingerprint`, `config_fingerprint`, …) | any NEW key is hashed by default |
| **model** `renquant_model_gbdt/fit_calibrator_alpha158_fund.py:35` | **ADDITIVE**: hash an explicit ~12-field allowlist (`params`, `feature_cols`, `feature_means/stds`, `feature_norm_*`, `label_col`, …) | any NEW key is ignored by default |
| **umbrella** `scripts/fit_calibrator_alpha158_fund.py:32` | imports the PIPELINE impl (not a third copy — one prior belief corrected); `stamp_walkforward_fingerprints.py` to be classified in the implementation PR | — |

**Mismatch by construction**: an artifact stamped under the model repo's allowlist and
verified under the pipeline's denylist disagrees the moment ANY key exists outside both
lists — new predictive fields (allowlist silently ignores → false MATCH) and new
operational fields not yet in the denylist (denylist hashes them → false MISMATCH, the
observed incident class). Each incident was "fixed" by a manual re-stamp, which mutates the
artifact and re-arms the trap.

## 2. The shared contract (proposal)

One implementation in **renquant-common** (`renquant_common.model_fingerprint`), with
**TOTAL classification** — the design property both current impls lack:

1. Every payload key MUST be classified as exactly one of {PREDICTIVE, OPERATIONAL}.
   An **unclassified key fails LOUDLY at stamp time** (never a silent default in either
   direction — the silent defaults are the root cause). See §2a for the recursive
   (not top-level-only) version of this rule and §2b for the exact serialization it
   hashes over.
2. The hash covers the PREDICTIVE set; the classification tables ship IN the shared module
   and carry a `fingerprint_schema_version` stamped into the artifact next to the hash.
3. Verification checks hash AND schema version; a version gap is its own explicit error
   ("re-stamp under vN" — an auditable operation), never a bare mismatch.
4. Migration: a 4-stage rollout (§2c) — NOT a dual-accept OR-window. The two current
   implementations' silent defaults are exactly what let a stamp/verify mismatch go
   undetected for three incidents; an "accept either old or new hash" window reproduces
   that same failure mode one layer up (a new-contract mismatch can hide behind a passing
   old hash). Cross-repo fixtures assert identical hashes on identical payloads from all
   import sites (the test that has never existed) at every stage.

### 2a. Classification is recursive and artifact-family scoped

Top-level key classification is not sufficient: real artifacts nest predictive content
inside dict/list-valued fields (for example a top-level `metadata` or `metrics` key whose
*value* is itself a dict mixing real content with incidental bookkeeping). A classifier
that only inspects top-level keys would treat the whole nested value as one opaque
PREDICTIVE-or-OPERATIONAL blob and miss exactly the class of hidden field this redesign
exists to catch.

- The classifier walks the full artifact tree. Every **leaf** value (or an explicitly
  frozen, named sub-structure treated as an atomic PREDICTIVE/OPERATIONAL unit — e.g. a
  fixed-shape `feature_means` array is one classified unit, not N per-index leaves) is
  addressed by a **key-path**: dot-separated for dict keys, `[i]` for list indices (e.g.
  `params.learning_rate`, `feature_cols[3]`). The classification table is keyed by
  key-path, with a wildcard form for homogeneous list/dict contents
  (`feature_means[*]` classifies every element of that array identically) so the table
  doesn't have to enumerate every index of every run's array.
- **Artifact-family scoping**: an XGB/GBDT JSON artifact and an HF/PatchTST checkpoint do
  not share a field structure, so they get separate classification tables under one
  shared mechanism — `renquant_common.model_fingerprint.classify(payload, family=...)`.
  This mirrors the two-family split already landed this session in the PatchTST
  provenance-stamping fix (RenQuant#426): XGB stamps `recipe_id` into the JSON payload
  itself (content-hash-bound); HF/PatchTST stamps it into the `.pt` checkpoint's own
  persisted training contract at save time (whole-file-hash-bound), because the two
  artifact *shapes* require different binding mechanics. `model_fingerprint` reuses that
  same family split rather than inventing a third scheme.

### 2b. Frozen technical details

- **Canonical serialization**: sorted-key JSON (`json.dumps(payload, sort_keys=True,
  separators=(",", ":"))`) over the PREDICTIVE-classified subset of the tree, matching the
  sorted-key convention `stamp_walkforward_fingerprints.py:209` already uses for its own
  summary output and the fixed-precision approach RenQuant#430's
  `regen_oos_pick_table.py::canonical_table_content_hash()` established this session for
  the same reason (platform-stable float repr, not raw float64 bytes).
- **Numeric/NaN handling — corrected (r3 review)**: r2 specified rounding floats to 8
  significant digits before hashing. That is a real bug, not a refinement: two genuinely
  DIFFERENT model parameter values that happen to agree to 8 sig figs would silently
  COLLIDE under that rule — a false-MATCH manufactured by the fingerprinting mechanism
  itself, the mirror-image of the original false-MISMATCH bug this whole design exists to
  remove. Global lossy rounding is dropped entirely. Floats are hashed via an EXACT,
  cross-language-stable canonical representation instead: Python's `repr(float)` (since
  3.1, guaranteed to produce the shortest decimal string that round-trips to the exact
  same IEEE-754 double via `float(repr(x)) == x`) is the reference representation; any
  other language/runtime computing or verifying these hashes MUST implement the equivalent
  shortest-round-tripping-decimal algorithm (e.g. Grisu3/Ryu-class formatters — most
  modern languages' default float-to-string already satisfies this; the requirement is
  that whatever is used is documented and tested to round-trip exactly, not merely
  "close enough"). This is EXACT canonicalization, not quantization — two floats produced
  by different code paths (numpy vs. plain Python) still hash identically PROVIDED they
  are the exact same IEEE-754 value; if they differ in the last bit (a genuine numerical
  difference from different computation order), they correctly hash differently, which is
  the desired property for a content fingerprint. If a SPECIFIC field's modeling contract
  deliberately requires quantization (for example, a price field the model itself defines
  as cents-precision), that quantization is declared explicitly in that field's
  classification-table entry (a per-field `quantize` annotation, documented and reviewed
  as part of the modeling contract per the ownership split below) — never applied as a
  blanket rule to all predictive floats.
- **Non-finite values are rejected, not canonicalized (r3 review)**: r2 canonicalized
  `NaN`/`Infinity`/`-Infinity` to string literals so they could be included in a "stable"
  fingerprint. This is wrong: a predictive field containing a non-finite value almost
  always indicates an INVALID model state (a training failure, a numerical instability,
  a division-by-zero in a derived feature) — silently normalizing it into a hashable,
  stable representation blesses that invalid state as legitimate, reproducible content,
  exactly the kind of silent acceptance this redesign exists to remove elsewhere. Fixed:
  `classify()`/the stamping path REJECTS any artifact whose PREDICTIVE-classified subset
  contains a non-finite float (`NaN`, `Infinity`, `-Infinity`) — this is a hard error at
  stamp time (the artifact is never written), not a warning and not a canonicalization
  rule. `None` continues to serialize to JSON `null` as normal (a legitimate, finite
  "no value" state, unrelated to non-finite numerics).
- **Unknown-key behavior at stamp time**: a key-path with no classification-table entry
  (and no matching wildcard) is a **hard error** — `classify()` raises, the artifact is
  never written. This is the actual mechanism behind §2.1's "fails loudly at stamp time";
  it is not optional/warn-only.
- **Unknown-key behavior at verify time**: identical — a stamped artifact containing a
  key-path absent from the CURRENT classification table (e.g. the table was rolled back,
  or the artifact predates a table update) fails closed to NOT ACTIONABLE, the same
  fail-closed convention `RenQuant#426`'s `shadow_scoring.py::_compute_admission`
  established for missing/unrecognized recipe stamps. Never silently ignored, never
  silently treated as OPERATIONAL-by-default (the exact silent-default bug this design
  exists to remove).
- **Schema-version ownership**: the classification TABLES (which key-paths are
  PREDICTIVE vs OPERATIONAL, per artifact family) are a **modeling contract** — the model
  repo (`renquant-model` / `RenQuant/backtesting`) owns and reviews changes to them, since
  only that repo's authors know whether a new field is predictive. The fingerprinting
  MECHANISM (canonical serialization, recursion, hashing, schema-version stamping) is
  **shared infrastructure** — `renquant-common` owns it. A `fingerprint_schema_version`
  bump is required whenever a classification table changes; the mechanism module version
  and the table version are stamped and checked independently so a table-only change
  doesn't require a mechanism-code review and vice versa.

### 2c. Migration: staged, never OR-accepting

1. **Stage 1 — shadow.** Every stamp call dual-writes both the OLD hash (current
   subtractive/additive impl, whichever the call site already uses) and the NEW hash
   (shared `model_fingerprint`). Verifiers continue gating on the OLD hash only — no
   behavior change. The NEW hash's agreement/disagreement with what the OLD contract
   would have concluded is logged to telemetry on every verify call. This stage's only
   job is to surface every real-world disagreement without blocking anything.
2. **Stage 2 — classify.** Every disagreement stage 1 surfaces gets triaged by hand
   against real production artifacts: is it a genuine PREDICTIVE difference the old
   contract was silently missing (the actual bug class), or a field that's genuinely
   OPERATIONAL and the new table currently misclassifies it as PREDICTIVE? Fix the
   classification table for the latter; log the former as confirmed findings, each
   recorded as a frozen **promotion record** (schema below) — this record is what stage 3
   checks against, not an operator's unlogged say-so.

   **Promotion-record schema (frozen, r3 review)** — every accepted-expected divergence
   must be recorded as a structured entry, never an ad hoc "accounted for" comment:
   ```
   {
     "key_path": "<the exact key-path, e.g. params.early_stopping_patience>",
     "artifact_family": "<xgb | hf_patchtst | ...>",
     "classification_rationale": "<why this is OPERATIONAL not PREDICTIVE, or why this
        specific old/new disagreement is expected and safe>",
     "classified_by": "<agent or operator identity>",
     "stage2_work_item": "<reference to the specific triage record/commit/ticket this
        classification came from>",
     "timestamp": "<ISO-8601, when classified>"
   }
   ```
   A divergence with no matching promotion record is, by definition, NOT accounted for —
   there is no other path to "accepted" status. This is what prevents "accounted for" from
   becoming an informal operator bypass: acceptance requires a real, auditable record with
   a rationale and an identified classifier, not a passing mention in a PR description.
3. **Stage 3 — block on unexplained disagreement.** Verifiers still gate on the OLD hash
   (no live-trading behavior change yet — this is the corrected r3 semantics, replacing
   r2's ambiguous "NEW hash disagrees with the OLD hash's verdict" framing, which read as
   comparing raw hash DIGESTS directly). The old and new mechanisms use different
   algorithms and field sets by design — their digest VALUES need not and generally will
   not be byte-equal even when both correctly describe the same artifact, so a raw digest
   comparison is a category error, not a signal. What stage 3 actually compares: **each
   verifier checks the artifact against its OWN matching stamp** (the old verifier
   evaluates the artifact under the old contract, producing an accept/reject verdict; the
   new verifier evaluates it under the new contract, independently producing its own
   accept/reject verdict) — the divergence being classified is whether these two
   INDEPENDENT SEMANTIC VERDICTS agree (both accept, or both reject), not whether the two
   hash strings match byte-for-byte. Promotion fails if the verdicts disagree in a way with
   no matching promotion record from stage 2 (per the schema above); a disagreement WITH a
   matching record passes as an expected, already-classified difference; anything new
   blocks and gets triaged the same way as stage 2.
4. **Stage 4 — cutover.** Only once stage 3 has run clean for the acceptance window in
   §3 do verifiers SWITCH to REQUIRING the new `model_fingerprint` hash + schema version
   as the actual gate. From this point the OLD hash is retained **only as audit/rollback
   metadata** — it is never again an OR-acceptable alternative to the new hash. There is
   no step, at any stage past stage 3, where "old hash passes" substitutes for "new hash
   passes": the entire point of the new contract is to catch what the old one silently
   missed, and any OR-acceptance at cutover would let exactly that class of miss through
   permanently, which is the same failure mode as the original three incidents.

Re-stamp tooling becomes a thin wrapper over the shared impl at every stage past 1.

## 3. Acceptance (from #231 M6, made concrete)

Fixture green from all import sites; the stage 3→4 cutover (§2c) requires, over its
observation window (default 30 days, extendable if call-site traffic is too sparse to
exercise every site in 30 days):

- **Coverage**: every call site enumerated in §3a has been genuinely EXERCISED at least
  once during the window (not merely "nothing failed," which is indistinguishable from
  "nothing ran" and would be a false-positive pass).
- **Zero unexplained old/new divergence**: divergences classified and accepted in stage 2
  are fine; anything new is not.
- **Deliberate unknown-key tests fail closed**: a synthetic artifact with an intentionally
  unclassified key-path injected must be verified, during the window, to actually raise/
  fail-close per §2b — proving the fail-closed behavior works in practice, not only that
  it's documented.
- **Zero manual restamps** occurred during the window (a manual restamp during the
  observation period means an operator had to work around a still-broken verification,
  which disqualifies that window from counting toward acceptance — restart the clock).

The original "zero fingerprint-class fail-closed events in 30 days" criterion is dropped:
a silent no-op (nothing runs, nothing fails) would trivially satisfy it without proving
anything. The criterion above requires exercised coverage, not just an absence of alarms.

### 3a. Every real stamp/verify call site (mechanical inventory, not "TBD")

Read-only grep across RenQuant, 2026-07-02 — every function that currently stamps or
verifies `model_content_sha256` or an artifact-level content hash:

| Site | Role | Current impl used |
|---|---|---|
| `backtesting/renquant_104/kernel/panel_pipeline/panel_scorer.py:108` (`model_content_sha256`) | canonical stamp/verify function, pipeline semantics (SUBTRACTIVE denylist) | itself — the impl being replaced |
| `renquant_model_gbdt/fit_calibrator_alpha158_fund.py:35` | stamp, model-repo semantics (ADDITIVE allowlist) | independent impl — the other divergent semantics |
| `scripts/fit_calibrator_alpha158_fund.py:32` | stamp (umbrella script) | **imports** the pipeline impl above (confirmed by read — not a third independent copy, corrects the earlier "three hand copies" belief further: it's a call site, not a divergent implementation) |
| `scripts/stamp_walkforward_fingerprints.py:35,114` (`stamp_manifest`) | stamp (walk-forward manifest) | **imports** `model_content_sha256` from `panel_scorer.py` — a call site of the pipeline impl, not independent; also stamps a separate `file_fp` (whole-file sha256, unrelated to content classification — out of scope for `model_fingerprint`, stays as-is) |
| `backtesting/renquant_104/kernel/walk_forward/loader.py:154,158,377` | verify (WF loader, cross-checks manifest fingerprints against artifacts at load time) | **imports** `model_content_sha256` from `panel_scorer.py` — a call site, not independent |
| `scripts/train_production_model.py` (`build_artifact`) | stamp (XGB/GBDT production training) | writes its own artifact JSON directly; classified separately as XGB-family per §2a — confirmed in RenQuant#426 to already stamp `recipe_id` into this same payload |
| `backtesting/renquant_104/kernel/panel_pipeline/hf_patchtst_scorer.py` | stamp/verify (HF/PatchTST checkpoint) | whole-file-hash-bound, HF-family per §2a — confirmed in RenQuant#426 |
| `backtesting/renquant_104/kernel/panel_pipeline/shadow_scoring.py::_compute_admission` | verify (shadow-serving admission gate) | consumes the recipe/schema stamp from the two sites above; not a fingerprint stamp/verify site itself but a downstream consumer — migrates automatically once its inputs do |

Net correction to §1: there are **two** independent stamp implementations (pipeline
SUBTRACTIVE, model ADDITIVE), not three — every other "site" found by this inventory is a
**caller** of one of those two, confirmed by reading the actual import statements rather
than assumed from name similarity. `stamp_patchtst_fingerprint.py` referenced in the prior
revision does not exist under that name in the current tree; the HF/PatchTST stamping
this design must migrate is `hf_patchtst_scorer.py`, corrected above.

## 4. Ownership + order

renquant-common PR (the module + tables + fixtures, §2a/§2b) → model + pipeline migration
PRs (stage 1 dual-write at both current impls, §2c) → stage 2 classification pass against
real artifacts → stage 3 block-on-unexplained-divergence → 30-day (or coverage-extended)
watch against §3's real criteria → stage 4 cutover, umbrella re-point. Boundary note: the
classification TABLES are a modeling contract (model repo reviews them); the MECHANISM
(recursion, serialization, hashing, staged rollout) is shared infrastructure (common).
