# renquant105 — metrics, KPI, acceptance criteria & daily retrospective

2026-06-27. Status: PROPOSAL (part of the renquant105 suite; master spec:
`2026-06-27-renquant105-intraday-system.md`). Reuses the existing 104 stores under a
new `strategy='renquant-105'` / `run_type` tag and finally wires the built-but-dark
`GateRegistry`/`decision_ledger` as the acceptance + monitoring backbone.

**Primary horizon = open→close (intraday-only), finding 2.** All IC/hit-rate/forward-return
metrics below are computed on the **M0 session-horizon (open→close) forward-return surface**,
NOT daily `fwd_5d`. The daily `ticker_forward_returns(fwd_1/5/…d)` surface is **insufficient**
for an intraday strategy (it has no bar timestamps and no session-aware horizon); M0 builds the
required session-horizon surface. `fwd_5d` is retained only as a *secondary diagnostic*.

Binds to: `portfolio_daily_metrics` (sharpe/vol/dd/VaR/beta), `candidate_scores`
(raw/rank/mu/sigma/selected/blocked_by), the **M0 session-horizon return surface** (open→close
per name per session; `ticker_forward_returns(fwd_1/5/…d)` is a secondary diagnostic only),
`decision_ledger` (gate/verdict∈{allow,halve,block}/reason — currently dark),
`decision_pnl_attribution.selection_edge()`, MLflow `*_shadow` + `challenger_decisions`,
`post_ntfy()` alerting.

## 0. METRIC DICTIONARY — the SINGLE SOURCE OF TRUTH (finding 6)
Every metric below has **exactly one** definition here; M1/M2/M3, the reliability doc, and the
master spec MUST agree with it. Each entry pins: **numerator · denominator · sampling clock ·
annualization · benchmark · missing-data rule · CI method · action**. Thresholds are
**derived from the frozen H1 policy + the account risk budget** (one utility/capacity/vol/
min-effect basis), not asserted independently. The previously-inconsistent items (turnover,
G1-vs-cost/gross, IC/precision/dd thresholds, undefined alert windows) are reconciled here.

**Derivation basis (one frozen basis for ALL thresholds):**
- **Policy:** the pinned H1 policy (master §7) = **one book rotation/day** (a 4-name book
  entered once and exited at the close = 1.0 book turnover/day; **exactly one round trip per
  entered name**). All turnover/cost numbers are charged on THIS stateful path.
- **Account risk budget:** ~$10.6k, the per-name/per-session caps (M3 ladder), expected daily
  vol, and the max-tolerable-loss budget (§ reliability §3.3 / finding 7).
- **Min economically-meaningful effect:** net-of-cost Sharpe **1.0** on the policy replay (the
  power-calc target, M1 F1.7). **The open→close IC ≥ 0.03 bar is a SEPARATE, independently-stated
  threshold — NOT an equivalence** (round-4 #3: a Sharpe↔IC equivalence is false without a fixed
  score→position map, breadth, transfer coeff, vol, turnover, and cost, which are not all pinned;
  do not read "Sharpe 1.0" and "IC ≥ 0.03" as restatements of one another). Both are gating; the
  power calculation targets Sharpe 1.0, and IC ≥ 0.03 is a parallel acceptance row.

**0.1 Turnover — RESOLVE one-way vs round-trip (was contradictory).**
- **Round-trip (book) turnover/day** = book rotations/day. **Pinned policy value = 1.0** (one
  rotation). This is the cost-charging unit (each entered name = 1 round trip).
- **One-way turnover/day** = (shares traded in one direction) / book = with one full rotation,
  buying the new book is **100% one-way** and selling the old book is another 100% one-way →
  **a full rotation = ~100% one-way turnover/day**, NOT "<25%". **The old "one-way turnover
  <25%/day" KPI was WRONG for the open→close rotation policy** and is **REMOVED**. The pinned
  targets: **round-trip turnover/day ≤ 1.0** (warn >1.2 = unintended churn; alert >1.5 =
  multi-rotation, which §A rejects). One-way is reported as a diagnostic (~2× round-trip), not
  gated at 25%.
- *Numerator:* round-trips (entered names); *denominator:* book; *clock:* per session; *missing:*
  un-filled intents excluded from the numerator; *action:* >1.2 warn, >1.5 alert (churn).

**0.2 Cost-as-%-of-gross vs the G1 hurdle — RECONCILE to ONE number.**
- **G1 admission hurdle** (master §4): `net_alpha = ER − RT_cost > k·RT_cost` with **k = 1.75**
  ⇒ `ER > 2.75·RT_cost` ⇒ **cost/gross = RT_cost/ER < 1/2.75 = 36.4%** *at the per-trade
  admission margin* (the worst trade just clearing G1).
- The **portfolio KPI** `cost as % of gross alpha` is an **aggregate** over the whole book, not
  the marginal admitted trade; an aggregate below the marginal admission ceiling is expected
  because most admitted trades clear G1 with room to spare. **Pinned reconciliation:** the
  **per-trade G1 ceiling = 36.4%** (cost/gross at the k=1.75 margin) and the **portfolio
  aggregate target = ≤ 30%** (warn >36.4% = the book is running at the admission margin; alert
  >45%). The old "<25%" was an unjustified third number and is **replaced by ≤30% aggregate**,
  derived from k. *(If the operator prefers a tighter book target, raise k, not the KPI — the
  two must move together.)*
- *Numerator:* Σ realized RT cost (measured cost model); *denominator:* Σ gross alpha; *clock:*
  rolling effective-N window; *action:* >36.4% warn, >45% alert.

**0.3 IC / precision / dd — derived from ONE min-effect basis (NO Sharpe↔IC equivalence).** All
three trace to the **net-of-cost Sharpe 1.0** min-effect (M1 F1.7), but are stated as **separate
thresholds, not equivalences** (round-4 #3): **open→close IC ≥ 0.03** is an independent gating
threshold on the policy-replay rank IC; **gate-stack precision ≥ 0.55** is the meta-label
hit-rate that, at the policy's selection breadth and the measured σ_oc, yields net-Sharpe ≥ 1.0
after the measured cost (M2 acceptance); **max-dd thresholds** (warn −12..−15%, kill −20%) are
**consumed from the reliability §3.3b loss-budget config artifact** (finding 7 / §0.5 below), not
picked independently. If M1's measured moments change the basis, all are re-derived together via
the frozen procedure (the numbers move as one; the procedure is pinned).

**0.4 Alert WINDOWS — defined (were undefined).** Every alert below names its window explicitly:
rolling metrics use the **pre-registered effective-N window** (the step's ≥20 effective-
independent open→close sessions; M3) unless stated; freshness/dedup/slippage are **per-cycle**;
daily-loss is **per-session**; champion-vs-challenger divergence is over a **42-effective-session**
window. No metric below leaves its window implicit.

## 1. ALPHA metrics (metric | def | target | warn | alert)
*All "runs" below are reported with CIs over **effective-independent** observations (block
scheme on overlapping labels), not raw run counts (finding 3).*
- **X-sec rank IC** — Spearman(rank_score, **open→close return**) per session, rolled over the effective-N window | ≥+0.03 | <+0.02 | <0 with CI upper bound <0
- **IC decay curve / half-life** — IC at {open→close, 30min, 2hr} (intraday) + {1,5d} diag; h½ where IC≤½·peak | peak@open→close | not monotone | sign-flip / h½<1 session
- **Hit rate** — P(**open→close return**>0 | selected) | ≥52% | <50% | <47% (CI-bounded)
- **Net-of-cost Sharpe** — √252·mean/std of net daily return (on the **measured** cost model) | ≥1.0 | <0.7 | <0.3
- **Sortino** | ≥1.4 | <1.0 | <0.5 ; **Information Ratio** (vs SPY) | ≥0.5 | <0.3 | <0
- **Alpha vs SPY** (OLS intercept, ann.) | >0, t>1.5 | ≤0 | <0 t<−1.5 ; **Profit factor** | ≥1.3 | <1.1 | <1.0

## 2. RISK metrics
- **Max drawdown** | >−12% | <−15% | <−20% (kill) ; **Realized vol** 21/252d | 10–18% | >22% | >30%
- **Intraday vol** (ann. session) | ≤1.5× 21d | >2× | >3× ; **VaR/CVaR 95/99** (hist, 21d) | VaR95<2.5% | >3.5% | >5%
- **Beta SPY** 252d | 0.3–0.8 | >1.0/<0 | >1.3 ; **HHI** | <0.18 | >0.25 | >0.35 ; **Effective-N** | ≥6 | <4 | <3
- **Gross/net exposure** | ≤1.0× / regime band ; **Intraday MAE** per name | >−5% | <−8% | <−12% (stop breach)

## 3. COST / EXECUTION metrics (implementation-shortfall module — owned by **H2.0**, finding 2; gap today)
- **Realized vs expected slippage (bps)** | ±5 of model | >+15 | >+30 (blowout)
- **Cost as % of gross alpha** (aggregate; reconciled to G1 k=1.75 — §0.2) | ≤**30%** | >**36.4%** (running at the admission margin) | >**45%**
- **Round-trip (book) turnover/day** (the cost-charging unit; §0.1) | ≤**1.0** (one rotation) | >**1.2** | >**1.5** (multi-rotation churn — §A rejects)
- **One-way turnover/day** (diagnostic only — §0.1; the old "<25%" gate was WRONG for the rotation policy and is REMOVED) | ~2× round-trip | — | —
- **Fill rate** | ≥98% | <95% | <90% ; **Effective spread paid** | <quoted | >1.2× | >2×
- **Implementation shortfall (Perold)** decomposed {delay, exec/spread, impact, opportunity} | <20 bps | >40 | >75
- **Participation vs ADV** | <5% | >10% | >20%

## 4. MODEL HEALTH metrics
- **Rolling OOS IC** (effective-N window, live only) | ≥+0.03 | <+0.015 | ≤0 over the window → collapse
- **Calibration** (predicted ER vs realized; slope→1) | MAE<0.5%, slope∈[0.7,1.3] | slope<0.5 | slope≤0
- **Feature drift PSI** (already coded `score_drift_audit_prototype.py`) | <0.10 | 0.10–0.25 | ≥0.25
- **Staleness** | ≤1d | >2d | >4d (fail-closed)
- **Champion-vs-challenger** IC delta + rank-corr (MLflow + `challenger_decisions`) | challenger≤champion; ρ≥0.6 | challenger>+0.01 ×21 / ρ<0.4 | challenger>+0.02 ×42 / ρ<0.2 (one model broken)

## 5. PER-PHASE ACCEPTANCE CRITERIA (gating, not advisory)
**M1 model validation (offline):** OOS rank IC ≥ **+0.03** @**open→close** · net-of-cost Sharpe
≥ **1.0** (measured cost) · **probabilistic PSR/DSR ≥ 0.95** at the **full trial universe**
(horizons×labels×features×seeds×models×gates + prior 104/105 trials; the old "DSR>0" is dropped
as vacuous) · **PBO < 20%** · placebo-clean (shuffled-label + time-shift; trust the placebo-clean
DIFFERENCE). Sample = the **power/MinTRL-derived minimum in effective-independent observations**.
**M2 shadow e2e (`alpaca_shadow`, no orders):** gate-stack precision ≥ **0.55**
(P(**open→close return**>0|selected)) · killed-winner rate ≤ **15%** · selection edge with a
**block-bootstrap 95% CI lower bound > 0** (not "≥80% of 21 runs") · **pipeline parity
(champion-vs-itself) = EXACT 100% at the decision-contract level** (eligible universe,
features/fingerprints, scores-within-tolerance, gate verdicts, sizes, intents — every allowed
difference enumerated + reconciled; finding 5 — the old "≥90% / ρ≥0.9" is WRONG for a same-system
deterministic repro) reported separately from **strategy lift** (challenger-vs-champion marginal
IC, CI>0 — the ONLY comparator using statistical thresholds) · **per-gate ablation (ALPHA gates
only — finding 4; safety invariants verified by fault injection + property tests, never
PnL-scored)** with multiplicity correction · sample ≥ the power/MinTRL effective-N minimum.
**M3 live go/scale/kill:** go = M2 green + PSR/DSR ≥ 0.95 holds on shadow-period realized;
live Sharpe (over a pre-registered effective-N window) within **±0.5** of shadow → on track;
SCALE only on a **minimum live sample + exposure schedule** (not "+1 gross step" alone) if net
Sharpe ≥ **1.0** AND dd shallower than **−10%** AND killed-winner ≤15%; HOLD if dd −12..−15%
or Sharpe<0.5. (`252d-equiv` Sharpe is a scaling convenience and does NOT create 252 days of
evidence — the sample bar is effective-N, not annualization.)

### Hard KILL conditions (fail-closed) — state machine (finding 7/8)
*The session-loss / drawdown thresholds are **CONSUMED from the `loss_budget.yaml` config
artifact** (reliability §3.3b — the single source that PRODUCES them from caps × measured vol × gap
risk per ladder step; round-4 #7), NOT hardcoded here. The literal −5% / −20% below are the
artifact's current-step **generated** ceilings, shown for the reader; if the artifact changes,
these change with it. The safety trigger latency is the **fastest decision cadence**
(≤ `bar_interval`), not a generic 30 min (reliability §3.10).*
1. `max_drawdown_252d < dd_kill` (artifact; current ceiling **−0.20**) → **`NO_NEW_RISK` +
controlled flatten / reduce-only** (a drawdown breach is a MARKET-RISK event, not an integrity
failure — exits must stay ALLOWED; blocking all exits would TRAP risk). **`FULL_HALT` is reserved
for untrustworthy order-state/account-identity ONLY** (unreconciled broker state, wrong account).
2. single-session `daily_return < −session_loss_budget_step` (artifact; current ceiling **−0.05**)
→ **`NO_NEW_RISK`** (halt buys, **exits ALLOWED** — never a flag that blocks exits). 3. rolling
OOS IC ≤ 0 over
the effective-N window. 4. calibration slope ≤ 0 (CI-bounded). 5. live-shadow rank-corr ρ <
0.2 (CI-bounded) → revert to last-known-good champion.

## 6. DAILY RETROSPECTIVE (每日复盘)
Automated post-session job (read-only over runs DB + decision_ledger + MLflow); writes a report
artifact + posts one ntfy line + feeds the post-daily-reviewer loop + the `trade-review` skill.

**ntfy line:** `RETRO {date} | net P/L=$X (±%) | IC_oc=+.. (open→close; roll +..) | edge=+.. (kept>vetoed) |
killed-winners=n/N (%) | slip=+Xbps vs +Y exp | IS=Zbps | regime=.. | shadow ρ=.. Δ=.. | dd=-.. | FLAGS: ..`

**Full report:** (1) **PnL attribution** (Perold/Brinson-adapted) decomposing realized PnL into
{alpha, spread, slippage, timing/execution} + sector allocation/selection; (2) **killed-winner
counterfactual** (every block/veto ⨝ realized fwd, per-gate `selection_edge` — "did the gates kill
winners?"); (3) rolling-IC + decay; (4) realized-vs-expected slippage per fill; (5) regime-conditioned
performance; (6) champion-vs-shadow (mean_diff, corr, top5_overlap, IC delta). FLAGS: KILLED-WINNER,
IC-COLLAPSE, SLIP-BLOWOUT, IS-HIGH, EDGE-NEGATIVE, SHADOW-DIVERGE, DD-WARN, CALIB-OFF (each raises ntfy priority).

## 7. Real-time monitoring (alert-lifecycle state machine; deduped)
data-freshness (>4d → fail-closed), slippage blowout (>30bps → exits-only), daily-loss (<−5% → **NO_NEW_RISK**: halt buys, exits allowed; finding 7),
gate anomaly (one `blocked_by` >50%/100% of universe → the historic sell-only failure), model-collapse
(IC≤0 ×10 or PSI≥0.25 → revert champion), shadow-divergence (ρ<0.2), drawdown (<−20% →
**NO_NEW_RISK + controlled flatten**, exits allowed — NOT a full halt that traps exits).

## Build gaps to close (implementation PR)
1. **Wire `GateRegistry.persist()`** (built+tested, never called — the whole counterfactual/acceptance
layer needs a populated `decision_ledger`). 2. **Implementation-shortfall module — built in
**H2.0** (the independent observability milestone, finding 2), consumed by M2 + H2** (no
slippage/IS computation today — needs arrival/decision-price capture per fill, event-time-contract
bound — finding 1). 3. confirm the
**probabilistic PSR/DSR (≥0.95) + PBO** are computed in `model_acceptance.py` as GATING, fed the
**full trial universe** N (finding 3). 4. build the **M0 session-horizon (open→close) return
surface** (the daily `fwd_*d` surface is insufficient). 5. decide 105 schema reuse-vs-fork tag.

Sources: Deflated Sharpe / PBO (Bailey & López de Prado, SSRN 2460551 + backtest-prob), Alphalens (IC),
empyrical/quantstats (Sharpe/Sortino/VaR/CVaR/profit-factor), Perold/Kissell (implementation shortfall),
Arize/Fiddler (PSI), HHI (Wikipedia), Sweeney 1996 (MAE).
