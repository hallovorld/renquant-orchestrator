# XGB deployment via the gate's designed opt-ins — decision record + risk disclosure

Operator directive (2026-06-21): *"把xgb马力开足！目前无论什么regime都只能用它！不能交易是gate需要放宽."*
(Run XGB at full power, all regimes — it's the only model we have; if it can't trade, the gate must
be loosened.) This records the **legitimate, designed** way to do that, the exact relaxes required,
and the **material risk** the operator is accepting — per the gate's own audit-trail requirement.

## NOT a bypass — the gate's designed operator opt-ins
The WF gate ships **operator opt-in flags** (`strategy_config.wf_gate.{benchmark_required,
regime_required,sanity_regime_ic_required}` + `--allow-pass-open-trade-monotonicity`) whose own
docstring says: *"Real-money decision: enabling these accepts a model that may lag SPY or have weak
per-regime edge. Logged into wf_gate_metadata so the audit trail [records it]."* Using these is the
gate's **designed flexibility**, not a bypass (a bypass = `RQ_ALLOW_NO_WF` / disabling protection /
admin-merge — NOT done).

## What XGB actually passes / fails (fresh XGB, oos_mean_ic +0.053)
| gate check | XGB | relax needed to admit? |
|---|---|---|
| absolute Sharpe floor | **PASS** | no |
| §5.2 overall placebo | **PASS** (+0.0343 < 0.0379) | no |
| §5.2 shuffled-label | **PASS** | no |
| **benchmark (beat SPY)** | **FAIL — beat SPY APY 0/3** | `benchmark_required=false` |
| WF regime (no benchmark-lag) | FAIL (HIGH_CALM, LOW_SPIKED) | `regime_required=false` |
| §5.2 regime-sanity IC | FAIL (BULL_CALM, CHOPPY) | `sanity_regime_ic_required=false` |
| trade monotonicity | FAIL (BULL_CALM) | `--allow-pass-open-trade-monotonicity` |

`[VERIFIED — /tmp/xgb_gate5.log]`

So admitting XGB requires relaxing **four** checks. It cleanly passes only the absolute Sharpe floor
+ the overall placebo (which IS a genuine positive signal — overall real IC +0.054).

## The material risk being accepted (audit-trail disclosure)
1. **XGB LAGS SPY** — beat SPY APY **0/3** cuts. On this evidence, **trading XGB likely
   underperforms simply holding SPY.** `benchmark_required` exists to catch exactly this.
2. **Weak in the common regime** — BULL_CALM (the regime we are in now, and most of the time) real
   IC **+0.0149**, below the 0.02 floor, placebo > real (425 reliable OOS dates).
3. **Edge is BEAR-concentrated** and that BEAR IC (+0.347) is implausibly high / unvalidatable.

**The operator is making an informed real-money decision to accept these** in exchange for having a
trading model + live data to improve it, rather than remaining sell-only indefinitely. That trade-off
is the operator's to make; this PR is the disclosure + audit record the gate's design requires.

## Execution plan (on operator confirm — pending the lags-SPY decision)
1. Set the four opt-ins in `strategy_config.json.wf_gate` + `--allow-pass-open-trade-monotonicity`.
2. Re-gate XGB → expect `passed=true` (relaxes logged in wf_gate_metadata).
3. Promote XGB → swap prod `panel_scoring.kind` → xgb, PatchTST → shadow.
4. daily-full readonly E2E → validate the pipeline trades end-to-end (XGB active, all regimes).
5. Then Path 1: strengthen the calm-market signal so the relaxes can be withdrawn.

## Reversibility
All opt-ins are config flags (flip back to `true`); config backed up + git-tracked. Promotion is a
deliberate artifact swap. Nothing here disables the gate or its audit trail.
