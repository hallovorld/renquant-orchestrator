# Multi-Horizon **Sleeves** — Design Proposal (supersedes the rejected score-blend)

**Status:** proposal · evidence-gated · shadow-first · **no live sleeve activated today**
**Date:** 2026-06-16
**Supersedes:** the multi-horizon *ensemble* doc (reverted in #148) — that design
fused horizon scores and traded them at a single 60d cadence, which is
structurally incapable of capturing multi-horizon alpha. This document replaces
the *scoring* frame with a *portfolio-construction* frame.
**Relates to:** `renquant-system-feature-map.md` §2.4; the scorer-lineup decision.

---

## 0. The one-sentence reframe

**Multi-horizon is a capital-allocation / portfolio-construction problem, not a
scoring problem.** You do not average 5d/20d/60d *scores* into one ranking; you
run K independent single-horizon **sleeves** (each a complete strategy with its
own signal, holding period, turnover, and sizing) and allocate *capital* across
them. The diversification (the IR gain from low-correlated alphas) is realized at
the **portfolio level across sleeves** — exactly like a multi-strat fund combines
low-correlated strategies — not by blending their per-name scores.

## 1. Why the previous (score-blend) design was rejected — and why this fixes it

The blended-score design failed on five counts (operator critique, 2026-06-16).
The sleeve architecture answers each *structurally*, not with a patch:

| # | Critique of the score-blend | How sleeves resolve it |
|---|---|---|
| ④ | **Cadence mismatch (fatal).** A 5d signal held at 60d cadence has its alpha fully decayed before exit; sized for 5d, fees eat it. | Each sleeve trades at **its own** cadence/holding period. No signal is ever held at the wrong horizon. The mismatch cannot occur by construction. |
| ③ | **Rank fusion destroys conviction/information.** A strong 5d name is flattened to a percentile and diluted by a useless 60d's random rank. | **No fusion.** Each sleeve ranks internally with full conviction (winsorized z-score). Sleeves combine *capital*, never scores. |
| ② | **Mixing known-bad 60d "industrial garbage" poisons the alpha.** | A sleeve that fails its own gate receives **0 capital**. Bad horizons are *excluded*, never blended. |
| ① | **The 20d edge is paper-thin (0.49), suspected P-hacking.** | **Evidence gate:** a horizon earns a sleeve only after passing a robustness gate (≥3 seeds × ≥2 disjoint OOS windows, placebo-clean). One 0.49 number activates nothing. |
| ⑤ | **6+ checkpoints to rescue a failed 60d + thin 20d — terrible ROI.** | Complexity is **real and large** (§5). It is justified *only* if ≥2 sleeves each independently clear their cost+gate **and** their combined net IR beats the single best sleeve. Otherwise the design's own output is "run one sleeve." |

## 2. Theory — where the IR actually comes from

Trading-calendar mapping (≈252 td/yr): 5d ≈ 1 week, 20d ≈ 1 month, 60d ≈ 1
quarter. Different horizons capture different anomalies / participant classes
(5d: liquidity shocks, reversal, news pulses; 20d: momentum continuation,
monthly rebalancing, CPI/NFP; 60d: earnings cycle, slow style drift). Because
their generating logic differs, the *realized returns of the sleeves* tend to be
low-correlation.

Portfolio of K low-correlated sleeves with per-sleeve Information Ratios `IR_k`
and a return-correlation matrix `ρ`: the combined IR is
`IR_port = (wᵀμ) / √(wᵀΣw)`. When off-diagonal `ρ` is low, `IR_port` exceeds the
best single `IR_k`. **Crucially this is a property of the sleeves' P&L streams,
not of their stock scores** — which is precisely why it must be built at the
capital layer, not the scoring layer.

The long-horizon S/N trap (our 60d placebo failure) is *contained*, not
exported: a failing 60d sleeve is a sleeve that gets 0 weight, full stop.

## 3. Architecture

```
            ┌──────────── signal layer (per horizon, independent) ───────────┐
  5d model ─┤ rank → 5d sleeve target book   (held ~5d,  weekly rotation)     │
 20d model ─┤ rank → 20d sleeve target book  (held ~20d, monthly rotation)    │
 60d model ─┤ rank → 60d sleeve target book  (held ~60d, quarterly rotation)  │
            └──────────────────────────┬─────────────────────────────────────┘
                                       │ each sleeve sized within ITS horizon's
                                       │ Kelly/σ; each passes ITS own WF gate
                          ┌────────────▼─────────────┐
                          │ capital allocator (§5.6)  │  w_k by validated IR,
                          │ + shared risk budget(§5.5)│  gate-failing sleeve→0
                          └────────────┬─────────────┘
                                       │ per-sleeve target tranches
                          ┌────────────▼─────────────┐
                          │ position netting (§5.1)   │  same symbol across
                          │ broker = net; sleeves own  │  sleeves → one net
                          │ tranches for exits         │  position, per-sleeve
                          └────────────┬─────────────┘  attribution retained
                                       ▼
                                 broker (Alpaca)
```

Each sleeve is internally **single-horizon** — it reuses the *existing*
QP/sizing/rotation/exit stack unchanged, just parameterized to its own horizon.
No downstream component has to understand "blended horizons," because there is no
blended signal. The only genuinely new components are the **allocator**, the
**netting layer**, and per-sleeve **attribution**.

## 4. Evidence-gated activation — the honest current state

Component evidence today:
- **60d:** fails placebo (intrinsic slow-drift). → no sleeve.
- **20d:** passes at ratio 0.49, 2 seeds — marginal, operator flagged as P-hacking
  risk. → **not yet** a sleeve; must clear the §6 robustness gate first.
- **5d:** val IC BULL_VOLATILE +0.017 / CHOPPY −0.061 — weak, regime-dependent,
  unproven. → not a sleeve.

**Therefore, as of today, this design activates ZERO new sleeves.** The live book
remains the single incumbent model. The deliverable now is (a) the framework, and
(b) the robustness protocol that gates any second sleeve. A second sleeve goes
live only when its horizon independently clears §6 **and** the portfolio passes
the §7 shadow-IR test. I am explicitly **not** assembling a real-money ensemble
out of a 0.49 marginal 20d.

## 5. Every hard problem, spelled out (no "open questions")

### 5.1 Position netting & cross-sleeve conflict
Same symbol targeted by multiple sleeves → **one net broker position**; each
sleeve owns a **tranche** with its own cost basis and exit clock. Conflict (60d
sleeve wants to hold AAPL, 5d sleeve wants to flip it):
- Sleeves are **independent sub-books**; the broker shows the algebraic sum.
- An exit reduces **only the owning sleeve's tranche**, never another sleeve's.
- A 5d sell of its own tranche can reduce the *net* position while the 60d tranche
  is untouched (net long shrinks, 60d thesis intact).
- Net target = Σ sleeve tranches; the executor diffs net-target vs broker and
  emits the minimal order set (avoids round-tripping the overlap).

### 5.2 PDT / sub-$25k constraint (can veto the 5d sleeve outright)
The live account is ~$10.5k → **Pattern Day Trader** rule: ≤3 day-trades / 5
business days. A 5d sleeve's weekly rotation risks breaching this. **The 5d sleeve
may be operationally infeasible on this account regardless of its alpha.**
Mitigations: enforce ≥1-overnight holds (no same-day round trips), cap 5d-sleeve
day-trade count against a shared PDT budget, or **shelve the 5d sleeve until the
account clears $25k**. This constraint is a first-class gate, not an afterthought.

### 5.3 Wash sales
5d and 60d sleeves trading the same name in opposite directions within 30 days →
wash-sale disallowance, distorting realized-loss accounting. Track wash-sale
windows per symbol **across sleeves**; either suppress the conflicting open or tag
the basis adjustment. (Tax-lot correctness, not alpha — but real money.)

### 5.4 Turnover-cost hurdle (per sleeve)
5d sleeve turns over ~12× the 60d sleeve. Its **gross** alpha must clear ~12× the
per-period cost (spread + fees + slippage + borrow) before it contributes net.
Each sleeve's gate (§6) is evaluated **net of its own turnover cost**, so a
high-churn sleeve with thin gross alpha is rejected automatically.

### 5.5 Shared risk budget
Sleeves do **not** each get a full Kelly/σ budget — they **share** the existing
portfolio vol target. Allocation: total target risk `σ*` split across sleeves
(`σ*² = wᵀΣw`); per-sleeve sizing scaled so the *combined* book respects the
incumbent vol/Kelly caps. No sleeve can push aggregate exposure past today's
limits. Correlated sleeve drawdowns (a risk-off day hits all horizons) are
budgeted via `Σ` using **realized sleeve-return correlation**, not assumed-zero.

### 5.6 Capital allocation across sleeves
Options, in increasing sophistication: (a) fixed weights; (b) IR-proportional
(`w_k ∝ IR_k`); (c) risk-parity; (d) mean-variance on sleeve P&L. Start **(b)
with a hard floor**: a sleeve below a min validated IR (or failing its gate) gets
**0**. Re-estimate weights on a slow cadence (e.g. quarterly) to avoid fitting to
noise. 60d → 0 today.

### 5.7 Per-sleeve gate independence + portfolio gate
Each sleeve passes the **WF gate at its own horizon** (placebo at 2×-horizon
shift). The *portfolio* additionally passes a **combined shadow-IR test** (§7):
the multi-sleeve book, net of all extra turnover, must beat the **best single
sleeve** out-of-sample. If it does not, the design's own conclusion is **"run the
single best sleeve"** — i.e. no ensemble. The architecture must be able to say no.

### 5.8 Attribution & observability
Every fill tagged with its owning sleeve → per-sleeve P&L, IR, turnover, and
realized sleeve-return correlation tracked live. This feeds §5.6 re-weighting and
§7 promotion, and makes "is the diversification real?" an empirical, auditable
question rather than a theoretical claim.

### 5.9 Operational / compute
K sleeves = K model inferences + K rotation passes daily. Offline/shadow this is
free (the whole point of shadow-first). Live, it is bounded (K≤3) and gated on the
§7 net-IR test clearing the *added* operational cost.

## 6. Robustness gate (what makes a horizon eligible for a sleeve)

A horizon does **not** earn a sleeve until:
1. Placebo-clean (`|placebo_ic| < 0.5·|aligned_ic|` at 2×-horizon shift), held
   across **≥3 seeds AND ≥2 disjoint OOS windows** (kills the single-0.49 risk).
2. Aligned IC ≥ a minimum economically-meaningful threshold (not just >0).
3. Net-of-turnover sleeve backtest IR positive at its own cadence.
4. (5d only) passes the §5.2 PDT-feasibility check on the live account size.

## 7. Deployment — shadow-first, falsifiable

1. Build the allocator + netting + attribution as **offline/shadow** components.
2. Run every gate-passing sleeve in the **daily shadow** path (no live orders):
   log per-sleeve would-be books, accumulate live OOS per-sleeve IR + realized
   cross-sleeve correlation.
3. Promote a second sleeve to live **only** when: its horizon clears §6 **and** the
   combined shadow book beats the best single sleeve net of all added turnover/cost
   over N weeks **and** a full WF-gate pass. High bar by design.
4. If shadow never beats the single best sleeve → **correct outcome is one sleeve.**

## 8. Honest limitations (carried, not buried)

- The whole thesis rests on sleeves' *realized P&L* being low-correlation. That is
  a bet to be **measured in shadow (§5.8)**, not assumed. If correlations are high,
  there is no IR gain and the complexity is unjustified.
- On a sub-$25k PDT account the 5d sleeve may be permanently infeasible (§5.2),
  reducing "multi-horizon" to 20d+60d — and 60d currently fails (§4).
- Today the design activates **nothing** live. That is the point: it makes "should
  we add a sleeve?" a cheap, safe, evidence-gated decision instead of a leap.

## 9. Next steps

1. Robustness-prove 20d to the §6 bar (≥3 seeds × ≥2 windows) — or fail it cleanly.
2. Build allocator + netting + attribution as offline/shadow primitives (flag-off,
   unwired) — same safety pattern as the intraday-governor primitive (#26/#390).
3. 5d PDT-feasibility analysis (§5.2) before any 5d modelling effort is justified.
4. Only if ≥2 horizons clear §6: run the §7 shadow comparison and report net IR.
