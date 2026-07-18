# Progress: AC-1 sidecar 176-column consumer evidence (orchestrator surfaces)

Date: 2026-07-18
Scope: test-only companion to the renquant-base-data RFC
`doc/design/2026-07-18-rawlabel-sidecar-sentiment-reconciliation.md` (AC-1)
and its evidence appendix (the base-data PR carries the full inventory).

## What this PR adds

`tests/test_sidecar_176_consumer_evidence.py` +
`tests/fixture_rawlabel_sidecar_columns_176.json` (embedded export of
base-data `RAWLABEL_SIDECAR_COLUMNS` @ main `b72dd92`; drift guard =
base-data `tests/test_rawlabel_sidecar_schema_export.py`), pinning both
orchestrator surfaces of the served
`alpha158_291_fundamental_dataset_rawlabel.parquet`:

1. `build_patchtst_wf_manifest` / `retrain_patchtst` — pure path plumbing to
   `renquant_model_patchtst.fit_calibrator --raw-label-panel`; no parquet is
   opened here; safe at 176 transitively.
2. `retrain_alpha158_fund` σ-head refresh — **an ACTIVE WRITER, not just a
   reader** (weekly via `weekly_wf_promote.sh` →
   `daily_retrain_alpha158_fund.sh`). Pinned executably:
   - `_default_rawlabel_build_fn` emits the full panel schema + raw label —
     sentiment INCLUDED (the 179-column contract) — from a sentiment-carrying
     panel;
   - `_default_rawlabel_validate_fn` never checks the column contract
     (keys/label/coverage only): it admits 176-column and 179-column staged
     files alike;
   - it REJECTS bar-frontier extension rows, so a base-data-built (176-col,
     axis-extended) sidecar cannot be revalidated by the σ-head path as-is.

This is the AC-1 finding that a one-time 179→176 served-file migration is
insufficient by itself: the next σ-head refresh re-emits sentiment and
re-arms the weekly PatchTST corpus-refresh deadlock unless the two writer
recipes are unified. Evidence only — the fix is a design call in the RFC's
rollout (base-data owns the recipe decision).

## What this PR does NOT do

No behavior change, no migration, no served-file mutation.
