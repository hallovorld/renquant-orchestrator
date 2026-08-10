# Served-model reproduction, full-width: 0.97-0.99 same-week with the right artifact — the feature pipeline is substantially clean

STATUS: measurement, read-only; task #26 first acceptance table. REVISES
the working narrative around orch#931 (see §4).

## 1. Question

On the dates live actually scored (2026-05-20..08-07), does scoring the
extension panel (orch#948: bit-for-bit invariant with the frozen corpus,
172/172 columns after the fundamental merge) with the SERVED artifact —
its own booster bytes, its own normalization, through the production
transform (`renquant_pipeline...feature_transform.transform_feature_frame`,
`source_space='panel'`) — reproduce the scores recorded in
`ticker_daily_state` (canonical run per date)?

## 2. The confound that had to be split first

The naive full-window comparison (current artifact vs all recorded scores)
gives median daily Spearman 0.684 [VERIFIED — committed
`data/2026-08-09-served-repro-daily.csv`, 36 days ≥10 joined names] — but
that number is UNINTERPRETABLE, because the window mixes:

* **artifact identity**: the current prod artifact is trained 2026-08-02;
  live days 07-20..08-03 were served by the previous artifact
  (training_cutoff 2026-06-21, DB `model_content_sha256` sha256:656b70be…);
* **score semantics**: from 08-04 `active_scorer='blend'`, and under blend
  the recorded `panel_score` is the blend COMPOSITE
  (pipeline `blend_scorer.py:315`), not the panel leg — comparing a panel
  leg to a composite bounds Spearman well below 1 by construction.

## 3. The clean cell

Days 07-20..08-03 with `active_scorer='panel_ltr_xgboost'` (pure panel
score recorded), scored offline with the artifact that served them:
`artifacts/prod/panel-ltr.alpha158_fund.previous.json` — trained_date
2026-06-21 matching the DB cutoff; part of the 507,224-byte family the
07-16 binding-fix note identifies as "v1 content hash 656b70be" [VERIFIED —
the calibration rollback metadata's literal text; the v1-hash recipe
itself was not re-derived — identity rests on trained_date + the binding
note + the byte-identical rollback family, caveat §5].

| day | n | Spearman | top-5 overlap |
|---|---|---|---|
| 07-20 | 79 | 0.8615 | 3 |
| 07-21 | 78 | 0.8415 | 3 |
| 07-22 | 77 | 0.8360 | 3 |
| 07-23 | 77 | 0.8398 | 3 |
| 07-24 | 76 | 0.8393 | 3 |
| 07-27 | 84 | 0.9861 | 5 |
| 07-28 | 85 | 0.9734 | 5 |
| 07-29 | 84 | 0.9801 | 4 |
| 07-30 | 83 | 0.9801 | 5 |
| 07-31 | 83 | 0.9749 | 5 |
| 08-03 | 84 | 0.9789 | 5 |

Median 0.9734, mean top-5 overlap 4.0 [VERIFIED — committed
`data/2026-08-09-served-repro-cleancell.csv`; reproduced by the committed
script, invocation in §6].

## 4. Reading

1. **The serving feature path substantially reproduces the panel build in
   the freshest week: 0.973-0.986 Spearman, top-5 overlap 4-5/5.** With
   the right artifact and the right score semantics, served ≈ offline.
2. The step down to ~0.84 for 07-20..24 and the earlier-window decay are
   consistent with **lookback data-revision drift** (the offline panel is
   built from TODAY's OHLCV/SEC files; live scored with that day's files —
   revisions accumulate with distance) [GUESS — two candidate causes, not
   separated: (a) OHLCV/SEC revisions; (b) a serving-side fix deployed
   around 07-26 changing live feature computation. Separable by rebuilding
   from an older OHLCV snapshot or reading the live tree's deploy log.]
3. This REVISES the #931-derived working narrative "the served scores
   diverge from panel features" — at least for late July onward, the
   divergence measured earlier is dominated by artifact identity and blend
   compositing, NOT by a broken feature pipeline.
4. The remaining gap for the replay-vs-served story is therefore the MODEL
   FAMILY (z-blend composite vs validated per-fold WF xgb) and the
   candidate screen — not feature transport.

## 5. Caveats

* Artifact identity for the clean cell rests on trained_date + binding
  note + byte-family; the v1 content-hash function was not located in the
  pinned checkouts (2 recipe guesses failed; abandoned per the 2-3-failures
  rule). If that function lives in the live runtime tree and disagrees,
  the cell's artifact could in principle be a different member of the
  same-bytes family — which would not change the numbers.
* The offline transform ran the PINNED pipeline checkout's
  `feature_transform`; the live tree may have run a different version on
  those dates (the assumed-tree lesson) — unseparated from §4.2(b).
* Blend-day reproduction of the composite (reconstructing the z-blend from
  its legs) is NOT done here; it is the natural next cell.

## 6. Reproduction

```
python data/2026-08-09-served-repro-score.py \
  <artifact.json> <alpha158_extension_fund.parquet> <runs.alpaca.db> \
  <W0> <W1> [active_scorer_filter] [out_prefix]
```
Full window: current prod artifact, 2026-05-20..2026-08-07, no filter →
`…-served-repro-daily.csv` / `…-summary.json`. Clean cell:
`panel-ltr.alpha158_fund.previous.json`, 2026-07-20..2026-08-03, filter
`panel_ltr_xgboost` → `…-served-repro-cleancell.csv`. The extension panel
is rebuilt by the orch#948 recipe (two-line builder patch + fundamental
merge; both scratch-only).
