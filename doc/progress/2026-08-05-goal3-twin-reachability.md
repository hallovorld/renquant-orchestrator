# GOAL-3: the twin registry counts definitions, not executions — and for the headline pair, neither twin is on today's live path

**Date:** 2026-08-05
**Lane:** GOAL-3 (architecture compliance audit)

## Bottom line

I set out to confirm a specific defect and **the code refuted it**. That refutation
is the finding.

The public-export audit reproduces `[VERIFIED — this session]`, against the pinned
pipeline at revision `e13cd3eba378`:

| | n |
|---|---:|
| exported duplicate names | 20 |
| resolve to the **NON-kernel** twin while a kernel twin exists | **19** |
| resolve to the kernel twin | **0** |
| no counterpart twin | 1 |

Sharpening that 19, which the earlier record did not do:

| shape | n | matters behaviourally? |
|---|---:|---|
| `identical-copy` (all five `state_paths` helpers) | 5 | **no** — same bytes |
| `differing-bodies` | **14** | **yes** |

## The hypothesis I tried to confirm, and why it is WRONG

Of the 14 divergent exports, only **3 unique production modules** import one
through the public surface (diagnostics bundles excluded — including them
inflates the count to 331 across 68,251 files, which is an artefact of archived
`modal_sweep_*/bundle/` snapshots, not production):

| module | imports |
|---|---|
| `renquant-backtesting/.../runtime_parity.py` | `PanelScoringJob` |
| `renquant-orchestrator/.../contract_fixture.py` | `PanelScoringJob`, `SelectionJob` |
| `renquant-orchestrator/.../daily.py` | `validate_order_attribution` |

Two of those three are **parity/contract-checking** code, so the obvious
hypothesis was the one this repo keeps meeting: *a parity harness validating the
wrong object* — backtest simulating the non-kernel twin while live executes the
kernel one.

**That is not what happens.** `kernel/pipeline/pp_inference.py:334` reads:

```python
from renquant_pipeline.panel_scoring import PanelScoringJob   # noqa: PLC0415
```

The **kernel's own inference pipeline imports the NON-kernel twin.** So
`runtime_parity.py` and the live kernel path bind the *same* object, and there is
no backtest-vs-live divergence to report for `PanelScoringJob`.

## What is actually true about the kernel twin

`[VERIFIED]` Searching the pinned pipeline, the umbrella `live/` tree and the
orchestrator sources: **nothing imports `kernel/panel_pipeline/job_panel_scoring`
by name.** Every hit is a docstring or comment reference pointing at it as the
canonical implementation.

Yet it is the larger and the more recently maintained file:

| file | lines | last commit |
|---|---:|---|
| `renquant_pipeline/panel_scoring.py` (the one that runs) | 1005 | 2026-08-01 |
| `kernel/panel_pipeline/job_panel_scoring.py` | **4350** | **2026-08-03** |

## And for today's live config, neither twin appears

Today's prod config is `panel_scoring.kind = blend`. The loggers that actually
emitted in `logs/daily_104/2026-08-05.log`:

```
kernel.panel_pipeline.scoring                 10
kernel.panel_pipeline.shadow_scoring           4
kernel.panel_pipeline.fingerprint_dispatch     3
kernel.panel_pipeline.momentum_residual_scorer 2
kernel.panel_pipeline.blend_scorer             2
kernel.panel_pipeline.feature_matrix           1
```

Neither `kernel.panel_pipeline.job_panel_scoring` nor
`renquant_pipeline.panel_scoring` logged at all.

**Epistemic status, stated precisely: this is logger evidence, not execution
evidence.** A module can run without logging, so this does NOT establish that
neither `PanelScoringJob` was instantiated. It establishes that the modules doing
the visible panel-scoring work today are a *third* set — the blend dispatch —
and that the twin pair the registry treats as the headline risk is not where
today's decisions are being made.

## The correction this lane needs

**The registry counts definitions; the risk is about executions.** "20 duplicate
exports, 19 resolving the wrong way" reads like 19 live hazards. Measured:
5 are byte-identical, 14 could matter, 3 modules import any of them, the one
plausible parity defect is refuted by the kernel importing the same twin, and the
headline pair is not visibly on today's decision path.

That is a much smaller and much more actionable claim, and it is only reachable
by measuring reachability rather than counting definitions.

## Next

1. Make reachability a first-class column in the twin registry — a twin nothing
   imports is debt; a twin two paths import differently is a defect. Today they
   are recorded identically.
2. Resolve the `job_panel_scoring` question deliberately: 4350 maintained lines
   that nothing imports is either dead code or a canonical implementation the
   runtime has silently stopped using. Both are worth knowing; they need
   opposite fixes.
