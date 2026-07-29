# Progress: inference-frame cache design memo (PR #589)

STATUS:   delivered (design memo only, no code). Decision needed on proposal A
          (narrow the cache key via an allowlist) + B (scheduled warm step).

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
          daily session down — GOAL-5 reliability class. Proposal A narrows the
          key by allowlist (fail-closed: a new frame-affecting field must be
          added explicitly, asserted by a test that every config lookup in the
          builder appears in the allowlist) with a cache-version bump so old
          entries cannot be reinterpreted; proposal B pre-builds frames once
          daily after the data refresh so every lane starts warm.

EVIDENCE:
artifact:      training_panel/pipeline.py (`_inference_frame_cache_key`, `_selected_config_fingerprint`); run logs for the three 2026-07-28 cold-rebuild sessions on this machine; `artifacts/cache/inference_frames` (62 entries)
prod or exp:   prod — production-shaped live-inference path, not a sim/experiment harness
existing data: `[VERIFIED — direct log read]` three independent cold rebuilds: 751 s, 1355 s, and one run raising `prepare_inference_panel_frames timed out after 1200s` → `RuntimeError: Panel frame prep failed while panel_scoring.enabled=true`; the 2026-07-28 daily log shows one `cache HIT`, confirming the cache mechanism itself works; key composition confirmed by direct read of `_inference_frame_cache_key` / `_selected_config_fingerprint` source, which feeds the whole `ranking.panel_scoring` block (incl. `artifact_path`, `buy_floor`, `sizing`, thresholds) into the key
best-known?:   n/a — this is a design memo identifying a defect (over-specified cache key), not a model/variant performance comparison; no narrower-key implementation exists yet to compare against
scope:         claim is scoped to the three measured cold-rebuild runs on this machine on 2026-07-28 plus the source-level read of the cache-key composition; does not claim a production-wide timeout-hit frequency. No model/IC/Sharpe number is claimed, so the §4(b) sanity triad does not apply.

NEXT:     Operator/codex decision on A + B. If accepted, the implementation PR
          belongs in the canonical kernel (renquant-pipeline) with the umbrella
          fork mirrored in the same batch — the fork-divergence class already hit
          twice today (blend `kind` unknown; `adaptive_quantile` buy_floor
          unsupported in the umbrella copy).
