# daily-full multi-lane shared feature panel — design (G-K, doc only)

STATUS:    design for review. Docs only — NO code / config / behavior change.
           Per operator: approve BEFORE implementing.

WHAT:      Commit `doc/design/2026-08-14-daily-full-multilane-shared-feature-panel.md`:
           the measured multi-lane structure of the daily-full, the root cause of the
           per-lane feature-prep recomputation, and the output-invariant fix (share
           the feature panel across lanes by removing the scorer config from the
           feature cache key), with a mandatory byte-identical proof and a
           verification plan.

WHY/DIR:   Operator-directed 2026-08-14 ("压"). The daily-full's ~72-min "tail" is not
           order-working — it's ~6 sequential lanes each re-running the ~10-min
           feature-prep. This pins the redundancy and the safe fix before code.

EVIDENCE:
  artifact:      `doc/design/2026-08-14-daily-full-multilane-shared-feature-panel.md`
                 + this progress doc. No code, no config, no production/live path.
  prod or exp:   neither — design/theory only; no computation run, no live change.
  existing data: 08-12 lane logs (`logs/daily_104/2026-08-12_shadow_blend.log` 14:21→14:33,
                 `_shadow_blend_mom.log` 14:33→14:44) each show an own ~10-min
                 `prepare_inference_panel_frames` + 1 InferencePipeline; `daily_104.sh`
                 Step 3 (prod --once) + Step 5+ shadow lanes; code read of
                 `training_panel/pipeline.py` — the feature cache key
                 (`_selected_config_fingerprint`) includes `ranking.panel_scoring`
                 (per-lane scorer) → per-lane cache miss.
  best-known?:   yes — the root cause is [VERIFIED] from the lane logs + code; the fix's
                 output-invariance is NOT assumed but a HYPOTHESIS to prove — §5 makes a
                 byte-identical (assert_frame_equal check_exact) test across EVERY
                 resolved lane config (prod + 5 shadow), over ALL FOUR returned artifacts
                 (`neutralized_frames, factor_frames, macro_frame, asset_embeddings`),
                 plus a lane-2 cache-hit proof, the FIRST implementation gate — because
                 the panel-jobs file does read `panel_scoring`; the change is flag-gated
                 + behaviour-invariant.
  scope:         "a design to share the daily-full inference feature panel across its
                 ~6 scoring lanes (NOT executed, NOT implemented). Authorizes no code,
                 no config, no live change. Implementation lands in the OWNING subrepo
                 `renquant-pipeline` (per RENQUANT_REPOS.md — runtime inference code, NOT
                 the umbrella), with a migration/thin-adapter path reconciling the
                 pre-existing umbrella-copy + G-J boundary debt; four-artifact
                 output-invariance-tested + flag-gated, then operator-gated live-tree
                 deploy. Compounds with the already-deployed G-J per-lane feature-prep
                 speedup."

TESTS:     none — doc-only PR.

NEXT:      (1) codex approval; (2) implementation step 1 (in `renquant-pipeline`) = the §5
           four-artifact byte-identical proof across the resolved runtime set captured
           from the executable lane-resolution path (the proof run's successful
           `renquant_strategy_config(...)` resolutions / invocation-capture manifest, NOT
           a static read of `daily_104.sh`) + lane-2 cache-hit proof + resolve §6
           cross-lane cache-dir parity; (3)
           cache-key change + lane-sharing test; (4) operator-gated live-tree deploy.
           Also: confirm G-J's real magnitude from the first post-G-J daily-full
           (08-14) before sizing G-K's marginal gain.
