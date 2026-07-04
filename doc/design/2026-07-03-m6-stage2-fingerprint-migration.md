# M6 stage-2: consumer migration to the schema-v1 fingerprint API + the live-artifact re-stamp plan

STATUS: design for review (docs only; implementation lands as separate per-repo PRs
per §6). Successor to #244 (`doc/design/2026-07-02-m6-fingerprint-unification.md`,
the stage-1 contract design) and to renquant-common#21 (0.9.1, which restored the
0.8.1 legacy surface as deprecated shims and names *this* stage-2 PR as their
removal point). Direct trigger: renquant-pipeline#160, which REVERTED the #159
v1-classification cutover because no migration plan existed for already-stamped
production artifacts — this document is that plan.
DATE: 2026-07-03

## 0. Why stage-2 exists

The 0.9.1 shims are a migration window, not a destination. They are the VERBATIM
0.8.1 semantics — including every silent default that caused the three fail-closed
no-trade incidents (2026-05-27, 06-22, 07-01): unknown keys hashed silently
(denylist), `default=str` lossy serialization, silent fallbacks from content hash
to whole-file hash. The v1 API (`stamp()`/`verify()`, frozen
`PREDICTIVE_KEYS`/`OPERATIONAL_KEYS`, fail-loud `UnclassifiedKeyError`, explicit
`VersionGapError` vs `MismatchError`) is the actual fix to the triple-impl incident
class: no key can ever again be silently included by one side and excluded by the
other, because an unclassified key is a hard error at both stamp and verify time.

Staying on the shims indefinitely keeps the incident class alive with a
`DeprecationWarning` attached. Each shim's warning text names the removal contract:
*"REMOVED in the M6 stage-2 pipeline migration PR (when renquant-pipeline moves to
the schema-versioned stamp()/verify() API)"*. Master-plan anchor: M6 row of
`doc/design/2026-07-02-unified-107-master-plan.md` ("one shared content-fingerprint
impl — kills the recurring fail-closed no-trade class (3 incidents) … staged
per-site"); its Forward-pulled note queues "M6 stage-2 (pipeline fingerprint
migration + re-stamp plan)" behind the 0.9.1 shims, which shipped 2026-07-02.

### 0a. The #160 constraint (primary design constraint)

renquant-pipeline#159 round 1 cut `panel_scorer.py` over to the v1 names directly.
It was reverted by #160 because the cutover **silently changed
`model_content_sha256` output for every existing artifact** while live calibrators
carry stamps produced under 0.8.1 semantics, and both binding checks are genuinely
fail-closed (`raise ValueError`). #160's own words: the cutover is *"premature
without a real migration plan for already-stamped production artifacts"* —
*"potentially triggered by this migration rather than prevented by it."*

Everything in §3 exists to answer that constraint: **no verifier's effective
semantics may change before the artifacts it verifies carry stamps under the new
semantics, and no artifact may be re-stamped before the code that reads it can
dispatch on the stamp's schema version.**

## 1. Ground truth, measured 2026-07-03 (read-only census, live umbrella tree)

Recomputed with the actual renquant-common 0.9.1 module from origin/main (both the
`_legacy_model_content_sha256` 0.8.1 engine and the v1 hasher) — not asserted from
PR narratives:

| Artifact | stamped `model_content_fingerprint` | legacy 0.8.1 hash | v1 hash | unclassified keys under v1 |
|---|---|---|---|---|
| `data/panel-ltr-prod-alpha158-fund-fwd60d.json` (prod panel-LTR) | **NONE** | `9c4bbd74…` | `0f798015…` | none |
| `data/shadow_analyst/panel-ltr-shadow-analyst-rev3-fwd60d.json` | **NONE** | `8ea3b5f6…` | `65ff1af3…` | none |
| `data/shadow_analyst/panel-ltr-shadow-baseline-noan-fwd60d.json` | **NONE** | `a5566cd9…` | `fde9a033…` | none |
| WF fold `artifacts/walkforward_gbdt_prod_recipe_v2/2026-03-02/panel-ltr.json` (1 of 43 in the active corpus) | **NONE** | `6e9a09f3…` | `c5a59816…` | none |

| Calibrator | declared `scorer_model_content_fingerprint` | matches |
|---|---|---|
| `artifacts/prod/panel-rank-calibration.json` (active) | `9c4bbd74…` | the prod artifact's **legacy** recompute |
| WF fold calibrator `sim/walkforward_calibrators/2026-03-02/panel-rank-calibration.json` | `6e9a09f3…` | that fold's **legacy** recompute |
| `artifacts/prod/panel-calibration-{BEAR,BULL_CALM,BULL_VOLATILE}.json` | **NONE** | n/a (see §5 row 8) |

Live venv: `renquant-common == 0.8.1` (`RenQuant/.venv`, checked 2026-07-03).

Three load-bearing findings:

1. **The live artifacts are UNSTAMPED.** Their identity is recomputed at every
   read: by the pipeline runtime (`stamp_artifact_metadata`'s `setdefault` only
   preserves a stamp when one exists), by the calibrator-fit scripts
   (`payload.get("model_content_fingerprint") or <recompute>` — the stamped-value
   branch is dead when there is no stamp), and by the WF loader. So the binding
   between the active calibrator and the prod scorer holds ONLY because both sides
   currently recompute under the same (0.8.1) semantics. "Re-stamp before flipping"
   is therefore not even sufficient as stated — the artifacts must first be given
   stamps at all (§3 step 0), because until then ANY semantic change on ANY reader
   changes the identity out from under the other readers.
2. **v1 ≠ legacy on every live artifact** (as #21's divergence proofs predicted:
   `label_col`/`label`/`lookahead_days` moved to PREDICTIVE, canonicalization
   replaced `default=str`). There is no artifact for which the flip is a no-op.
3. **No live artifact has unclassified keys under the v1 tables** — the 0.9.x
   real-artifact census additions covered them, so v1 stamping will not crash on
   the current inventory. This must be re-verified by dry-run at execution time
   (§5 row 4), not assumed from this snapshot.

### 1a. The armed sequence (why stage-2 is urgent, not hygiene)

The fleet is converging on renquant-common 0.9.1 (the D1 chain: common#21 → cap
bumps backtesting#63 / base-data#30 / artifacts#11). On a 0.9.1 venv, with TODAY'S
merged code — no stage-2 changes at all — the bare name `model_content_sha256`
carries v1 semantics, and:

1. **Daily path, delayed detonation.** The weekly calibrator refit
   (`RenQuant/scripts/fit_calibrator_alpha158_fund.py:48`, which imports the bare
   name via the pipeline re-export) recomputes the unstamped prod artifact under
   v1 and stamps `scorer_model_content_fingerprint = 0f798015…`. The runtime
   active-scorer identity stays legacy (`stamp_artifact_metadata` shim →
   `9c4bbd74…`). Next daily run: `job_panel_scoring.py::
   _assert_calibrator_matches_scorer` (strict, fail-closed) raises → the recurring
   "no trade" fail-close, scheduled in advance.
2. **WF path, immediate detonation.** `walk_forward/loader.py:158` recomputes v1
   (`c5a59816…`); the 43 fold calibrators declare legacy stamps (`6e9a09f3…`);
   fold artifacts are unstamped so no stamped-value route exists; the whole-file
   hash matches nothing. `_assert_calibrator_matches_entry` (loader.py:424) is
   fail-CLOSED — only the recompute step at :158 is fail-soft (its `try/except`
   swallows errors, not mismatches). **Correction to the prior framing that the WF
   loader is "degraded-but-survivable": measured against the real corpus, every
   fold raises and `weekly_wf_promote` breaks outright on venv convergence.**
3. **Corpus pollution.** `scripts/stamp_walkforward_fingerprints.py:114` starts
   stamping v1 hashes into new/updated manifests while old manifests and
   calibrators carry legacy — a mixed corpus with no version marker to tell them
   apart.

Consequence for sequencing: §3 step 0 must land BEFORE the live venv converges on
0.9.x (or in the same maintenance window). It is deliberately a zero-code-change,
stamp-only step so it cannot be blocked behind the stage-2 code reviews.

## 2. Semantic delta inventory: what hashes differently under v1 vs 0.8.1

| Input class | 0.8.1 (shims) | v1 | Divergence proof |
|---|---|---|---|
| Unclassified key present | hashed silently (subtractive denylist) | `UnclassifiedKeyError` at stamp AND verify | #21 fixture proof 1 |
| `label_col` / `label` / `lookahead_days` relabel | hash INVARIANT (denylisted) | hash CHANGES (PREDICTIVE) | #21 fixture proof 2 |
| Non-JSON value | lossy `default=str` | hard `FingerprintError` | 0.9.x tests |
| Non-finite float in predictive field | serialized (`allow_nan` default) | `NonFiniteValueError` | 0.9.x tests |
| No predictive content | `ValueError`; the path API silently falls back to whole-file hash | `NoPredictiveContentError`; no silent path fallback in the v1 API | shim docstrings |
| Schema identity | no version stamped | `fingerprint_schema_version: 1` stamped; `verify()` raises `VersionGapError` ("re-stamp under vN") distinctly from `MismatchError` | v1 API |

Measured net effect (§1): every live artifact's hash changes. There is no "the
delta happens not to matter for us" escape.

### 2a. Per-call-site impact (every consumer, with verdicts)

| # | Call site | What it does today | Delta impact | Class |
|---|---|---|---|---|
| 1 | pipeline `panel_scorer.py:140` — `stamp_artifact_metadata` (0.8.1 shim) inside `PanelScorer.load` | computes the ACTIVE scorer identity (stamped value if present, else legacy recompute) | this identity feeds site 2; changing its semantics without re-stamping calibrators = the incident | **incident-hot** |
| 2 | pipeline `job_panel_scoring.py:2255` — `_assert_calibrator_matches_scorer` (strict, fail-closed daily buy path) | list-intersection of scorer identities vs calibrator-declared identities | pure comparison — migrates when its inputs do; end state replaces the heterogeneous list-OR (which also accepts 12-char prefixes and file hashes) with `verify()` + exact match | **incident-hot** (the 05-27/06-22/07-01 site) |
| 3 | pipeline `walk_forward/loader.py:158` — bare `model_content_sha256` recompute for fold candidate matching | **already v1 under 0.9.x** (the bare name is the v1 hasher; #160 could not revert this because the legacy payload-level hasher has no public name) | recompute route goes foreign on venv convergence; combined with fail-closed site 4 → WF promote breaks (§1a.2) | **incident-hot** (measured, corrects the "fail-soft = survivable" belief) |
| 4 | pipeline `walk_forward/loader.py:424` — `_assert_calibrator_matches_entry` | fail-closed per-fold scorer/calibrator contract | as site 2 | **incident-hot** |
| 5 | pipeline `loader.py:405` — whole-file sha256 | file identity, not content classification | unchanged under v1 | none |
| 6 | umbrella `scripts/fit_calibrator_alpha158_fund.py:48` (imports the pipeline re-export) | stamps `scorer_model_content_fingerprint` into prod calibrators at weekly refit | the ARMING site for §1a.1 — first refit on a 0.9.x venv stamps v1 against a legacy runtime | **incident-arming** |
| 7 | umbrella `scripts/stamp_walkforward_fingerprints.py:114` | stamps content_fp + file_fp into WF manifests | mixed-semantics corpus (§1a.3) | degraded |
| 8 | renquant-model `renquant_model_gbdt/fit_calibrator_alpha158_fund.py:22` (+ `renquant_model_patchtst/fit_calibrator.py`) — imports `model_content_sha256` from common DIRECTLY | already v1 on any 0.9.x venv; stamped-value precedence (`payload.get(...) or recompute`) is dead while artifacts are unstamped | same arming behavior as site 6 on the model-factory side | **incident-arming** |
| 9 | pipeline `tests/test_model_content_sha256_shared.py` | pins is-identity of the four SHIM names | must be rewritten at the stage-2 code PR to pin the v1 API identity instead (same "no re-fork" property, new surface) | test-only |
| 10 | HF/PatchTST shadow lane (`hf_patchtst_scorer.py`, `.pt` checkpoints) | whole-file-hash-bound family (stage-1 §2a split); `config_fingerprint` lane stamped by `scripts/stamp_patchtst_fingerprint.py` | content-hash re-stamp N/A; unaffected by the JSON-payload semantics change | none (family-split) |

The mitigating pattern shared by sites 1, 6, and 8: **every reader prefers an
artifact's stamped value over its own recompute** (`setdefault` /
`payload.get(...) or ...` / the loader's collected-stamps list). §3 step 0 exploits
exactly this to make the whole fleet venv-version-insensitive without touching any
code.

### 2a-bis. Inventory amendment — campaign B1+B2 sites (2026-07-04)

The compliance campaign's B1/B2 audit (PR #297; RQ#444 F-2/F-10, #295 P0-2,
#296 BT-1) found this table under-counted the WF-loader legs: the
`WalkForwardModelLoader` existed as ×3 DIVERGENT forks, and two umbrella
call-sites were on the umbrella kernel's stale local `model_content_sha256`
copy (not the pipeline re-export as site 6 previously implied). Corrections
and dispositions, landed 2026-07-04 (backtesting `fix/wf-loader-unify` +
umbrella `fix/wf-gate-loader-repoint`; equivalence proven read-only against
the real 47-artifact inventory — identical green/red sets on all legs,
ZERO green matches relying on 12-char prefixes):

| # | Call site | Was | Now | Class |
|---|---|---|---|---|
| 6′ | umbrella `scripts/fit_calibrator_alpha158_fund.py:32` (CORRECTION to site 6: it imported `kernel.panel_pipeline.panel_scorer` — the umbrella kernel's STALE LOCAL copy, not the pipeline re-export) | 0.8.1-frozen local recompute as the fallback under stamped-value precedence | recompute fallback = the EXPLICIT legacy engine, `renquant_common.model_fingerprint` imports only; propagates `scorer_fingerprint_schema_version` for v1-stamped scorers (dead until step 2) | migrated (B2) |
| 7′ | umbrella `scripts/stamp_walkforward_fingerprints.py` (site 7) | UNCONDITIONAL recompute via the same stale local copy — would go v1 the day the local copy is ever synced (and was the §1a.3 pollution path via any venv-coupled route) | stamped-value-first + explicit legacy fallback; propagates the schema version into calibrator bindings (keeps a post-step-2 stamper re-run from downgrading step-2 declarations) | migrated (B2) |
| 11 | umbrella `backtesting/renquant_104/kernel/walk_forward/loader.py` — the LIVE promote-gate leg (`run_wf_gate.py` loader imports at :2311 area + `adapters/sim.py`); previously MISSING from this table | full fork: local 12-char-prefix matcher + stale-copy recompute | verification via the pipeline `fingerprint_dispatch` (resolved importable → `RENQUANT_SUBREPO_ROOT` → `.subrepo_runtime/repos` → siblings; FAIL-LOUD if absent); #421 bounded resolver + digest binding preserved | migrated (B2) |
| 12 | renquant-backtesting `walk_forward/loader.py`; previously MISSING from this table | full fork: local matcher + venv-coupled bare-name recompute from pipeline `panel_scorer` (the #160 hazard — v1 semantics on any 0.9.x assembly) | subclass of the pipeline loader; ONLY the backtesting URI-resolution layer stays local; verification inherited from the dispatch | migrated (B1) |

Step-4 note: the 12-char-prefix retirement now covers all four loader legs
through the ONE `accept_legacy_stamps` flag — no per-repo matcher remains to
retire separately. The step-5 zero-legacy-callers grep already covers these
paths.

## 3. The re-stamp plan (sequenced cutover)

Reconciliation with stage-1 §2c ("never an OR-accepting window"): the migration
window here uses **version-dispatched acceptance**, not a naked OR. Every stamp
carries (or lacks) `fingerprint_schema_version`; a verifier verifies each artifact
under the ONE semantics its stamp declares — a versionless stamp IS the legacy
declaration (all 0.8.1 stamps predate the version field by construction). Per
artifact there is exactly one acceptable hash at all times; "accepts either" is
true only across the population during the window, and is controlled by one
explicit flag. A v1 mismatch can never hide behind a passing legacy hash because no
artifact is ever evaluated under both. Stage-1's dual-write/shadow-compare stages
were designed for unifying two divergent impls (shipped as 0.9.x); stage-2's
problem is one shared impl with two schemas and a live population on the old one —
version dispatch is the staged mechanism appropriate to that shape, and the end
state (§3 step 5) is identical to stage-1 stage-4: the legacy value survives only
as audit/rollback metadata, never as an acceptable alternative.

**Step 0 — semantics-pinning pre-stamp (legacy), BEFORE fleet venv convergence.**
New umbrella repair tool `scripts/restamp_model_content_fingerprint.py`, following
the two existing precedents: `scripts/stamp_patchtst_fingerprint.py` (stamps
against the PINNED config, dry-run by default, FAIL-CLOSED compatibility checks
before writing, refuses on any real drift) and `scripts/restamp_prod_fingerprint.py`
(refuses unless the diff is exactly the expected fields; never touches weights).
The tool computes the LEGACY hash via the 0.9.1 shim (imports only — see §5 row 3)
and writes `model_content_fingerprint: <legacy>` into every artifact in the §3a
inventory that lacks a stamp. Effect: all reader precedence routes (§2a) now
resolve identity from the stamp, so D1/fleet venv convergence to 0.9.1 becomes safe
with ZERO code change. Post-write: re-run `stamp_walkforward_fingerprints.py` on
affected manifests (fold file bytes changed → manifest `scorer_artifact_sha256`
refresh), then re-run the §3c census and confirm every calibrator binding still
holds. This mutates production inputs on the live tree → operator grant required
(landing-actions ask-first), `.bak` per file + before/after hashes recorded in a
run bundle.

**Step 1 — stage-2 code: version-dispatched verification behind a flag.**
renquant-pipeline PR (plus a strategy-104 config PR for the flag — policy lives in
strategy config, enforcement in pipeline, per #210 §6):

- New config key `ranking.panel_scoring.fingerprint.accept_legacy_stamps`
  (default `true` during the window). This is THE dual-accept flag, and its exact
  enforcement points are the two fail-closed checks:
  `job_panel_scoring.py::_assert_calibrator_matches_scorer` and
  `walk_forward/loader.py::_assert_calibrator_matches_entry`.
- Dispatch rule at both points: an identity pair is compared **within one schema
  only** — v1-stamped scorer identity against v1-declared calibrator identity via
  `renquant_common.model_fingerprint.verify()`; versionless (legacy) against
  versionless via the shim equality path. Cross-schema comparison is never a match.
  With the flag `false`, only the v1 route exists and a versionless stamp fails
  closed with the explicit "re-stamp under v1" remedy (`VersionGapError` text).
- `PanelScorer.load` stamps BOTH identities into the in-memory scorer metadata
  (legacy via shim for the window + v1 via `stamp()` when computable) and logs a
  divergence-telemetry line on every load and every verify (the stage-1 stage-1
  shadow analog): stamped-schema seen, both recomputes, match verdicts. Zero
  behavior change while the flag is `true` and artifacts are legacy-stamped.
- `walk_forward/loader.py:158` moves off the bare name onto the explicit pair
  (legacy shim + `stamp()`/`verify()`), removing the silent
  semantics-follows-the-venv coupling that #160 could not fix.
- `tests/test_model_content_sha256_shared.py` rewritten: is-identity pins on the
  v1 API re-exports + a frozen legacy test-vector (from the #21 fixtures) that must
  keep passing until step 5 removes the shims.
- Prerequisite common 0.9.2 (small): classify the new stamp-adjacent fields this
  plan writes (e.g. `model_content_fingerprint_legacy_081`,
  `restamp_provenance`) into `OPERATIONAL_KEYS` — otherwise the first v1
  `stamp()` of a step-2 dual-stamped artifact raises `UnclassifiedKeyError` on the
  very fields the migration added. Table change ⇒ `FINGERPRINT_SCHEMA_VERSION`
  handling per stage-1 §2b ownership (model repo reviews the classification).

**Step 2 — the v1 re-stamp run.** GATED on: step-1 code merged AND pinned AND
deployed on the live machine (pin-align + venv `renquant-common >= 0.9.2` verified
and recorded — merged-is-not-deployed is a known trap, §5 row 2). The same umbrella
tool, second mode: for every artifact in §3a — recompute v1 (dry-run first over the
FULL inventory; any `UnclassifiedKeyError` aborts the whole run into a common-table
PR, §5 row 4), then write `model_content_fingerprint: <v1>` +
`fingerprint_schema_version: 1`, preserving the prior value as
`model_content_fingerprint_legacy_081` (audit/rollback metadata per stage-1
stage-4 — never read by any verifier). Calibrators: refit is NOT required (the
scorer content did not change); the tool re-stamps each calibrator's declared
identity to the v1 value of its paired scorer (`scorer_model_content_fingerprint`
+ `scorer_fingerprint_schema_version: 1`, legacy preserved as
`scorer_model_content_fingerprint_legacy_081`) — pairing resolved via the §3c
census, refusing any calibrator whose legacy declaration does not match its paired
scorer's legacy stamp (that would be a REAL pre-existing mismatch, not migration
noise). Order within the step: scorer artifacts first, then calibrators, then
`stamp_walkforward_fingerprints.py` re-run on affected manifests — version
dispatch keeps every intermediate state consistent.

**Step 3 — verification census (the "both computations agree" proof).**
New read-only script in the orchestrator (`scripts/census_model_fingerprints.py` —
coordination/monitor/provenance is orchestrator-owned per #210 §6), runnable at
every step and wired into the daily run bundle during the window. Green means, for
EVERY artifact in §3a: (a) a v1 stamp is present with schema version 1; (b) the v1
recompute equals the stamp; (c) the legacy-081 audit field equals the legacy
recompute (proves the re-stamp didn't paper over a real drift); (d) every
calibrator's declared v1 identity matches its paired scorer's v1 stamp; (e) the
step-1 telemetry shows ZERO legacy-route acceptances over the observation window —
minimum: 7 consecutive daily full runs + 1 weekly calibrator refit + 1
`weekly_wf_promote` cycle, so every §2a site is genuinely EXERCISED (stage-1 §3's
coverage rule: "nothing failed" without traffic proves nothing).

**Step 4 — flag flip.** strategy-104 config PR: `accept_legacy_stamps: false`.
From here a versionless stamp fails closed with the "re-stamp under v1" remedy.
Rollback = flip the flag back (one config PR; artifacts still carry both values).

**Step 5 — shim removal (renquant-common 0.10), LAST.** Gated on ALL of:
- census green (step 3 definition) including the zero-legacy telemetry window
  AFTER step 4;
- zero-legacy-callers grep across every repo main + the umbrella tree:
  `grep -rn "model_content_sha256_from_path\|stamp_artifact_metadata\|MUTABLE_ARTIFACT_KEYS\|PREDICTIVE_CONTENT_HINTS\|_legacy_model_content_sha256"`
  over renquant-pipeline, renquant-model, renquant-backtesting, renquant-common
  (own tests excluded), RenQuant `scripts/` — must return only historical docs;
- the #21 removal contract satisfied (pipeline on `stamp()`/`verify()`).
Removes the four shim names + the `_legacy_*` engine; pipeline then bumps its cap
to `>=0.10`. Rollback = 0.9.x remains published; repin.

### 3a. Re-stamp inventory (enumerated by GLOB at run time, snapshot below)

| Family | Paths (live umbrella tree) | Step 0 | Step 2 |
|---|---|---|---|
| prod panel-LTR | `data/panel-ltr-prod-alpha158-fund-fwd60d.json` | stamp legacy | re-stamp v1 |
| shadow lanes (both) | `data/shadow_analyst/panel-ltr-shadow-analyst-rev3-fwd60d.json`, `data/shadow_analyst/panel-ltr-shadow-baseline-noan-fwd60d.json` | stamp legacy | re-stamp v1 |
| WF fold scorers | `backtesting/renquant_104/artifacts/walkforward_gbdt_prod_recipe_v2/*/panel-ltr.json` (43) + any other corpus the active manifests reference | stamp legacy | re-stamp v1 |
| prod calibrators | `backtesting/renquant_104/artifacts/prod/panel-rank-calibration.json` (+ `.staging`/`rollback` snapshots — see §5 row 1) | already legacy-declared (verify only) | re-declare v1 |
| WF fold calibrators | `backtesting/renquant_104/artifacts/sim/walkforward_calibrators/*/panel-rank-calibration.json` | already legacy-declared (verify only) | re-declare v1 |
| regime calibrators | `artifacts/prod/panel-calibration-{BEAR,BULL_CALM,BULL_VOLATILE}.json` | §5 row 8 decision first | per decision |
| WF manifests | `artifacts/**/walkforward*manifest*.json` (active set) | re-run stamper post-mutation | re-run stamper |
| HF/PatchTST checkpoints | `.pt` + sidecars | N/A (whole-file family) | N/A |

The tool enumerates by glob + manifest reachability at execution time, never from
this table (artifacts retrain during the window — §5 row 1).

## 4. Ownership + merge order + rollback

Per the #210 §6 ownership table (gate semantics → backtesting/model · policy/config
→ strategy-104 · runtime admission enforcement → pipeline · coordination/monitor/
provenance → orchestrator · umbrella scripts schedule and invoke but own no
selection logic) and stage-1 §2b (classification tables → model-repo review;
mechanism → common):

| Order | Step | Repo / artifact | Owner review | Rollback |
|---|---|---|---|---|
| 1 | re-stamp tool PR (both modes, dry-run default) | RenQuant `scripts/` (invoke-only; hash logic imports renquant-common exclusively) | operator + codex | revert PR (no artifacts touched yet) |
| 2 | **step-0 legacy pre-stamp RUN** (unblocks safe fleet 0.9.1 convergence — do not converge the live venv before this) | live tree artifacts | operator grant per landing-actions rule | restore `.bak` (recorded in run bundle) |
| 3 | common 0.9.2 (OPERATIONAL_KEYS additions for the migration stamp fields) | renquant-common | model repo (table change) | 0.9.1 repin |
| 4 | pipeline stage-2 code (version dispatch + telemetry + loader:158 explicit pair + test rewrite) | renquant-pipeline | codex; fixture parity with common | revert PR; flag default already `true` |
| 5 | flag introduction (default `true`) | renquant-strategy-104 config | operator | config revert |
| 6 | deploy: pin bumps + live pin-align + venv ≥ 0.9.2, evidence recorded | umbrella lock | operator grant | repin |
| 7 | **step-2 v1 re-stamp RUN** (dry-run first) | live tree artifacts | operator grant | restore from `*_legacy_081` (auditable, tool-supported) |
| 8 | census green over the step-3 window | orchestrator script + run bundles | — | n/a (read-only) |
| 9 | flag flip `accept_legacy_stamps: false` | renquant-strategy-104 | operator | flip back |
| 10 | common 0.10 shim removal + pipeline cap `>=0.10` | renquant-common, renquant-pipeline | codex + grep/census gates | 0.9.x repin |

## 5. What could go wrong

| # | Risk | Mechanism | Mitigation |
|---|---|---|---|
| 1 | mid-window drift: retrain/refit lands between census and re-stamp; weekly `.staging`/`rollback_*` calibrator snapshots appear continuously | new unstamped artifact re-arms §1a; a re-stamp run misses it | tool enumerates by glob+manifest reachability at RUN time; census re-runs in the daily bundle during the whole window; the weekly refit is scheduled AROUND step-2 (same maintenance window) and any refit during the window triggers an immediate census re-run; a red census blocks promotion tooling |
| 2 | sim/live parity trap (merged-not-deployed) | v1 re-stamp with live venv still on 0.8.1 (measured TODAY) or live code behind pins ⇒ self-inflicted fail-close: 0.8.1 readers keep the stamped (now v1) value via `setdefault`/`payload.get` precedence and mismatch every legacy calibrator | step-2 hard-gated on recorded pin-align + venv-version evidence from THE live machine (verify-freshness rule); census runs on the live tree, not a checkout |
| 3 | agents hand-copy the hash impl AGAIN | a "small helper" re-fork in the re-stamp tool / census / a fix PR re-creates the triple-impl incident by construction | never-again rule stated as a review gate on every PR in §4: hash logic is IMPORTS ONLY from `renquant_common.model_fingerprint`; pipeline keeps the is-identity test (rewritten, §3 step 1); the step-5 grep doubles as the no-local-copy check; delegate prompts for any implementation work must carry the no-git-in-live-tree and imports-only rules |
| 4 | `UnclassifiedKeyError` at step-2 on an artifact this census didn't cover (older fold, exotic side artifact) | v1 stamping crashes mid-run → half-stamped corpus | dry-run over the FULL inventory is a hard precondition of the write run; any unclassified key aborts into a renquant-common table PR (model-repo review per stage-1 §2b) — never a local table patch or a skip; version dispatch keeps a half-stamped corpus CORRECT anyway (each artifact verified under its own stamp), so the failure mode is delay, not mismatch |
| 5 | file-byte mutation invalidates whole-file hashes | stamping changes fold-file bytes → WF manifest `scorer_artifact_sha256` (file_fp) goes stale; `.bak` diffs churn | `stamp_walkforward_fingerprints.py` re-run is part of BOTH re-stamp runs (§3); census checks manifest-vs-file agreement; the loader's file-hash route is last-resort only and the end state drops it for v1 artifacts |
| 6 | the heterogeneous list-OR matcher accepts something it shouldn't during the window | `_any_fingerprints_match` accepts 12-char prefixes and mixes content/file/config identities across five key names | step-1 dispatch compares within one schema only (no cross-schema, no prefix acceptance on the v1 route: exact digest match via `verify()`); prefix + multi-key acceptance dies with the flag at step 4 |
| 7 | shadow-lane dark failure | a shadow e2e fail-close is a CONTRACT failure that looks like a decision ("no trade") and can run dark for days (the 06-25 config-FP precedent) | both shadow-lane artifacts are first-class census rows; shadow telemetry included in step-3 green criteria |
| 8 | regime calibrators declare NO scorer identity (measured, §1) | under post-flip strictness, any path that strict-checks them fails on the "missing fingerprint" branch | implementation PR must classify their load path first: either they are refit-with-stamp during step 2, or their loader is documented as outside the strict contract (with a test pinning that) — not discovered in production at step 4 |
| 9 | the WF corpus is enormous and partially historical | re-stamping dead corpora wastes the window and multiplies risk | scope = manifests reachable from the ACTIVE promote/sim configs (census lists them); historical corpora stay legacy-stamped and readable until step 4, after which loading one fails loudly with the re-stamp remedy — acceptable for archives, documented |

## 6. Acceptance (concrete, per stage-1 §3 discipline)

- Step-0 done: census shows every §3a scorer artifact carrying a legacy stamp equal
  to its legacy recompute; all existing calibrator bindings still hold; fleet venv
  convergence to 0.9.1 verified safe (one daily run + one wf_promote on 0.9.1,
  green, zero behavior change).
- Step-1 done: pipeline suite green with fixtures for all four dispatch cases
  (v1/v1 match, legacy/legacy match, cross-schema never-match, flag-off
  `VersionGapError` on versionless); telemetry lines visible in a real run bundle.
- Step-3 green: definition in §3 step 3 (a)–(e), coverage-exercised, zero manual
  re-stamps during the window (a manual re-stamp = the window restarts, per
  stage-1 §3).
- Step-5 done: grep clean, 0.10 published, pipeline cap bumped, shims gone; the
  #21 removal contract (`DeprecationWarning` text) is discharged by THIS plan's
  completion, closing M6.
