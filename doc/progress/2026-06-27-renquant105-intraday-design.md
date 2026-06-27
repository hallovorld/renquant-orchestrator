# renquant105 intraday system — design proposal

2026-06-27.

## What & why
Operator asked for a complete, professional, scientific design for an INTRADAY
trading system (renquant105) on the ~$10.6k Alpaca account: how to train the model,
get intraday data, decide; whether data/model/logic must change; speed/GPU; stricter
gating for unreliable trades; expected trade-count rise. This PR is the **design
proposal for Codex review** — no code.

## How it was grounded
Five parallel read-only research sweeps (regulatory/cost feasibility, 104→105 delta,
intraday data/latency, intraday model/training/GPU, stricter trade-vetting) + a
direct live-account check. All read-only; no git in the live tree.

## Headline findings (these shape the design)
- **PDT is gone (verified):** the $25k/3-trade rule was eliminated 2026-06-04; the
  live account shows `pattern_day_trader=False`, 4× intraday BP $37.7k. Regulation
  is no longer the blocker — **economics (cost vs tiny intraday edge) is.**
- **Not greenfield:** the intraday data + feature + model-swap infrastructure is
  already built and parked (disabled 2026-05-04). 105 is re-activation + an intraday
  model + tighter gates + a buy path.
- **No GPU needed; latency isn't the bottleneck.** The bottlenecks are IEX data
  coverage (~50% of universe lacks intraday history → liquid coverage-gated universe;
  $99/mo SIP only for live NBBO fills) and incremental ingestion.
- **QUANTITATIVE FEASIBILITY = likely NO-GO for intraday alpha at this size/data
  (§A):** RT cost ~11 bps vs ~1 bp single-bar edge (underwater ~10×); net-Sharpe
  band −2.0 to +0.5 (centered negative); 104's own realized Sharpe is sub-1. So the
  design pivots to a **measurement-grade cost-charged shadow harness** (no real
  money) + intraday **execution-timing/risk** on the daily book — NOT a new-alpha
  churn machine. Live intraday alpha stays OFF unless Phase-1 empirically clears
  net-Sharpe ≥1.0 + OOS IC ≥0.03 placebo-clean + DSR>0.
- **The decisioning is** a strict conjunctive fail-closed gate stack (cost-edge,
  conformal lower-bound, entry meta-label, CHOPPY no-trade, P&L circuit breaker,
  top-k under scarcity), with a
  **kill condition** if Phase-1 net-of-cost edge isn't placebo-clean.

## Deliverable
- `doc/design/2026-06-27-renquant105-intraday-system.md` — the full design: honest
  feasibility verdict, what's reusable vs new, data/model/logic deltas, GPU verdict,
  the gate stack, shadow-first deploy, a validation-gated phased rollout with a kill
  condition, and the open decisions for the operator.

## Next
Operator decisions (universe size, label horizon, SIP go/no-go, cost-edge bar,
single-horizon scope, kill condition) → then a Phase-0 (data) implementation PR.
Codex review on feasibility + the validation/kill discipline.
