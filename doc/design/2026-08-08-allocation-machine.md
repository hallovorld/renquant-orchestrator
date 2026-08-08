# The allocation machine — a generative redesign in three layers

Operator directive 2026-08-08: *"我要的是高级的设计而不是只是满足我的要求!我的
要求只是一些方向性的。"* This document is the answer. It replaces the offline
routing-table frame as the system's target architecture; the gate machinery
built this week is retained, demoted to promotion-guard duty (§5).

## 0 · Why the previous frame deserved rejection

Two days of measurement produced an apparatus that kills ideas and a routing
table whose honest content is "change nothing." The measurements were correct
— whole-book switching dead and per-sector switching 3–5× over the gate
bound `[VERIFIED — prior work,
doc/research/2026-08-08-moe-stage-minus1-results.md, diagnostics 1–2]`,
120-cube all |t| < 0.8 (strongest cell t = +0.76) `[VERIFIED — prior work,
doc/design/2026-08-08-routing-table-v0.md]`, blend sign-reversed out of
sample `[VERIFIED — prior work,
doc/research/2026-08-08-moe-s10-confirmatory-kill.md]` — but the FRAME was
wrong: it demanded **offline per-cell proof of edge** from a history that
mathematically cannot supply it (regime n_eff 2–4 `[VERIFIED — prior work,
doc/design/2026-08-07-moe-revision-2-power-and-membership.md §7 combiner
ladder (2–3); doc/design/2026-08-08-bear-exit-prereg.md (BEAR n_eff ≈ 4)]`;
label overlap divides all date counts by 20 — the frozen `n_dates / H` rule,
H = 20). A frame whose only possible outputs are "no" is not a
design; it is a veto. The operator asked for a machine that makes money, not
a machine that refuses noise.

The redesign rests on three moves that are standard in advanced practice and
need **less** data than the dead frame, not more:

1. **Predict what is predictable.** Returns are nearly unforecastable at our
   power; volatility and regime are the most persistent objects in the data
   (vol clustering; the production HMM already emits a daily posterior).
   Condition **exposure** on them, not model identity.
2. **Allocate adaptively under guarantees instead of selecting offline.**
   Online learning (Hedge / exponentiated-gradient) carries regret bounds:
   the realized allocation provably tracks the best expert in hindsight
   without ever proving t ≥ 2 for any expert — the theory substitutes for
   the power the history cannot give. `[knowledge anchor — Freund–Schapire
   Hedge; Helmbold et al. EG portfolios; Cover universal portfolios]`
3. **Filter, don't forecast.** Meta-labeling raises the precision of an
   existing signal by learning WHEN to act on it — trade-outcome labels give
   far more effective samples per year than 20d-overlap IC. `[knowledge
   anchor — López de Prado, Advances in Financial ML, meta-labeling; the
   repo's own memory already names this "the honest win-rate lever" with a
   built foundation: meta-label-exit.json, pipeline #23/#24]`

Prior survey work done for this system independently points the same way
(references inlined here so this document is self-contained): **AlphaMix**
`[knowledge anchor — arXiv:2207.07578]` — train experts independently, then
LEARN the routing — is layer 2's shape; **Two-Level Uncertainty (2025)**
`[knowledge anchor — arXiv:2603.13252]` — a strategy-level regime gate plus a
position-level cap — is layer 1's shape; **MarketRegimeNet**
`[knowledge anchor — github.com/lu8848/MarketRegimeNet]` is the closest
runnable analog (regime-aware multi-model ensemble over Alpha158 features).
The research was already in the house; this design finally uses it.

## 1 · Layer 1 — the deployment controller (ship first)

**Today the book's exposure is an accident.** Measured: **78.0% mean cash**
(median 80.2%, max 94.7%; 61 snapshot days on the benchmark window's own
dates) while the universe ran +11.63% in the same window — **≈ $994 missed
over the window, ≈ $4,820/yr at the window rate** on the $10,961.59 book
`[VERIFIED — prior work, orch#914 r3,
doc/research/2026-08-08-pocket-layer-return-space.md §2, script-measured from
live_state_snapshots]`. No routing idea in the dead frame was
within an order of magnitude of it.

**Design: exposure becomes a designed quantity.**

```
target_exposure(t) = clip( (σ* / σ̂(t)) · g(π(t)),  E_min,  E_max )

σ̂(t)   EWMA realized vol of the invested book (or universe proxy), λ frozen
σ*      target vol, frozen (calibrated once to the operator's drawdown appetite)
π(t)    the production HMM regime posterior (already emitted daily)
g(π)    a frozen, monotone exposure multiplier:
        g = 1 − κ_bear·π_bear − κ_vol·π_bull_volatile   (κ's frozen, small set)
E_min   floor — the book never sits accidentally in cash again
E_max   cap (≤ 1: no leverage)
```

* **This solves G-B on the size dial.** The BEAR signal — the strongest
  per-regime measurement in the system — controls HOW MUCH is at risk, a
  continuous decision needing no per-name selection and no 77-day-sample
  exit rule. orch#917's exit prereg stays open as a complementary line, no
  longer the G-B main line.
* **It is estimable on 1910 days, not 77** `[VERIFIED — prior work,
  doc/research/2026-08-08-pocket-layer-return-space.md (1910-day OHLCV
  panel); doc/design/2026-08-08-bear-exit-prereg.md (~77 BEAR days)]`. The
  controller is defined every day; its backtest does not condition on rare
  regimes. Vol-managed exposure
  has first-rank academic support. `[knowledge anchor — Moreira & Muir 2017
  "Volatility-Managed Portfolios"; Barroso & Santa-Clara 2015]`
* **Interaction with the deployment blockers (G-E):** the controller sets the
  TARGET; the three measured blockers (wash-sale mass block, integer-share
  floor, anti-high-price tilt) throttle the PATH to it. Shipping the
  controller makes the blockers' cost explicit run by run — `target minus
  achieved` becomes a monitored quantity with an owner, instead of an
  ambient accident.
* **Reproducible baselines (NOT a performance guarantee):** `g ≡ 1,
  σ*/σ̂ ≡ 1` reproduces a fully-invested book; `E_min = today's achieved
  exposure` reproduces the status quo. These are operational fallback
  CONFIGURATIONS — a clip constrains exposure, not returns, and a chosen
  controller can still underperform both baselines through vol/regime
  estimation error, timing, cash-implementation friction, or the deployment
  blockers themselves. **The full-history evaluation (§6.1) is the only
  source of any performance conclusion about this layer.**

## 2 · Layer 2 — online expert allocation (the routing table becomes alive)

Every registered expert (`xgb_rank_60d`, `xgb_clf_60d`, `mom_resid_252`,
`mom_resid_63`, and every future `val_*`/`rev_*` build) already runs — or
can run — a daily **paper book** in the shadow-lane infrastructure with its
own DB. That paper P&L is the training signal the offline frame threw away.

```
w_i(t+1) ∝ w_i(t) · exp(η · r_i^paper(t))      (Hedge / EG update, η frozen)
subject to  w_panel ≥ 0.5                       (champion floor)
```

* The weight vector **is** the routing table — no longer a frozen artifact
  but a published daily state (ops report line), with its full history in
  the DB. The operator watches the machine reallocate instead of reading
  kill verdicts.
* **Guarantees replace missing power — conditional on the following
  frozen contract**, without which the update equation supplies no theorem:
  1. *bounded loss transform*: the update consumes
     `clip(r_i^paper, −c, +c)` with `c = 5%/day` frozen — the Hedge bound
     holds for the transformed bounded series, and c is wide enough that
     clipping a diversified paper book is rare (logged when it happens);
  2. *feedback timing*: weights computed after day `t`'s paper marks are
     final, applied from day `t+1`'s open — no same-day feedback;
  3. *eligible-arm rule*: an arm with no honest mark that day (missing
     price, stale score) receives NO update that day and is renormalized
     with its weight carried; the exclusion is logged, never silent;
  4. *costs*: in the shadow phase weights allocate paper capital only; any
     live phase charges turnover costs INSIDE `r_i^paper` before the
     transform, so the bound applies to net series;
  5. the regret statement is then `O(√(T ln N))` versus the best FIXED
     expert in hindsight on the transformed net series — and it is a bound
     on regret, not a profitability claim.
  The champion floor `w_panel ≥ 0.5` is containment, not the theorem: it
  caps the allocation gap to today's system at the floored half regardless
  of what the learner does.
* Start whole-book. Regime-conditioned weights (a separate weight vector per
  regime — the operator's regime×model table, learned online) are **v2**,
  gated on L1 shipping first: one axis at a time.
* Paper fills use the same cost model as live; a lane whose paper book
  cannot be marked honestly (missing prices, stale scores) is excluded that
  day — exclusion is logged, never silent.

## 3 · Layer 3 — the meta-label entry filter

The repo's own measured history: the "76% win rate" headline was **sim**,
while the live record (35 closed trades, payoff 0.89) ranked names no
better than chance `[VERIFIED — prior work,
doc/research/2026-06-21-gate-calibration-results.md]` — exactly the
precision gap meta-labeling exists to close (selection, not curve-fit
thresholds), and the standing memory already names a meta-label **entry**
filter as the next lever (`doc/memory/mid-term/win-rate-payoff.md`), with
the exit-side foundation merged. *(Correction, visible per LONG #10: r1 of
this doc quoted "+9.4% expectancy" — no committed artifact carries that
number, so it is removed rather than tagged.)*

* A second-layer classifier on the panel's proposed entries:
  `P(win | regime posterior, vol state, score dispersion, breadth, name
  features)` → act / half-size / skip.
* Labels = realized trade outcomes (entry-to-exit), NOT 20d-overlap IC —
  a different, denser label structure.
* Training data exists today (`trade_evaluations` + sim trades with the
  live/sim provenance flag from the data-integrity memory); the model is
  deliberately small (logistic or shallow GBDT) and ships to SHADOW first.

## 4 · Why this is the advanced version of the operator's asks

| operator's directional ask | where it lands |
|---|---|
| "regime 和 sector 用不同的模型" | L2 weights, regime-conditioned in v2 — learned online, never proven offline |
| "芯片用快动量、大科技用回归" | a hypothesis L2 can EXPRESS and adaptively reward if true — without needing the 120-cube to reach t ≥ 2 first |
| "table 记录哪个 regime/sector 用哪个 model" | the L2 weight state, published daily with history — a living table |
| "多造几个模型" | the registry pipeline (val/rev/lowvol builds) feeds L2 as new arms; each arm is safe under the floor |
| "panel 最好就继续用 panel" | the champion floor is that sentence, as a constraint in the optimizer |
| BEAR conflict (G-B) | L1's `g(π_bear)` — the size dial, where the signal's strength actually fits the decision's data needs |

## 5 · What survives from the gate era

The §10 machinery, the receipts, the monitors, and the naming registry are
not discarded — they become the **promotion guards**: any change to L1's
frozen parameters (σ*, κ's, η, floors) or L3's threshold goes through the
freeze-then-measure protocol; the emitter supplies evaluation data; the
identity monitors watch the new surfaces. The gates guard the machine's
evolution instead of standing where the machine should be.

## 6 · Build order (each step has a floor, none needs new alpha to exist)

1. **L1 spec + full-history evaluation** (next session): frozen parameter
   set, 1910-day backtest of `target_exposure` vs the accidental book,
   report in return space (net, maxDD, Sharpe) with the same reproducibility
   standard as #913. Deliverable: the measured dollar value of designed
   exposure, and the proposal to the operator.
2. **L2 paper bandit in shadow**: the weight engine reads the existing lane
   DBs; publishes weights daily; touches nothing live. Two weeks of live
   weight history before any proposal.
3. **L3 dataset build**: trade-outcome labels with live/sim provenance; then
   the small classifier, shadow-first.

Authorization boundary unchanged: everything above is research/shadow;
**any live surface change remains operator-granted, one batch at a time.**
