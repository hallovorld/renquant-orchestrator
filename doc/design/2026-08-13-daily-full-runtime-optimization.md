# Design: daily-full (104) runtime optimization — profile, theory, and speedup plan

STATUS: **design + theory for review (docs only — NO code / config / behavior change).**
DATE: 2026-08-13. Operator-directed ("104/105 运行时间太长，分析设计架构加速，缩短 daily-full；
提前搜集数据 / 并发 / 缓存"). Per operator: land this design PR and get it approved BEFORE implementing.

## 1. Bottom line
The daily-full run measured **83.5 min** end-to-end, but the model is not the problem
(inference ≈ 5 s). The time is two structurally different costs:
- **~10 min of feature-panel prep** whose "12-way parallelism" is **GIL-serialized** (a
  `ThreadPoolExecutor` running CPU-bound pandas) → it delivers ≈ 1× and its cache misses
  every day. This is the real *compute* bottleneck and is what "并发 / 缓存" should target —
  but the current concurrency/caching are **present yet ineffective**, so naïvely "adding
  concurrency/caching" does nothing.
- **~72 min post-decision execution/polling tail** — the live runner working orders across
  the market session. This is **I/O / waiting, not compute**; shortening it is a
  trading-behavior decision, not a caching/concurrency fix, and is scoped out here pending
  an explicit operator choice.

The recommended compute win: make the feature prep **actually multi-core** (process pool
and/or cross-sectional vectorization) and **pre-warm its cache pre-market**. Expected: the
decision pipeline drops from ~11.5 min to ~2–3 min. GPU is not applicable on this hardware
(see §4.4).

## 2. Measured profile (08-12 daily-full) `[VERIFIED — logs/daily_104/2026-08-12.log, wall-clock from line timestamps]`
Total **83.5 min** (13:55:08 → 15:18:35):

| phase | wall | evidence |
|---|---|---|
| startup: load 120/145 models + backfill fwd returns | ~0.5 min | 13:55:08–13:55:38 |
| **`prepare_inference_panel_frames`** (145-ticker feature build) | **~10 min** | 13:55:38 → 14:06:02, progress `done=0→136/145`, ≈ 4 s/ticker `[VERIFIED — 1× START, not per-lane]` |
| feature z-scoring (Neutralized/FactorZScore) | ~26 s | 14:06:02–14:06:28 |
| **InferencePipeline (scoring + rotation)** | **~5 s** | 14:06:28 → 14:06:33 `[VERIFIED — total=4.94s]` |
| **post-decision execution/polling tail** | **~72 min** | 14:06:37 → 15:18:35; 5 SHADOW-ACTION/DECISION cycles ~11 min apart, incl a 26-min silent gap |

The heavy phases run **once** per daily-full (not per-lane) `[VERIFIED — 1× `InferencePipeline START`, 1× `prepare_inference_panel_frames done=0/`]`.

## 3. Root-cause theory
### 3.1 Feature prep — GIL-serialized threads on CPU-bound work `[DERIVED — code + throughput]`
`prepare_inference_panel_frames` (`backtesting/renquant_104/training_panel/pipeline.py`):
- Loads all shared inputs **once** before the parallel section (`LoadFundamentals`,
  `LoadEarningsSurprise`, `LoadInsiderTrades`, `LoadHourlyBars`, `SectorMomentum`), so the
  parallel section is **pure per-ticker computation**, not I/O.
- Runs the per-ticker `_chain` = `TickerPanelFeatureJob → TickerPanelNeutralizeJob →
  TickerPanelFactorJob` over a **`ThreadPoolExecutor(max_workers = cpu_count − 2)`** = **12
  workers** on this 14-core M4 Pro `[VERIFIED — os.cpu_count()=14]`.
- **The defect:** those three jobs are CPU-bound pandas/numpy. Python's **GIL** lets only one
  thread execute Python bytecode at a time, so a thread pool gives **≈ 1×** on CPU-bound work.
  12 "workers" therefore run effectively **serially**: 145 tickers × ~2.5–4 s each ≈ 10 min.
  The observed throughput (~12 tickers / 30 s, with plateaus) is exactly the serial-CPU
  signature, not a 12× parallel one.
- **Cache is real but daily-useless:** `_load_inference_frame_cache` keys on
  `_inference_frame_cache_key(watchlist, ohlcv, ticker_sectors, config)`. `ohlcv` changes
  every day (a new bar), so the key changes every day → **cache MISS every daily run** →
  the full compute re-runs. On 08-12 the log shows the compute path (`done=0/145 …`), i.e. a
  miss. So the existing cache only helps intra-day re-runs, never the once-a-day production run.

### 3.2 Model inference — not a bottleneck `[VERIFIED — 5 s]`. Do not spend effort here.

### 3.3 Execution tail — waiting, not compute `[VERIFIED — 26-min silent gap + ~11-min cycles]`
Post-decision, the live runner works the order across the session (SHADOW-ACTION/DECISION
cycles), including a repeated "BUY AFRM x15 FAILED". This is order-working / polling latency,
not CPU. Compressing it trades against fill quality and is a **behavioral** change — out of
scope here (see §5, operator decision).

## 4. Speedup design (theory + expected gains)
### 4.1 Make the feature prep actually parallel (the primary win)
Two candidates; the implementation phase picks by measurement (§5):
- **(A) `ProcessPoolExecutor`** — true multi-core, bypasses the GIL. Upper bound ≈ 12× on the
  CPU section, but real gain is reduced by **inter-process serialization** (pickling each
  `TickerPanelContext` + its frames) and process spin-up. Net expected ≈ 4–8× → ~10 min → ~1.5–2.5 min.
  Lowest-refactor option (swap the executor + make `_chain` picklable / top-level).
- **(B) Cross-sectional vectorization** — compute the feature/neutralize/factor steps for **all
  145 tickers at once** in batched pandas/numpy (one panel), instead of a per-ticker Python loop.
  Avoids both the GIL and the process-overhead; typically the fastest and also lowers memory
  churn — but the largest refactor (the three Jobs must be rewritten to operate on the panel).
  Best long-term target.
- Recommendation: ship (A) first (fast, low-risk, big win), then evaluate (B) for the hottest job.

### 4.2 Pre-warm the feature cache pre-market ("提前搜集数据")
The compute is deterministic given the cache_key. Add a **pre-market job** that, once the day's
data has landed, computes `prepare_inference_panel_frames` and writes the cache — so the daily-full
run hits a warm cache and pays ~0 for feature prep on the critical path. This **relocates** the cost
off the critical path even before (A)/(B) shrink it. Requires the daily-full to read the same
cache_key (it already does).

### 4.3 Incremental cache (stretch)
Most per-ticker features change only at the newest bar. A delta-cache that recomputes only the new
bar's contribution (rather than the full history per ticker) could make prep near-instant. Larger
redesign; propose as a follow-up after (A)+(4.2).

### 4.4 GPU — not applicable here `[VERIFIED — Apple M4 Pro, arm64]`
The mainstream GPU data stack (RAPIDS cuDF, XGBoost-GPU) is **NVIDIA-CUDA only** and does not run
on Apple Silicon. The bottleneck is CPU-parallelism (GIL) + I/O, not GPU-shaped compute, and 145
tickers of daily bars is small relative to GPU transfer overhead. The only conditional GPU angle is
**Apple MLX/Metal** for a *specific* numeric hotspot IF the §5 profile shows one dominating — a
targeted optimization, not "GPU-accelerate the daily run."

### 4.5 Amdahl summary
Decision pipeline ≈ 11.5 min = ~10 min prep + ~1.5 min everything else. Cutting prep to ~1–2 min
(via 4.1) or ~0 on the critical path (via 4.2) yields a **decision latency of ~2–3 min** — a ~4–5×
improvement on the part that is actually computation. The 72-min execution tail is unaffected (and
untouched) unless the operator opts into execution-cadence changes.

## 5. Validation plan (measure before implementing, and A/B after)
1. **1-ticker CPU-vs-I/O profile** of `_chain` (cProfile / py-spy on one `TickerPanelFeatureJob`
   run) to *confirm* it is CPU-bound (theory §3.1) and to locate the hottest job — this also
   answers whether any MLX-worthy numeric hotspot exists (§4.4).
2. Prototype (A) process-pool on a fixed corpus; measure wall-clock vs the thread-pool baseline on
   the same 145-ticker input (expect ≥ 3–4×). Confirm identical outputs (byte-equal frames) — a
   speedup that changes scores is a regression.
3. Pre-warm cache: verify a warm-cache daily-full skips the compute (cache HIT log) and is
   output-identical.
4. Ship behind a config flag; A/B a full daily-full run (before/after wall-clock + identical
   decisions) before it becomes the default.

## 6. Scope / boundaries / rollout
- `prepare_inference_panel_frames` and its Jobs live in **strategy-104** (`backtesting/renquant_104/…`).
  This design is authored in the orchestrator (the run-orchestration owner); the **implementation
  PRs land in the strategy-104 repo**, output-invariance-tested, then pin-advanced here.
- Every change is **behavior-invariant** (identical scores/decisions) and flag-gated; the daily-full
  must never change what it decides, only how fast. `[[fix-wave-protect-production]]`
- The 72-min execution tail is **explicitly out of scope** pending an operator decision on whether
  session-long order-working is desired (fill quality) or should be compressed.

## 7. Open decision for the operator
Do you want the daily-full to simply **decide faster** (this design: ~11.5 → ~2–3 min, execution
left to work the session), or **also compress the ~72-min execution tail** (a separate,
fill-quality-sensitive behavioral change)?
