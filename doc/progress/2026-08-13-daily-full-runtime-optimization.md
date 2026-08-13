# daily-full runtime optimization — design + theory (G-J, doc only)

STATUS:    design + theory for review. Docs only — NO code / config / behavior
           change. Per operator: approve this design BEFORE implementing.

WHAT:      Commit `doc/design/2026-08-13-daily-full-runtime-optimization.md`: a
           measured profile of the 83.5-min daily-full run, the root-cause theory,
           and a targeted speedup design (make the feature prep actually multi-core
           + pre-warm its cache), with a validation plan and an out-of-scope note on
           the 72-min execution tail.

WHY/DIR:   Operator-directed 2026-08-13 ("104/105 运行时间太长，分析设计架构加速，
           缩短 daily-full；提前搜集数据 / 并发 / 缓存" + "先把设计和理论发 PR，通过后
           再实现" + "有可能 GPU 加速吗"). The run is slow (83.5 min) but the model is
           not the cause (~5 s); the compute cost is a GIL-serialized feature-prep
           and the bulk is post-decision order-working. This design pins the real
           levers before any code is written.

EVIDENCE:
  artifact:      `doc/design/2026-08-13-daily-full-runtime-optimization.md` (+ this
                 progress doc). No code, no config, no production/live path.
  prod or exp:   neither — design/theory only; no computation run, no live change.
  existing data: profile from `logs/daily_104/2026-08-12.log` (wall-clock by
                 timestamp): 83.5 min = ~10 min `prepare_inference_panel_frames` +
                 ~26 s z-scoring + ~5 s inference + ~72 min execution/polling tail;
                 heavy phases run 1× (not per-lane). Code reads:
                 `training_panel/pipeline.py` — `ThreadPoolExecutor(max_workers=
                 cpu_count-2=12)` over CPU-bound `_chain`
                 (TickerPanelFeature/Neutralize/Factor); cache keyed on daily-changing
                 `ohlcv` (misses every day). Hardware: Apple M4 Pro arm64 (no CUDA GPU).
  best-known?:   yes — this is the analysis vs no prior runtime design. The GIL-bound-
                 threads root cause is [DERIVED] from code + the serial-CPU throughput
                 signature; the design's §5 makes a 1-ticker CPU-vs-I/O profile the
                 FIRST implementation step to convert it to [VERIFIED] before coding,
                 and requires byte-identical outputs (speed only, never different
                 decisions).
  scope:         "an architecture design + theory for daily-full runtime (NOT executed,
                 NOT implemented). It authorizes no code, no config, no live change.
                 Feature-prep implementation will land in the strategy-104 repo,
                 output-invariance-tested + flag-gated, then pin-advanced. The 72-min
                 execution tail is out of scope pending an operator decision."

TESTS:     none — doc-only PR.

NEXT:      (1) codex approval of this design; (2) implementation phase step 1 = the
           1-ticker CPU-vs-I/O profile (confirm §3.1, locate the hottest job, check
           for an MLX-worthy hotspot); (3) prototype ProcessPoolExecutor + measure
           A/B on a fixed 145-ticker corpus (byte-identical outputs); (4) pre-warm
           cache pre-market; (5) operator decision on the execution tail.
