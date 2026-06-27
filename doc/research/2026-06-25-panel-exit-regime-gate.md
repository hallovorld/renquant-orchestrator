# CrossSectionalPanelExit: ledger evidence SUGGESTS the bottom-20% exit is predictive (incl. BULL_CALM) — the earlier mis-fire claim is RETRACTED

2026-06-25 (rewritten 2026-06-27 after two Codex reviews of PR #195). Trigger: the 2026-06-25
SHADOW run exited AMZN on `panel_conviction` (`CrossSectionalPanelExit`) at a −2.35% loss; prod
(XGB) held it. This is the theory + data teardown. **Exploratory research/decision evidence — the
rule lives in renquant-pipeline; NO change here.** This is a *diagnostic*: the ledger SUGGESTS a
direction; it does not decide a deployment (the decision gate is the shadow replay below).

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

## Method (leakage-robust, dependence-aware, aging-enforced — Codex #195 r1 #3, r2 #1/#2)
One run per date (the full-pool run); all stats are **within-date** and aggregated as a **per-date
block** (each date contributes one number). A uniform per-date level/leakage offset cancels inside
each date, and the unit of inference is the date, not the overlapping `(date,ticker)` row.

- **Trading-session aging (`--as-of`, Codex r2 #2).** `fwd_60d` is a 60-TRADING-SESSION label
  (`shift(-60)` over daily bars), ≈ 84 calendar days — NOT 60 calendar days. A row can carry a
  non-NULL `fwd_60d` written before its full horizon elapsed, so `fwd_60d IS NOT NULL` alone does
  NOT prove a date is aged. The script ages against the ledger's own session calendar (the sorted
  distinct `ticker_forward_returns.as_of_date`): a date is aged iff ≥ horizon later sessions fall
  in `(date, as_of]`. At `as_of=2026-06-27` the aged cutoff is **2026-03-05** and this drops **15**
  not-yet-aged dates (2026-03-06…03-26) that the prior version had silently included.
- **Overlap-aware significance (Codex r2 #1).** Adjacent dates' 60-session forward windows overlap
  and share regime shocks, so the per-date block series is NOT iid — `mean / SEM over dates` still
  overstates significance. Significance is reported via a **MOVING-BLOCK BOOTSTRAP** (block = the
  label horizon in sessions); a regime is called predictive/inverted only when the **block-bootstrap
  95% CI excludes zero**. The naive iid t is retained ONLY as a labelled, anti-conservative
  reference. Regimes with fewer dates than one block (≤ horizon) have no independent blocks to
  resample → they read **thin** (no CI), not "significant".
- Regime = the pipeline's own per-run `pipeline_runs.regime` tag.

## Result — REAL ledger, 473 aged dates (`--as-of 2026-06-27`, cutoff 2026-03-05), 2024-01 → 2026-03
AND-rule (bottom-20% panel AND mu≤0) exited names vs the names you'd KEEP, within-date,
**block-bootstrap CIs** (iid t shown only as an anti-conservative reference):

| regime | fired−kept fwd60 | block-bootstrap 95% CI | dates | % days fired<kept | rank-IC | reading |
|---|---|---|---|---|---|---|
| ALL | **−0.077** | **[−0.132, −0.003]** | 431 | 74% | +0.21 | SUGGESTS predictive (CI < 0) |
| **BULL_CALM (today)** | **−0.079** | **[−0.131, −0.002]** | **410** | **75%** | +0.22 | **SUGGESTS predictive (CI < 0, marginal)** |
| BULL_VOLATILE | −0.277 | thin (<1 block, 7d) | 7 | 86% | +0.48 | thin — not decision-grade |
| CHOPPY | +0.083 | thin (<1 block, 14d) | 14 | 29% | −0.27 | thin — not decision-grade |

`t_iid` (anti-conservative reference only): ALL −8.9, BULL_CALM −9.0. The honest CI is far wider
than the iid t implied: the BULL_CALM upper bound is **−0.002**, i.e. it excludes zero only
**marginally**. fwd20 corroborates the direction with a comfortably-negative CI (BULL_CALM −0.044,
95% CI **[−0.063, −0.023]**), where the shorter horizon means less label overlap.

## Conclusion — SUGGESTIVE, and the mis-fire claim is RETRACTED
**The earlier claim that the bottom-20% panel exit "mis-fires in BULL_CALM" does NOT survive the
real ledger.** On 410 aged BULL_CALM dates with the pipeline's own panel scores, the AND-fired
names underperform the names you would keep by −0.079 fwd60, with a block-bootstrap 95% CI of
[−0.131, −0.002] (75% of days; positive rank-IC +0.22). With overlap-aware uncertainty the ledger
**SUGGESTS the exit is predictive in BULL_CALM** — but only marginally (CI upper bound ≈ 0), so this
is suggestive, not established. fwd20 strengthens the direction (CI cleanly negative).

The prior "not predictive in BULL_CALM" reading came from a tiny (n≈260) covid+inflation OOS
PatchTST cut where BULL_CALM was rare and noisy; the production ledger (BULL_CALM-dominant,
2024–2026) is the larger sample and points the other way. The BULL_VOLATILE (7d) and CHOPPY (14d)
splits are now correctly reported as **thin** — fewer dates than one 60-session block, so no
overlap-aware CI; their earlier large iid t's were exactly the dependence artifact the block
bootstrap removes. CHOPPY's positive point estimate (+0.08) is hypothesis-generating only. BEAR has
no aged ledger coverage yet.

## What still stands (independent of predictiveness)
The original PR also raised a **portfolio-construction** critique that this predictiveness test
does NOT settle and does NOT refute: the rule is **σ-blind and overrides the QP**. On 2026-06-25
`QP_HOLDING_SOLVE AMZN target_w=+0.0261` (the μ/σ² optimizer wanted to KEEP AMZN, the lowest-vol
holding, σ=0.156) while `QP_TRADE_SUPPRESSED [preexisting_exit]` dumped it. That a name's
bottom-20% rank predicts lower mean fwd return does not mean dumping the book's low-σ ballast on a
single near-zero-μ reading is optimal for a Markowitz/Kelly book — that is a turnover / risk /
QP-interaction question for a shadow replay, below.

## Proposal (NOT a regime gate anymore; validate → renquant-pipeline PR, NOT now)
1. **Do NOT regime-gate the AND-rule off in BULL_CALM** — the ledger SUGGESTS it is predictive
   there (marginally). The original regime-gate proposal is withdrawn. This is suggestive, not a
   green light: the BULL_CALM CI upper bound sits at ≈ 0, so "leave it on" rests on the shadow
   replay, not on this diagnostic alone.
2. **σ / QP interaction**: the live concern is the rule overriding the QP on a near-zero-μ name it
   wants to keep as low-σ ballast. Test "exit only when the QP also targets ~0" vs the current
   σ-blind override — a turnover/drawdown question, not a predictiveness one.
3. No regime carve-out is supported by this data: BULL_VOLATILE and CHOPPY are now **thin** (fewer
   dates than one 60-session block → no overlap-aware CI). CHOPPY's positive point estimate is a
   hypothesis to test on more dates, nothing more.

## Caveats (honest)
- The ledger `panel_score` / `mu` are the live+sim pipeline's own outputs joined to realized
  `ticker_forward_returns`. Aging is **executable**: dates are kept only if ≥ 60 TRADING SESSIONS
  (from the ledger's own session calendar) have elapsed by `--as-of` — not merely `fwd_60d` non-NULL
  (which dropped 15 not-yet-aged 2026-03 dates). A regression test fails on a 60-calendar-day-but-
  <60-session case.
- Uncertainty is **overlap-aware**: a moving-block bootstrap (block = 60 sessions) gives an honest
  CI; the BULL_CALM result is significant only **marginally** (CI [−0.131, −0.002]) and the iid t
  (−9.0) is anti-conservative and reported as such. fwd20 (less overlap) is more robustly negative.
- Survivorship-biased panel; per-date IC/gap is in-sample of the scorer's deployment but the
  within-date gap cancels a uniform per-date offset.
- BULL_VOLATILE / CHOPPY / BEAR coverage is thin (≤ 1 block / 0 dates) — not decision-grade.
- Before ANY renquant-pipeline change, run a **pre-registered, path-dependent shadow replay** of
  current rule vs the σ/QP-defer variant on the same live scorer artifacts, with fixed acceptance
  metrics (turnover, suppressed-trade PnL, drawdown) and BULL_CALM-dominant coverage. The
  diagnostics here justify the experiment; they are not the experiment.
