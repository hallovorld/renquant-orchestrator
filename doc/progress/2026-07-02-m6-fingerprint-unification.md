# M6 fingerprint unification design — design PR

STATUS:   design for review (docs only; renquant-common + migration PRs follow).
REVISION: r1.
WHAT:     `doc/design/2026-07-02-m6-fingerprint-unification.md` — M6/R2 (#231 Term PROCESS):
          the measured divergence (pipeline = SUBTRACTIVE denylist at panel_scorer.py:108;
          model = ADDITIVE ~12-field allowlist at fit_calibrator_alpha158_fund.py:35;
          umbrella's calibrator script IMPORTS the pipeline impl — the "three hand copies"
          belief corrected to two divergent semantics + one import) and the shared contract:
          renquant_common.model_fingerprint with TOTAL classification (unclassified key
          fails LOUDLY at stamp time — the silent defaults in both current impls are the
          root cause), fingerprint_schema_version stamped alongside, version-gap as its own
          explicit error, dual-hash migration window, cross-repo identity fixtures.
WHY/DIR:  three fail-closed no-trade incidents (05-27/06-22/07-01) share this root cause;
          each manual re-stamp mutates the artifact and re-arms the trap. Total
          classification converts "new field ⇒ silent false match/mismatch" into "new field
          ⇒ loud stamp-time error," which is the only failure mode that gets fixed before it
          trades.
EVIDENCE: read-only code inventory with file:line cites (2026-07-02); incident dates from
          the memory record.
NEXT:     Codex review; implementation order: common module+fixtures → model/pipeline
          migrations → umbrella re-point → 30-day zero-incident watch (the #231 M6 AC).

## Round 2 (Codex CHANGES_REQUESTED — fail-open migration + shallow classification)

**Finding.** (1) r1's migration proposed "verifiers accept either old or new hash for one
release window" — an OR-accept window that lets an old-hash pass mask a new-contract
mismatch, reproducing the exact silent-default failure mode this design exists to remove,
one layer up. (2) r1's "total classification" only implied top-level key coverage —
insufficient if predictive content lives in nested dict/list paths; also left
`stamp_walkforward_fingerprints.py` as an unenumerated "to be classified" placeholder and
used a criterion ("zero fail-closed events in 30 days") that a total no-op would trivially
satisfy.

**Fix.**
- §2c replaces the OR-accept window with a 4-stage rollout (shadow dual-write → classify
  real disagreements → block-on-unexplained-divergence while still gating on the old hash
  → cutover to requiring the new hash, old hash retained for audit only, never
  OR-acceptable again).
- §2a makes classification recursive (key-path addressed, wildcard-capable for
  homogeneous arrays) and artifact-family scoped, reusing the XGB-vs-HF/PatchTST split
  RenQuant#426 already established this session for the same underlying reason (the two
  families' artifacts don't share a binding mechanism).
- §2b freezes canonical serialization (sorted-key JSON, reusing RenQuant#430's
  fixed-precision-float convention), NaN/Infinity canonicalization, the key-path schema,
  fail-closed unknown-key behavior at both stamp and verify time, and schema-version
  ownership (tables = model repo, mechanism = common).
- §3a is a mechanical, read-only-verified inventory of every real stamp/verify call site
  (confirmed via actual import statements, not name-similarity guessing) — corrects r1's
  belief further: there are 2 independent implementations, not 3; every other "site" is a
  caller of one of those two. `stamp_patchtst_fingerprint.py` (named in r1) does not exist
  under that name; the real HF/PatchTST site is `hf_patchtst_scorer.py`.
- §3's acceptance criterion is now coverage-aware: every enumerated call site actually
  exercised, zero unexplained divergence, deliberate unknown-key fixtures proven to fail
  closed, zero manual restamps during the window — not just an absence of alarms.

**Evidence:** read-only grep + import-statement verification across RenQuant
(`backtesting/renquant_104/kernel/panel_pipeline/{panel_scorer,hf_patchtst_scorer,
shadow_scoring}.py`, `kernel/walk_forward/loader.py`, `scripts/{fit_calibrator_alpha158_fund,
stamp_walkforward_fingerprints,train_production_model}.py`), 2026-07-02; RenQuant#426 and
RenQuant#430 read-only for precedent reuse (recipe/family split, canonical hash pattern).

**Scope:** design-doc-only change, no code in this PR (unchanged from r1) — the staged
migration and recursive classifier are specified here for the implementation PRs that
follow, not built in this one.
