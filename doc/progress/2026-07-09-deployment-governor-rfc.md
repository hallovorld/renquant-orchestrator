# Deployment Governor RFC — design

**Date**: 2026-07-09
**Status**: Design RFC (no behavior change)

## Bottom line

Full sizing-architecture redesign RFC per operator mandate (2026-07-09): replace
bottom-up multiplicative sizing (no deployment owner, 65% idle cash) with a
four-layer top-down design — dynamic regime-bounded deployment algorithm (aggregate
shrunk-Kelly, NOT a fixed number), concentrated conviction-weighted allocation,
integer-aware execution, staged long-short extension.

## Key evidence feeding the design

1. [VERIFIED] No component owns deployment — the only target-deployment concepts in
   the codebase are in the disabled QP and the passive benchmark sleeve
2. [VERIFIED] QP root cause: hard L1 turnover cap + 2% min-Δw floor interaction pins
   all new buys at ≈1.5% → dropped; both mitigations OFF in prod. Judgment: replace
   as primary sizer (keep as optional constraints-only projection), not repair —
   the replacement (`hybrid_option_f_allocator`, `fractional_kelly_top_k`) already
   exists in-repo with a replay harness and live shadow telemetry
3. [VERIFIED] conviction × sigma multipliers double-count μ/σ² on top of Kelly;
   `min_mult=0` zeroes at-floor names (cliff)
4. [VERIFIED] `panel_buy_top_n` is not in the active path — live initiation cap is
   `open_slots = max_concurrent_positions − held` (kills a recurring misattribution)
5. Config drift (ops note): umbrella-tree strategy_config.json copy is stale
   (fractional 0.5) vs pinned runtime config (0.3) — "merged ≠ deployed" again

## Changes

- `doc/design/2026-07-09-deployment-governor-rfc.md` — the RFC: architecture (L1–L4),
  deployment algorithm, evaluation protocol (end-of-chain preregistered replay with
  DeMiguel naive-diversification baseline arms), staged rollout (S0–S3), deliverable
  split across pipeline/strategy-104/orchestrator (D1–D8)

## Context

Supersedes knob-level Lane A framing (strategy-104 PRs #47/#48 closed; #49 one-share
floor stays as interim L3 measure). Evidence memo PR #442 reworked to
working-diagnosis status per Codex review and feeds this RFC.

## r4 update (2026-07-10)

Codex's r4 review (post cap-grid exploratory tuning run) raised four blockers, all
addressed in this round without touching the design's actual mechanics (the L2
allocator's down-only safety property was never broken — only the RFC's written
justification needed correcting):

1. **L1 candidate independence**: §2.1 now defines all three L1 candidates
   (regime-ceiling `E*_ceil`, `E*_kelly`, `E*_voltarget`) as fully independent
   formulas and states explicitly which one (`E*_kelly` only) is bounded by
   `E_raw` by construction. §2.2's feasibility claim was corrected — it had
   silently assumed the `E*_kelly` bound applies to all three candidates.
2. **Arm-specific gate contract**: the 12%-vs-20% cap contradiction is resolved
   by splitting the single-name-weight gate into a construction invariant
   (≤ the arm's own cap) and a separate operator-policy ceiling (12% to ENABLE
   without extra sign-off). Concentration-event and turnover-tax gates now have
   explicit formulas and frozen thresholds (D6 §2/§4).
3. **Fold construction**: D6 §2 now specifies deterministic contiguous 60-day
   blocks, walk-forward tuning/evaluation assignment with a 30-day embargo, and
   per-block HAC + inverse-variance-weighted pooling across blocks.
4. **Breadth-lever protocol**: cross-referenced to `renquant-strategy-104#52`,
   which was independently found to satisfy configurations/estimands/stop-rules/
   window/promotion-rule — with one flagged gap (no run-bundle fingerprint
   stamped per shadow session) noted as a follow-up to that PR, not fixed here.

## r4-correction update (2026-07-10, same day)

Codex then reviewed `strategy-104#52` DIRECTLY and found the r4 cross-reference
above premature: the within-shadow marginal-entrant decomposition + prod-XGB
counterfactual in #52 cannot identify the floor's causal effect once QP/sizing
interactions change portfolio weights, and the cross-repo protocol belongs in
orchestrator, approved BEFORE any strategy config is armed — not bundled into
a strategy-104 PR. `strategy-104#52` is now DRAFT pending this correction.

D6 §2a (new) replaces the #52 cross-reference with the actual protocol:
**two simultaneous isolated shadow arms** (S-0.5 = existing `shadow.json`;
S-1.0 = new `shadow_b.json`, identical except `buy_floor_std_mult`) instead of
one shadow arm decomposed after the fact — this makes the floor-effect
estimand (A) a true paired comparison with no hypothetical portfolio (both
arms actually execute, so real cost/tax applies automatically), and separates
it from a residual-environment diagnostic estimand (B: S-1.0 vs production)
that Codex's review showed the superseded design had conflated with the causal
claim. Also worked out, with the reasoning shown: the original ≥10-session HAC
test on 20d/60d overlapping returns is not adequately powered (effective
independent blocks `N_eff ≈ N/h` is ~0.5 at N=10,h=20 — far below the ~5-10
block reliability floor for HAC inference); replaced with a two-tier scheme
(directional-only kill-check at N=10, confirmatory HAC verdict gated on
`N_eff ≥ 8` matured observations, ~160 sessions for 20d / ~480 for 60d) plus a
predeclared 50bps/period non-inferiority margin. Infrastructure this requires
(new `alpaca_shadow_b` broker tag, parameterized `ReadOnlyBrokerWrapper`, a
new CLI surface, a `daily_104.sh` step, and strategy-104's `shadow_b.json`) is
specified concretely but NOT built in this doc-only PR — tracked as follow-up.
`strategy-104#52` will be resubmitted as a config-only treatment PR (just the
`shadow_b.json` + pin test) once §2a itself is reviewed and merged.
