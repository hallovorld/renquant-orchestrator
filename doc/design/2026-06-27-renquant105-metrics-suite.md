# renquant105 — metrics, KPI, acceptance criteria & daily retrospective

2026-06-27. Status: PROPOSAL (part of the renquant105 suite; master spec:
`2026-06-27-renquant105-intraday-system.md`). Reuses the existing 104 stores under a
new `strategy='renquant-105'` / `run_type` tag and finally wires the built-but-dark
`GateRegistry`/`decision_ledger` as the acceptance + monitoring backbone.

Binds to: `portfolio_daily_metrics` (sharpe/vol/dd/VaR/beta), `candidate_scores`
(raw/rank/mu/sigma/selected/blocked_by), `ticker_forward_returns` (fwd_1/5/10/20/60d),
`decision_ledger` (gate/verdict∈{allow,halve,block}/reason — currently dark),
`decision_pnl_attribution.selection_edge()`, MLflow `*_shadow` + `challenger_decisions`,
`post_ntfy()` alerting.

## 1. ALPHA metrics (metric | def | target | warn | alert)
- **X-sec rank IC** — Spearman(rank_score, fwd_5d) per date, 21-run roll | ≥+0.03 | <+0.02 | <0 ×5 runs
- **IC decay curve / half-life** — IC at {1,5,10,20,60d}; h½ where IC≤½·peak | peak@5d, h½≥5d | not monotone | sign-flip / h½<1d
- **Hit rate** — P(fwd_5d>0 | selected) | ≥52% | <50% | <47% (21 runs)
- **Net-of-cost Sharpe** — √252·mean/std of net daily return | ≥1.0 | <0.7 | <0.3
- **Sortino** | ≥1.4 | <1.0 | <0.5 ; **Information Ratio** (vs SPY) | ≥0.5 | <0.3 | <0
- **Alpha vs SPY** (OLS intercept, ann.) | >0, t>1.5 | ≤0 | <0 t<−1.5 ; **Profit factor** | ≥1.3 | <1.1 | <1.0

## 2. RISK metrics
- **Max drawdown** | >−12% | <−15% | <−20% (kill) ; **Realized vol** 21/252d | 10–18% | >22% | >30%
- **Intraday vol** (ann. session) | ≤1.5× 21d | >2× | >3× ; **VaR/CVaR 95/99** (hist, 21d) | VaR95<2.5% | >3.5% | >5%
- **Beta SPY** 252d | 0.3–0.8 | >1.0/<0 | >1.3 ; **HHI** | <0.18 | >0.25 | >0.35 ; **Effective-N** | ≥6 | <4 | <3
- **Gross/net exposure** | ≤1.0× / regime band ; **Intraday MAE** per name | >−5% | <−8% | <−12% (stop breach)

## 3. COST / EXECUTION metrics (NEW implementation-shortfall module — gap today)
- **Realized vs expected slippage (bps)** | ±5 of model | >+15 | >+30 (blowout)
- **Cost as % of gross alpha** | <25% | >40% | >60% ; **Turnover** (1-way/day) | <25% | >40% | >60%
- **Fill rate** | ≥98% | <95% | <90% ; **Effective spread paid** | <quoted | >1.2× | >2×
- **Implementation shortfall (Perold)** decomposed {delay, exec/spread, impact, opportunity} | <20 bps | >40 | >75
- **Participation vs ADV** | <5% | >10% | >20%

## 4. MODEL HEALTH metrics
- **Rolling OOS IC** (21-run, live only) | ≥+0.03 | <+0.015 | ≤0 ×10 → collapse
- **Calibration** (predicted ER vs realized; slope→1) | MAE<0.5%, slope∈[0.7,1.3] | slope<0.5 | slope≤0
- **Feature drift PSI** (already coded `score_drift_audit_prototype.py`) | <0.10 | 0.10–0.25 | ≥0.25
- **Staleness** | ≤1d | >2d | >4d (fail-closed)
- **Champion-vs-challenger** IC delta + rank-corr (MLflow + `challenger_decisions`) | challenger≤champion; ρ≥0.6 | challenger>+0.01 ×21 / ρ<0.4 | challenger>+0.02 ×42 / ρ<0.2 (one model broken)

## 5. PER-PHASE ACCEPTANCE CRITERIA (gating, not advisory)
**M1 model validation (offline):** OOS rank IC ≥ **+0.03** @5d · net-of-cost Sharpe ≥ **1.0**
· **Deflated Sharpe > 0** at the true trial count · **PBO < 20%** · placebo-clean (shuffled-label
+ time-shift; trust the placebo-clean DIFFERENCE, not absolute WF IC). All four gate.
**M2 shadow e2e (`alpaca_shadow`, no orders):** gate-stack precision ≥ **0.55** (P(fwd_5d>0|selected))
· killed-winner rate ≤ **15%** (blocked names whose fwd_5d was top-tercile) · selection edge
(selected_mean − vetoed_mean) > 0 on ≥80% of 21 runs · live-vs-shadow order-intent agreement ≥ **90%**,
score rank-corr ρ ≥ **0.9** · ≥ **20** full shadow runs.
**M3 live go/scale/kill:** go = M2 green + DSR>0 holds on shadow-period realized; live 21d Sharpe
within **±0.5** of shadow → on track; SCALE if 252d-equiv net Sharpe ≥ **1.0** AND dd shallower than
**−10%** AND killed-winner ≤15% (+1 gross step); HOLD if dd −12..−15% or Sharpe<0.5.

### Hard KILL conditions (fail-closed)
1. `max_drawdown_252d < −0.20`. 2. single-session `daily_return < −0.05` → halt buys, exits only.
3. rolling OOS IC ≤ 0 for **10** runs. 4. calibration slope ≤ 0 over 21 runs. 5. live-shadow rank-corr
ρ < 0.2 for 5 runs → revert to last-known-good champion.

## 6. DAILY RETROSPECTIVE (每日复盘)
Automated post-session job (read-only over runs DB + decision_ledger + MLflow); writes a report
artifact + posts one ntfy line + feeds the post-daily-reviewer loop + the `trade-review` skill.

**ntfy line:** `RETRO {date} | net P/L=$X (±%) | IC5d=+.. (21d +..) | edge=+.. (kept>vetoed) |
killed-winners=n/N (%) | slip=+Xbps vs +Y exp | IS=Zbps | regime=.. | shadow ρ=.. Δ=.. | dd=-.. | FLAGS: ..`

**Full report:** (1) **PnL attribution** (Perold/Brinson-adapted) decomposing realized PnL into
{alpha, spread, slippage, timing/execution} + sector allocation/selection; (2) **killed-winner
counterfactual** (every block/veto ⨝ realized fwd, per-gate `selection_edge` — "did the gates kill
winners?"); (3) rolling-IC + decay; (4) realized-vs-expected slippage per fill; (5) regime-conditioned
performance; (6) champion-vs-shadow (mean_diff, corr, top5_overlap, IC delta). FLAGS: KILLED-WINNER,
IC-COLLAPSE, SLIP-BLOWOUT, IS-HIGH, EDGE-NEGATIVE, SHADOW-DIVERGE, DD-WARN, CALIB-OFF (each raises ntfy priority).

## 7. Real-time monitoring (alert-lifecycle state machine; deduped)
data-freshness (>4d → fail-closed), slippage blowout (>30bps → exits-only), daily-loss (<−5% → hard halt),
gate anomaly (one `blocked_by` >50%/100% of universe → the historic sell-only failure), model-collapse
(IC≤0 ×10 or PSI≥0.25 → revert champion), shadow-divergence (ρ<0.2), drawdown (<−20% → kill).

## Build gaps to close (implementation PR)
1. **Wire `GateRegistry.persist()`** (built+tested, never called — the whole counterfactual/acceptance
layer needs a populated `decision_ledger`). 2. **New implementation-shortfall module** (no slippage/IS
computation today — needs arrival/decision-price capture per fill). 3. confirm **DSR/PBO** are computed
in `model_acceptance.py` as GATING. 4. decide 105 schema reuse-vs-fork tag.

Sources: Deflated Sharpe / PBO (Bailey & López de Prado, SSRN 2460551 + backtest-prob), Alphalens (IC),
empyrical/quantstats (Sharpe/Sortino/VaR/CVaR/profit-factor), Perold/Kissell (implementation shortfall),
Arize/Fiddler (PSI), HHI (Wikipedia), Sweeney 1996 (MAE).
