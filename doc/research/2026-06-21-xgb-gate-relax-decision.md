# XGB gate opt-ins — neutral inventory + risk disclosure

Operator directive (2026-06-21): *"把xgb马力开足！目前无论什么regime都只能用它！不能交易是gate需要放宽."*
(Run XGB at full power, all regimes — it's the only model we have; if it can't trade, the gate must
be loosened.) This is a **neutral inventory** of the gate's designed opt-ins, the checks XGB fails,
and the **material risk** — NOT a durable decision to relax all four and call the resulting
`passed=true` good enough. Relaxing four independent acceptance checks after seeing a failed result
is a major change to the bar, not a small toggle; the deployment question stays governed by the
bounded diagnosis (#167) and a downstream conviction floor, not by this document.

## The gate's designed operator opt-ins (what they are)
The WF gate ships **operator opt-in flags** (`strategy_config.wf_gate.{benchmark_required,
regime_required,sanity_regime_ic_required}` + `--allow-pass-open-trade-monotonicity`) whose own
docstring says: *"Real-money decision: enabling these accepts a model that may lag SPY or have weak
per-regime edge. Logged into wf_gate_metadata so the audit trail [records it]."* These are designed
flags (distinct from a hard bypass such as `RQ_ALLOW_NO_WF` / disabling protection / admin-merge,
none of which are in scope). Documenting what they do is not the same as endorsing flipping all four.

## What XGB actually passes / fails (fresh XGB, oos_mean_ic +0.053)
| gate check | XGB | flag that would admit it |
|---|---|---|
| absolute Sharpe floor | **PASS** | — |
| §5.2 overall placebo | **PASS** (+0.0343 < 0.0379) | — |
| §5.2 shuffled-label | **PASS** | — |
| **benchmark (beat SPY)** | **FAIL — beat SPY APY 0/3** | `benchmark_required=false` |
| WF regime (no benchmark-lag) | FAIL (HIGH_CALM, LOW_SPIKED) | `regime_required=false` |
| §5.2 regime-sanity IC | FAIL (BULL_CALM, CHOPPY) | `sanity_regime_ic_required=false` |
| trade monotonicity | FAIL (BULL_CALM) | `--allow-pass-open-trade-monotonicity` |

`[VERIFIED — /tmp/xgb_gate5.log]`

XGB cleanly passes only the absolute Sharpe floor + the overall placebo (a genuine positive aggregate
signal, overall real IC +0.054). Admitting it through the gate would require relaxing **four** checks.

## The material risk (disclosure)
1. **XGB LAGS SPY** — beat SPY APY **0/3** cuts. On this evidence, trading XGB likely underperforms
   simply holding SPY. `benchmark_required` exists to catch exactly this.
2. **Weak in the common regime** — BULL_CALM (current and most-of-the-time) real IC **+0.0149**,
   below the 0.02 floor, placebo > real over 425 reliable OOS dates (#167).
3. **Aggregate is BEAR-inflated** — the +0.054 is carried by a rare BEAR regime whose IC (+0.347) is
   implausibly high and unvalidatable (#167); it is not a robust calm-market edge.

## Decision (bounded)
- "Relax all four → `passed=true` → promote" is **not** recorded here as a settled deployment path on
  this evidence; doing so would write a post-hoc acceptance-bar change as if earned.
- If XGB is deployed at the operator's real-money discretion, opt-in use must be paired with a
  **downstream economic conviction floor** (`mu_floor`, renquant-pipeline #140) so the book buys only
  well-separated names, plus the bounded #167 read — not "everything the relaxed gate now admits".
- The durable goal remains: strengthen the calm-market signal so the relaxes can be withdrawn.

## Reversibility
The opt-ins are config flags (flip back to `true`); configs are git-tracked. Nothing here disables the
gate or its audit trail.
