# MoE revision 3 — champion/challenger per sector, with every threshold frozen

Supersedes revision 2 in this same file. Revision 1
(`2026-08-07-sector-regime-moe.md`, orch#904) stands only where this document
does not override it.

Two changes since revision 2, one from the operator and one from codex review:

* **The architecture was wrong.** Revision 2 made experts additive corrections
  `δ` on one shared base. A correction cannot express "chips use fast momentum,
  mega-cap tech uses mean reversion" — those are different functional forms, not
  offsets. §2 replaces it.
* **The kill gate was not falsifiable.** Codex, correctly: the MDE comparison
  target and the `ΔIC→bps` transfer were both deferred, so the analyst could
  choose the threshold after seeing the result. §4 freezes every number, and §5
  fully specifies the positive control.

---

## 1. Bottom line

**Default is the panel. A challenger takes a sector only by clearing a frozen
gate. A sector with no winning challenger keeps the panel, and that is a
successful outcome, not a failed one.**

The worst case of this design is today's system. That property is the reason to
prefer it — but it holds **only if the gate is honest**. An in-sample gate will
swap noise into production and the worst case becomes worse than today. §4 and
§6 are therefore the load-bearing sections; the architecture in §2 is the easy
part.

---

## 2. Architecture: champion / challenger, per sector

```
for each sector s:
      ┌── CHAMPION ────────────────────────────────┐
      │  panel-ltr.alpha158_fund   (today's model) │ ◄── default, always eligible
      └────────────────────────────────────────────┘
                          ▲
                          │  replaced ONLY if a challenger clears the §4 gate
                          │  on embargoed validation folds
      ┌── CHALLENGERS (already trained, already running) ──┐
      │  momentum_fast     fast momentum                   │
      │  momentum          slow momentum                   │
      │  rb / rb_mom       mean reversion                  │
      │  panel-clf         top-decile classifier           │
      │  (optional) a model trained on sector s alone      │
      └────────────────────────────────────────────────────┘
```

Scores are combined on **rank**, not raw score: the lanes are on different
scales (the panel is z-scale, the calibrated output is a probability), and a
rank blend is invariant to that. This is not a modelling choice, it is the
existing measured fact that mixing the two scales is what saturated the drift
alarm.

**Why this beats revision 2's shrinkage form.** Both fall back to the panel when
a cell has no signal. Only this one can *switch hypothesis class*, which is the
thing being tested. Revision 2's `δ` could never have expressed the operator's
actual hypothesis.

**Why it does not need training.** Every challenger listed above already exists
as a trained artifact and already scores the live universe:

| lane | artifact | live scored dates |
|---|---|---|
| panel (champion) | `artifacts/prod/panel-ltr.alpha158_fund.json` | **541** |
| clf top-decile | `artifacts/shadow/panel-clf.top-decile.fwd60.json` | 38 |
| blend | `runs.alpaca_shadow_blend.db` | 9 |
| momentum (slow) | `runs.alpaca_shadow_blend_mom.db` | **4** |
| mean reversion | `runs.alpaca_shadow_blend_rb_mom.db` | **4** |
| momentum_fast | `runs.alpaca_shadow_blend_mom_fast.db` | **0** |
| rb_fast | `runs.alpaca_shadow_blend_rb_fast.db` | **0** |

`[VERIFIED — per-DB query over RenQuant/data/runs.alpaca*.db, 2026-08-08]`

**So the sector × expert matrix cannot be built from live shadow data.** Two
lanes have zero observations and two have four; those lanes activated
2026-08-02/04. This is not a power problem, it is an absence of data.

**The unblock is offline replay, not waiting.** Each challenger is a model and
can score the historical feature matrix over the full 541-date history. That is
Stage 1's first task and it does **not** depend on orch#905.

---

## 3. What is actually being estimated

Per sector `s` and challenger `c`, the quantity is a **paired** per-date
difference against the champion, on the same names and the same dates:

```
Δ_{s,c,t}  =  IC_s( challenger c , t )  −  IC_s( panel , t )
```

Pairing is not a convenience. The common market factor is the dominant term in
`IC_t` and it is *identical* in both arms, so differencing removes it. §4 shows
the entire viability of this line rests on how much it removes.

---

## 4. Stage −1 — the kill gate, every number frozen before it runs

### 4.1 Frozen inputs (fixed here; changing any of them voids the prereg)

| input | frozen value | source |
|---|---|---|
| label horizon `H` | 20 trading days | `fwd_20d`, the traded label |
| `n_eff` rule | `n_dates / H` | independence arrives at the label horizon |
| `sd(IC_t)` | **0.1233** | measured, live 33-date series |
| panel mean IC | **+0.0223** | measured, same series |
| history for the gate | **541 dates**, 2024-01-02 .. 2026-08-07 | `runs.alpaca.db` |
| `n_eff` at that history | **27.05** | 541 / 20 |
| power / α | 80% / 0.05 two-sided | `MDE = 2.8 · sd / √n_eff` |

`[VERIFIED — candidate_scores(role='candidate') ⋈ ticker_forward_returns.fwd_20d,
33 usable dates 2026-05-04..07-10, median 71 names/date]`

### 4.2 The frozen plausible-effect ceiling

**`ΔIC_ceiling = 0.05`.**

Justification, fixed in advance: the panel's *entire* measured mean IC is
`+0.0223`. A ceiling of 0.05 asserts that a sector-routing rule could plausibly
add **2.2× the whole existing edge of the model**. That is already generous. Any
experiment whose MDE exceeds it cannot distinguish a real effect from noise
inside the range of effects worth having.

### 4.3 The frozen ΔIC → bps transfer

Committed before Stage −1, computed from this book's own realised selection, not
from a textbook formula:

```
regress   r_topN,t   on   IC_t     over the frozen 541-date history
                                    (topN = the book's actual buy rule)
transfer  β̂  =  bps of realised top-N return per 1.0 of IC
break-even ΔIC  =  round_trip_cost_bps / β̂
```

`round_trip_cost_bps` is taken from the live execution cost model at the pinned
config, read once and recorded in the Stage −1 output. **If `β̂` is not
significantly positive, the transfer is undefined and the line stops there** —
an IC that does not move this book's realised return is not worth routing.

Precedent for why this must be stated first: the Phase −1 intraday line measured
a real IC of 0.03 and a **net edge of −6.4 bps**. A genuine signal that does not
clear costs is a loss, not a small win.

### 4.4 The gate, as one falsifiable inequality

Unpaired, at the frozen inputs:

| series | n_dates | n_eff | MDE | verdict |
|---|---|---|---|---|
| live scored | 33 | 1.65 | 0.269 | **KILL** |
| full DB history | 541 | 27.05 | 0.066 | **KILL** |
| *needed for MDE < 0.05* | *953* | *47.7* | *0.050* | threshold |

**So the unpaired comparison is already dead at the frozen ceiling**, and no
universe expansion changes it — only dates do.

The line survives only through pairing (§3), and that reduces the entire gate to
**one measurable quantity**:

> **GATE.** `MDE(Δ) = 2.8 · sd(Δ_{s,c,t}) / √27.05 < 0.05`
> ⟺ **`sd(Δ_{s,c,t}) < 0.0929`**
> measured on the frozen 541-date history, per (sector, challenger) pair.

| `sd(Δ)` | MDE | verdict |
|---|---|---|
| 0.1233 (= no cancellation at all) | 0.0664 | KILL |
| 0.0900 | 0.0485 | PASS |
| 0.0600 | 0.0323 | PASS |

**KILL CONDITION.** A (sector, challenger) pair whose `sd(Δ)` on the frozen
history is ≥ 0.0929 is dropped before any modelling. If **no** pair clears it,
the line stops and the answer is "keep the panel everywhere" — which §1 already
declared a valid outcome.

Stage −1 needs no served matrix and no new artifact. It is one query plus one
replay over data that exists.

---

## 5. Stage 0′ — positive control, fully specified

A placebo proves the pipeline does not hallucinate signal. It does **not** prove
the pipeline can find signal that is there. Revision 1 had only the placebo.

**Frozen specification** (codex P1 #2; each item fixed here, not at run time):

| item | frozen choice |
|---|---|
| membership source | published ETF holdings, **as-of the fold's training end**, never a later vintage |
| membership version | the holdings snapshot is recorded by publish date + digest in the Stage 0′ output |
| injection point | **inside the fold, on training dates only**, after the split and before any fitting |
| injection target | `fwd_20d` of the names in one membership dimension |
| δ grid | **{0, 0.01, 0.02, 0.05, 0.10}** in IC units, fixed |
| replicates | **200 seeds per δ** |
| evaluation | **embargoed validation folds only**; training-fold recovery is never reported as evidence |

**Three required outputs:**

1. **Recovery** — point estimate tracks injected δ with no attenuation beyond
   what shrinkage predicts.
2. **Calibration** — the 95% CI covers the true δ in ≥90% of the 200 seeds.
3. **Empirical power curve** — smallest δ recovered at 80% power.

**KILL CONDITION.** No recovery at `δ = 0.10` (twice the §4.2 ceiling), or CI
coverage below 90%.

**Precedence rule, fixed now:** if the empirical power curve disagrees with the
§4.4 analytic MDE, **the empirical curve wins** and §4.4's gate is re-evaluated
against it. The analytic MDE is a prior; the control is a measurement.

---

## 6. Routing-table discipline

15 sectors × 5 challengers = **75 cells**. Taking each sector's best challenger
is 75 implicit comparisons, and the winner of 75 noise draws looks exactly like
a discovery.

**Rules, all frozen:**

* The **entire routing table** is selected **inside each walk-forward fold, on
  training dates only**, then frozen before the fold's embargoed validation
  dates are touched.
* Fold-to-fold routing agreement is reported (adjusted Rand index). **A table
  that does not survive its own folds is evidence against a stable
  sector↔model correspondence**, and is reported as such rather than averaged
  away.
* A sector with insufficient data never gets a challenger and keeps the panel by
  construction — `telecom` (n=1), `commodity` (n=2), `real_estate` (n=3) need no
  hand rule.
* The **primary endpoint is one number**: the pooled paired increment of the
  routed book over the panel-everywhere book, on embargoed dates, CI from a
  block bootstrap with gap ≥ H. Per-cell numbers are description and carry no
  decision weight.

---

## 7. Combiner ladder, ordered by what the data can afford

| | combiner | free params | affordable at n_eff ≈ 27 |
|---|---|---|---|
| **C0** | panel alone | 0 | **control arm, prespecified** |
| C1 | equal-weight rank blend | 0 | yes |
| C2 | inverse-variance weights | 0 fitted | yes |
| C3 | sector routing table | 15 discrete choices | marginal — needs §6 |
| C4 | sector × regime routing | 60 | **no** (regime `n_eff` 2–3) |

C4 is out on arithmetic, not taste: a regime effect is a date-level quantity, so
it is identified only across dates, giving `n_eff` of 2.8 (BEAR), 2.0
(BULL_VOLATILE), 2.0 (CHOPPY). A sector effect varies *within* a date. **The
axis revision 1 called "the only well-populated one" is the weak one.**

---

## 8. Execution order

1. **Stage −1** — replay each challenger over the frozen 541-date history;
   compute `sd(Δ_{s,c,t})` per pair; apply §4.4. Also produce the §4.3 transfer.
   *Blocked by nothing.*
2. **Stage 0′** — the §5 control, on pairs that survived. *Blocked by nothing.*
3. **Stage 1** — C0 vs C1 vs C2 on embargoed folds.
4. **Stage 2** — C3 under §6, evaluated as a paired increment over the best of
   Stage 1.
5. **Stage 3** — economics via §4.3. Net bps ≤ 0 kills regardless of IC.
6. **Stage 4** — shadow lane, then a gated promotion.

Steps 1 and 2 run on existing data. orch#905 blocks only what follows.

---

## 9. Honest statement

At the frozen ceiling the **unpaired** comparison is already dead on every
history this book has, including the full 541 dates. The line lives or dies on
whether pairing pulls `sd(Δ)` below **0.0929**, which is a measurement, not an
argument — and it is the first thing Stage −1 produces.

If it does not clear, the answer is *keep the panel everywhere*. That is the
outcome §1 was built to make safe, and reporting it is the deliverable.
