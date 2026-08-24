# GOAL-2: conditional blend weights — a meta-learner over the existing legs

STATUS: design for review. No implementation in this PR. Operator-directed
2026-08-23; the operator delegated the two open design decisions (output form,
horizon) and mandated design → codex approval → implementation → deploy.

## 1. Estimand

Does a per-leg weight vector **w(state)**, conditioned on SLOW state variables,
beat the served **uniform z-sum** of the same legs, on 60-trading-day forward
DGTW-adjusted returns of the blended cross-sectional score?

Null = uniform weights = current production. Everything else is the alternative.

## 2. The two delegated decisions, and why they landed here

**Output = (b) dynamic weights on the existing z-blend legs** — not (a) a
replacement scorer, not (c) hard on/off routing.
- The served blend is an unweighted z-sum, and the weighting slot is already
  reserved in the system design (MoE AC5) — this fills a designed hole rather
  than opening a new estimand.
- Bounded failure: weights are clamped to [0, w_max] and renormalised;
  degenerate output ⇒ uniform ⇒ byte-identical to production.
- (c) hard routing is the form the frozen gates already killed three times
  (sector 27.8% < 33.3% chance with adjacent-quarter Spearman −0.185; daily
  dispersion contrast negative; momentum/reversal all-arm KILL). Soft weights
  conditioned on SLOW state are the one surviving hypothesis (orch#966), and
  the operator's macro variables (yield trend, VIX) are slow variables —
  the intuition and the surviving door coincide.

**Horizon = 60d, 104 lane only.** 105 consumes nothing from this line unless
it survives Stage 1. Intraday horizons would be a different model; they are
not this design.

## 3. Data — no new granularity, no new infrastructure

- **Base-model outputs**: the shadow fleet already records daily cross-sections
  for prod legs + `momentum_fast_v1`, `momentum_residual_v0`,
  `topdecile_clf_blend_leg`. This IS the meta-panel's X, already produced.
- **State variables (all daily, all free)**: VIX level and 3-month trend, 10Y
  yield 3-month trend, multi-month realized cross-sectional dispersion,
  regime label. Slow by construction — the surviving timescale.
- **Labels**: `ticker_forward_returns.fwd_60d` plus the backtest corpus.
- **10-minute data: explicitly rejected as a prerequisite.** The conditioning
  variables are slow and the label is 60d; finer granularity adds engineering
  and noise, not information. It belongs to 105 execution, which also does not
  need it in v1.

## 4. Stage 0 — ESS first, or nothing (~1 week, $0)

1. Assemble the meta-panel (leg scores × state × fwd returns), committed
   script, read-only inputs.
2. **Compute the effective sample BEFORE freezing any rule**: non-overlapping
   observation dates spaced ≥ h trading days, per horizon. Live data gives
   n_eff=2 at h=60 [measured 2026-08-23]; the backtest corpus must be measured
   the same way, and the yearly concentration of the edge (2020/2025/2026)
   counted against it, not around it.
3. Screen-grade conditional-skill table: per-leg IC by state tercile. SCREEN
   only — no decision follows from Stage 0.

**KILL: if n_eff at h=60 < 12 independent observations, Stage 1 is NOT run**
and that is the finding. (12 is the floor for a block-t to mean anything at
all; it is deliberately harsher than hope.)

## 5. Stage 1 — the simplest conditional model, prereg-frozen

- Model: ridge gating or depth-≤2 xgb, strong regularisation. NOTHING larger:
  a transformer at this n_eff is guaranteed memorisation of which years were
  good, indistinguishable in-sample from discovery.
- Prereg frozen BEFORE the run: folds, fold-defining constants (they are
  prereg content), the comparison statistic (block-t on non-overlapping
  blocks, gap ≥ h — never a borrowed 1.96), and the placebo discipline the WF
  gate applies (shuffled-label floor ≈ +0.04 is the known leakage floor;
  nothing under it counts).
- Comparison: w(state) blend vs uniform blend, same legs, same corpus.
- **Known trap, avoided by construction**: arms with different leg-counts
  measure DILUTION, not contribution [memory: served-blend-is-unweighted-zsum,
  08-18]. Both arms here always carry ALL legs; only weights differ.

**KILL: Stage 1 fails placebo or fails to beat uniform ⇒ line closed, written
up, no Stage 2.**

## 6. Stage 2 — capacity, only on survival

Larger models (deeper xgb, attention over leg histories) and richer state,
each against the same frozen comparison. Reaching Stage 2 requires Stage 1
surviving review — not merely being run.

## 7. Deployment path (if it survives everything)

The weight vector ships as a slow artifact (weekly refresh at most), through
the WF gate like any scorer change, then shadow before prod. No fast loop:
the hypothesis is slow-state; a daily-updating weight vector would be the
already-killed fast-routing hypothesis wearing new clothes.

## 8. Explicitly NOT in this design

- No 10-minute or finer data pipeline.
- No coupling to 105 until post-Stage-1 survival.
- No new base models — this line weighs existing legs. (New legs are their own
  WF-gated lines.)
- No claim that this fixes `genuine_ic ≈ 0`. If no leg has conditional skill,
  Stage 0's table will say so, and that is a finding worth having.

## 9. Review

codex (haorensjtu-dev). Implementation only after design approval.
