# Blend-composite reconstruction: 0.9948-0.9979 — the served scoring stack is end-to-end reproducible offline

STATUS: measurement, read-only; task #26 serving-fidelity cell 3 (after
the full-window decomposition and the clean panel cell, orch#949).

## 1. Question and recipe

On the blend-served days (2026-08-04..08-07, `active_scorer='blend'`),
rebuild the composite from its two legs offline and compare to the
recorded `ticker_daily_state.panel_score` (which under blend records the
COMPOSITE — `blend_scorer.py:315`):

* leg 0 — the current prod panel artifact
  (`panel-ltr.alpha158_fund.json`, trained 2026-08-02, the golden
  config's pinned component), booster bytes + its own normalization
  through the production transform;
* leg 1 — momentum_residual v0, the ledger-served dated artifact in
  force on those dates (`artifacts/momentum/2026-08-02/…`, content sha
  a824c480…, n_scored 144), static per-name `scores`;
* composite = z(leg0) + z(leg1), cross-sectional ddof=0 per leg,
  NaN propagates (blend_scorer semantics).

The running config was verified in the PINNED strategy-104 checkout
(`configs/strategy_config.golden.json`: kind `blend`, component pins
6461b827… = the prod panel file's byte sha + `momentum-v0` recipe
fingerprint) — NOT in the umbrella `strategy_config.json`, whose
`panel_scoring.kind` still reads `hf_patchtst` (the assumed-tree lesson,
again; that stale surface is a separate hygiene item).

## 2. Result

| day | n | Spearman | top-5 overlap |
|---|---|---|---|
| 08-04 | 88 | 0.9970 | 5 |
| 08-05 | 94 | 0.9948 | 5 |
| 08-06 | 92 | 0.9974 | 5 |
| 08-07 | 92 | 0.9979 | 5 |

Median 0.9972, min 0.9948, top-5 overlap 5/5 on every day [VERIFIED —
committed `data/2026-08-09-blend-recon_daily.csv` +
`…-blend-recon_summary.json`, the committed script's VERBATIM outputs
(full precision in the artifacts; this table displays 4 decimals)].

## 3. Reading — what closes with this cell

Together with orch#949's cells, the serving-fidelity question is closed
across the whole live window:

| cell | window | agreement |
|---|---|---|
| pure panel, same artifact | 07-27..08-03 | 0.973-0.986 |
| pure panel, same artifact | 07-20..07-24 | ~0.84 (unattributed step, see below) |
| blend composite, both legs | 08-04..08-07 | 0.9948-0.9979 |

**The traded system's scoring stack is faithfully reproducible offline.**
The validated-vs-traded gap does NOT live in serving mechanics — it lives
in WHICH model family is served (z-blend vs the replay-validated per-fold
WF xgb), the candidate screen, and the admission gates. Repair attention
moves entirely there.

Remaining open (unchanged from orch#949 §5): the pre-07-27 step to ~0.84
— data-revision drift vs a ~07-26 serving-side change, unseparated. Note
the blend cell scores 0.995+ with TODAY'S rebuilt features on the SAME
week live ran, which is consistent with same-week features agreeing
almost perfectly and older weeks drifting — but it does not attribute the
step.

## 4. Reproduction

```
python data/2026-08-09-blend-recon-score.py \
  RenQuant/backtesting/renquant_104/artifacts/prod/panel-ltr.alpha158_fund.json \
  RenQuant/backtesting/renquant_104/artifacts/momentum/2026-08-02/momentum_residual_v0.json \
  <alpha158_extension_fund.parquet> <runs.alpaca.db> \
  2026-08-04 2026-08-07 data/2026-08-09-blend-recon
```
The committed evidence files are these outputs, unmodified. The extension
panel is rebuilt by the orch#948 recipe (hash-pinned builder patch +
fundamental merge; both scratch-only).
