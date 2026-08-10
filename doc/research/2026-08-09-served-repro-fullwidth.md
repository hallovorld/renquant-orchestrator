# Served-model reproduction: same-artifact pure-panel days reproduce at 0.97-0.99 in the late window

STATUS: measurement, read-only; task #26 first acceptance table. REVISES
the working narrative around orch#931 (see §4).

## 1. Question

On the dates live actually scored (2026-05-20..08-07), does scoring the
extension panel (orch#948: FEATURES invariant bit-for-bit with the frozen
corpus — labels excepted on one boundary date, 2026-05-07 — 172/172
columns after the fundamental merge) with the SERVED artifact —
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
`data/2026-08-09-served-repro-cleancell_daily.csv` +
`…cleancell_summary.json`, which are the committed script's VERBATIM
outputs for the §6 clean-cell invocation (full precision in the artifact;
this table displays 4 decimals). An earlier revision committed a
hand-rounded/renamed copy instead — review-caught; the artifact is now
script-native with no manual transform].

## 4. Reading (scoped to what this cell measures — review r2)

What IS measured: on 11 pure-panel days scored by the artifact this cell
loads, offline panel scoring associates with the recorded `panel_score`
at 0.836-0.986 daily Spearman — 0.973-0.986 in the late window
(07-27..08-03). That is a HIGH SAME-ARTIFACT / PURE-PANEL ASSOCIATION IN
THE LATE WINDOW, and it is the only conclusion this cell carries.

What this cell does NOT test (each retained as UNRESOLVED here):
* the candidate screen (score → candidate set) — untested;
* the blend composite — not reproduced in this PR (measured separately,
  PR #950);
* transform-version drift — the offline transform ran the PINNED pipeline
  checkout; the live tree's version on those dates is not isolated;
* the pre-07-27 step down to ~0.84 — unattributed here [GUESS — candidate
  causes: (a) OHLCV/SEC revisions accumulating with lookback distance;
  (b) a serving-side change around 07-26].

Bearing on #931: the specific full-window number 0.684 decomposes into
artifact identity + blend-composite semantics — those two confounds, once
removed, leave high association on the days measured. Any wider
"feature transport is clean" or "the residual gap is model family +
candidate screen" claim needs the other cells and the untested surfaces
above; it is NOT established by this PR.

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
`panel_ltr_xgboost`, out_prefix `…-served-repro-cleancell` →
`…-served-repro-cleancell_daily.csv` / `…cleancell_summary.json`
(the committed files ARE these outputs, unmodified). The extension panel
is rebuilt by the orch#948 recipe (two-line builder patch + fundamental
merge; both scratch-only).
