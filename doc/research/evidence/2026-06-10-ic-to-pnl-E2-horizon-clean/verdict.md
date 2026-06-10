# E2 holding-horizon sweep on the clean PatchTST signal — verdict

**Date:** 2026-06-10 · **Experiment:** E2 (IC→Sharpe RFC §5/E2), the pre-registered next-action #1 from the E1-clean verdict — settle the A0-cost question by measuring the A0 decile-L/S ceiling **held at horizon**, not daily-rebalanced.
**Status:** Strong directional evidence (measurement instrument; same clean-signal caveats as E1). Run dir `RenQuant/.../ic_to_pnl/E2_clean_fixed/20260610T204539Z/` (manifest + tidy CSV committed alongside).

## A bug was found and fixed first (disclosed)

The first E2 run produced a tell-tale artifact: hold=20 and hold=40 came out **byte-identical** (Sharpe 0.667). Root cause (renquant-pipeline #75): `HorizonHeldWrapper` held the book **by array index**, but the replay universe membership rotates daily (names enter/leave on coverage). Changing-n bars hit the safe-resolve path and **degenerated every horizon to daily rebalancing**. The wrapper now holds a `{ticker: weight}` map projected onto each bar's tickers; a changing-universe regression test pins that distinct horizons now give distinct return streams. **The numbers below are post-fix; the pre-fix run (all long horizons ≈0.65) was wrong and is not used.**

## Result — A0 decile L/S held at horizon (clean signal, 190 bars, 1-day PnL, 5bp cost)

| hold (bars) | Sharpe | TC | turnover |
|---|---|---|---|
| 1 (daily) | 0.09 | 0.70 | high |
| **5** | **0.49** | 0.55 | — |
| 20 | −0.49 | 0.40 | — |
| 40 | −0.65 | 0.30 | — |
| 60 | −2.14 | 0.27 | low |

## What this settles — and the counter-intuitive finding

1. **The A0-cost question is answered: the A0 ceiling, held optimally, is ~Sharpe 0.49 at hold≈5 bars** — not the daily-rebalanced 0.09 (cost-shredded), and emphatically **not** higher at the label horizon.
2. **Counter-intuitive and important: the optimal holding horizon is ~5 days, not 60 — and holding to the 60-day label horizon is strongly negative (−2.14).** The 60-day *label* IC (+0.0724, placebo-clean) does **not** imply a 60-day *holding* is right. The tradeable component of the signal decays fast; TC falls 0.70→0.27 as the held book drifts from the live cross-section. This is textbook IC-decay (Qian-Hua-Sorensen 2007) and a concrete instance of the RFC §2.1 caution that label horizon ≠ holding horizon.
3. **It reinforces, not replaces, the E1 conclusion.** A0 is a market-neutral measurement instrument; even at its best (0.49) it is far below A2 long-only (1.85, E1). In this market-beta-positive window the dollar-neutral book gives up the beta that A2 keeps. A2 long-only remains the deployable winner; E2 simply maps the A0 ceiling and shows it is horizon-sensitive and modest.

## Implication for the production experiment

The recommended first production experiment (A2 long-only + scalar overlay, stops demoted to safety-only) should **not** assume a 60-day hold just because the label is 60-day. E2 says the tradeable horizon is short; the production design should rebalance on a shorter cadence (or use the GP-2013 cost-aware glide) and let the WF gate + step-4g replay pick the horizon with DSR/PBO. A dedicated A2 horizon sweep (E2 with `base=alpha_tilt_long_only`) is the natural next measurement before the production config is frozen.

## Caveats (unchanged from E1-clean)

1. Minimal long-only snapshot, not a production decision-trace reproduction.
2. Single fixed holdout, not walk-forward; promotion still gates on WF + DSR/PBO.
3. A0/A1 are dollar-neutral measurement instruments (short legs are `w_lower` violations by design); only A2 is deployable.
4. 1-day PnL with N-bar holding; the absolute Sharpes are measurement benchmarks, the **horizon ordering** (short ≫ long) is the robust takeaway.

Reproduction:
```bash
cd /Users/renhao/git/github/RenQuant && set -a && source .env && set +a
RENQUANT_REPO_ROOT=$PWD PYTHONPATH=/Users/renhao/git/github/renquant-pipeline/src \
  .venv/bin/python -m renquant_pipeline.kernel.portfolio_qp.patchtst_replay_loader \
  --experiment e2 --predictions <P0>/predictions.parquet \
  --clean-oos-manifest <P0>/manifest.json --sim-db data/sim_runs.db \
  --horizons 1 5 20 40 60 --out-dir backtesting/renquant_104/artifacts/diagnostics/ic_to_pnl/E2_clean
```

Agent-Origin: Claude
