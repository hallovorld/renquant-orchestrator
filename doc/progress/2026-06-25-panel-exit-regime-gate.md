# Panel-exit predictiveness research (read-only ledger; BULL_CALM mis-fire RETRACTED)

2026-06-25 (rewritten 2026-06-27 after Codex review of PR #195). Trigger: the SHADOW run exited
AMZN on `panel_conviction` (−2.35%) while prod held it; operator asked for a theory+data teardown.
Research/decision evidence; NO behavior change (the rule lives in renquant-pipeline).

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
1. **Repo boundary** (was training XGBRegressor in the orchestrator): REMOVED. The script now
   only reads the ledger and joins to realized returns — no model is trained here.
2. **Non-reproducible live-PatchTST table**: GONE. The decisive evidence is now the committed
   read-only script over the pinned ledger DB; anyone can re-run it.
3. **Anti-conservative CIs** (row bootstrap on overlapping 60d labels): replaced with WITHIN-DATE
   per-date-block inference (t = mean/SEM over dates; the date, not the row, is the unit).
4. **Execution plan not decision-grade**: the doc now explicitly defers any pipeline change to a
   pre-registered, path-dependent shadow replay and does not propose a config change off
   diagnostics.

## Finding — and a SELF-CORRECTION (the headline flips)
On 417 aged BULL_CALM ledger dates, the AND-fired names underperform the names you'd keep by
−0.081 fwd60 (t=−9.3, 76% of days; rank-IC +0.22). **So the "mis-fires in BULL_CALM" headline is
RETRACTED — the exit IS predictive in BULL_CALM on the real ledger.** The earlier "not predictive"
reading came from a tiny covid/inflation OOS PatchTST cut, not the production ledger. The signal
is strongest in BULL_VOLATILE (−0.29) and only **inverts in CHOPPY** (+0.08, 14 dates) — that, not
BULL_CALM, is the candidate carve-out.

## What still stands
The σ-blind / QP-override portfolio critique (the rule dumped AMZN, the lowest-σ ballast the QP
wanted to keep) is INDEPENDENT of predictiveness and is not refuted — but it is a turnover/risk/QP
question for a shadow replay, not a regime gate. The original regime-gate proposal is withdrawn.

## Note
Second self-correction on this thread: I previously retracted an XGB-proxy "zero alpha" over-claim;
now I also retract the "BULL_CALM mis-fire" claim once measured on the wired ledger instead of a
trained proxy. Lesson reinforced: validate on the ledger ground truth, in this repo's lane.
