# Progress: inference-frame cache design memo (PR #589)

STATUS:   CONFIRMED and merge-ready (design memo only, no code). Round-2
          revision after codex's HIGH finding (original Proposal A's
          "fail-closed" allowlist was actually fail-open on an omitted
          field). Operator confirmed adopting A′ (revised) + B together
          in-session (2026-07-28/29), no amendment to the 5-point recommendation.

WHAT:     Adds `doc/research/2026-07-28-inference-frame-cache-warm-design.md`.
          Documents that `training_panel/pipeline.py::_selected_config_fingerprint`
          puts the ENTIRE `ranking.panel_scoring` block into the inference-frame
          cache key — including `artifact_path`, `buy_floor`, `sizing` and
          thresholds, none of which change frame content — so any model swap or
          profile variation forces a full 145-ticker rebuild.

WHY/DIR:  Not only speed: on the production-shaped path a cold key hit the
          1200 s ceiling and RuntimeError-aborted the session
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
artifact:      training_panel/pipeline.py (`_inference_frame_cache_key`, `_selected_config_fingerprint`); run logs for the three 2026-07-28 cold-rebuild sessions on this machine; `artifacts/cache/inference_frames` (62 entries)
prod or exp:   prod — production-shaped live-inference path, not a sim/experiment harness
existing data: `[VERIFIED — direct log read]` three independent cold rebuilds: 751 s, 1355 s, and one run raising `prepare_inference_panel_frames timed out after 1200s` → `RuntimeError: Panel frame prep failed while panel_scoring.enabled=true`; the 2026-07-28 daily log shows one `cache HIT`, confirming the cache mechanism itself works; key composition confirmed by direct read of `_inference_frame_cache_key` / `_selected_config_fingerprint` source, which feeds the whole `ranking.panel_scoring` block (incl. `artifact_path`, `buy_floor`, `sizing`, thresholds) into the key
best-known?:   n/a — this is a design memo identifying a defect (over-specified cache key), not a model/variant performance comparison; no narrower-key implementation exists yet to compare against
scope:         claim is scoped to the three measured cold-rebuild runs on this machine on 2026-07-28 plus the source-level read of the cache-key composition; does not claim a production-wide timeout-hit frequency. No model/IC/Sharpe number is claimed, so the §4(b) sanity triad does not apply.

NEXT:     Confirmed. The implementation PR belongs in the canonical kernel
          (renquant-pipeline) with the umbrella fork mirrored in the same
          batch — the fork-divergence class already hit twice today (blend
          `kind` unknown; `adaptive_quantile` buy_floor unsupported in the
          umbrella copy).
