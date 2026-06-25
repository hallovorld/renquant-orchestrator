# Panel-exit predictiveness research (XGB proxy + LIVE PatchTST validation)

2026-06-25. Trigger: the SHADOW run exited AMZN on `panel_conviction` (−2.35%) while prod held
it; operator asked for a theory+data teardown. Research/decision evidence; NO behavior change
(the rule lives in renquant-pipeline).

## What this is
Tests whether `CrossSectionalPanelExit`'s AND-rule (held name bottom-20% panel + mu≤0) predicts
forward underperformance, and whether that depends on regime — first with an XGB proxy, then
**validated on the live PatchTST pt07 seed44 scorer** (which CORRECTED a proxy artifact).

## Deliverables
- `doc/research/2026-06-25-panel-exit-regime-gate.md` — rule mechanism, QP-vs-rule contradiction,
  XGB-proxy + LIVE-PatchTST empirical tables, theory, regime-gated proposal.
- `scripts/research_panel_exit_predictiveness.py` + `tests/test_research_panel_exit.py`.

## Findings — and a self-correction
- **XGB proxy** suggested the bottom-20% ≈ the middle (exit captures ~0 alpha). **Live PatchTST
  (20k OOS rows, 2020–22) RETRACTS that**: the real bottom-20% is monotonic and significantly
  underperforms (AMZN-zone vs median = −0.086, CI [−0.124,−0.046]) → the rule has REAL aggregate
  value where the scorer discriminates losers. The proxy understated it.
- **The regime split SURVIVES the live model** (the actionable issue): bottom-20% predicts in
  BEAR (−0.22) / BULL_VOLATILE (−0.05) but **NOT in BULL_CALM** (+0.026, CI [−0.073,+0.123],
  leans positive). AMZN was exited in BULL_CALM — the regime where it doesn't hold.
- Internal contradiction: the QP wanted to KEEP AMZN (+2.6%, lowest-σ holding); the σ-blind,
  pre-QP rule overrode it.

## Proposal (validate further → renquant-pipeline PR, not now)
Regime-gate the AND-rule (BULL_CALM → strong-negative μ or defer to QP); don't override the QP
when it wants to keep; tighten `mu_sell_ceiling`. Caveat: live-model BULL_CALM sample is small
(n=260; these cuts are stress-heavy) — confirm with PatchTST scores from BULL_CALM-dominant
periods, then shadow-test, before any pipeline change.

## Note
Self-corrected after validating on the live PatchTST: retracted the "exit captures zero alpha"
over-claim (XGB-proxy artifact); the regime-conditional core (BULL_CALM mis-fire) held up.
