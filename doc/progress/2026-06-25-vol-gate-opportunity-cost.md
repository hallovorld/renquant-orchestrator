# Vol-gate opportunity-cost research

2026-06-25. Trigger: the 2026-06-25 daily-full no-trade — `RealizedVolGateTask` dropped
21/97 buy candidates over the 60% annualized-vol cap. Operator: high-vol days are
opportunities too; raise the bar, don't freeze — research + experiment before concluding.

## What this is
A **research/discussion PR** (no behavior change). It tests whether the hard
`RealizedVolGateTask` (drop candidates >60% annualized 60d vol, config
`risk_gates.realized_vol.max_annualized`) costs risk-adjusted return vs. letting the
existing Kelly `1/σ²` vol-target sizing shrink high-vol names instead of excluding them.

## Deliverables
- `doc/research/2026-06-25-vol-gate-opportunity-cost.md` — method, results, caveats, proposal.
- `scripts/research_vol_gate_opportunity_cost.py` — reproducible purged-WF experiment.

## Headline finding
Among the model's top-quintile would-buy names, the GATED (>60% vol) set has a HIGHER
hit-rate (55% vs 49%) and per-name Sharpe (+0.181 vs +0.057) than the admitted set, and a
daily-basket sim shows **inverse-vol sizing (admit all) beats the hard cap on both return
(+0.078 vs +0.063) and Sharpe (+0.342 vs +0.259)**. The 60% cap is an untested heuristic
that contradicts Kelly's own realized-vol clip ceiling of 1.50.

## Proposal (to discuss, NOT deployed)
Raise `risk_gates.realized_vol.max_annualized` 0.60 → ~1.0–1.5 (align with the Kelly clip),
relying on the existing `1/σ²` sizing to shrink the high-vol band. One-line, reversible.
Validate with live-PatchTST scores + costs + per-regime, then shadow-test before any graduate.

## Honest caveats
Tail-inflated means (trust hit-rate/Sharpe); 2016–2026 was high-vol-friendly (edge may be
momentum-conditional); gross of costs/constraints; XGB proxy not live PatchTST; "raise the
ceiling" ≠ "no ceiling" (keep a hard cut for distressed >150% names). See the research doc.
