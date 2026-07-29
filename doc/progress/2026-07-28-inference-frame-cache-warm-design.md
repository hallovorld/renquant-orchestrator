# Progress: inference-frame cache design memo (PR #589)

STATUS:   CONFIRMED and merge-ready (design memo only, no code). Round-2
          revision after codex's HIGH finding (original Proposal A's
          "fail-closed" allowlist was actually fail-open on an omitted
          field). Operator confirmed adopting A′ (revised) + B together
          in-session `[VERIFIED — PR #589 comment
          https://github.com/hallovorld/renquant-orchestrator/pull/589#issuecomment-5113613780,
          2026-07-29T05:28:33Z]`, no amendment to the 5-point recommendation.

WHAT:     Adds `doc/research/2026-07-28-inference-frame-cache-warm-design.md`.
          Documents that `training_panel/pipeline.py::_selected_config_fingerprint`
          puts the ENTIRE `ranking.panel_scoring` block into the inference-frame
          cache key — including `artifact_path`, `buy_floor`, `sizing` and
          thresholds, none of which change frame content — so any model swap or
          profile variation forces a full 145-ticker rebuild `[VERIFIED —
          watchlist length, per the research doc's own citation]`.

WHY/DIR:  Not only speed: on the production-shaped path a cold key hit a
          1800.07 s hard timeout and RuntimeError-aborted the session
          `[VERIFIED — /tmp/ptprod_e2e.log, "timed out after 1800.07s"]`
          ("aborting live inference instead of silently trading without panel
          scores"). A model swap or a threshold edit can therefore take the next
          daily session down — GOAL-5 reliability class. Proposal A′ (revised)
          replaces the withdrawn allowlist design with a structural fix: a
          typed, versioned `FrameRecipe` object is the builder's *only*
          config-shaped input, so a field the builder cannot read cannot
          silently affect frame content while being excluded from the
          fingerprint — closing the fail-open gap the allowlist design had
          (an omitted frame-affecting field would keep matching a stale cache
          entry instead of missing). Cache-version bump so old entries cannot
          be reinterpreted. Proposal B pre-builds frames once daily after the
          data refresh, through the identical `FrameRecipe`/freshness code
          path as live serving (no bypass of freshness/integrity gates), so
          every lane starts warm.

EVIDENCE:
artifact:      training_panel/pipeline.py (`_inference_frame_cache_key`, `_selected_config_fingerprint`); `/tmp/ptserve_e2e.log`, `/tmp/ptprod_e2e2.log`, `/tmp/ptprod_e2e.log` (the three 2026-07-28 cold-rebuild sessions); `artifacts/cache/inference_frames` (67 entries as of this session, a live/growing counter — 62 when an earlier draft was written)
prod or exp:   prod — production-shaped live-inference path, not a sim/experiment harness
existing data: three independent cold rebuilds, re-measured directly this session from each log's own timestamps: ~795 s (`/tmp/ptserve_e2e.log`, run start to cache-WRITE line) `[VERIFIED]`, ~1201 s (`/tmp/ptprod_e2e2.log`, same method) `[VERIFIED]`, and one run raising `prepare_inference_panel_frames timed out after 1800.07s` → `RuntimeError: Panel frame prep failed while panel_scoring.enabled=true` `[VERIFIED — /tmp/ptprod_e2e.log lines 254/263/286]` (an earlier draft cited 751s/1355s/"1200s" — corrected here, those figures matched no log on disk); multiple 2026-07-28 daily logs each show a `cache HIT` `[VERIFIED — /tmp/daily_shadow_verify.log:190, /tmp/daily_live_early.log:190, /tmp/step5_live_now2.log:191]`, confirming the cache mechanism itself works; key composition confirmed by direct read of `_inference_frame_cache_key` / `_selected_config_fingerprint` source `[VERIFIED — training_panel/pipeline.py, this repo]`, which feeds the whole `ranking.panel_scoring` block (incl. `artifact_path`, `buy_floor`, `sizing`, thresholds) into the key
best-known?:   n/a — this is a design memo identifying a defect (over-specified cache key), not a model/variant performance comparison; no narrower-key implementation exists yet to compare against
scope:         claim is scoped to the three measured cold-rebuild runs on this machine on 2026-07-28 plus the source-level read of the cache-key composition; does not claim a production-wide timeout-hit frequency. No model/IC/Sharpe number is claimed, so the §4(b) sanity triad does not apply.

NEXT:     Confirmed. The implementation PR belongs in the canonical kernel
          (renquant-pipeline) with the umbrella fork mirrored in the same
          batch — the fork-divergence class already hit twice today (blend
          `kind` unknown; `adaptive_quantile` buy_floor unsupported in the
          umbrella copy).
