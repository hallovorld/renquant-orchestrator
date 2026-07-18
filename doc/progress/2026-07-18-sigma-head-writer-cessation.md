# Progress: σ-head writer cessation — Stage 2 (single-writer amendment)

Date: 2026-07-18

## What

Stage 2 of the merged single-writer amendment
(`renquant-base-data` `doc/design/2026-07-18-sidecar-single-writer-amendment.md`,
base-data#48 §2.1). The served
`alpha158_291_fundamental_dataset_rawlabel.parquet` had TWO weekly writers with
contradictory recipes — the base-data builder and this orchestrator's σ-head
refresh — a writer war that deadlocked the weekly PatchTST corpus refresh
(07-11/07-18). The amendment makes `renquant_base_data.rawlabel_sidecar` the SOLE
writer (canonical 179-col contract, no bar-frontier extension; Stage 1 =
base-data#49). This PR retires the orchestrator's second writer.

**Code + tests only — NO migration, NO served-file mutation, NO scheduling.**
The one supervised 179 regeneration is AC-D, an ask-first umbrella runbook.

## Changes (`src/renquant_orchestrator/retrain_alpha158_fund.py`)

`RefreshSigmaHeadRawLabelTask` no longer BUILDS/SWAPS the sidecar — it CONSUMES
the canonical file the sole writer published upstream (§2.1):

- **Retired** `_default_rawlabel_build_fn` (the self-build port of
  `build_raw_fwd60d_label.py`) and the column-contract-blind pre-swap validator
  `_default_rawlabel_validate_fn`; the `rawlabel_build_fn` / `rawlabel_validate_fn`
  context DI hooks are replaced by a single `rawlabel_verify_fn`.
- The task now **verifies** the canonical sidecar is present, FAIL-CLOSED on the
  amendment's 179-col contract at the consumption boundary, in LOCKSTEP with the
  freshly-merged panel (exact `(ticker,date)` coverage), unique-keyed and clears
  the finite-label floor, then **certifies** it (computes `rawlabel_sha256` from
  the on-disk consumed bytes + stamps the provenance sidecar, clears the receipt).
- **Consumer verifier binds Stage 2 to the EXACT ORDERED Stage-1 contract
  (review 4729292850 P0 → review 4729337947 P0 fix).** The first draft checked
  only `{ticker,date,fwd_60d_excess_raw}` + keys + coverage + finite; the second
  draft added the three `SENTIMENT_COLUMNS` + a zero-extension check. Codex review
  4729337947 correctly found that a distinguishing-column heuristic still admits
  noncanonical artifacts — a 177-col file missing another required feature, a
  reordered schema, or a file with arbitrary extra columns all certified wrongly.
  The verifier now binds the consumed file to the **EXACT ORDERED 179-column
  contract** — `list(columns)` must equal the canonical schema exactly (same
  names, same order, same count). That ordered list is **IMPORTED** from the
  base-data builder that owns and writes the served sidecar
  (`renquant_base_data.rawlabel_sidecar.RAWLABEL_SIDECAR_COLUMNS`, base-data#49,
  merged), via the new fail-closed helper `_canonical_rawlabel_columns()` — never
  re-listed locally (avoiding the cross-repo-duplication P1 that bit Stage 1;
  base-data's schema-export drift guard is the versioned, reviewable attestation
  on the owner side). Every noncanonical shape is REFUSED: **reordered /
  missing-feature / extra-column / sentiment-free 176-col** all fail closed. The
  intrinsic **zero bar-frontier extension** check (§2.3 row-domain semantics) is
  retained: a key-only all-feature-NaN row is REFUSED even when its key is in
  panel-lockstep. If the canonical contract can't be imported, the file is
  REFUSED (never certified against an unknown schema).
- It **never opens the served sidecar for write** (AC-A). Read-only consumption:
  the corpus bytes are byte-identical before/after; no `.staging` file is created.
- Failure isolation, soft-skip-on-missing-panel, ntfy alerting, and the
  provenance/receipt/`assert_rawlabel_admissible` file-contract (RenQuant #427,
  by file-contract not import) are preserved — now anchored to the consumed file.
- CLI flag name `--refresh-rawlabel` / `--no-refresh-rawlabel` kept (weekly
  scripts wire it) — now gates the CONSUME step.

## Tests

- `tests/test_retrain_sigma_head_rawlabel.py` (rewritten to the consumer model,
  35 tests): **AC-A writer cessation** (the σ-head path never opens the served
  sidecar for write — byte-identical before/after, no staging; retired symbols
  gone); consume-verify-certify happy path; absent / invalid / out-of-lockstep
  canonical → isolated failure + invalidation receipt (corpus untouched); default
  consumer verifier rejection cases; provenance digest binding + tamper-detection
  + atomicity; admission helpers; pipeline isolation. **The 6-column proxy fixture
  is replaced with a REAL canonical-179 fixture built by running the merged
  Stage-1 base-data builder (`build_rawlabel_sidecar`) on a full 178-column fund
  panel + OHLCV** — the genuine artifact the sole writer publishes. The reviewer's
  **5-probe** is exercised against that real fixture: only the exact-179
  zero-extension file is **CERTIFIED**; a **176-col sentiment-free**, a **177-col
  missing-feature** (sentiment retained), a **+junk-column (180)**, a
  **reordered-179**, and a **179+bar-frontier-extension-row** file are ALL
  **REFUSED**. The three the old heuristic wrongly certified (missing-feature,
  junk-column, reordered) now refuse.
- `tests/test_sigma_head_fit_equivalence.py` (new, base-data sibling import):
  **AC-B σ-head fit INPUT-POPULATION equivalence** (relabeled honestly per review
  P1 — this is an INPUT claim, NOT byte-identical NGBoost σ artifacts). The
  retired σ-head self-build recipe is transcribed verbatim as the baseline; over
  the IDENTICAL labeled-row population (row-set digest equality, proper subset of
  all rows) the σ-head-consumed feature matrix + raw label from the canonical
  builder is **byte-identical INPUT** (max abs diff = 0.0) to the former
  self-build. A deterministic least-squares SURROGATE maps that identical input to
  identical coefficients — it demonstrates the input-identity ⇒ output-identity
  step for a fixed-seed estimator, but it is a stand-in, NOT the NGBoost σ head
  (this producer-only repo must not run training — CLAUDE.md). The fit-input
  comparison keys on the non-sentiment (169-col head) columns; that fit-scope
  fact makes the INPUT proof independent of the sibling builder, but it does NOT
  let Stage 2 certify a pre-amendment file — the 179/sentiment/zero-extension
  contract is bound fail-closed at the CONSUMPTION boundary by the consumer
  verifier above, not by this fit-equivalence proof. Plus AC-A base-data-side
  (the sole builder publishes the sidecar; zero extension rows; 179 pinned when
  the amendment builder is present).
- `tests/test_sidecar_176_consumer_evidence.py`: the three σ-head WRITER-conflict
  AC-1 evidence tests are removed (they exercised the retired functions and
  documented the now-resolved deadlock); surface-1 path-plumbing coverage kept.

## AC-B result

**INPUT-POPULATION equivalence HELD** (relabeled per review P1). Over the
identical labeled-row population (row-set digest equality; max abs diff 0.0) the
σ-head fit INPUT from the canonical builder equals the former self-build's, so
writer cessation loses nothing the σ-head fit consumes. This is an INPUT claim;
it is NOT a proof of byte-identical deployed NGBoost σ artifacts (the surrogate
least-squares only demonstrates input-identity ⇒ output-identity for a fixed-seed
estimator). The real fixed-seed NGBoost fit comparison + the full Saturday chain
are AC-C umbrella-stage work (below).

## Not in this PR

- The one supervised 179 regeneration + AC-2 digest integrity + Saturday-chain
  dry-run (AC-C) + sentinel retirement (AC-E) = ask-first UMBRELLA runbook (AC-D),
  never the scheduled job.
- **Real fixed-seed NGBoost σ-artifact equivalence (AC-C).** This PR proves fit
  INPUT-population equivalence only; the actual fixed-seed NGBoost fit producing
  byte-identical deployed σ heads runs in the umbrella integration/runbook stage
  (this producer-only repo must not run training — CLAUDE.md).
- **Rollout gating on the pinned base-data revision (AC-C/AC-D).** Stage 2's
  consumption is only sound once the SOLE writer publishing the 179-col canonical
  file is live — i.e. the umbrella pin is bumped to the base-data revision that
  merges base-data#49. Until then the fail-closed verifier simply refuses to
  certify (the pre-amendment 176-col file is REFUSED, not silently accepted). The
  pin bump + supervised regeneration is the umbrella runbook's job, not this PR.
- Provenance/receipt WRITE ownership ultimately moving to the sole writer is left
  to the AC-D umbrella runbook; this PR keeps the orchestrator certifying the
  CONSUMED file so the #427 admission contract is not orphaned in the interim.

Cites amendment base-data#48. Stage 1 = base-data#49 (merge order #49 → #553).

**No separate base-data export PR was needed to discharge review 4729337947.**
Stage 1 (base-data#49, merged) already exposes the exact ordered contract as the
importable module constant `RAWLABEL_SIDECAR_COLUMNS`
(`renquant_base_data.rawlabel_sidecar`), guarded by its committed schema-export
drift test — so the consumer binds to it directly (importing the ordered list is
a strict superset of a digest: same names, same order, same count, with
actionable diffs). `renquant-base-data` is already a declared dependency of this
repo, so the import resolves at the pinned base-data revision the umbrella deploys
(the rollout-gating note above is unchanged).
