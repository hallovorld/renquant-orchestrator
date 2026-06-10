# Stage-A Significance - Post-#78 Diagnostic Evidence

**Date:** 2026-06-10.
**Purpose:** Statistical hardening of the IC-to-Sharpe synthesis on the verified clean PatchTST signal.
**Status:** Diagnostic evidence only. This is not live-promotion evidence.

This replaces closed PR #76. That PR was generated before pipeline #78's fail-closed diagnostic fix and had unsafe machine-readable promotion flags.

## Provenance

The committed manifest pins:

- `renquant-pipeline`: `6e0eedd0f609cfc8c3e4c4f39999a16d7f445d91`
- `renquant-model`: `19919ec9350fdcb6931dfb2de4a10c3c90d1393a`
- clean-OOS manifest SHA256: `sha256:47a398f28bdad41d8fd907997865f9ede7701459b8b253449b1bfba395739632`
- predictions SHA256: `sha256:d74fc52d1bf91101edcfd09ecc362300b31448c43bd9045366e0145024813109`

Structured run params:

- `a2_hold_bars: 3`
- `pbo_n_slices: 16`
- `fwd_horizon_days: 1`
- `promotion_decision_grade: false`

The `significance.json` output is explicitly fail-closed:

- top-level `promotion_decision_grade: false`
- per-allocator `diagnostic_only: true`
- per-allocator `live_promotable_per_section_8: false`
- `per_regime_available: false`, because the clean PatchTST replay bars do not carry regime labels

## Results

Clean PatchTST signal, 190 bars, minimal long-only diagnostic snapshot:

| allocator | Sharpe | DSR | PBO |
|---|---:|---:|---:|
| A2 long-only hold3 | 2.59 | 1.00 | 0.00 |
| current_qp | 0.21 | 0.96 | 0.00 |
| equal_weight_top_k | -0.18 | 0.003 | 0.00 |
| inverse_vol_top_k | -0.18 | 0.003 | 0.00 |

Paired incumbent comparisons:

| comparison | delta Sharpe, QP - candidate | HAC t-stat | QP win-rate z |
|---|---:|---:|---:|
| current_qp vs A2_long_only_hold3 | -2.59 | -2.30 | -2.76 |
| current_qp vs equal_weight_top_k | 0.44 | 0.39 | -2.18 |
| current_qp vs inverse_vol_top_k | 0.44 | 0.39 | -2.18 |

The diagnostic ordering survives the additional DSR/PBO/HAC checks: A2 hold3 is materially better than current QP on this clean-signal minimal replay, while QP is not statistically distinguishable from the simple equal/inverse-vol baselines by HAC t-stat.

## Interpretation

This removes the narrow "raw Sharpe only" objection to the diagnostic synthesis. It does not authorize a live change. The robust diagnostic statement is:

> On the clean PatchTST minimal replay, A2 long-only hold3 is stronger than current QP after autocorrelation and multiple-comparison checks.

The production statement remains gated:

> Any Stage-A candidate must still pass WF, step-4g replay, DSR/PBO, per-regime analysis, and production constraint fidelity before live use.

## Caveats

1. Minimal long-only snapshot, not a production decision-trace reproduction.
2. Single fixed OOS holdout, not walk-forward.
3. Gross of tax.
4. Per-regime analysis is unavailable in this clean replay because the bars do not carry regime labels.

Agent-Origin: Codex
