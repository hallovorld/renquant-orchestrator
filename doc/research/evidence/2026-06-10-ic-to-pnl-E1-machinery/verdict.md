# E1 machinery-validation run — verdict (NOT a promotion-grade result)

**Date:** 2026-06-10 · **Experiment:** E1 transfer-coefficient decomposition (IC→Sharpe RFC §5/E1)
**Status:** MACHINERY VALIDATION ONLY. This run exists to prove the E1 ladder produces well-formed, attributable Sharpe+TC numbers end-to-end. **It must not be cited as evidence about the strategy**, for two disqualifying reasons recorded below. The promotion-grade E1 run awaits (a) the P0 clean-IC artifact and (b) the E2 horizon-held fix.

## Why this run is not decision-grade

1. **Signal provenance unverified (RFC §7.1).** μ̂ comes from the sim decision-trace DB (`data/sim_runs.db`); its placebo/leakage status is exactly the open 2026-06-02 audit question. A real TC decomposition must run on the placebo-clean OOS IC artifact (P0, in progress).
2. **Daily rebalance, not horizon-held (RFC §A spec).** The harness re-solves every bar, turning A0 ("rebalance at horizon") into a daily book. With 60d forward returns fed as per-bar returns this inflated Sharpe to 8–12; even the 1-day-return variant below is daily-rebalanced. The E2 `HorizonHeldWrapper` (PR #69) is the fix; E1 must be re-run on top of it.

Both are pre-registered blockers in RFC §5 and §7 — this run does not bypass them, it validates the instrument while they are resolved.

## What the run does show (machinery is sound)

Run dir: `RenQuant/backtesting/renquant_104/artifacts/diagnostics/ic_to_pnl/E1/20260610T165049Z/`
(window 2025-04-01..2026-03-28, `--fwd-horizon-days 1`, cost 5bp, floor q=0.55, basis `replay_net_of_cost`).

| step | book | Sharpe | TC | ΔTC vs prev |
|---|---|---|---|---|
| 0 | A0 decile L/S, zero cost | 1.78 | 0.835 | — (ceiling) |
| 1 | A0 + 5bp cost | 1.65 | 0.835 | 0.000 |
| 2 | A2 long-only tilt | 1.92 | 0.865 | +0.030 |
| 3 | + vol/dd scalar overlay | 2.13 | 0.865 | **0.000** |
| 4 | + admission floor (q=0.55) | 1.81 | 0.691 | **−0.174** |
| 5 | + single-day-loss stop | 2.26 | 0.626 | −0.065 |
| 6 | current QP | 2.75 | 0.586 | −0.040 |

**Three machinery checks pass:**

- **H-B holds exactly (step 2→3):** the scalar overlay leaves per-date TC unchanged to 1e-9, as the hypothesis predicts by construction. The instrument correctly distinguishes a TC-neutral risk scaler from a selection change.
- **The admission floor is the largest single-step TC destroyer (−0.174):** the ladder localises information loss to a specific gate, which is the entire point of E1. (Whether that lost information was *real* alpha or noise is the P0/clean-IC question — the instrument measures TC, not signal truth.)
- **TC and Sharpe are NOT monotone together:** step 6 (QP) has the lowest TC (0.586) yet the highest Sharpe (2.75). On a daily-rebalanced, provenance-unverified signal this is uninterpretable — but it confirms the instrument reports them independently, so the real run can show whether the QP's risk shaping earns its TC loss.

## Reproduction

```bash
cd /Users/renhao/git/github/RenQuant && set -a && source .env && set +a
RENQUANT_REPO_ROOT=$PWD PYTHONPATH=/Users/renhao/git/github/renquant-pipeline/src \
  .venv/bin/python -m renquant_pipeline.kernel.portfolio_qp.e1_tc_decomposition \
  --sim-db data/sim_runs.db --start 2025-04-01 --end 2026-03-28 \
  --fwd-horizon-days 1 --out-dir backtesting/renquant_104/artifacts/diagnostics/ic_to_pnl/E1
```

Manifest (command, pins, sha256 of every output) and per-step traces are in the run dir; the tidy `e1_results.csv` is the file analyses should read.

## Next actions (pre-registered, RFC §5.6)

1. Land E2 horizon-held (PR #69) → re-run E1 with the held wrapper.
2. Consume the P0 clean-IC artifact (renquant-model, in progress) → promotion-grade E1.
3. Apply the §5.6 outcome table to the clean run: A0 ceiling weak ⇒ stop; ladder step with the largest Sharpe drop ⇒ the target to redesign.

Agent-Origin: Claude
