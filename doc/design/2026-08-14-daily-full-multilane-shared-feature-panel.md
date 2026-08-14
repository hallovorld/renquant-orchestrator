# Design: share the inference feature panel across daily-full lanes (G-K)

STATUS: **design for review (docs only — NO code / config / behavior change).**
DATE: 2026-08-14. Operator-directed ("压" — compress the daily-full runtime, after the
G-J per-lane feature-prep speedup landed). Per operator: approve this design BEFORE implementing.

## 1. Bottom line
The daily-full runs **~6 sequential lanes** (prod + 5 shadow scoring variants), and **each
re-runs the full ~10-min feature-prep** — because the inference feature cache key includes the
per-lane **scorer** config (`panel_scoring`). The feature panel is **hypothesized** scorer-independent
(a HYPOTHESIS the §5 oracle must PROVE — see §4/§5 — not an established fact); IF proven, this is
~6× redundant computation. Proposed fix: strip the scorer config from the **feature** cache key so
lanes with identical feature inputs share ONE cache entry (compute once, re-score per lane) → 6
feature-preps → 1. Output-invariant ONLY IF §5's four-artifact byte-identity proof passes (same
frames, same scores); flag-gated. This compounds with G-J (already deployed).

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

## 4. Fix (output-invariant — CONDITIONAL on the §5 proof)
Proposed change (authorized to implement ONLY after §5 proves scorer-independence): remove
scorer-only config (`panel_scoring`) from the FEATURE cache fingerprint; key only on the
**feature-relevant** inputs (watchlist, ohlcv shape/date, ticker_sectors, benchmark, the
`panel_ltr` FEATURE/model recipe, sector_etf_map, side-data source fingerprints). Then all lanes
sharing the same feature inputs share ONE cache entry: lane 1 computes (now ~1.4 min post-G-J),
lanes 2-6 HIT the cache → the feature-prep is paid ONCE per daily-full instead of ~6×. Scorer-
independence is a hypothesis until §5's four-artifact byte-identity oracle passes across every
resolved lane config; if any returned artifact differs, keep the differing field in the key (retain
that key subset) rather than sharing the entry.

## 5. Output-invariance — MUST be PROVEN, not assumed (the crux)
`prepare_inference_panel_frames` returns **FOUR** artifacts (`neutralized_frames, factor_frames,
macro_frame, asset_embeddings` — `asset_embeddings` was added as the 4th return value 2026-04-27,
`training_panel/pipeline.py`) and scoring happens later — BUT the panel-jobs file
(`pp_panel_training.py`) DOES read `ranking.panel_scoring` in places (inference `artifact_path`,
`ngboost`, `global_calibration`). So we CANNOT assume ANY of the four returned artifacts is
scorer-blind. Mandatory gate before the cache-key change:
- Enumerate **every resolved lane config** the daily-full actually runs — the prod lane plus every
  shadow lane `scripts/daily_104.sh` resolves — by **reading the script at proof time**, never from a
  list written here. A hand-picked "≥2" is insufficient, and so is a hardcoded roster: a
  lane-specific conditional field (a scorer sub-key only one lane sets) must be exercised, so the
  oracle has to use the real fleet.

  **Why the roster is not written into this document:** an earlier revision of this section named
  the lanes by their lane/log **alias** and conflated those aliases with config filenames — which is
  exactly the mistake that makes a prose roster unreliable. The distinct shadow config filenames
  actually referenced by `scripts/daily_104.sh` are **five** — `strategy_config.shadow_blend.json`,
  `…shadow_blend_momentum.json`, `…shadow_blend_momentum_fast.json`, `…shadow_blend_rb_fast.json`,
  `…shadow_blend_rb_mom.json`. The lane/log **aliases** `shadow_blend_mom` and `shadow_blend_mom_fast`
  (used ONLY for `${DATE}_<lane>.log` filenames and the `RENQUANT_READONLY_TAG`) are NOT config
  filenames: the Step 5b lane logged as `shadow_blend_mom` resolves
  `strategy_config.shadow_blend_momentum.json`, and the Step 5c lane logged as `shadow_blend_mom_fast`
  resolves `strategy_config.shadow_blend_momentum_fast.json` — there is no
  `strategy_config.shadow_blend_mom.json` in the script or the pinned strategy configs. The §2 lane
  list uses those log aliases (matching the log filenames); the config-filename roster here is the
  five above `[VERIFIED — grep -oE 'strategy_config\.shadow[a-z_]*\.json' scripts/daily_104.sh →
  5 distinct filenames, none named shadow_blend_mom.json, 2026-08-14]`. A roster frozen in prose goes
  stale the moment a lane is added or renamed — and, as this very alias/filename slip shows, is easy
  to get wrong even when current — making the oracle silently incomplete while still reading as
  exhaustive. **The requirement is therefore "every lane the script resolves", enforced by
  enumerating from the script, with the resolved set recorded in the proof's own output.**
- Run `prepare_inference_panel_frames` on the SAME feature inputs under each resolved lane config;
  assert **ALL FOUR** returned artifacts are **byte-identical** across every lane pair —
  `neutralized_frames`, `factor_frames`, `macro_frame`, AND `asset_embeddings`
  (`pd.testing.assert_frame_equal(check_exact=True)` for frames; exact array/dict equality for
  embeddings). Omitting `asset_embeddings` (or any of the four) leaves a path by which a scorer
  field silently changes scores.
- Plus a **lane-2 cache-hit proof**: after lane 1 writes the shared entry under the proposed
  feature-only key, lane 2 (a *different* `panel_scoring`) must HIT that entry (no recompute) AND
  produce byte-identical frames — proving the shared entry is both reused and correct.
- If ALL four are identical across ALL resolved lane configs AND the cache-hit proof passes →
  `panel_scoring` is safe to strip from the feature key.
- If ANY artifact differs for ANY lane → the frames depend on some scorer field; identify the
  **exact scorer-INDEPENDENT subset** the frames actually use and key on that (retain the differing
  key subset rather than sharing that cache entry). NEVER strip a key the returned artifacts read
  (that would silently change scores — a regression).

## 6. Open verification (design → implementation)
- **Cross-lane cache parity:** do the shadow lanes share `panel_ltr` + `inference_frame_cache.cache_dir`
  (prod = `artifacts/cache/inference_frames`)? Lane isolation (`RENQUANT_READONLY_TAG`) routes STATE
  (`live_state.*`, `runs.*.db`) to disjoint per-lane paths — but the feature panel is NOT lane-state;
  the shared cache must live at a common feature-cache path, distinct from those per-lane state dbs.
  Confirm each lane's resolved cache dir, and route the feature cache to a shared location if needed.
- Confirm the ~6-lane list and that all lanes use the same watchlist/ohlcv/date (they should — same
  universe, same session).

## 7. Plan
This design PR → codex approve → implementation **in the owning subrepo `renquant-pipeline`** (see
§8 for the owner-of-record + migration/thin-adapter story — NOT a new umbrella edit): the
cache-fingerprint change + the §5 four-artifact byte-identical oracle over every resolved lane
config + a lane-sharing test proving lane 2 HITs the entry lane 1 wrote → codex → **operator-gated
live-tree deploy** (like G-J). Behavior-invariant (identical scores per lane, only faster).
**Flag-gated** — a config toggle to fall back to the current per-scorer key.

## 8. Boundary & repo ownership (per `RENQUANT_REPOS.md`)
- **Owner-of-record = `renquant-pipeline`, NOT the umbrella.** `RENQUANT_REPOS.md` is explicit:
  runtime inference/decision code belongs in `renquant-pipeline`; "never add code to the umbrella
  `RenQuant` (integration/rollback only)". The cache-fingerprint is inference-runtime code, so its
  home is `renquant-pipeline` — it is NOT umbrella-owned merely because the only current copy of
  `training_panel/pipeline.py` (consumed at runtime via umbrella `adapters/panel_runtime.py`)
  happens to live in the umbrella today `[VERIFIED — grep: file exists only under
  backtesting/renquant_104/…; renquant-pipeline has no training_panel/pipeline.py]`.
- **Pre-existing boundary debt (do NOT deepen it).** The feature-prep module and G-J's own perf
  change (SPY-hurst memoize, PR #591, 2026-08-14) both currently live in the umbrella copy — a
  pre-existing migration gap, NOT a licence for G-K to add a third runtime edit to the umbrella.
  G-K must not bless umbrella ownership by default.
- **Migration / thin-adapter path.** Two acceptable shapes, decided at implementation with codex:
  (a) migrate the feature-prep cache-key surface into `renquant-pipeline` (its rightful home) and
  have the umbrella `adapters/panel_runtime.py` import from the subrepo via a thin adapter, landing
  the G-K change there; or (b) if the full module migration is out of G-K's scope, land the change
  in `renquant-pipeline` behind a thin shim and pin it from the umbrella — reconciling the shared
  G-J debt in the same step. Either way the code + its §5 oracle + lane-sharing test live in
  `renquant-pipeline`, paired-PR into the umbrella pin only. This design is authored in the
  orchestrator (the run-orchestration owner); it authorizes no code and picks the shape at
  implementation time with codex, but names `renquant-pipeline` as owner so the umbrella is not the
  default.
- **Context:** G-J (deployed 2026-08-14) already cut EACH lane's feature-prep 10.6→1.4 min, so the
  daily-full is expected ~83 → ~20-30 min already; G-K removes the residual ~6× on the feature-prep
  portion (6×1.4 → 1×1.4). Confirm the G-J magnitude from the first post-G-J daily-full before
  sizing G-K's marginal gain.
