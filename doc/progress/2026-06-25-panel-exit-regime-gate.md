# Panel-exit predictiveness research (read-only ledger; ledger SUGGESTS predictive, mis-fire RETRACTED)

2026-06-25 (rewritten 2026-06-27 after two Codex reviews of PR #195). Trigger: the SHADOW run
exited AMZN on `panel_conviction` (−2.35%) while prod held it; operator asked for a theory+data
teardown. Exploratory research/decision evidence; NO behavior change (the rule lives in
renquant-pipeline).

## What this is
Tests whether `CrossSectionalPanelExit`'s AND-rule (held name bottom-20% panel + mu≤0) predicts
forward underperformance, and whether that depends on regime — **read-only over the wired decision
ledger** (`data/runs.alpaca.db`: `candidate_scores.panel_score`/`mu` joined to
`ticker_forward_returns.fwd_60d`, per-run-date), within-date per-date-block inference.

## Deliverables
- `doc/research/2026-06-25-panel-exit-regime-gate.md` — rule mechanism, ledger tables, conclusion.
- `scripts/research_panel_exit_predictiveness.py` (read-only, no model training) +
  `tests/test_research_panel_exit.py` (synthetic-ledger unit tests).

## Codex review (PR #195) — addressed
Round 1 (accepted):
1. **Repo boundary** (was training XGBRegressor in the orchestrator): REMOVED — read-only ledger.
2. **Non-reproducible live-PatchTST table**: GONE — committed read-only script over the pinned DB.
3. **Anti-conservative row bootstrap** → WITHIN-DATE per-date-block inference (date is the unit).
4. **Execution plan**: defers any pipeline change to a pre-registered shadow replay.

Round 2 (this revision):
1. **Dependence still anti-conservative** (adjacent dates' 60-session windows overlap → per-date
   blocks not iid; `mean/SEM` overstated t=−9.3): added a **MOVING-BLOCK BOOTSTRAP** (block = 60
   sessions); significance now keys on the bootstrap 95% CI excluding 0. The iid t is kept only as
   a labelled anti-conservative reference. Regimes with < 1 block of dates read **thin**, not sig.
2. **Aging not executable** (query only checked `fwd_60d IS NOT NULL`): added `--as-of` /
   trading-session aging against the ledger's own `as_of_date` session calendar; at as_of
   2026-06-27 this drops **15** not-yet-aged 2026-03 dates. New regression test fails on a
   60-calendar-day-but-<60-trading-session case.
3. **Conclusion too strong**: softened to "ledger evidence SUGGESTS predictive" (title + doc);
   shadow replay remains the decision gate.

## Finding — SUGGESTIVE (and a SELF-CORRECTION: the mis-fire claim flips)
On 410 aged BULL_CALM ledger dates the AND-fired names underperform the names you'd keep by −0.079
fwd60, **block-bootstrap 95% CI [−0.131, −0.002]** (75% of days; rank-IC +0.22). With overlap-aware
uncertainty the ledger **SUGGESTS the exit is predictive in BULL_CALM** — but only **marginally**
(CI upper bound ≈ 0). So the earlier "mis-fires in BULL_CALM" headline is RETRACTED, while the new
claim is stated as suggestive, not established. fwd20 corroborates with a cleanly-negative CI
([−0.063, −0.023]). BULL_VOLATILE (7d) and CHOPPY (14d) are now **thin** (< 1 block) — their earlier
large iid t's were the dependence artifact the block bootstrap removes.

## What still stands
The σ-blind / QP-override portfolio critique (the rule dumped AMZN, the lowest-σ ballast the QP
wanted to keep) is INDEPENDENT of predictiveness and is not refuted — but it is a turnover/risk/QP
question for a shadow replay, not a regime gate. The original regime-gate proposal is withdrawn.

## Note
Second self-correction on this thread: I previously retracted an XGB-proxy "zero alpha" over-claim;
now I also retract the "BULL_CALM mis-fire" claim once measured on the wired ledger instead of a
trained proxy. Lesson reinforced: validate on the ledger ground truth, in this repo's lane.
