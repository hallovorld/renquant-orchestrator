# MID-TERM PLAN — direction & open workstreams

> Tier: **MID.** Agent proposes, operator confirms. Codex checks that PRs align with
> this, or that the PR explicitly justifies a change. Truth tags required.
> Last updated: 2026-06-17.

## North star
daily-full trades again, driven by a model with genuine **positive real cross-sectional
IC** that passes the WF gate — then raise *live* return (payoff, not hit-rate).
Main-line plan = PR #150.

## The binding problem
**The model has no current edge.** PatchTST (prod + fresh rebuilds) has *negative*
recent OOS IC; the gate correctly blocks it. This is the one thing between us and live
buys. `[VERIFIED — gate logs + panel-transformer.oos_mean_ic=-0.0246]`

## The lever
**Feature pruning** — the slow-drift family drives the placebo *and* drags IC negative.
The pruned **B2** variant is the only one with positive val IC. Direction: find the
feature subset with positive *aligned* IC **and** low placebo (per-feature audit →
retrain), as a **bounded, checkpointed** task — not open-ended autonomy.

## Enablers in place `[VERIFIED]`
- WF gate works end-to-end for PatchTST (config parity + manifest auto-match); a passing
  model promotes via the 3-key horizon contract.
- Win-rate reality: live hit-rate already ~83%; real lever is **payoff 0.89** (winners
  exited ~8d on a 60d strategy). Tool: PR #393.

## Open workstreams (PRs awaiting review)
- #150 main-line plan · #393 live win-rate tracker · #390 intraday governor primitive
  (flag-off) · #153 agent control contract + this memory structure.
