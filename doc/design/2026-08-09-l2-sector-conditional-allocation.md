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
width so the book never holds >21% of its sector]`. Ranking into the
top-k is by `(−score, ticker)` — descending score, ties broken by
ascending ticker lexicographic order — applied AFTER the staleness and
investability filters, so an equal-score pair can never create a book
choice `[ASSUMED — frozen here; review r3]`.

**Shortfall rule (frozen)**: if a sector×arm book has fewer than k
investable fresh names on a day (after the staleness and investability
filters), it holds the top min(k, available) names equal-weight; if
available = 0 it holds cash and books a 0.0 return for that day, and the
sector's Hedge recursion consumes that 0.0 unchanged — no skipped update,
no re-normalization, no substitute names from outside the sector
`[ASSUMED — frozen here; cash-at-zero is the only fallback that adds no
new selection choice]`. The backtest artifacts commit a shortfall-day
count per sector×arm book, so the frequency of this state is published,
not assumed away.

## 4 · Evaluation (frozen before any number exists)

One backtest, executed once after this design merges, at the #926/#927
reproducibility standard (committed daily CSV per sector×arm book + hedge
paths, verifier that re-runs every recursion and the mixture arithmetic,
hash-pinned input manifest).

**Cost model (frozen; generalizes #927 — review r2, with one visible
correction to the review's literal formula)**: #927's "name swap = 2/3
book" shortcut is exact only for a one-name replacement in a full
equal-weight top-3 book; §3's top-2 books and cash-shortfall states break
it (a one-name swap in a top-2 book trades the whole book, and entering or
leaving the cash state re-weights every retained name uncharged). The
frozen general rule, applied to EVERY book in this design:

```
cost(t) = 10 bps × Σ_{j ∈ names} |h_{j,t} − h_{j,t−1}|
```

— the sum runs over NAME holdings only, no ½ factor, and the cash sleeve
is deliberately EXCLUDED from the sum: every cash change is the mirror of
name changes already counted, so including it would double-charge pure
cash transitions. Reduction check `[DERIVED]`: full top-3 one-swap gives
Σ|Δh| = ⅓ + ⅓ = ⅔ → cost = ⅔ × 10 bps, exactly #927's committed identity
`cost == names_changed/3 · 2 · 10bps` (its verifier asserts this
row-by-row). Full liquidation to cash gives 1.0 × 10 bps (one leg), and
re-weighting among retained names is charged on their |Δh|.

VISIBLE CORRECTION to the review's literal prescription: "10 bps ×
0.5·Σ|Δh| including cash" yields ⅓ × 10 bps for the top-3 one-swap — a
factor-2 SHORTFALL against the #927 convention it is required to reduce
to (and the cash-inclusive sum with ½ would in turn be correct only for
pure cash transitions). The structure of the review's rule (turnover-based,
cash states charged, no set-difference shortcut) is adopted; the constant
is fixed so the reduction actually holds.

Initial convention `[ASSUMED — frozen here]`: `h_{·,0}` is all-cash and
day 0 pays the full entry cost (Σ|h_0| = the invested fraction × 10 bps),
so no book starts with free inventory. The committed daily artifacts
expose per-sector×arm turnover and cost columns, and the verifier
re-derives cost from the committed holdings paths — cost is never a
scalar summary only.

Books compared, all net of costs:
1. **L2-S composite**: capital splits by name count (frozen): each
   eligible sector s holds N_s/159 of capital in its own w^s-weighted
   sector books; the nine ineligible sectors are POOLED into a single
   bucket of 43/159 = 27.0% that replicates the unchanged global-only
   book (whole-universe arm books weighted by w^g) — NOT per-sector
   sub-books under global weights. Pinned this way because (i) sub-14-name
   sectors have no frozen k, and a top-k book on a 1–3 name sector is a
   single-name bucket (§5.1 amplified); (ii) the pool makes the composite
   an exact convex mix, r_composite = 0.730·r_sector-machinery +
   0.270·r_global-only, so the composite-vs-global delta is attributable
   to the sector machinery alone `[DERIVED — capital shares from §2's
   name counts]`. The pooled bucket's whole-universe books may hold
   eligible-sector names; that overlap is accepted and stated — the pool
   is a baseline replica, not a complement book;
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
design.

**Placebo `[ASSUMED — frozen here; review r3 pinned every constant]`**:
sector labels permuted across names — if the composite's edge over
global-only survives under permuted maps too, the "sector structure" is
width arithmetic, not sector information. Zero runner discretion remains:

* **Permutations**: seeds are the integers 0..199. For seed σ, with the
  159 tickers enumerated once in ascending lexicographic order
  t_0 < … < t_158, draw π = `numpy.random.default_rng(σ).permutation(159)`
  and assign ticker t_i the TRUE sector label of ticker t_{π[i]}. The
  map is drawn ONCE per seed and held fixed across ALL dates of that
  seed's replay. A permutation preserves §2's sector-count vector by
  construction, so the same six labels stay eligible at the same widths,
  tiers (m_s), and k — only membership changes.
* **Delta metric**: delta(σ) = net Sharpe of the seed-σ permuted
  composite − net Sharpe of global-only, both on the identical 541-day
  calendar under this section's cost rule. Global-only is
  label-invariant, so it is computed once; the observed delta uses the
  true map in the same formula.
* **Gate**: sort the 200 deltas ascending; p95 = the 190th value
  (the ⌈0.95·200⌉ order statistic). The placebo passes iff
  observed delta > p95, strictly — observed = p95 fails. A placebo fail
  demotes ADOPT-for-shadow to RECORD-ONLY.
* **Artifacts**: every seed's full ticker→label map and its delta(σ) are
  committed with the run, and the verifier re-derives each map from its
  seed and recomputes the gate from the committed dailies.

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
