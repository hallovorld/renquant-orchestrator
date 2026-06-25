# Panel-exit predictiveness research

2026-06-25. Trigger: the SHADOW run exited AMZN on `panel_conviction` (−2.35% loss) while prod
held it; operator asked for a theory + data grounded teardown of the exit rule's logic.

## What this is
Research/decision evidence (NO behavior change; the rule lives in renquant-pipeline). Tests
whether `CrossSectionalPanelExit`'s AND-rule (held name in bottom-20% panel + mu≤0) actually
predicts forward underperformance, or fires on noise — and whether that depends on regime.

## Deliverables
- `doc/research/2026-06-25-panel-exit-regime-gate.md` — exact rule mechanism, today's
  QP-vs-rule contradiction, the empirical percentile/decision-delta/regime tables, theory,
  and a regime-gated proposal to validate.
- `scripts/research_panel_exit_predictiveness.py` + `tests/test_research_panel_exit.py`.

## Key findings (purged-WF XGB proxy, 549k OOS rows, bootstrap CIs)
- Model alpha is **entirely in the top 20%** (+0.118); the bottom 0–80% is uniformly negative
  and statistically indistinguishable — the AMZN zone (10–20) ≈ the middle (40–60).
- **Decision delta**: exiting an AMZN-zone name vs holding the median name = **+0.0001, CI
  [−0.007, +0.007]** → exiting captures **zero** alpha.
- **By regime**: bottom-20% predicts underperformance in BEAR (−0.32) and BULL_VOLATILE (−0.046)
  but is **noise in BULL_CALM** (−0.0036, CI incl 0) — today's regime, where AMZN was exited.
- Internal contradiction: the QP wanted to KEEP AMZN (+2.6%, lowest-σ holding); the σ-blind,
  pre-QP rule overrode it.

## Proposal (validate in shadow → renquant-pipeline PR, not now)
Regime-gate the AND-rule (BULL_CALM → require strong-negative μ or defer to QP); don't override
the QP when it wants to keep; tighten `mu_sell_ceiling` toward `mu_strong`. Caveat: XGB proxy,
not live PatchTST — re-confirm with live scores + shadow-test before any deploy.
