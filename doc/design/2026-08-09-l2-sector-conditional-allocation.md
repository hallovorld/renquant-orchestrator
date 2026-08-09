# L2-S: sector-conditional expert allocation — the operator's MoE, at the granularity the data supports

STATUS: design proposal, frozen before any backtest output. Extends the
merged L2 engine (orch#923, backtested #926, costed #927). Direction set by
the operator 2026-08-09: the three-layer machine lost sector awareness; this
design restores it as a first-class citizen — as SOFT sector tilts with
shrinkage to the global allocation, which contains both of the operator's
original shapes ("this sector uses that model" = full local deviation;
"sector model no good → keep panel" = full shrinkage) as endpoints of one
continuous, data-governed dial.

## 1 · Why this granularity and not the routing table (the honest boundary)

The original vision — a regime×sector→model table where each cell's model
SCORES AND SELECTS names — was tested and its measurement collapsed
(orch#910–#913): a per-sector selection signal is a Spearman IC on an 8–26
name cross-section, 3–5× noisier than whole-book, and the one promising
diagnostic (+0.0204, 33 days) sign-reversed out of sample (−0.0108, n=278
governed). That kill stands FOR SELECTION-LEVEL routing.

This design measures a different estimand: **sector-level ALLOCATION among
arms**. Each (sector, arm) pair keeps a paper book — a top-k concentrated
portfolio of that arm's scores restricted to that sector — and the question
is which ARM's sector book earns, judged on a 541-trading-day daily return
series per book, not an IC on a daily 8–26 name width. Same data, ~20×
longer evidence axis per decision. The operator's "fast momentum for
chips?" becomes: does mom_resid_63's ai_chip book beat the panel's ai_chip
book net of costs over 541 days — answerable, falsifiable, and cheap.

## 2 · Universe geometry `[VERIFIED — pinned strategy_config sector_map, sha 43cbb9b2…, read this session]`

159 names, 15 sectors: software 26 · industrial 21 · finance 20 · ai_chip
19 · consumer 16 · datacenter_hw 14 · healthcare 12 · giant_tech 9 ·
energy 8 · utility 6 · real_estate 3 · commodity 2 · telecom 1 ·
defensive_bonds 1 · benchmark 1.

**Frozen eligibility rule**: a sector hosts a local book iff it has ≥14
mapped names — six sectors qualify (software, industrial, finance, ai_chip,
consumer, datacenter_hw), covering 116/159 = 73.0% of the universe
`[DERIVED — sums over the map above]`. Every other sector is permanently
global-allocated in this design (its λ is pinned at 1); widening
eligibility is a NEW dated design, not a knob.

## 3 · Mechanism (frozen)

Notation: arms i ∈ {panel, mom_resid_252, mom_resid_63} (the merged L2
registry); global weight path w^g(t) from the UNCHANGED merged engine
(η=0.21, clip 0.05, champion floor w_panel ≥ 0.5 — its projected-OMD
guarantee, #926 §2, is untouched).

For each eligible sector s:

```
ŵ^s(t+1) = HedgeStep(ŵ^s(t), r^s(t))          same recursion, same η=0.21,
                                                same clip C=0.05, on the
                                                SECTOR-book return vector r^s
w^s(t+1) = (1 − m_s) · ŵ^s(t+1) + m_s · w^g(t+1)
```

`m_s` is the shrinkage weight toward the global path, frozen by width tier
`[ASSUMED — frozen here; the tier boundaries mirror §2's eligibility logic]`:

| sector width N_s | m_s | reading |
|---|---|---|
| N_s ≥ 20 (software, industrial, finance) | 0.50 | half local |
| 14 ≤ N_s < 20 (ai_chip, consumer, datacenter_hw) | 0.67 | one-third local |
| N_s < 14 (all others) | 1.00 | pure global (structural) |

Champion containment is inherited, not re-derived: because w^g carries
w_panel ≥ 0.5 and w^s is a convex mixture, every sector's panel weight
satisfies `w^s_panel ≥ (1 − m_s)·ŵ^s_panel + m_s·0.5 ≥ m_s/2` — the frozen
floors are 0.25 (m=0.5) and 0.335 (m=0.67) per tier `[DERIVED — mixture
bound at ŵ^s_panel = 0]`. The worst case is bounded and stated, not
implicit.

Sector books: top-k equal-weight of the arm's freshest scores (staleness =
the single 7-calendar-day rule, data/l2_staleness.py) restricted to the
sector, filter-investable-FIRST (the #926 §6.1 lesson), k frozen at 3 for
N_s ≥ 20 and 2 for 14 ≤ N_s < 20 `[ASSUMED — frozen here; k scales with
width so the book never holds >21% of its sector]`.

## 4 · Evaluation (frozen before any number exists)

One backtest, executed once after this design merges, at the #926/#927
reproducibility standard (committed daily CSV per sector×arm book + hedge
paths, verifier that re-runs every recursion and the mixture arithmetic,
hash-pinned input manifest; the #927 cost model verbatim: 10 bps one-way,
name swap = 2/3 book).

Books compared, all net of costs:
1. **L2-S composite**: eligible sectors run w^s, ineligible capital follows
   w^g, sector capital shares proportional to name count (frozen);
2. **global-only** (the merged L2 = today's design) on the same calendar;
3. **pure-local** (m_s = 0 on eligible sectors) — prices the shrinkage;
4. per-sector×arm standalone books (descriptive table — the operator's
   routing intuition made legible: 6 sectors × 3 arms net Sharpe).

Decision rule `[ASSUMED — frozen here]`:
* **ADOPT-for-shadow** iff composite net Sharpe ≥ global-only net Sharpe
  − 0.05 AND composite net maxDD ≤ global-only maxDD + 5pp AND at least
  one eligible sector's local Hedge path ends with a non-champion arm
  weight ≥ 0.40 (i.e., the machinery found at least one sector where the
  operator's tilt thesis has allocation-level support);
* otherwise **RECORD-ONLY**: the per-sector×arm table publishes as the
  answer to "which sector likes which model", and the global L2 stands.
No parameter may move after the first output; a re-attempt is a new dated
design. Placebo `[ASSUMED — frozen here]`: sector labels randomly
permuted across names (200 seeds, preserving tier sizes) — the composite's
edge over global-only must exceed the permuted p95, else the "sector
structure" is width arithmetic, not sector information.

## 5 · Failure modes anticipated (so they cannot be surprises)

1. **Thin-book concentration**: a k=2 book on 14 names is 2 names — single
   -name events dominate. Mitigation is structural (k tiers, m_s floors),
   and the placebo detects width-driven artifacts.
2. **Sector-book churn cost**: sector books churn like mom_fast's (#927:
   0.58/day → 9.8pp drag); the cost pass is inside the primary metric, not
   an afterthought.
3. **Double-counting the champion**: the composite could drift from the
   book the champion floor was designed to protect; the §3 mixture bound is
   the containment, and the verifier asserts it row-by-row.
4. **Regime interaction is OUT OF SCOPE**: no regime-conditional sector
   weights in this design (the causality verdict on regime availability,
   orch#930/#931, stands). A regime axis is a NEW dated design after the
   producer stamps score-time regime.

## 6 · What this design does not claim

* Not that sector-level selection skill exists (#913's kill stands).
* Not that six local Hedges have a fresh regret theorem — the mixture step
  is a heuristic shrinkage; the global engine's projected-OMD bound is
  inherited only by the w^g component. Stated, not hidden.
* Not a live change: the deliverable is a backtest + (on ADOPT) a shadow
  lane proposal, each behind its own review and grant.

## 7 · Execution order

1. This design merges (codex review, operator veto window).
2. Backtest PR: derivation + committed artifacts + verifier, executed once
   under §4's frozen rule.
3. On ADOPT-for-shadow: shadow-job grant batch (the L2 batch pattern).
