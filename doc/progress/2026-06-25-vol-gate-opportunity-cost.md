# Vol-gate opportunity-cost — EXPLORATORY diagnostic (no config change)

2026-06-25. Trigger: 2026-06-25 daily-full no-trade (`RealizedVolGateTask` dropped 21/97
candidates over the 60% vol cap). Operator: high-vol is opportunity too — but with theory +
rigorous data. Research/discussion PR — **NO behavior change, and (now) NO config proposal.**

## What this is
An exploratory diagnostic of whether the hard 60% realized-vol admission cap is conservative
given the downstream `1/σ²` Kelly sizing. Rebuilt twice after Codex review; the honest verdict
is **inconclusive** and explicitly **not** a basis for a config change.

## Deliverables
- `doc/research/2026-06-25-vol-gate-opportunity-cost.md` — theory (Kelly continuous; low-vol
  anomaly/BAB; Moreira–Muir is *portfolio* vol-timing, not this gate), survivorship caveat,
  regime-sliced cap sweep with bootstrap CIs.
- `scripts/research_vol_gate_opportunity_cost.py` + `tests/test_research_vol_gate.py` (pure
  helpers tested: fold non-overlap/embargo, bootstrap CI, metrics).

## Honest findings
- Point estimate: relaxing 0.6→1.0 raises Sharpe (+0.20→+0.70) without raising drawdown.
- **But the paired block-bootstrap CI for the 0.6-vs-1.0 monthly delta INCLUDES ZERO**
  (+0.0032/mo, 95% CI [−0.0002, +0.0080]) → **not statistically significant**.
- By **actual regime**: helps in BULL_CALM (n=42) and BULL_VOLATILE (n=47); **BEAR is n=3 →
  unmeasurable** (the earlier "cap helps in bear" was a calendar-period artifact — withdrawn).
- Panel is **survivorship-biased** (291/291 survive to 2026); proxy XGB ranker, not live PatchTST
  in the real sizing/QP/gate stack.

## Conclusion
**No config change supported.** Withdrew the prior "60% is the worst point / regime-aware rule"
claims. A real decision needs: PIT universe w/ delistings + live PatchTST + real Kelly/QP/gate
order + paired net/DD/turnover deltas with uncertainty → shadow-test before any production change.

## Note
Supersedes two earlier framings (a survivorship-biased mean; then an over-claimed "regime-aware"
calendar split). This version is faithful to the data: suggestive, not significant, not deployable.
