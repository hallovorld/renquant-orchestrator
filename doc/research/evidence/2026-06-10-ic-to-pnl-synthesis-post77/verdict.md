# IC to Sharpe Investigation Synthesis - Post-#77 Production Recommendation

**Date:** 2026-06-10.
**Scope:** Synthesis of the IC-to-Sharpe RFC experiments on the verified clean PatchTST signal.
**Status:** Operator decision document for a production experiment. This is not a live promotion approval.

This replaces closed PR #74. The prior synthesis used A2 E2 evidence whose manifest pinned a pipeline commit that could not reproduce `--e2-base a2_long_only`. This version is regenerated after merged pipeline #77 and merged orchestrator #73.

## Provenance

Merged dependencies:

- Pipeline #77: `26e6537309cb2c8c66279a4a18b74f6fc5c70c5a`
- Orchestrator #73: `3347f550878be00bb87b2c90c71fc573d29d0fe7`
- Model clean-OOS manifest commit: `19919ec9350fdcb6931dfb2de4a10c3c90d1393a`

The A2 horizon sweep manifest in this directory records:

- `experiment: E2`
- `params.e2_base: a2_long_only`
- `repo_pins.renquant-pipeline: 26e6537309cb2c8c66279a4a18b74f6fc5c70c5a`
- predictions SHA256: `sha256:d74fc52d1bf91101edcfd09ecc362300b31448c43bd9045366e0145024813109`

The committed `e2_a2_results.csv` is a copy of the generated `e2_results.csv`; its content hash matches `e2_a2_manifest.json.outputs["e2_results.csv"]`.

## Answer

The operator question was: PatchTST has real IC, but realized APY and Sharpe are poor; is the decision tree wasting the IC?

Answer: yes, based on the clean-signal diagnostic evidence. The IC is real but lower than the informal premise: placebo-clean OOS mean IC is `+0.0724`, not about `+0.10`. The current decision stack captures little of it. The strongest destroyers observed in the diagnostic ladder are the single-day-loss stop, hard admission/floor behavior, and the current QP-style allocation path.

The fix should not be a broad live switch. It should be one gated production experiment.

## Evidence Chain

| Item | Finding | Evidence |
|---|---|---|
| P0 clean signal | PatchTST clean OOS IC `+0.0724`, sanity battery passed | renquant-model #37/#38 |
| E1 ladder | A2 long-only alpha tilt Sharpe `1.85`; current QP minimal long-only Sharpe `0.21`; stop and floor are major taxes | `2026-06-10-ic-to-pnl-E1-clean-patchtst/` |
| E2 A0 horizon | Dollar-neutral A0 peaks at short hold and is poor at long holds after post-#76 rerun | `2026-06-10-ic-to-pnl-E2-clean-post76/` |
| E2 A2 horizon | Deployable A2 long-only peaks near hold 3 with no hard-constraint violations | this directory |

## A2 Horizon Sweep

Clean PatchTST signal, minimal long-only snapshot, 1-day realized PnL, 5 bps cost:

| hold bars | Sharpe | TC | mean turnover | cumulative return | hard violations |
|---:|---:|---:|---:|---:|---:|
| 1 | 1.99 | 0.92 | 0.7435 | 39.60% | 0 |
| 3 | 2.59 | 0.70 | 0.2855 | 55.03% | 0 |
| 5 | 2.32 | 0.66 | 0.1792 | 41.52% | 0 |
| 10 | 2.13 | 0.57 | 0.1010 | 35.39% | 0 |
| 20 | 1.75 | 0.48 | 0.0557 | 26.48% | 0 |
| 40 | 2.24 | 0.37 | 0.0294 | 29.54% | 0 |

The absolute Sharpe numbers are diagnostic benchmarks, not production promises. The useful ordering is that a direct long-only rank-to-weight book is materially stronger than the current QP-style path in the same minimal replay, and the best tested cadence is short, around 3 bars, not the 60-day label horizon.

## Recommendation

Build one production-gated candidate:

Stage-A A2 long-only alpha tilt, using positive cross-sectional z-score weights, a short rebalance cadence around 3 bars, a cost-aware glide, scalar volatility/drawdown overlay, and hard stops demoted to safety-only controls. Remove QP from the selection path for this candidate.

This candidate must go through the real promotion gate:

- walk-forward evaluation;
- step-4g replay;
- DSR/PBO;
- per-regime analysis;
- explicit cost/tax treatment before live use.

No live change is authorized by this document. Live stays unchanged until a candidate clears the gate.

## Caveats

1. This is a minimal long-only diagnostic snapshot, not a production decision-trace reproduction.
2. This is one fixed OOS holdout, not walk-forward evidence.
3. The replay is gross of tax and uses 1-day realized PnL.
4. A2 is deployable in this simplified constraint space, but production still needs the WF/replay gate.

Agent-Origin: Codex
