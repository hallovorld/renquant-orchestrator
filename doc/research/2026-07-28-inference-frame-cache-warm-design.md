# Inference-frame cache: over-specified key + no warm step

Date: 2026-07-28
Status: CONFIRMED — operator adopted A′ + B in-session (2026-07-28/29), no amendment.
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

**A′. Narrow the key by construction, not by allowlist (revised — see
"Correction" below for why the original A was withdrawn).** Introduce a
typed, versioned `FrameRecipe` object (explicit schema + `recipe_version`)
that is the *only* input the frame builder is allowed to consume for
cache-relevant parameters — candidate universe, feature column policy,
benchmark, sector map, `panel_ltr` feature settings. Refactor
`prepare_inference_panel_frames` (and whatever it calls) to take `FrameRecipe`
as its sole config-shaped parameter instead of closing over the full
`ranking.panel_scoring` dict or reaching back into raw config. The cache key
becomes the fingerprint of `FrameRecipe`, and bump
`_INFERENCE_FRAME_CACHE_VERSION` so pre-existing entries can never be
reinterpreted under the new rule.

This makes correctness structural instead of checklist-based: a field the
builder does not read cannot silently affect frame content (there is nothing
left to read it from), so *every* field that does affect frames is
necessarily inside `FrameRecipe` and therefore inside the fingerprint — the
failure mode from the original A (a frame-affecting field added later,
forgotten from a hand-maintained allowlist, silently reuses a stale cache
entry) cannot occur because there is no path for the builder to consume a
field outside the recipe. Test: (1) for every `FrameRecipe` field, changing
just that field changes the fingerprint (no accidental invariance); (2) for
a fixed `FrameRecipe`, cache-hit output is byte/row-equivalent to a fresh
rebuild (round-trip idempotency) — not a static "is this field listed"
assertion, which only checks the checklist was updated, not that the
builder actually can't read anything else.

**B. Add a scheduled warm step, on the same recipe.** After the daily data
refresh, pre-build the frames once per served `FrameRecipe` so every
downstream session (prod session, PatchTST shadow, blend lane, 105 export,
experiments) starts warm. The warm step must construct its `FrameRecipe`
and freshness/as-of fingerprints through the identical code path the live
serving path uses (no parallel/duplicate derivation that could drift), and
it goes through the same data freshness/integrity gates as a live-triggered
rebuild — it is not a bypass, only an earlier-scheduled instance of the same
gated build. Cost: one rebuild per day instead of one per lane per run.

**C. Make the timeout degrade, not abort, on a warm-cache miss?** NOT
proposed. Fail-closed is correct here (trading without panel scores is
worse). A′ + B remove the cold path instead.

**Recommendation: adopt A′ + B together.** A′ alone fixes correctness but
not the cold-start cost; B alone speeds up the common case but leaves the
fail-closed abort path reachable on any un-warmed recipe (a new model or
profile before its first warm run). Together: A′ guarantees the fingerprint
can't go stale, B guarantees the fingerprint is usually already warm.

### Correction (post-review): the original Proposal A was fail-open, not fail-closed

The first draft's allowlist design claimed "fail closed": a frame-affecting
field omitted from the allowlist would "fail closed by not being in the
list." That is backwards. If a new frame-affecting config field is omitted
from the allowlist, the fingerprint does not change when that field changes
— so the *existing* cache entry still matches and is served, unchanged and
stale. That is fail-open cache poisoning (silently serving wrong frames),
not a safe miss. A test that every *direct* lookup inside the builder
appears in the allowlist does not close this gap: it does not see indirect
reads through a helper the builder calls, and it only holds if every future
change to the builder remembers to update the assertion — the same
hand-maintained-scope failure mode that produced today's over-broad key in
the first place (a whole config block included because no one tracked which
fields actually mattered). Proposal A′ above replaces the allowlist with a
structural constraint: the builder's only config-shaped input is the typed
`FrameRecipe`, so there is no unlisted field left for it to read.

## Why this is not a micro-optimization

Tonight three separate diagnostic runs each paid 12–22 minutes of rebuild,
and one production-shaped run aborted. The same cost lands on every future
model swap — including the PatchTST artifact swap now in flight — and on
every incident where an operator edits a threshold and reruns.
