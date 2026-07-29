# Inference-frame cache: over-specified key + no warm step

Date: 2026-07-28
Status: DECISION NEEDED (correctness-sensitive cache change — design first)
Owner: claude · Reviewer: codex

## Measured problem

`prepare_inference_panel_frames` rebuilds the per-ticker feature/factor
frames for the full watchlist (145 tickers) on a cache miss. Measured
tonight on this machine, three independent runs: **751–1355 s** per cold
rebuild, and one run **aborted the whole session**:

```
RuntimeError: Panel frame prep failed while panel_scoring.enabled=true;
aborting live inference instead of silently trading without panel scores:
prepare_inference_panel_frames timed out after 1200s
```

The cache itself works — it is enabled in both live profiles
(`inference_frame_cache.enabled=true`, dir `artifacts/cache/inference_frames`,
62 entries) and the 2026-07-28 daily session logged one HIT.

## Root cause: the key includes fields that do not determine frame content

`training_panel/pipeline.py::_selected_config_fingerprint` feeds the key:

```python
{"benchmark", "panel_ltr", "panel_scoring": ranking["panel_scoring"], "sector_etf_map"}
```

`panel_scoring` is taken WHOLE. It carries `artifact_path`, `buy_floor`,
`sizing`, `quality_floor`, `sell_gate_b`, thresholds — none of which change
a single row of the produced frames. Consequences observed tonight:

- swapping ONLY the scorer artifact (same watchlist, same OHLCV, same
  feature recipe) invalidates every cached frame;
- each shadow profile (prod / shadow / blend / experiment) keeps its own
  full copy of the same frames under a different key;
- a cold key on the production path hits the 1200 s ceiling and **aborts**
  rather than degrading — so a model swap or a threshold edit can take the
  next daily session down. This is a live-run reliability exposure
  (GOAL-5 class), not only a speed complaint.

## Proposal

**A. Narrow the key to frame-determining inputs (correctness-first).**
Replace the whole-`panel_scoring` blob with an explicit ALLOWLIST derived
from what the frame builder actually reads (candidate universe, feature
column policy, benchmark, sector map, `panel_ltr` feature settings), and
bump `_INFERENCE_FRAME_CACHE_VERSION` so pre-existing entries can never be
reinterpreted under the new rule. Allowlist, never denylist: a field added
later that DOES affect frames must fail closed by not being in the list —
so the allowlist is derived by reading the builder, and a test asserts every
config lookup inside the builder appears in it.

**B. Add a scheduled warm step.** After the daily data refresh, pre-build
the frames once per served recipe so every downstream session (prod
session, PatchTST shadow, blend lane, 105 export, experiments) starts warm.
Cost: one rebuild per day instead of one per lane per run.

**C. Make the timeout degrade, not abort, on a warm-cache miss?** NOT
proposed. Fail-closed is correct here (trading without panel scores is
worse). A + B remove the cold path instead.

## Why this is not a micro-optimization

Tonight three separate diagnostic runs each paid 12–22 minutes of rebuild,
and one production-shaped run aborted. The same cost lands on every future
model swap — including the PatchTST artifact swap now in flight — and on
every incident where an operator edits a threshold and reruns.
