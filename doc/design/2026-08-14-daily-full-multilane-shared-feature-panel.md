# Design: share the inference feature panel across daily-full lanes (G-K)

STATUS: **design for review (docs only — NO code / config / behavior change).**
DATE: 2026-08-14. Operator-directed ("压" — compress the daily-full runtime, after the
G-J per-lane feature-prep speedup landed). Per operator: approve this design BEFORE implementing.

## 1. Bottom line
The daily-full runs **~6 sequential lanes** (prod + 5 shadow scoring variants), and **each
re-runs the full ~10-min feature-prep** — because the inference feature cache key includes the
per-lane **scorer** config (`panel_scoring`). The feature panel is scorer-independent, so this is
~6× redundant computation. Fix: strip the scorer config from the **feature** cache key so lanes
with identical feature inputs share ONE cache entry (compute once, re-score per lane) → 6
feature-preps → 1. Output-invariant (same frames, same scores), flag-gated. This compounds with
G-J (already deployed).

## 2. Measured structure `[VERIFIED — 08-12 lane logs + daily_104.sh]`
- `daily_104.sh` runs Step 3 prod (`--broker alpaca --once`) + Step 5+ shadow lanes:
  `shadow_blend`, `shadow_blend_mom`, `shadow_blend_mom_fast`, `shadow_blend_rb_fast`,
  `shadow_blend_rb_mom` — **~6 lanes, sequential**, each to its own `logs/daily_104/<date>_<lane>.log`.
- The lane logs each contain their OWN feature-prep: `2026-08-12_shadow_blend.log` (14:21→14:33)
  and `2026-08-12_shadow_blend_mom.log` (14:33→14:44) each show a ~10-min
  `prepare_inference_panel_frames` (20-21 progress lines) + one `InferencePipeline START`.
- So the ~72-min "tail" after the prod decision is **the 5 shadow lanes running one-after-another**,
  each dominated by feature-prep — NOT order-working/retries (the "BUY … FAILED" lines are per-lane
  decision outputs, not a retry loop).

## 3. Root cause `[VERIFIED — training_panel/pipeline.py]`
The feature cache key = `_inference_frame_cache_key(watchlist, ohlcv, ticker_sectors, config)` →
`_selected_config_fingerprint(config)`, which includes **`ranking.panel_scoring`** (the scorer).
Each lane has a different `panel_scoring` (solo-xgb / blend / blend+mom / rb …) → a different
cache_key → a cache MISS → each lane recomputes the **identical** feature panel.

## 4. Fix (output-invariant)
Remove scorer-only config (`panel_scoring`) from the FEATURE cache fingerprint; key only on the
**feature-relevant** inputs (watchlist, ohlcv shape/date, ticker_sectors, benchmark, the
`panel_ltr` FEATURE/model recipe, sector_etf_map, side-data source fingerprints). Then all lanes
sharing the same feature inputs share ONE cache entry: lane 1 computes (now ~1.4 min post-G-J),
lanes 2-6 HIT the cache → the feature-prep is paid ONCE per daily-full instead of ~6×.

## 5. Output-invariance — MUST be PROVEN, not assumed (the crux)
`prepare_inference_panel_frames` returns pure frames (`neutralized_frames, factor_frames,
macro_frame, asset_embeddings`) and scoring happens later — BUT the panel-jobs file
(`pp_panel_training.py`) DOES read `ranking.panel_scoring` in places (inference `artifact_path`,
`ngboost`, `global_calibration`). So we CANNOT assume the returned frames are scorer-blind.
Mandatory gate before the cache-key change:
- Run `prepare_inference_panel_frames` with ≥2 different `panel_scoring` configs on the SAME
  feature inputs; assert the neutralized + factor + macro frames are **byte-identical**
  (`pd.testing.assert_frame_equal(check_exact=True)`).
- If identical → `panel_scoring` is safe to strip from the feature key.
- If they differ → the frames depend on some scorer field; identify the **exact
  scorer-INDEPENDENT subset** the frames actually use and key on that. NEVER strip a key the
  returned frames read (that would silently change scores — a regression).

## 6. Open verification (design → implementation)
- **Cross-lane cache parity:** do the shadow lanes share `panel_ltr` + `inference_frame_cache.cache_dir`
  (prod = `artifacts/cache/inference_frames`)? Lane isolation (`RENQUANT_READONLY_TAG`) routes STATE
  (`live_state.*`, `runs.*.db`) to disjoint per-lane paths — but the feature panel is NOT lane-state;
  the shared cache must live at a common feature-cache path, distinct from those per-lane state dbs.
  Confirm each lane's resolved cache dir, and route the feature cache to a shared location if needed.
- Confirm the ~6-lane list and that all lanes use the same watchlist/ohlcv/date (they should — same
  universe, same session).

## 7. Plan
This design PR → codex approve → implementation (umbrella `training_panel/pipeline.py`: the
cache-fingerprint change + the §5 byte-identical test + a lane-sharing test proving lane 2 HITs the
cache lane 1 wrote) → codex → **operator-gated live-tree deploy** (like G-J). Behavior-invariant
(identical scores per lane, only faster). **Flag-gated** — a config toggle to fall back to the
current per-scorer key.

## 8. Boundary & context
- The cache-key code is **umbrella-owned** (`backtesting/renquant_104/training_panel/pipeline.py`);
  the implementation is an umbrella PR + operator-gated live-tree deploy. This design is authored in
  the orchestrator (the run-orchestration owner).
- **Context:** G-J (deployed 2026-08-14) already cut EACH lane's feature-prep 10.6→1.4 min, so the
  daily-full is expected ~83 → ~20-30 min already; G-K removes the residual ~6× on the feature-prep
  portion (6×1.4 → 1×1.4). Confirm the G-J magnitude from the first post-G-J daily-full before
  sizing G-K's marginal gain.
