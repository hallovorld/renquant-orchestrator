# Extension corpus reproduces the frozen corpus bit-for-bit; the scoring window now exists (orch#939)

STATUS: measurement, read-only inputs; scratch-only outputs (nothing under
RenQuant was written). Unblocks task #26's full-width replay-vs-served
comparison and the Stage-C extension corpus (model#215 §2b).

## 1. What was built

The frozen xgb_mom_60d corpus (`RenQuant/data/alpha158_291_fundamental_dataset.parquet`,
sha256 `870f68eb…`) ends 2026-05-07 because the builder
(`RenQuant/scripts/build_alpha158_qlib.py`) drops every row whose forward
labels are not yet computable (`dropna(subset=[fwd_5d/20d/60d_excess])`,
line 448) — the last ~60 trading days of features never survive. Live
scoring starts 2026-05-20 (`ticker_daily_state`), so replay and served
scores had ZERO shared dates (the orch#937/#938 finding's structural gap).

A scratch copy of the builder was changed in exactly two places
(never the umbrella tree — the copy ran from the session scratchpad):

1. `REPO_ROOT` pinned to `/Users/renhao/git/github/RenQuant` (line 97
   resolves relative to `__file__`, which breaks for an out-of-tree copy —
   the first rerun failed on exactly this and exit-code masking in a `;`
   chain briefly hid it; visible correction in the 19:45 loop round);
2. the label `dropna` replaced by a keep-and-count (feature rows are kept
   when their forward labels are NaN; rows missing all features still drop).

Output: `alpha158_extension_full.parquet` (scratch, 794MB, not committed —
rebuildable by the two-line recipe above).

## 2. The invariance claim, checked

Committed checker: `data/2026-08-09-overlap-invariance-check.py`
(FEATS and the corpus pin are ast-read from the committed harness
`renquant-model/doc/design/frozen/2026-08-09-xgbmom-v2-harness.py`; the
frozen parquet's sha256 is asserted against that pin before comparison;
paths are CLI arguments so the check is machine-independent).
Report: `data/2026-08-09-overlap-invariance-report.json`.

| quantity | value |
|---|---|
| shared (date,ticker) rows | 726,128 (= every frozen row; frozen-only rows 0) |
| worst feature abs diff over 70 frozen features | **0.0** |
| feature NaN mismatches | **0** |
| verdict | invariant on shared rows, bit-for-bit |

[VERIFIED — checker run 2026-08-09, exit 0, printed JSON above matches the
committed report.]

So the extension build is the SAME measurement process as the corpus the
v2 verdict ran on, not a near-reproduction.

## 3. What the extension window contains

| slice | rows | detail |
|---|---|---|
| extension window (date > 05-07) | 9,953 | 63 trading days 2026-05-08..2026-08-07, all 292 tickers |
| … with fwd_5d_excess label | 8,771 | usable for 5d-horizon checks now |
| … with fwd_60d_excess label | 432 | only the earliest days; the 60d tail realizes on its own clock |
| historical resurrected rows (date ≤ 05-07) | 8,616 | 150 tickers, label-gap rows the frozen build dropped mid-history (COHR 504 = the largest gap); **excluded by construction** from any extension corpus — the frozen window stays exactly the frozen corpus |

[VERIFIED — split computed 2026-08-09 from the scratch parquet vs the
frozen parquet; the committed checker reports the aggregate new-row count
(18,569 = 9,953 + 8,616).]

## 4. What this unlocks and what it does not

* Unlocks (task #26): replay-side scores can now be computed on the same
  dates live scored (05-20..08-07) — the full-width comparison against
  `ticker_daily_state` (~92 served scores/day) becomes constructible.
* Unlocks (model#215 §2b): the Stage-C extension corpus source exists;
  Stage C itself stays frozen until its deterministic clock (~Nov 2026)
  and takes ONLY `date > 05-07` rows.
* Does NOT: no scores were computed here, no comparison run, no verdict of
  any kind. fwd_60d labels cover only 432 extension rows — any 60d-horizon
  evaluation on this window is out of reach until the calendar delivers.

NEXT: score the extension window with the replay-side model, join to
`ticker_daily_state`, publish the full-width overlap/rank-correlation
table (task #26 acceptance surface).
