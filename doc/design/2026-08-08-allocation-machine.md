# The allocation machine — a generative redesign in three layers

Operator directive 2026-08-08: *"我要的是高级的设计而不是只是满足我的要求!我的
要求只是一些方向性的。"* This document is the answer. It replaces the offline
routing-table frame as the system's target architecture; the gate machinery
built this week is retained, demoted to promotion-guard duty (§5).

## 0 · Why the previous frame deserved rejection

Two days of measurement produced an apparatus that kills ideas and a routing
table whose honest content is "change nothing." The measurements were correct
— whole-book switching dead, per-sector switching 3–5× over the gate bound,
120-cube all |t| < 0.8, blend sign-reversed out of sample — but the FRAME was
wrong: it demanded **offline per-cell proof of edge** from a history that
mathematically cannot supply it (regime n_eff 2–4; label overlap divides all
date counts by 20). A frame whose only possible outputs are "no" is not a
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

The repo's own reference file (`multi-panel-ensemble-references`, collected
earlier) independently points the same way: **AlphaMix** (train experts
independently → LEARN the routing) is layer 2's shape; **Two-Level
Uncertainty (2025)** (strategy-level regime gate + position-level cap) is
layer 1's shape. The research was already in the house; this design finally
uses it.

## 1 · Layer 1 — the deployment controller (ship first)

**Today the book's exposure is an accident.** Measured: 78.3% mean cash over
63 days (median 80.6%, max 94.7%) while the universe ran +11.6% in the same
window — ≈ $4.8k/yr forgone on a $11k book, the one number this week that
got LARGER under every correction. No routing idea in the dead frame was
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
* **It is estimable on 1910 days, not 77.** The controller is defined every
  day; its backtest does not condition on rare regimes. Vol-managed exposure
  has first-rank academic support. `[knowledge anchor — Moreira & Muir 2017
  "Volatility-Managed Portfolios"; Barroso & Santa-Clara 2015]`
* **Interaction with the deployment blockers (G-E):** the controller sets the
  TARGET; the three measured blockers (wash-sale mass block, integer-share
  floor, anti-high-price tilt) throttle the PATH to it. Shipping the
  controller makes the blockers' cost explicit run by run — `target minus
  achieved` becomes a monitored quantity with an owner, instead of an
  ambient accident.
* **Fallback floor:** `g ≡ 1, σ*/σ̂ ≡ 1` reproduces a fully-invested book;
  `E_min = today's achieved exposure` reproduces the status quo. The layer
  cannot be worse than either bound by construction.

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
* **Guarantees replace missing power:** the Hedge regret bound caps the gap
  to the best expert in hindsight at `O(√(T ln N))`; the panel floor caps
  the gap to today's system at a factor of 2 on the allocated half. Neither
  requires any expert to clear an offline significance gate.
* Start whole-book. Regime-conditioned weights (a separate weight vector per
  regime — the operator's regime×model table, learned online) are **v2**,
  gated on L1 shipping first: one axis at a time.
* Paper fills use the same cost model as live; a lane whose paper book
  cannot be marked honestly (missing prices, stale scores) is excluded that
  day — exclusion is logged, never silent.

## 3 · Layer 3 — the meta-label entry filter

The repo's own measured history: sim shows 76% win rate / +9.4% expectancy
while the live book is flat — and the standing memory names **meta-labeling
as the honest lever** (precision via selection, not curve-fit thresholds),
with the exit-side foundation already merged.

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
