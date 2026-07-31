# Qualifying my own #677: one regime satisfies the criterion, on 55 dates, and that is not evidence it generalises

**Bottom line `[本次实测 2026-07-31]`.** #677 concluded *"the regime criterion IS
satisfiable — `BEAR` clears it on 11 of 11 artifacts."* The demonstration comes from the
**thinnest slice in the panel**, and the conclusion drawn from it — that
mis-specification is excluded — does not follow. **What is established is descriptive;
why `BEAR` behaves this way is not established here.**

| regime | n_dates | n_rows | mean_ic | **hit_rate** | placebo_ic | passed |
|---|---:|---:|---:|---:|---:|---:|
| BULL_CALM | **444** | **127 092** | 0.0220 | **0.508** | 0.0605 | **0 / 11** |
| BEAR | 55 | 15 320 | **0.3346** | **0.982** | 0.0158 | **11 / 11** |
| BULL_VOLATILE | 41 | 8 716 | 0.1116 | 0.732 | 0.1468 | 1 / 11 |
| CHOPPY | 41 | 11 972 | 0.0129 | 0.707 | 0.0798 | 0 / 11 |

## What the numbers support

`BEAR`'s per-date IC is positive on **98.2%** of its dates, at **15×** the IC of the
regime carrying **8×** the rows, stable across all eleven artifacts (range 0.0050). The
one regime that satisfies the criterion does so on **55 dates — 12%** of `BULL_CALM`'s
rows.

That supports exactly one conclusion: **satisfiability has been demonstrated only on the
panel's smallest regime, and 55 dates are not evidence that the criterion is reachable
in the regimes that carry the panel.** The mis-specification hypothesis is therefore
**not excluded**; it is only excluded for a criterion that never passes anywhere, which
is not the situation.

## The explanation I offered is a HYPOTHESIS — and my own data argues against it

An earlier version of this document asserted:

> ~~*"A 98.2% hit rate is not what ranking skill looks like — it is what a cross-section
> moving as one looks like."*~~

**That is a causal claim and nothing here measures it.** Reviewed `[codex on #680]`: *"a
high hit rate and mean IC can also result from a genuinely predictive score."* Correct —
the profile is descriptive, and I read a mechanism into it.

Worse, the one statistic in this table that bears on the mechanism points the **other**
way. If `BEAR`'s ranking were driven by beta- or volatility-like exposure, that exposure
is **persistent over 60 days**, so the 60-day-shifted placebo label should also rank well
in `BEAR`. It ranks **worst there of any regime**: placebo IC **0.0158**, 4% of its real
IC, against 2.7× in `BULL_CALM`.

**That is suggestive, not decisive, and the confound is structural:** `BEAR` is 55
scattered dates, so a 60-day shift usually lands the label *outside* the bear window
altogether. A low placebo IC in a short regime is partly a statement about regime
duration. So this neither establishes the leakage story nor refutes it — which is the
point. **H1 (beta/volatility-like exposure) and H2 (genuine ranking skill concentrated
in drawdowns) are both live.**

### What would actually settle it

Per-name scores and forward returns on the 55 `BEAR` dates, which the walkforward
artifacts do not carry — they hold the booster and regime-level summaries
`[VERIFIED — inspected wf_gate_metadata across the 29 prod panel-ltr artifacts;
per-regime blocks only, no per-name panel]`. With that panel, two diagnostics
discriminate:

1. **cross-sectional dispersion** — regress per-date IC on that date's dispersion of
   forward returns. H1 predicts the relation; H2 does not require it;
2. **a control** — recompute IC after neutralising the score on beta and realised
   volatility. Under H1 the IC largely goes; under H2 it survives.

Both need re-scoring the panel (703 759 rows) with the artifact's own booster. That is a
**preregistered study**, not a paragraph in a qualification doc, and registering it
before looking is the whole point — an after-the-fact choice of estimand is the defect
that killed a verdict on model#2 this month.

## Provenance of the table, checked while correcting it — and it is weaker than it looked

The table above is a median over the **11 artifacts named in #677's CSV**
(`doc/research/evidence/2026-07-31-regime-sanity-decomposed/regime_placebo_vs_real.csv`).
Re-checking that source today:

| | |
|---|---|
| artifacts named in #677's CSV | **11**, all present on disk |
| still carrying a `wf_gate_metadata.sanity_regime_ic` block | **1** — the deployed `panel-ltr.alpha158_fund.json`, whose numbers match the CSV exactly (`BULL_CALM n_dates=399`) |
| carrying **no `wf_gate_metadata` key at all** | **10** — the `weekly_*.staging.json` set |
| prod artifacts carrying the block at all | **14 of 29** |
| artifacts anywhere under the artifact tree with `BULL_CALM n_dates` ≠ 399 | **none** |

`[VERIFIED — json inspection of the 11 named files and an rglob over 17 687 JSON files
under `backtesting/renquant_104/artifacts`, 2026-07-31]`

**So ten of the eleven rows cannot be re-derived by reading the artifacts they name.**
They were produced by *running* the sanity battery over those artifacts, and #677
recorded neither the command nor a digest of what it read. One of the ten has an mtime of
**2026-07-16** and has not been touched since, so this is not a case of the file changing
underneath the claim — the numbers were never stamped into it.

That makes the table `[VERIFIED — prior work, orch#677]` and **not independently
re-derivable today**. It is exactly the defect codex named on backtesting#89: *"the
manifest does not identify an immutable source snapshot."* Same programme, same week,
found from the other end — and it is why the corrected conclusion below rests on the
*shape* of the evidence (one small regime) rather than on any individual number.

## The corrected statement

**Original (#677):** *"the criterion is satisfiable; therefore neither 'the gate is
mis-specified' nor 'the models are bad' holds."*

**Corrected:** the criterion is satisfied **in exactly one regime, on 55 dates**. That is
**insufficient evidence of generalisability** to the regimes that carry the panel, so
#677's exclusion of the mis-specification hypothesis does not stand. **No claim is made
here about *why* `BEAR` passes.**

## What survives untouched

#677's other finding stands and is re-pinned here: **`BULL_CALM` fails the placebo leg,
not the skill floor.** Its `mean_ic` is positive (0.0220) and its placebo IC is **2.7×**
that — a 60-day-shifted label out-ranking the aligned one. That measurement is
independent of anything `BEAR` does, and independent of which hypothesis explains `BEAR`.

Also unchanged: the concrete bar. Passing `BULL_CALM` by skill alone still requires
`real_ic ≥ 2 × placebo_ic` ≈ **0.121** against today's **0.022**.

## Method note

I found this by asking a question about **my own published claim** — *"BEAR passes; is
BEAR normal?"* — rather than by any check firing. **That is the second self-correction in
two rounds** (the other retracted #676's 7/14). Both were found by re-interrogating a
number I had already shipped, which is the only mechanism that has actually caught these.

And then I did the same thing again inside the correction: having caught an overclaim, I
replaced it with a mechanism I had not measured either. The review caught that one. The
generalisable rule is narrower than "re-interrogate your numbers" — **a profile licenses
a scope statement, never a cause.**

Tests: 6 — including a control that this qualification does **not** overturn the placebo
finding, and one asserting the document offers no causal explanation as established.

---

# Two diagnostics on the regime profile — added after codex on #680

The causal explanation was already withdrawn above (struck through, with `H1`/`H2`
named as live hypotheses and the conclusion scoped to insufficient evidence of
generalisability from 55 dates). **This section adds nothing to that withdrawal** — it
records two things measurable from the committed profile that bear on it, one of which
cuts against the hypothesis I favoured.

## Two things I checked before leaving it there

### 1. The hit rate is not independent evidence — it is a restatement of mean/σ

`[本次实测 2026-07-31, from the committed regime_profile.csv]` If per-date ICs were
i.i.d. Normal, the hit rate implied by a regime's own mean and σ is `Φ(mean/σ)`:

| regime | n dates | mean IC | σ IC | mean/σ | implied hit | observed hit | diff |
|---|---:|---:|---:|---:|---:|---:|---:|
| BULL_CALM | 444 | 0.0220 | 0.1620 | 0.136 | 0.554 | 0.508 | −0.046 |
| **BEAR** | **55** | **0.3346** | **0.1331** | **2.514** | **0.994** | **0.982** | **−0.012** |
| BULL_VOLATILE | 41 | 0.1116 | 0.1473 | 0.758 | 0.776 | 0.732 | −0.044 |
| CHOPPY | 41 | 0.0129 | 0.1147 | 0.113 | 0.545 | 0.707 | **+0.162** |

`BEAR`'s 54-of-55 is **exactly what its own mean/σ = 2.51 implies** —
`P(≥54 of 55 | p = 0.994) = 0.957`, i.e. entirely unsurprising. So *"hit rate 0.982"*
adds **no information** beyond *"mean IC is 2.5 σ above zero"*, and my earlier framing of
it as a separate symptom of degeneracy was double-counting one number.

`CHOPPY` is the one regime that departs (**+0.162**), which points at skew or
non-normality in its per-date ICs. Recorded, not explained.

### 2. The placebo evidence points AWAY from my hypothesis

| regime | placebo IC |
|---|---:|
| **BEAR** | **0.0158** — the cleanest of the four |
| BULL_CALM | 0.0605 |
| CHOPPY | 0.0798 |
| BULL_VOLATILE | **0.1468** |

If leakage explained `BEAR`, its shuffled-label placebo would be the one most likely to
be elevated. It is instead **the lowest**, by a factor of four against
`BULL_VOLATILE`. That is not decisive — a placebo tests label leakage, not a beta or
volatility tilt, which would survive a label shuffle — but it is evidence in the
opposite direction from the story I told, and reporting the profile without it would
have been selective.

## What would actually settle it, and why it is not run here

The discriminating measurement is **per-date cross-sectional dispersion** of forward
returns by regime, plus the same IC computed after controlling for beta and realised
volatility. If the cross-section moves as one in `BEAR`, dispersion collapses and a
near-constant-sign score scores mechanically.

**The artifacts cannot supply it.** They carry the booster and regime-level summaries
only — no per-date rows. Producing them means re-scoring the panel (**703 759 rows**)
with each artifact's own booster, which is **the same blocked evaluation path** that
GOAL-6 is already stuck behind: the WF gate admits on recipe hash alone, and all four
artifacts share `cfdd6cb8e950da0f`.

So this is not a diagnostic I declined to run — it is the *same* blocker, reached from a
second direction. That is worth knowing: it raises the value of unblocking the
re-scoring path, because two open questions resolve on it rather than one.
