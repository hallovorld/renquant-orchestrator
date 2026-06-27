# CrossSectionalPanelExit: predictive on the real ledger — the BULL_CALM "mis-fire" is RETRACTED

2026-06-25 (rewritten 2026-06-27 after Codex review of PR #195). Trigger: the 2026-06-25 SHADOW
run exited AMZN on `panel_conviction` (`CrossSectionalPanelExit`) at a −2.35% loss; prod (XGB)
held it. This is the theory + data teardown. **Research/decision evidence — the rule lives in
renquant-pipeline; NO change here.**

## What changed in this rewrite (repo boundary + reproducibility)
The first version of this study TRAINED an `XGBRegressor` inside `renquant-orchestrator` and then
leaned on an uncommitted ad-hoc PatchTST val-preds cut. Both are wrong for this repo: the
orchestrator orchestrates — it must not implement model-training / signal internals — and the
decisive table was not reproducible (no committed code, manifest, or hashes). This version is
**read-only over the now-wired decision ledger** (`data/runs.alpaca.db`): it joins the REAL
live/sim `panel_score` + `mu` the pipeline actually scored (`candidate_scores`) to REALIZED
forward returns (`ticker_forward_returns`). No model is trained; the scores are the pinned
scorer's own outputs. Repro: `scripts/research_panel_exit_predictiveness.py`.

## The rule (renquant-pipeline `task_panel_conviction_xs.py`)
- **AND-rule**: exit a held name if `panel ≤ bottom-20%ile threshold` AND `mu ≤ mu_sell_ceiling
  (0.0)`. **OR-bypass**: `mu ≤ mu_strong_sell_ceiling (−0.05)` alone. σ-blind; pre-QP; overrides QP.
- AMZN 2026-06-25: `panel=−0.200 ≤ thr=−0.176` (5th-lowest of 19), `mu=−0.0008 ≤ 0` → **AND-rule**
  fired (OR-bypass did not). Exited purely for ranking bottom-20% with a **near-zero** μ.

## Method (leakage-robust, dependence-aware — Codex #3)
One run per date (the full-pool run); all stats are **within-date** and aggregated as a **per-date
block** (each date contributes one number; t = mean / SEM **over dates**). A uniform per-date
level/leakage offset cancels inside each date, and the unit of inference is the date, not the
overlapping `(date,ticker)` row — so the prior anti-conservative row bootstrap is gone and the
effective sample is the number of independent dates (reported per regime). Regime = the pipeline's
own per-run `pipeline_runs.regime` tag.

## Result — REAL ledger, 477 aged dates, 2024-01 → 2026-03
AND-rule (bottom-20% panel AND mu≤0) exited names vs the names you'd KEEP, within-date:

| regime | fired−kept fwd60 | t | dates | % days fired<kept | rank-IC | reading |
|---|---|---|---|---|---|---|
| ALL | **−0.080** | −9.25 | 440 | 75% | +0.21 | exit PREDICTIVE |
| **BULL_CALM (today)** | **−0.081** | **−9.26** | **417** | **76%** | +0.22 | **exit PREDICTIVE** |
| BULL_VOLATILE | −0.291 | −4.28 | 9 | 89% | +0.45 | exit PREDICTIVE (stronger) |
| CHOPPY | +0.083 | +3.67 | 14 | 29% | −0.27 | exit INVERTED |

Decision delta (AND-fired fwd − the median name you'd hold instead): BULL_CALM = **−0.041
(t=−5.4)**; horizon-robust (fwd20: −0.044, t=−10.9).

## Conclusion — the headline is RETRACTED
**The earlier claim that the bottom-20% panel exit "mis-fires in BULL_CALM" does NOT survive the
real ledger.** On 417 aged BULL_CALM dates with the pipeline's own panel scores, the AND-fired
names underperform the names you would keep by −0.081 fwd60 (t=−9.3, on 76% of days), with a
positive cross-sectional rank-IC (+0.22). The exit is **predictive in BULL_CALM** — not noise.

The prior "not predictive in BULL_CALM" reading came from a tiny (n≈260) covid+inflation OOS
PatchTST cut where BULL_CALM was rare and noisy; the production ledger (BULL_CALM-dominant,
2024–2026) is the right sample and reverses it. The signal is strongest in BULL_VOLATILE
(−0.29) and only **inverts in CHOPPY** (+0.08, t=+3.7) — the one regime where exiting the
bottom-20% would forfeit alpha; that, not BULL_CALM, is the regime worth a second look (thin: 14
dates). BEAR has no aged ledger coverage yet.

## What still stands (independent of predictiveness)
The original PR also raised a **portfolio-construction** critique that this predictiveness test
does NOT settle and does NOT refute: the rule is **σ-blind and overrides the QP**. On 2026-06-25
`QP_HOLDING_SOLVE AMZN target_w=+0.0261` (the μ/σ² optimizer wanted to KEEP AMZN, the lowest-vol
holding, σ=0.156) while `QP_TRADE_SUPPRESSED [preexisting_exit]` dumped it. That a name's
bottom-20% rank predicts lower mean fwd return does not mean dumping the book's low-σ ballast on a
single near-zero-μ reading is optimal for a Markowitz/Kelly book — that is a turnover / risk /
QP-interaction question for a shadow replay, below.

## Proposal (NOT a regime gate anymore; validate → renquant-pipeline PR, NOT now)
1. **Do NOT regime-gate the AND-rule off in BULL_CALM** — the ledger says it is predictive there.
   (The original regime-gate proposal is withdrawn.)
2. **σ / QP interaction**: the live concern is the rule overriding the QP on a near-zero-μ name it
   wants to keep as low-σ ballast. Test "exit only when the QP also targets ~0" vs the current
   σ-blind override — a turnover/drawdown question, not a predictiveness one.
3. If any regime carve-out is worth testing, it is **CHOPPY** (exit inverted), not BULL_CALM — but
   on 14 dates that is hypothesis-generating only.

## Caveats (honest)
- The ledger `panel_score` / `mu` are the live+sim pipeline's own outputs joined to realized
  `ticker_forward_returns`; all 477 dates are aged (≥60d elapsed as of 2026-06-27 — no lookahead).
- Survivorship-biased panel; per-date IC/gap is in-sample of the scorer's deployment but the
  within-date gap cancels a uniform per-date offset.
- BULL_VOLATILE / CHOPPY / BEAR coverage is thin (9 / 14 / 0 dates) — directional only.
- Before ANY renquant-pipeline change, run a **pre-registered, path-dependent shadow replay** of
  current rule vs the σ/QP-defer variant on the same live scorer artifacts, with fixed acceptance
  metrics (turnover, suppressed-trade PnL, drawdown) and BULL_CALM-dominant coverage. The
  diagnostics here justify the experiment; they are not the experiment.
