# Sector × Regime MoE — revision 2

## Two changes, both of which can kill the line before any modelling

1. **A power gate that fires before Stage 0.** The design's motivating
   measurement sits at its own detection threshold. That was never computed.
2. **Sector membership is soft and externally defined**, not a hand-written
   partition into thematic buckets that overlap by construction.

Revision 1 (`2026-08-07-sector-regime-moe.md`, orch#904) stands except where
this document overrides it. What it got right — additive shrunk corrections on a
shared base, nested/temporal group formation, a soft regime gate, kill conditions
written before each stage — is retained verbatim and is not restated here.

---

## 1. The calculation revision 1 never did

The label is `fwd_20d`. Two consecutive dates share 19 of the 20 days in their
forward window, so **per-date IC is not an independent observation**. The number
of effectively independent observations for any *time-averaged* claim is

```
n_eff  ≈  n_dates / H        H = 20 (the label horizon)
```

`[DERIVED — n_dates ÷ 20. Consistent with the measured autocorrelation: the
per-date IC series shows no significant dependence at lag 20/25/30/40
(p = 0.452/0.344/0.315/0.065; block bootstrap L=60, n=465), i.e. independence
arrives at roughly the label horizon and not before.]`

| regime | n_dates | **n_eff** |
|---|---|---|
| BULL_CALM | 454 | **22.7** |
| BEAR | 55 | **2.8** |
| BULL_VOLATILE | 41 | **2.0** |
| CHOPPY | 41 | **2.0** |
| (all dates) | 465 | **23.2** |

Minimum detectable effect for a mean-IC claim, 80% power, α=0.05 two-sided,
`MDE ≈ 2.8 · sd(IC_t) / √n_eff`:

| sd(IC_t) | BEAR MDE | BULL_CALM MDE |
|---|---|---|
| 0.10 | 0.169 | 0.059 |
| 0.15 | **0.253** | 0.088 |
| 0.20 | 0.338 | 0.118 |

**The reported BEAR genuine IC is +0.245 at 1x.** At a plausible
`sd(IC_t) = 0.15` the MDE is **0.253**. The motivating number is *at* the noise
floor, not above it.

This also explains, quantitatively, the thing revision 1 noticed and could only
gesture at: the BEAR placebo swinging +0.108 → +0.016 → −0.122 across shift
multiples is not the leakage floor moving. **It is sampling noise on fewer than
three effective observations.**

### 1.1 The consequence that reorders the whole design

Revision 1 calls regime "the ONLY well-populated axis (42–489 dates each)". That
is true of *dates* and false of *information*.

* **A regime effect is a date-level quantity.** Every name on a date shares the
  regime, so it is identified only from variation *across* dates → `n_eff` 2–3
  inside any regime except BULL_CALM.
* **A sector effect varies within a date.** Different names on the same day sit
  in different groups, so the cross-section carries real information about
  between-group differences at every date.

So the axis revision 1 treats as safe is the weak one, and the axis it treats as
the risky addition is the better-identified one. **The regime × sector
interaction is the worst of both** — it inherits the 2–3 effective observations
of the regime axis.

**This does not make the sector axis free.** A claim about the *time-averaged*
sector effect is still bounded by `n_eff ≈ 23` overall. The cross-section
sharpens each date's estimate; it does not manufacture independent dates.

---

## 2. Stage −1 (NEW, blocking, cheap): the power gate

Runs before Stage 0. Needs no new data source, so it is **not blocked by
orch#905**, unlike everything downstream.

1. Measure `sd(IC_t)` per regime on the existing per-date IC series.
2. Estimate `n_eff` **empirically** rather than by the `n/H` rule of thumb:
   block bootstrap the per-date IC series with gap ≥ H, and take
   `n_eff = (sd(IC_t) / se_boot(mean IC))²`. The rule of thumb is the prior; the
   bootstrap is the measurement. **Report both and use the smaller.**
3. Convert MDE from IC units to basis points via the transfer function in §4.
4. Compare the MDE in bps to round-trip cost.

**KILL CONDITION.** If the MDE in bps exceeds the realistic effect size — and
the honest prior for a sector-group correction on a scorer that already sees
sector features is *small* — the experiment cannot answer its own question and
the line stops here. This is the G1 EW precedent: that prereg was blocked
because power at the MDE was ≈ α, and shipping it anyway would have produced an
uninterpretable null.

**A null result without this gate is uninterpretable**: "no effect" and "no
power to see an effect" are the same output.

---

## 3. Stage 0′ (NEW, blocking): positive control

Revision 1 has a placebo (it estimates the leakage floor) but **no positive
control**. A placebo proves the pipeline does not hallucinate signal. It does
not prove the pipeline can *find* signal that is there.

**Procedure.** Inject a synthetic sector-group effect of known magnitude δ into
the forward returns of one group in one regime, run the entire unmodified
pipeline end to end, and record the recovered estimate and its CI. Repeat over a
grid of δ and over seeds.

**Three things it must produce:**

* **Recovery** — the point estimate tracks the injected δ with no systematic
  attenuation the design does not already expect from shrinkage.
* **Calibration** — the 95% CI covers the true δ in ≈95% of seeds. An
  under-covering CI means the effective-n estimate in §2 is wrong, and the whole
  power gate is wrong with it.
* **An empirical power curve** — the smallest δ recovered at 80% power. If this
  disagrees with the analytic MDE from §2, **the analytic MDE is the one that is
  wrong** and §2's kill condition is re-evaluated against the empirical curve.

**KILL CONDITION.** The pipeline fails to recover an injected effect at twice
the analytic MDE, or CI coverage is below 90%.

---

## 4. State the economic transfer BEFORE measuring anything

`ΔIC → Δbps` must be written down first, so the MDE can be expressed in the
units the decision is actually made in. Otherwise the experiment optimises a
quantity nobody trades.

The precedent is on file: the Phase −1 intraday line measured a real IC of 0.03
and a **net edge of −6.4 bps** — a genuine signal that did not clear costs. An
IC improvement that maps below round-trip cost is not a small win, it is a loss.

**Deliverable of this section, produced before Stage 1:** the mapping from ΔIC
to Δbps at this book's turnover, position count, and cost model, plus the
break-even ΔIC. If the §2 MDE is above break-even but the *plausible* effect is
below it, the line stops for the same reason as §2.

---

## 5. Sector membership: soft, external, and overlapping by design

### 5.1 The current labels are not a partition

Measured from the live `sector_map` `[VERIFIED — strategy_config.json,
159 names, 15 labels]`:

```
software 26 · industrial 21 · finance 20 · ai_chip 19 · consumer 16
datacenter_hw 14 · healthcare 12 · giant_tech 9 · energy 8 · utility 6
real_estate 3 · commodity 2 · benchmark 1 · defensive_bonds 1 · telecom 1
```

`software + ai_chip + datacenter_hw + giant_tech = 68 names` across four labels
that describe **one correlated block** under different themes. A single name is
routinely all of: a chip company, an AI-infrastructure company, and a mega-cap
technology company. Forcing one label per name **discards the fact that it
belongs to several** — and that fact is the information a sector model would
want.

Two further problems with hand themes:

* They drift with narrative. "AI infrastructure" did not exist as a category
  three years ago; a label whose meaning changes over the sample is a
  time-varying treatment masquerading as a fixed one.
* They are unauditable. There is no external referent to check an assignment
  against, so a disputed name has no resolution procedure.

### 5.2 Replace the partition with a membership vector

Let `w_i ∈ R^K` be name `i`'s membership across `K` reference baskets, taken
from **published ETF holdings weights** (mainstream, external, versioned,
auditable) with GICS as the fallback for names no basket holds.

The expert correction becomes a weighted sum instead of a lookup:

```
revision 1:   δ_{r, g(i)}            g(i) = one hard bucket
revision 2:   Σ_k  w_{i,k} · δ_{r,k}    w_i = membership weights, Σ_k w_{i,k} = 1
```

This is the **same softening already applied to the regime axis** — revision 1
uses `π_r = p(regime | data)` rather than a hard regime label, for exactly the
reason that a hard assignment treats an estimate as ground truth. Revision 2
makes both axes soft. A hard partition is the special case `w` one-hot.

**Consequences, all deliberate:**

* A name in three baskets contributes to three corrections, proportionally. No
  arbitration is needed because none is forced.
* Membership is **versioned and dated**: ETF holdings are published on a
  schedule, so `w_i` is a point-in-time quantity and can be lagged to avoid
  look-ahead. A hand map has no vintage at all.
* The three degenerate labels stop being a special case. `telecom` n=1 is only
  degenerate because it is a *bucket*; as a membership dimension it is simply a
  column with little mass, and shrinkage handles that with no hand rule.
* Basket selection is itself a design choice and must be preregistered — the
  baskets are fixed before any effect is estimated, exactly as the clustering
  rule is in revision 1.

### 5.3 What this does NOT change

The clustering in revision 1 §4.1(b) stays. Baskets define membership;
clustering still runs **inside each fold on training dates only and is frozen
before the embargoed validation dates**. The post-selection flaw codex caught on
orch#897 is not reintroduced: an externally-defined membership is not fitted to
the outcome, which makes it strictly safer than a partition the analyst chose.

---

## 6. Expanding the universe: what would actually help

Adding names is a real lever but "≥20 per sector" is the wrong target.

* **The binding constraint is ticker-DAYS, not ticker count.** A name added
  today contributes zero history and cannot retroactively create BEAR
  observations. The cell floor is 500 ticker-days.
* **Breadth helps every date immediately**, independent of sectors: more names
  per date is a less noisy cross-sectional Spearman. This is the one benefit
  that does not wait for the MoE.
* **`n_eff` does not improve at all.** Adding names does not add independent
  dates. **No amount of universe expansion fixes §1.** Only a longer history,
  or a shorter label horizon, moves `n_eff`.

Under §5.2 the "which bucket" question dissolves, so the remaining criterion for
adding a name is: does it extend *coverage* (history depth, or mass in a
membership dimension that currently has almost none), not does it fill a quota.

**This is a live-system change**, not a research action: the traded universe
changes, watchlist growth re-stamps the shadow config fingerprint, and the new
names need history backfilled. It carries its own gates.

---

## 7. Revised kill-condition ladder

| stage | question | kill if | blocked by |
|---|---|---|---|
| **−1 power** | can this experiment answer its question? | MDE(bps) above the plausible effect | nothing — runs today |
| **0′ control** | can the pipeline find an effect that is there? | no recovery at 2× MDE, or CI coverage < 90% | nothing |
| 0 eligibility | is there data to estimate on? | no membership dimension forms a viable cell | orch#905 |
| 1 regime-only | does the regime axis beat pooled? | fails on the paired held-out increment | orch#905 |
| 2 + membership | does the sector axis add anything? | CI for Δ covers zero | Stage 1 |
| 3 economics | does it survive costs? | net bps ≤ 0 | Stage 2 |
| 4 shadow | does it hold live? | shadow disagrees with backtest | Stage 3 |

Stages −1 and 0′ are new, blocking, and **runnable now** — they need no served
matrix. Everything downstream still waits on orch#905.

---

## 8. One primary endpoint, fixed before any run

Four regimes × K membership dimensions is a large implicit comparison surface.
Reporting per-cell effects invites reading the maximum as the result.

**The primary endpoint is a single pre-specified number**: the paired held-out
increment of Stage 2 over Stage 1, pooled across all cells, with its CI from a
block bootstrap with gap ≥ H. Per-cell numbers are reported as *description*
and carry no decision weight. Any decision on a per-cell number requires FWER
control declared in advance.

---

## 9. Honest statement of where this leaves the line

Under §1 the regime axis inside BEAR, BULL_VOLATILE and CHOPPY has 2–3 effective
observations. **No amount of modelling sophistication recovers information that
the label horizon has already destroyed.** The most likely outcome of Stage −1
is that the regime-conditional part of this design is not estimable on the
current history, and the honest response is to say so rather than to run four
stages and report a null.

What would change that, in order of cost:

1. **A shorter label horizon** for the *gating* question only — `n_eff` scales
   as `n/H`, so H=5 quadruples it. The cost is that the strategy trades a
   multi-day horizon, so this measures a different quantity and must be
   justified, not assumed equivalent.
2. **More history.** `n_eff ≈ 23` overall needs roughly an order of magnitude
   more dates before per-regime work is viable.
3. **Drop the regime conditioning** and test the membership axis pooled, where
   `n_eff ≈ 23` rather than 2–3. This is the version of the design most likely
   to survive its own power gate.

Recommendation: **run Stage −1 now**, and let its output choose among these
three rather than deciding in advance.
