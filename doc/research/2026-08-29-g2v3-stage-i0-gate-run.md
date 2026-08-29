# GOAL-2v3 Stage I-0 — the GATE RUN: PASS (BEAR n_eff_adj 191 vs bar 30)

Date: 2026-08-29 ~03:00 PDT. Executed with `--gate-run` from the frozen main
commit **f3d5bf7b** (Amendment A1 acknowledged by the operator, #1074), on a
fresh vendor fetch of the same 2,144-name seed (2,124 with bars + 20 empty —
identical tally to the development fetch; sha256 of every consumed bar file
is in the committed audit artifact).

Every gate parameter was frozen on main BEFORE this run: bar (BEAR
n_eff_adj ≥ 30 @ h=13), the AR(1) fail-closed estimator with raw ρ̂₁
reported beside the floored value, the canonical 39-slot grid, the s₀ proxy,
the trailing eligibility rule, and the A1 drift thresholds (1% name-day /
5% eligible-day breach, in declared order).

## The table (machine-readable report committed alongside; `run_status: GATE_RUN`)

| regime | n_blocks | episodes | ρ̂₁ raw → used | **n_eff_adj** | s₀ block IC |
|---|---|---|---|---|---|
| **BEAR** | 191 | 11 | −0.057 → 0.00 | **191** | +0.021 |
| BULL_CALM | 520 | 16 | +0.022 → +0.022 | 497.4 | +0.014 |
| BULL_VOLATILE | 159 | 16 | −0.100 → 0.00 | 159 | +0.011 |
| CHOPPY | 47 | 10 | −0.184 → 0.00 | 47 | +0.035 |

917 block sessions; median eligible cross-section 1,256 names; 102 names
excluded by the frozen two-layer drift rule (the development runs' 432 was
the pre-A1 all-days rate — this is the declared rule's output).

## Verdict

**`gate_verdict: PASS` — BEAR n_eff_adj = 191, 6.4× the bar.** Raw
dependence is small and mostly negative; the conservative floor changes
CALM only (520 → 497.4). Every regime clears 30, so Stage I-1 conditioning
is fundable in all states. The naive frozen proxy carries positive block IC
in every regime (diagnostic, not a gate).

Development-run indication (191, #1073) and gate run agree on the count
because the count is a property of the frozen construction; the s₀ ICs
moved slightly with the re-fetched vendor bytes (expected; hashes differ
and are recorded).

## Next

Stage I-1 exactly as preregistered in the design (#1076, merged before this
result existed): bases B0/B1/B2/B3, feature set F, K5 XGB verbatim with the
literal seeds, five 6-month OOF folds with a 13-bar purge, life screen
block-t ≥ 1.0 at h=13 on dependence-adjusted units, overall bar only.
Evaluation window 2024-07..2026-06 remains sealed.
