# PREREGISTRATION (freeze on merge): clf WF corpus build — walkforward_clf_top_decile_fwd60_v1

Closes the design gap in orchestrator#788. Everything below is fixed BEFORE
any window is built for scoring purposes; the two probe artifacts (cost
measurement, scratchpad-only, 2026-08-04) are not part of the corpus.

## 1. Panel vintage — a PRESERVED dated copy, not a sha of a mutable path

- Vintage id: **2026-08-04**. Procedure (execution step 0, before any
  training): copy `data/alpha158_291_fundamental_dataset.parquet` →
  `data/research/alpha158_291_fundamental_dataset.vintage-2026-08-04.parquet`
  and record the sha256 of the COPY in the RUN_CLAIM (the live-path sha at
  freeze time, read back: `870f68ebad5d2d87…`; the claim must re-hash the
  copy).
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

The 43 post-seam cutoffs exactly as the Stage-2 lineage stamp enumerates them
(2023-10-02 … 2026-03-02, 3-week spacing — source: today's first
`lineage_stage2` stamp, post_seam segment). No pre-seam windows in v1: the
pre-seam panel vintage question is the same unpreserved-bytes problem and is
out of scope until a preserved pre-seam vintage exists.

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

## 6. Cost basis (measured 2026-08-04)

6 s/window warm (probe 2, stamped), ≤90 s cold, peak 5.94 GB → the 43-window
build is a single ~5-minute caffeinate loop after step 0's copy (~1 min for
797 MB). No Modal, no spend.
