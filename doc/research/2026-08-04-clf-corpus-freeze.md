# PREREGISTRATION (freeze on merge): clf WF corpus build — walkforward_clf_top_decile_fwd60_v1

Closes the design gap in orchestrator#788. Everything below is fixed BEFORE
any window is built for scoring purposes; the two probe artifacts (cost
measurement, scratchpad-only, 2026-08-04) are not part of the corpus.

## 1. Panel vintage — a PRESERVED dated copy, not a sha of a mutable path

- Vintage id: **2026-08-04**. The vintage is ALREADY MATERIALIZED (codex
  round 1: a freeze that copies later from a mutable path can silently drift):
  `data/research/alpha158_291_fundamental_dataset.vintage-2026-08-04.parquet`
  exists as of 2026-08-04 19:02 PT with full sha256
  `870f68ebad5d2d87e2601f62310f34615d2d8d25df9d9cbf563629b13129bf7e`
  (read back from the COPY, not the live path). FAIL-CLOSED RULE: build step 0
  re-hashes the copy and REFUSES on any mismatch with this digest — the
  corpus is impossible to build against different bytes while carrying this
  label. (The copy is a local data artifact, ~797 MB, deliberately not in
  git; this recorded digest is its immutable identity, and the RUN_CLAIM
  re-records the re-hash at build time.)
- WHY A COPY IS MANDATORY (measured today): Job B's `2026-08-01-rebuild`
  vintage recorded only `sha256_at_read_time=55811f63…` of the LIVE path; the
  daily retrain has since rewritten it (today: `870f68eb…`) — the Job-B
  vintage bytes are UNRECOVERABLE. A sha of a mutable path proves what was
  read, not what can be re-read. This corpus makes the dated copy the
  contract; the same rule is proposed for future ladders.
- Comparability caveat, stated at freeze: this corpus trains on the
  2026-08-04 vintage; the GBDT ladder used 2026-08-01 (3 days older, bytes
  unpreserved). Cross-family comparisons must treat the vintages as a
  DOCUMENTED difference; no cross-vintage pooled statistic is licensed.

## 2. Window grid — the post-seam ladder, verbatim

The exact ordered 43-cutoff list, frozen HERE (extracted from the first
`lineage_stage2` stamp's post_seam segment, staging artifact
`panel-ltr.alpha158_fund.weekly_20260804T200020Z.staging.json`, and now
independent of that mutable source):

```
2023-10-02, 2023-10-23, 2023-11-13, 2023-12-04, 2023-12-25,
2024-01-15, 2024-02-05, 2024-02-26, 2024-03-18, 2024-04-08,
2024-04-29, 2024-05-20, 2024-06-10, 2024-07-01, 2024-07-22,
2024-08-12, 2024-09-02, 2024-09-23, 2024-10-14, 2024-11-04,
2024-11-25, 2024-12-16, 2025-01-06, 2025-01-27, 2025-02-17,
2025-03-10, 2025-03-31, 2025-04-21, 2025-05-12, 2025-06-02,
2025-06-23, 2025-07-14, 2025-08-04, 2025-08-25, 2025-09-15,
2025-10-06, 2025-10-27, 2025-11-17, 2025-12-08, 2025-12-29,
2026-01-19, 2026-02-09, 2026-03-02
```

No pre-seam windows in v1: the pre-seam panel vintage question is the same
unpreserved-bytes problem and is out of scope until a preserved pre-seam
vintage exists.

## 3. Trainer invocation — frozen verbatim

`renquant-model scripts/train_topdecile_clf_shadow.py --data-dir <vintage-dir>
--out <corpus>/<cutoff>/panel-clf.json --train-cutoff <cutoff> --seed 42`
(the `--train-cutoff` handle truncates BEFORE build_normalization — the
leak-safe placement its own docstring pins). `<vintage-dir>` is a directory
containing ONLY the dated vintage copy under the panel's expected filename
(symlink-free staging dir), so the trainer cannot read the live panel by
accident. Recipe identity: `recipe_id=walkforward_only_v1` stamped by the
trainer; per-window `effective_train_cutoff_date` stamped from data.
NO recipe edits inside the build — a corpus that "improves" the recipe
measures nothing.

## 4. Corpus home + claim

`backtesting/renquant_104/artifacts/walkforward_clf_top_decile_fwd60_v1/`
with `RUN_CLAIM.json` (claimed_at, vintage copy path + re-hashed sha,
manifest sha over the per-window artifact shas — the Job-B claim shape) and a
manifest listing every window's cutoff + artifact sha256. Shadow-path guard:
the trainer's `refuse_non_shadow` requires a `shadow` path component — the
build stages into `…/shadow_build/` then the reviewed move publishes, OR the
trainer gains a corpus-path allowance in its own repo first; whichever, the
PUBLISHED corpus lives at the path above and the choice is recorded in the
claim (mechanical detail, not an outcome degree of freedom).

## 5. Scoring & acceptance (unchanged from #788's skeleton)

Stage-2 lane scores each window on its own OOS slice; segment-only pooling;
placebo arm = the gate's existing 120d shifted-label convention (2× the 60d
horizon). Acceptance: corpus admitted by the lineage path with n_scored ≥
42/43 (the final ladder window's "no closing edge" refusal is DESIGNED).
Verdict vocabulary: the readout reports per-window IC + placebo per segment;
NO promotion interest is licensed by this corpus alone — it makes the clf
lane's serving record interpretable (honest negative included).

## 5b. Immutable source revisions (read back at freeze)

Every executable input is pinned to a commit; the build refuses to run from
any other revision (step-0 check alongside the vintage re-hash):

- trainer: renquant-model `810646198e9e0896c615aee29454c705cae2f520`
  (`scripts/train_topdecile_clf_shadow.py` with the `--train-cutoff` handle)
- Stage-2 scoring lane: renquant-backtesting `8c2c445649570a79b292c22fd988a7becae0e612`
  (the deployed gate runner with `_attempt_stage2_stamp`)
- pipeline (loader/identity contracts incl. `momentum_identity`):
  `ab5db5ab831237705c9de78960bdd92df0a79101`
- umbrella at freeze: `514b6c4a5bc6728bb9b4b9a215b87de7f1b18268`

A revision bump for any of these is a REVISION of this preregistration (new
PR), not an execution-time discretion.

## 6. Cost basis (measured 2026-08-04)

6 s/window warm (probe 2, stamped), ≤90 s cold, peak 5.94 GB → the 43-window
build is a single ~5-minute caffeinate loop after step 0's copy (~1 min for
797 MB). No Modal, no spend.
