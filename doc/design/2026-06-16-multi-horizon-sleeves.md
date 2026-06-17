# Multi-Horizon Sleeves — **CHEAP FALSIFICATION FIRST; runtime architecture PARKED**

> ## ★ VERDICT (2026-06-17): do NOT build the sleeve runtime. ★
>
> **Central takeaway: cheap falsification before system design.** The expected
> number of surviving sleeves is **0 or 1**, so the 8–12-week allocator / netting /
> ITP / stressed-covariance / tax machinery (§3–§9) is **over-engineering and is
> NOT to be built.** Everything below the line is **PARKED** as a contingent record,
> not a roadmap.
>
> **The only sanctioned work** is two cheap falsification steps (§11 #1, #2), and
> they are *single-model* questions that need **none** of this machinery:
> 1. **Robustness-prove 20d** through the existing WF gate (≥3 seeds × ≥2 disjoint
>    OOS windows). Pass → it's an ordinary *model-swap* decision. Fail (likely) →
>    the multi-horizon line is **closed.**
> 2. **5d is dropped outright** — PatchTST (a daily-feature model) structurally
>    cannot produce a 5d microstructure signal (critique §0★-3). No 5d modelling,
>    no 5d PDT analysis needed.
>
> **Reopening trigger (narrow, explicit):** revisit the architecture *only if*
> (a) ≥2 horizons independently clear the WF robustness gate, **and** (b) a model
> substrate capable of genuine short-horizon (≤5d) microstructure alpha exists —
> neither holds today. Absent both, this stays parked. See
> `doc/decisions/2026-06-12-scorer-lineup-decision.md` (ensemble SHELVED).

## 0★. Why the runtime architecture was rejected (the decisive critique, 2026-06-17)

A second structured critique killed the *build* (not the hypothesis direction).
Each point conceded, none patched:

1. **ITP is pseudo-science at $10.5k retail scale (kills §5.1).** Modeled slippage
   on fractional / small-lot orders through a zero-commission retail router is
   *dominated by bid-ask + routing noise*; without tick data + institutional
   routing the "standalone-cost" fill is not audit-grade truth → per-sleeve IR is
   effectively unmeasurable at this size. The whole attribution layer assumed a
   measurement we cannot make.
2. **Wash-sale "pricing" is mathematically intractable (kills §5.3).** The
   disallowance is *path-dependent, discontinuous, tax-calendar-sensitive* — there
   is no continuous differentiable penalty for a mean-variance allocator; the
   honest implementation degenerates into allocator-jamming if-else.
3. **5d × PatchTST is an architectural mismatch (the kill shot).** 5d alpha that
   survives ~12× friction must come from microstructure / intraday flow. PatchTST
   consumes *daily* price-volume / macro features — it structurally **cannot**
   produce a 5-day liquidity-anomaly signal. **This removes multi-horizon's reason
   to exist:** with no 5d, "multi-horizon" is {20d marginal, 60d dead} → no
   ensemble, only a single-model "swap to 20d?" question needing none of §3–§9.
4. **Joint-drawdown breaker is reactive damage-control, not risk control (weakens
   §5.5).** By the time several sleeves jointly breach, the loss is realized; you
   sell the bottom and miss the rebound. Real multi-strat risk control needs
   *forward-looking exogenous* signals (VIX, credit spreads, cross-asset vol) — and
   partial regime gating already exists (RegimeModelAdmission / regime resolver),
   making the bespoke allocator redundant.
5. **The paradox = the conclusion.** §11's own roll-up admits the likely surviving
   sleeve count is **0–1** for an **8–12 wk + 6–12 mo** build. Building this machinery
   for ≤1 strategy is classic over-engineering. **§11 is this design's own death
   certificate** — so the central principle is *cheap falsification before system
   design.*

---

**Status:** ~~proposal~~ → **PARKED / post-mortem** (verdict 2026-06-17)
**Date:** 2026-06-16 (rejected 2026-06-17)
**Note:** §0–§11 below are **preserved verbatim** as the record of what was
considered. They are PARKED, not endorsed — read the verdict box first.
**Supersedes:** the multi-horizon *ensemble* doc (reverted in #148).
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

### 5.1 Position netting, internal crossing & **internal transfer pricing (ITP)**
Same symbol targeted by multiple sleeves → **one net broker position**; each
sleeve owns a **tranche** with its own cost basis and exit clock. Internal
crossing (60d buys 100 AAPL, 5d sells 100 → 0 sent to broker) is an execution
optimization — **but it must never touch attribution.** The v1 draft omitted the
transfer-pricing rule; that omission would let a high-turnover sleeve free-ride a
low-turnover sleeve's liquidity and report a fictional IR. Fix: **separate
attribution from execution.**

- **Attribution (per-sleeve P&L/IR):** every sleeve is marked **as if it executed
  standalone in the market** — filled at the executor's benchmark (arrival / VWAP,
  the *same* one the live executor uses) **plus its own modeled market-impact &
  slippage for its own notional and urgency.** A sleeve is *always* charged the
  full cost it would have paid alone, and **never** gets a better price merely
  because another sleeve took the other side.
- **Execution (real orders):** the netting engine crosses offsetting legs and
  sends only the residual to the broker. The **real spread/impact saved by the
  cross is booked to a portfolio-level "crossing-benefit" account — to neither
  sleeve.**
- **The fixed ITP rule (ex-ante, auditable):** internal crosses are priced at the
  same arrival/VWAP benchmark used for standalone attribution; the saved cost is a
  portfolio overlay, never a per-sleeve credit. → no sleeve eats another's
  liquidity; per-sleeve IR (§5.8) reflects standalone economics and survives audit.
- **Conflict mechanics:** sleeves are independent sub-books; broker shows the
  algebraic sum; an exit reduces **only the owning sleeve's tranche**; a 5d sell of
  its own tranche shrinks the net while the 60d tranche (and thesis) is untouched.

### 5.2 PDT / sub-$25k constraint (can veto the 5d sleeve outright)
The live account is ~$10.5k → **Pattern Day Trader** rule: ≤3 day-trades / 5
business days. A 5d sleeve's weekly rotation risks breaching this. **The 5d sleeve
may be operationally infeasible on this account regardless of its alpha.**
Mitigations: enforce ≥1-overnight holds (no same-day round trips), cap 5d-sleeve
day-trade count against a shared PDT budget, or **shelve the 5d sleeve until the
account clears $25k**. This constraint is a first-class gate, not an afterthought.

### 5.3 Wash sales — **priced, never vetoed** (independence is sacrosanct)
The v1 draft's "suppress the conflicting open" was **wrong** and self-contradicting:
vetoing a sleeve's signal because *another* sleeve traded the same name within the
30d window makes the suppressed sleeve's live behaviour diverge from its
backtest/shadow — the high-frequency (5d) sleeve eats the low-frequency (60d)
sleeve's tax situation, its alpha decays, and the whole portfolio misses its
target Sharpe. **Hard principle: wash-sale handling must NOT alter any sleeve's
open/close decision.** Instead:
- The disallowed-loss effect is a **cost term**, charged to the *triggering* sleeve
  (or a shared tax account) and priced into that sleeve's **net-of-cost** gate
  (§6). The signal still fires; the cost is *priced*, not *blocked*.
- Where it materially recurs, prefer **tax-aware sizing** — a *continuous*
  tax-penalty term in the allocator (§5.6) — never a binary veto; and/or
  **account/entity separation** for execution.
- **IRS reality (stated, not glossed):** wash-sale matching applies **across all
  accounts of the same taxpayer** (incl. IRAs). So account separation reduces
  operational entanglement but does **not** by itself avoid the matching — the
  robust fix is pricing the cost, not hiding the trade.

### 5.4 Turnover-cost hurdle (per sleeve)
5d sleeve turns over ~12× the 60d sleeve. Its **gross** alpha must clear ~12× the
per-period cost (spread + fees + slippage + borrow) before it contributes net.
Each sleeve's gate (§6) is evaluated **net of its own turnover cost**, so a
high-churn sleeve with thin gross alpha is rejected automatically.

### 5.5 Shared risk budget — **diversification is an IR bonus, never a leverage license**
Sleeves **share** the existing portfolio vol target (no sleeve gets a full
Kelly/σ budget). But the covariance `Σ` is explicitly **NOT trusted to lever**:
- **Estimation is ill-conditioned.** 2–3 sleeves (60d currently dead, 5d unrun),
  short history, and — critically — **overlapping returns**: a 60d holding produces
  60d-overlapping observations, so the effective sample ≈ calendar_days ÷ horizon
  (tiny). A naive `Σ` from recent calm data is statistically unstable.
- **Tail-correlation breakdown.** Normal-times `ρ≈0` collapses to `ρ→1` in a
  liquidity/macro crisis — all horizons draw down together. Sizing up on
  realized-calm `ρ` invites a **fatal joint drawdown**.
- **Therefore sizing is conservative / sub-additive.** Aggregate exposure is capped
  **assuming `ρ=1` (zero diversification credit) for leverage purposes**, using a
  shrinkage (Ledoit–Wolf) / stressed-`Σ` with a crisis correlation floor; the
  combined book respects the incumbent vol/Kelly caps **under stress**. Measured
  low correlation (§5.8) is allowed to **improve reported IR**, **never** to
  **increase position size**.
- **Joint-drawdown circuit breaker.** A portfolio-level guard de-risks *all*
  sleeves when multi-sleeve drawdown breaches a threshold — it does not wait for
  `Σ` to "notice" the regime change.

### 5.6 Capital allocation across sleeves
Options, in increasing sophistication: (a) fixed weights; (b) IR-proportional
(`w_k ∝ IR_k`); (c) risk-parity; (d) mean-variance on sleeve P&L. Start **(b)
with a hard floor**: a sleeve below a min validated IR (or failing its gate) gets
**0**. Re-estimate weights on a **slow cadence (quarterly)** to avoid fitting to
noise; any covariance input uses the **shrinkage / stressed `Σ` of §5.5** — and
per §5.5 the diversification credit adjusts *weights*, never total *leverage*. The
optional **tax-penalty term** (§5.3) lives here as a continuous cost, not a veto.
60d → 0 today.

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

## 7. Deployment — shadow-first, **measured in independent cycles, not weeks**

The v1 draft's "over N weeks" was statistically naive: a 20d sleeve rotates ~1×/
month and a 60d sleeve <0.5 cycle/month, so "a few weeks" is ≈1 sample —
indistinguishable from beta/luck. The unit of evidence is **independent
(non-overlapping) holding cycles**, not calendar weeks.

1. Build allocator + netting + attribution as **offline/shadow** components.
2. Run every gate-passing sleeve in the **daily shadow** path (no live orders): log
   per-sleeve would-be books; accumulate **risk-/factor-adjusted, market-neutral**
   OOS performance (cross-sectional IC/IR, alpha net of factor beta — *not* raw
   return over a lucky window) + realized cross-sleeve correlation.
3. **Incubation requirement.** Promotion needs a minimum number of **non-overlapping**
   OOS cycles for significance → for a 60d sleeve that is **quarters-to-years
   (≈6–12+ months live)**, consistent with industry low-frequency incubation; for
   20d, multiple months. The implied calendar is stated honestly per horizon and
   **not** shortcut.
4. **Where the statistical weight actually sits.** Live time yields too few
   independent low-freq cycles to establish significance on its own, so the
   **cross-sectional WF gate over disjoint historical OOS windows** (many more
   independent cross-sections than live time can offer) carries the burden of proof;
   live shadow is **long-horizon confirmation + regime-change guard**, not the
   significance test itself.
5. **Power-aware default.** Until the sample clears the per-horizon power bar (it
   will be underpowered for months), the verdict is **"insufficient evidence → do
   not promote."** Promotion requires the historical WF evidence to *already* clear
   the bar **and** the combined shadow book to beat the best single sleeve net of
   all added turnover/cost **and** a full WF-gate pass.
6. If shadow never beats the single best sleeve → **correct outcome is one sleeve.**

## 8. Honest limitations (carried, not buried)

- The whole thesis rests on sleeves' *realized P&L* being low-correlation. That is
  a bet to be **measured in shadow (§5.8)**, not assumed — and per §5.5 even a
  measured low correlation buys **no extra leverage**, only better weights, because
  tail correlation goes to 1.
- On a sub-$25k PDT account the 5d sleeve may be permanently infeasible (§5.2),
  reducing "multi-horizon" to 20d+60d — and 60d currently fails (§4).
- Per-sleeve IR is only meaningful **if** the ITP discipline (§5.1) holds; a sloppy
  internal-crossing mark silently inflates the high-turnover sleeve.
- Low-frequency significance is **months-to-years** of independent cycles (§7); any
  promotion claim made on a few weeks of live data is noise, by construction.
- Today the design activates **nothing** live. That is the point: it makes "should
  we add a sleeve?" a cheap, safe, evidence-gated decision instead of a leap.

## 9. Next steps

1. Robustness-prove 20d to the §6 bar (≥3 seeds × ≥2 disjoint windows) — or fail it
   cleanly. This is the only step actionable today and gates everything else.
2. Build the offline/shadow primitives (flag-off, unwired — same safety pattern as
   the intraday-governor #26/#390): **(a)** attribution engine with the §5.1 ITP
   rule (standalone-cost fills + portfolio crossing-benefit account); **(b)** netting
   engine; **(c)** stressed-`Σ` / shrinkage risk allocator (§5.5) with the
   diversification-≠-leverage cap + joint-drawdown breaker; **(d)** tax-cost term
   (§5.3) — priced, never a veto.
3. 5d PDT-feasibility analysis (§5.2) **before** any 5d modelling effort is justified.
4. Only if ≥2 horizons clear §6: run the §7 shadow comparison — judged on
   risk-/factor-adjusted performance over **independent cycles** (months-to-years,
   not weeks) — and report net IR vs the best single sleeve.

## 10. Critique → resolution map (this v2 must close all four)

| objection (2026-06-16) | resolved in | one-line resolution |
|---|---|---|
| ① netting lacks transfer pricing → attribution fiction | §5.1 | standalone-cost fills; crossing benefit booked to portfolio, never a sleeve |
| ② wash-sale "suppress open" breaks independence | §5.3 | price the tax cost into the gate; **never** veto a sleeve's signal |
| ③ covariance model naive + tail-blind | §5.5–5.6 | stressed/shrunk `Σ`; diversification = IR bonus, **not** leverage; joint-DD breaker |
| ④ "shadow N weeks" statistically meaningless | §7 | unit = independent non-overlapping cycles (60d → 6–12+ mo); WF cross-sections carry significance |

## 11. Difficulty / effort estimation per deliverable

T-shirt size (S≈≤2d, M≈3–5d, L≈1–2wk, XL≈3wk+, all single-builder); effort is
*build + test*, not the (much longer) §7 incubation calendar. "Gated-on" =
nothing downstream is worth building until that gate is green.

| # | deliverable | size | effort | genuinely hard part / primary risk | gated-on |
|---|---|---|---|---|---|
| 1 | **Robustness-prove 20d** (§6: ≥3 seeds × ≥2 disjoint OOS windows) | **M** | 3–5d (mostly compute) | none technically — harness exists (R4-repaired WF gate). Risk: **likely FAILS** (0.49 is fragile) — but that is a *cheap, high-information* no | — (actionable now) |
| 2 | 5d **PDT-feasibility** analysis (§5.2) | **S** | 1–2d | pure simulation of 5d turnover vs PDT 3-trades/5-day on $10.5k. Risk: a hard NO that kills the 5d sleeve outright (also cheap, valuable) | — (actionable now) |
| 3 | **Attribution engine + ITP** (§5.1) | **L** | 1–2wk | **the subtle one** — per-sleeve standalone market-impact/slippage model + crossing-benefit account. A wrong impact model *silently* inflates the high-turnover sleeve → corrupts every IR/decision downstream | #1 |
| 4 | **Netting engine** (§5.1 exec) | **M** | ~1wk | tranche bookkeeping + net-target diff + minimal-order-set under partial fills / rejects / cross-sleeve exit ordering. Mechanical but edge-case heavy | #3 |
| 5 | **Stressed-`Σ` risk allocator + joint-DD breaker** (§5.5–5.6) | **L** | 1–1.5wk | math is standard (shrinkage/stressed-corr); the risk is **integration with live Kelly/σ sizing** without loosening existing caps + the no-leverage-from-diversification invariant | #1 |
| 6 | **Tax-cost term** (§5.3, priced not vetoed) | **M** | 3–5d | wash-sale window tracking across sleeves + continuous penalty in the allocator; tax-lot accounting is fiddly/easy to get subtly wrong | #5 |
| 7 | **Sleeve runner / shadow harness** (§7) | **L–XL** | 1.5–2.5wk | run K independent sleeves daily in shadow (each its own inference+rotation+sizing), isolated, logging per-sleeve books + attribution. Reuses the per-sleeve pipeline; the **orchestration + isolation** is new | #3,#4,#5 |
| 8 | **5d/20d model training to gate** (per horizon) | **M** each | 3–5d compute each | compute-bound; only justified *after* #1/#2. 5d is unproven + regime-dependent | #1,#2 |
| 9 | **Live wiring + promotion** | **XL** | 2wk+ build, **6–12+ mo** incubation | touches the **live trading path** — highest risk; flag-gated, operator-signed-off only, after §7 power bar clears | all above + operator |

**Roll-up.** Full build ≈ **8–12 single-builder weeks** *plus* a 6–12+ month
low-freq incubation (#9) — for a payoff that is, on today's evidence, **unproven**
(60d dead, 20d marginal, 5d weak/possibly PDT-infeasible).

**What the estimate itself tells us:** the cost curve is steeply back-loaded —
items **#1 and #2 are ≈S/M and cheap (≤1 week combined) yet gate the entire ≈10-week
L/XL build.** So the correct sequencing is *cost-to-information*: spend the cheap
week on #1+#2 first. If 20d fails its robustness gate (the likely outcome) and/or 5d
is PDT-infeasible, **the expensive 90% is correctly never built.** This design's
main value right now is making that a cheap, evidence-gated decision rather than a
multi-week leap.
