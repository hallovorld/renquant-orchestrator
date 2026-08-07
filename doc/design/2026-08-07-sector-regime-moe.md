# Sector × Regime MoE — a feasible design, and the three things that must be measured first

STATUS: DESIGN DRAFT. Nothing here is deployed, and Stage 0 is a blocking
measurement gate, not a formality — if Stage 0 comes back flat, the honest
outcome is that this goal closes NEGATIVE and the fleet keeps the current
scorer.

---

## 1. Bottom line

**A flat 13-sector × 4-regime mixture is not estimable on this book's data.** The
arithmetic below shows 29% of the 52 cells carry under 500 ticker-days, and two
sectors (`telecom` n=1, `commodity` n=2) cannot produce a cross-sectional IC at
all — a per-date Spearman over one name is undefined, not merely noisy.

**A hierarchical mixture with a regime gate and shrunk sector-group experts is
estimable**, and there is a specific, measured reason to expect it to help: the
current scorer's skill is not uniform across regimes, and the regime where it is
strongest is the one the strategy is hard-configured never to trade.

The design below is that hierarchy. It is staged so that each stage can kill the
next one.

---

## 2. What is actually measured — and one correction

### 2.1 Per-regime skill is real and very uneven

From the gate's own stamped `model_placebo_profile.per_regime`
`[VERIFIED — read directly from
panel-ltr.alpha158_fund.weekly_20260706T230931Z.staging.json, 2026-08-07]`:

| regime | n_dates (2x) | aligned_real_ic 1x/2x/3x | placebo_ic 1x/2x/3x | genuine_ic 1x/2x/3x |
|---|---|---|---|---|
| **BEAR** | 50 | 0.353 / 0.351 / 0.361 | +0.108 / +0.016 / **−0.122** | +0.245 / +0.335 / +0.483 |
| BULL_CALM | 363 | 0.014 / 0.030 / 0.039 | 0.041 / 0.059 / 0.108 | −0.027 / −0.029 / −0.068 |
| BULL_VOLATILE | 11 | −0.003 / 0.074 / 0.074 | +0.029 / +0.154 / **−0.195** | −0.032 / −0.080 / **+0.269** |
| CHOPPY | 28 | 0.014 / 0.020 / 0.010 | 0.015 / 0.061 / 0.004 | −0.001 / −0.041 / +0.006 |

**CORRECTION to how this has been reported, including by me.** orch#805 and my
own two summaries quoted the `2x` column as *the* number — "BEAR genuine_ic =
+0.335". `per_regime` is keyed by shift multiple first, and the three columns do
not agree:

* BEAR's **real** IC is remarkably stable across shifts (0.353 / 0.351 / 0.361).
  All of the swing in `genuine_ic` comes from the **placebo**, which moves from
  +0.108 to −0.122.
* A **negative placebo IC is a warning, not a bonus.** The placebo estimates the
  leakage floor; `genuine = real − placebo` with a negative placebo *adds* to the
  result. On ~50 dates, a placebo of −0.122 is far more likely to be sampling
  noise than a real negative leakage.
* BULL_VOLATILE is the reductio: n=11 dates, and a −0.195 placebo at 3x flips
  `genuine_ic` from −0.080 to +0.269. **No conclusion may rest on BULL_VOLATILE
  at this sample size.**

**How BEAR should be stated from now on:** real IC ≈ **0.35, stable**; genuine IC
**+0.245 to +0.483**, with the width owed entirely to leakage-correction
instability on ~50 dates. The qualitative claim survives at the most conservative
end — even +0.245 dwarfs BULL_CALM's negative — but any *point* estimate quoted
from one shift column is over-precise.

### 2.2 The strategy cannot act on its best regime

`[VERIFIED — pinned configs/strategy_config.json, 2026-08-07]`

```
BEAR.entry_mode       = 'blocked'
BEAR.max_position_pct = 0
BEAR.cash_reserve_pct = 1
```

Buys by regime: BULL_CALM 136 · CHOPPY 9 · BULL_VOLATILE 9 · **BEAR 0**.

The zero is not emergent from admission gates or from the signal. It is written
down. **The model's strongest measured regime is the one regime the risk policy
forbids entering.** Any MoE that routes to a BEAR expert inherits this conflict
unresolved; §6 treats it as a first-class decision rather than an implementation
detail.

### 2.3 Per-sector skill has NEVER been measured

`wf_gate_metadata` contains **zero** keys matching `sector`
`[VERIFIED — programmatic key hunt over the full metadata tree, 2026-08-07]`.
The sector map exists (144 tickers → 13 sectors) and is part of the config
fingerprint, but nothing in the evaluation path has ever conditioned on it.

**This is the single largest hole in the premise.** The proposal is to specialize
by sector; there is currently no evidence that skill *varies* by sector. Stage 0
exists to produce that evidence before anything is built.

---

## 3. The binding constraint: cell arithmetic

IC here is a **per-date cross-sectional rank correlation**. Two quantities
therefore matter independently: how many **dates** a cell has, and how many
**names per date** it has. A cell can have plenty of ticker-days and still be
useless if the names-per-date is small.

Regime dates: BULL_CALM 489 · BULL_VOLATILE 147 · BEAR 73 · CHOPPY 42.

Ticker-days per (sector, regime) cell `[DERIVED — sector counts × regime days]`:

| sector | n_tickers | BULL_CALM | BULL_VOL | BEAR | CHOPPY |
|---|---|---|---|---|---|
| industrial | 21 | 10,269 | 3,087 | 1,533 | 882 |
| software | 19 | 9,291 | 2,793 | 1,387 | 798 |
| finance | 18 | 8,802 | 2,646 | 1,314 | 756 |
| ai_chip | 17 | 8,313 | 2,499 | 1,241 | 714 |
| consumer | 16 | 7,824 | 2,352 | 1,168 | 672 |
| datacenter_hw | 14 | 6,846 | 2,058 | 1,022 | 588 |
| healthcare | 10 | 4,890 | 1,470 | 730 | 420 |
| giant_tech | 9 | 4,401 | 1,323 | 657 | 378 |
| energy | 8 | 3,912 | 1,176 | 584 | 336 |
| utility | 6 | 2,934 | 882 | 438 | 252 |
| real_estate | 3 | 1,467 | 441 | 219 | 126 |
| commodity | 2 | 978 | 294 | 146 | 84 |
| telecom | 1 | 489 | 147 | 73 | 42 |

**15 of 52 cells (29%) hold fewer than 500 ticker-days.** More decisive:
`telecom` has **one** ticker, so its per-date cross-section is a single name and
its IC is undefined on every date; `commodity` has two, where a Spearman takes
only the values ±1.

Even the healthiest BEAR cell — industrial — is 73 dates × 21 names. A per-date
IC over 21 names has a standard error of roughly `1/√20 ≈ 0.22`; averaged over 73
dates that is ≈ 0.026 **if the dates were independent**, which they are not
(regimes come in runs, so the effective date count is materially smaller than
73). The effect size we would be hunting per cell is of the same order as its own
standard error.

**Conclusion: 52 independent experts is not a design, it is 52 unfalsifiable
claims.** Everything below follows from taking this seriously.

---

## 4. Design

### 4.1 Shape: hierarchical mixture, not a flat grid

```
                        ┌─────────────────────────┐
   features ──────────► │  REGIME GATE  (soft)    │  4 states, 42–489 dates each
                        │  p(r | market state)    │  the ONLY well-populated axis
                        └───────────┬─────────────┘
                                    │ π_r
            ┌───────────────────────┼───────────────────────┐
            ▼                       ▼                       ▼
     ┌────────────┐          ┌────────────┐          ┌────────────┐
     │ EXPERT_r=1 │   ...    │ EXPERT_r=k │   ...    │  BASE      │  pooled scorer,
     │  (regime)  │          │            │          │  (shrink   │  today's model
     └─────┬──────┘          └─────┬──────┘          │   target)  │
           │                       │                 └─────┬──────┘
           │  per-expert sector ADJUSTMENT, shrunk toward 0 │
           └───────────────┬───────────────────────────────┘
                           ▼
                    score(i) = base(i) + Σ_r π_r · [ δ_r + δ_{r,g(i)} ]
```

Three deliberate departures from a textbook MoE:

**(a) Experts are additive adjustments on a shared base, not independent
models.** Each expert learns a *correction* to the pooled scorer. This is
James–Stein shrinkage by construction: a cell with no signal contributes a δ
indistinguishable from zero and the score falls back to today's behaviour. A
flat MoE with independent experts has no such floor — a thin expert produces
confident garbage.

**(b) The sector axis enters as `g(i)`, a sector GROUP, not the raw 13.** Groups
are formed by a preregistered rule applied to Stage-0 output — not by name, and
not by my intuition about which sectors "belong together". Candidate rule:
agglomerative clustering on the correlation matrix of sector-level daily residual
returns, cut so every group holds ≥ 8 names. On today's map that collapses 13 → 5
or 6 groups and dissolves `telecom`/`commodity`/`real_estate` into neighbours.
**The number of groups is an output of Stage 0, not an input.**

**(c) The gate is soft and regime-uncertainty-aware.** The regime label is an HMM
*estimate*. Hard-assigning a date to BEAR and training a BEAR expert on it treats
an estimate as ground truth — precisely the post-hoc slicing error the ledger
already warns about. Use `π_r = p(regime = r | data up to t)`, and require the
gate's own posterior entropy be carried into the score so a genuinely ambiguous
day does not get a confident regime-specific adjustment.

### 4.2 Why not the obvious alternatives

| alternative | why not |
|---|---|
| 13×4 independent experts | §3: 29% of cells under 500 ticker-days; 8 cells have <3 names/date |
| Sector as a one-hot FEATURE in the existing model | Already effectively available via the 172-feature set; it lets the model shift a *level* per sector but cannot change the *ranking function* per sector, which is the actual hypothesis |
| Regime-only MoE (4 experts, no sector) | Strictly simpler and should be the **control arm**. If regime-only captures the gain, the sector axis is unpaid complexity — see Stage 2 |
| Train only on BEAR | 73 dates. Also solves nothing: §2.2, the strategy cannot enter in BEAR |

The regime-only MoE as a control arm is load-bearing. **If Stage 2 cannot beat
it, the sector axis dies there.**

---

## 5. Staged plan, with the kill condition stated before each stage

### Stage 0 — measure the premise (BLOCKING, no modelling)

Produce, from the existing WF replay path and the persisted served matrix, a
per-(sector, regime) table of: `n_dates`, `mean_names_per_date`,
`aligned_real_ic`, `placebo_ic` at **all three shift multiples**, and
`genuine_ic` reported as a **range across shifts**, never a point.

Report `n_names_per_date < 5` cells as UNESTIMABLE rather than scoring them —
the `telecom` lesson generalizes, and a cell reported as 0.00 reads as "no skill"
when it means "no measurement".

**KILL CONDITION:** if, after grouping to ≥8 names, the between-group spread in
`genuine_ic` within any regime does not exceed the within-group shift-multiple
spread, **there is no sector effect to model** and this goal closes NEGATIVE.
That comparison is the whole point: the BEAR row in §2.1 shows the
shift-multiple spread alone can be ±0.12, so a "sector effect" of 0.05 is not an
effect.

### Stage 1 — the control arm

Build the **regime-only** additive MoE (4 soft experts, no sector axis).
Preregister: per-arm placebo, all three shift multiples, block bootstrap with a
gap ≥ the label horizon (`L = h` gives crossing 1.00 — the gap is the point).

**KILL CONDITION:** regime-only fails to beat the pooled base on
placebo-corrected OOS IC, with the comparison made on *differences* rather than
absolute IC (the WF-gate embargo leakage floor is ≈ +0.04; absolute IC below that
is uninterpretable).

### Stage 2 — add the sector axis

Add `δ_{r,g}` on top of the Stage-1 winner. Same preregistration.

**KILL CONDITION:** Stage 2 does not beat Stage 1 by more than the Stage-1
bootstrap CI width. Complexity that does not clear its own control is removed,
not "kept for later".

### Stage 3 — economics, not IC

IC is not money. Route the Stage-2 winner through the existing WF replay to get
Sharpe / APY / turnover **net of cost**, and confront §6. A model that improves
IC while the policy blocks its best regime has improved nothing tradeable.

### Stage 4 — shadow lane, then a gated promotion

Deploy as a shadow lane with a genuinely independent config (the current fleet
has `shadow_blend_mom` at ρ=1.0000 with PROD — a zero-information control, and
that mistake must not be repeated here). Promotion requires the Stage-3
economics plus a live shadow window agreed in advance.

---

## 6. The policy conflict must be decided, not designed around

`BEAR.entry_mode = 'blocked'` was a risk decision, and it is not obviously wrong
— a 73-date regime with elevated drawdown risk is a reasonable place to hold
cash. But it means:

**the expert with the strongest measured signal is the one whose output can never
become a trade.**

Three coherent resolutions, in increasing order of risk. This is an operator
decision, not a modelling one:

1. **Keep BEAR blocked.** Then the MoE's realistic upside is confined to
   BULL_CALM (363 dates, `genuine_ic` ≈ **−0.03**), and the honest framing of
   this goal changes from "exploit the BEAR edge" to "stop losing money in
   BULL_CALM". That is still worth doing — 88% of buys land there — but it is a
   different project with a different success metric.
2. **Allow a capped BEAR entry**, e.g. `max_position_pct` small and non-zero with
   `cash_reserve_pct` reduced, gated on the Stage-3 economics and preregistered
   before Stage 0 output is seen.
3. **Route BEAR skill into the EXIT side instead of entries.** BEAR already has
   12 sells and no buys; a signal that ranks well in BEAR can improve *which
   positions are exited* without any change to entry policy. **This is the
   cheapest path to using the strongest measured signal, and it does not touch
   the entry risk posture at all.** I would start here.

---

## 7. What would falsify this whole design

Stated now so it cannot be rationalized later:

* Stage 0 shows between-group IC spread inside the shift-multiple noise band → no
  sector effect, goal closes NEGATIVE.
* Stage 1 regime-only wins and Stage 2 adds nothing → the sector axis is dropped;
  the deliverable becomes a 4-expert regime MoE.
* BEAR's `genuine_ic` collapses toward its 1x value under a proper block
  bootstrap with a gap → the headline motivation weakens and Stage 3 economics
  becomes the only justification.
* The served feature matrix turns out not to support per-sector attribution
  retrospectively → Stage 0 cannot run as designed and must be rebuilt forward,
  which is a schedule fact worth knowing on day one rather than week three.

---

## 8. Concurrency and architecture notes

* Stage 0 is **read-only** and can run in parallel with everything else. It
  touches no production surface.
* Stages 1–2 belong in `renquant-model` (training internals) with the evaluation
  harness in `renquant-backtesting`. **Not here** — the orchestrator owns
  orchestration and must not grow model internals (Hard Boundaries, CLAUDE.md).
* The sector-group rule and the gate live with the scorer, i.e.
  `renquant-model`; `renquant-strategy-104` only ever sees a config that names
  the artifact.
* Experiments run on `epic/model-edge-experiments`; only gate-passing work
  graduates.
* Stage 4's shadow lane needs a genuinely distinct config — see the
  `shadow_blend_mom` ρ=1.0000 precedent.
