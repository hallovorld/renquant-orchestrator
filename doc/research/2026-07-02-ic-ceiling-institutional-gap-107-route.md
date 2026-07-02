# Research: the IC ceiling, the institutional gap, and the 105→106→107 route to ordinary-professional level

STATUS: research + route design for review (docs only). This is the durable record of the
2026-07-02 strategy discussion; the route section extends the H2 execution roadmap (PR #229) to
2028 and supersedes its §9 sign-off list per the operator's delegation grant (§1).
DATE: 2026-07-02
OPERATOR DIRECTIVES (2026-07-02, evening): (1) the four §9 sign-offs of PR #229 no longer require
operator signature — delegated to the author, CONDITIONAL on deep / professional / responsible
research ("我相信你的判断，但是注意！研究要深入专业负责！"); (2) answer whether **107 can reach
ordinary-professional-institution level** (普通专业机构 — the median professional, not the top
tier) and plan the development route; (3) record everything and file for discussion.

---

## 1. The delegated-decision protocol (what the research standard means operationally)

The delegation covers: parking-sleeve vehicle/beta, 105 canary envelope start, Track B structural
/ book-scaling decisions, thesis-review verdicts. It is exercised ONLY through this protocol:

1. **Evidence hierarchy, declared per claim:** measured-on-our-data > replicated-external >
   cited-literature > reasoned. Every decision memo tags its load-bearing claims with the tier.
2. **Pre-registration:** decision criteria are frozen and recorded BEFORE outcome evidence is
   read (the M10/L7 discipline applies to every delegated decision, not just thesis reviews).
3. **Adversarial review:** every decision lands as a PR reviewed by Codex; a standing
   disagreement between author and Codex escalates to the operator instead of being resolved by
   author fiat.
4. **Rollback stated, capital staged:** each capital-risk decision names its rollback trigger and
   path, and stages exposure (shadow → small → full) — never a single-step flip.
5. **Notification, not approval:** every exercised decision produces a recorded artifact
   (doc/research or doc/progress) and an operator notification. Silent decisions violate the
   grant.
6. **Unchanged hard limits:** branch protection, live-tree write bans, freeze-under-review, and
   the production-input rules are UNTOUCHED by this delegation.

---

## 2. Where the model-IC ceiling is

### 2.1 Theory: the ceiling is exogenous to the model

Portfolio value creation follows the fundamental law with the constraint correction
(Grinold–Kahn; Clarke–de Silva–Thorley 2002):

**IR = TC × IC × √BR** — transfer coefficient × information coefficient × √(independent bets/yr).

IC's ceiling is set by **information set × market efficiency × horizon**, not by architecture.
Internal proof: our own bake-offs (E27/E33) — Linear +0.032 > Qlib-faithful Transformer +0.026 >
iTransformer v2 +0.018 (train_ic 0.135 = pure overfit) on identical data. External anchors:

- **McLean–Pontiff (2016):** published anomalies decay ~26% out-of-sample, ~58% post-publication
  — any literature signal arrives pre-halved.
- **Hou–Xue–Zhang (2020):** most of 452 anomalies fail replication; survivors concentrate in
  micro/small caps — the large-cap cross-section is the most efficiently arbitraged in the world.
- **Gu–Kelly–Xiu (2020):** best-in-class NN on the full CRSP panel: monthly OOS R² ≈ 0.4%
  (equal-weight, microcap-driven); materially lower on the top-cap slice.
- Industry rule of thumb: sustained IC 0.02 = good, 0.05 = excellent, 0.10 = audit-for-leakage.

### 2.2 The ceiling table (our coordinate system)

| Information set / setting | Responsible placebo-clean IC ceiling | Basis |
|---|---|---|
| **Current**: 142 US large caps, price-derived features, fwd_60d | **0.02–0.04** | GKX large-cap decay + HXZ + our four NULLs |
| + orthogonal PIT (estimate revisions, full fundamentals, quality) | **0.03–0.05** | revision-drift literature ~0.02–0.03 standalone; orthogonal stacking |
| Down-cap (liquid small/mid, gross of cost) | **0.05–0.08 gross** | HXZ concentration; 25–40bps costs halve it |
| Intraday large-cap | higher per-forecast IC, cost-dominated at retail | our phase −1: net-negative (PR #199) |
| Reference: CSI300 alpha158+LightGBM | rank IC ~0.05–0.08 | Qlib benchmarks — a less efficient market, not ours |

### 2.3 Where we are: on the floor, not at the ceiling

Naive numbers (E35 +0.066; 5-cut +0.039±0.046) carry three inflations — 60d label overlap, **61%
cross-sectional persistence** (#256), the **~+0.04 embargo-leakage floor**. Leak-controlled: A1
genuine IC ≈ 0.04 with **CI [−0.031, +0.129] ∋ 0**; BULL_CALM (79% of live time) ≈ −0.003.
Cross-check: sim Sharpe 0.77 ≈ benchmark-period SPY; live flat ⇒ **active contribution ≈ 0,
consistent with genuine IC ≈ 0.** Conclusion: ~0.03–0.04 of headroom exists to OUR ceiling; the
ceiling itself moves only with the information set.

### 2.4 How to approach the ceiling (four paths, by ROI)

1. **Measurement first** (roadmap S1–S5): an unmeasurable IC cannot be optimized.
2. **Orthogonal stacking — the only theory-supported IC growth**: for k signals with pairwise
   score correlation ρ, IC_comb = k·IC/√(k + k(k−1)ρ). **Measured (POC-D,
   `poc_factor_orthogonality.py`): intra-price-family avg |ρ| = 0.217 on our panel ⇒ three
   0.02s stack to 0.029, not the ideal-orthogonal 0.035** — plan on **0.028–0.033**
   (cross-data-family ρ is typically lower). Candidate stack, by evidence: estimate revisions
   (PIT store, N2), quality/fundamentals (FMP, N3), regime-conditioned residual momentum
   (#176 — our one "relatively promising" lead).
3. **TC and BR are cheaper than IC**: our constraint stack (whole-share, top_n=3, σ
   double-shrinkage, panel-exit-overrides-QP) puts TC ≈ ~0.4; lane A + R4 → ~0.7 = **+75% IR at
   zero IC cost**. Breadth: nominal BR = 142 × 4.2 ≈ 600/yr, correlation-effective ~100–200;
   cluster-waves to ~400 quality names ≈ +60–70% IR (E34's transfer warning governs the method).
4. **Factor hygiene, honestly**: our neutralization NULL (label residualization destroys
   BULL_CALM) means today's returns are partly FACTOR-TIMING payoffs, not residual alpha. An
   institution would decompose our "IC" differently; a Barra-lite decomposition (106) makes us
   know which money we are earning without forcing residualization the evidence rejected.

---

## 3. The institutional gap, dissected

| Layer | Institution (top-tier reference) | Us | Catchable? |
|---|---|---|---|
| Data | tick/LOB depth, consolidated tape, alt-data at scale, decades of survivorship-free PIT | IEX free tier, daily bars, FMP Starter | **Partly** — money buys ~80% of the retail-relevant layer (RS-3, authorized) |
| Breadth × turnover | global multi-asset, 2000+ names, daily → BR ~10⁵–10⁶/yr | 142 names, 60d → effective BR ~10² | **Structurally 3 orders of magnitude apart** |
| Infrastructure | colocation, sub-ms execution, thousand-core grids | one Mac, 12-min launchd | Not chased (not needed at our size) |
| Process | Barra-class risk models, alpha-capture pipelines, dedicated execution research | being built (gate/ledger/prereg) | **12 months to process parity** |
| Cost structure | internalization, rebates, bps-level all-in | zero-commission + PFOF price improvement | **We are AHEAD at our size** |

**The quantitative reframe (the most important line in this document):** institutional IR ≈ 3–5
does NOT come from high IC. Stat-arb desks run per-forecast IC ≈ 0.005–0.02 — at or BELOW our
ceiling. Plug in: IC 0.01 × √500,000 × TC 0.5 ≈ **3.5**. **They win on √BR and TC, not on IC.**
"Catching up" therefore does not mean matching their IC (we can); it means maxing TC and buying
whatever BR is purchasable at our scale — and NOT pretending the 10⁵-BR layer is reachable.

**Our asymmetric advantages** (the only game worth playing): zero market impact ($10k orders move
nothing — the thing institutions envy), zero capacity pressure, zero redemption/career risk,
multi-day patience, free retail execution. Rational strategy = harvest what institutions are
capacity-constrained OUT of, not symmetric competition.

---

## 4. What "ordinary professional institution" actually is — quantified

The operator's question targets the **median** professional, not the top tier. The honest data on
the median professional (all cited-tier evidence):

- **SPIVA scorecards**: ~85–90% of US large-cap active funds underperform the S&P 500 over
  10–15 years, net of fees.
- **Median hedge-fund equity products**: long-run net Sharpe ≈ **0.5–0.8** (HFRI equity-hedge
  family); aggregate post-2010 hedge-fund alpha vs passive benchmarks ≈ 0 or negative in
  multiple academic and practitioner studies.
- Median institutional books carry heavy factor exposure sold as alpha; their genuine residual
  IC is frequently indistinguishable from zero — the same finding we made about ourselves,
  measured with better instruments.

**Therefore the "ordinary professional" bar, made falsifiable:**

| Dimension | Bar |
|---|---|
| Total book Sharpe (net, rolling 24m) | **≥ 0.7** |
| Benchmark-relative alpha (net, 24m) | **≥ 0 ± 2%/yr** (the median pro does NOT beat SPY) |
| Max drawdown discipline | ≤ 15% with a working regime/risk overlay |
| Process | validated models (a gate that renders verdicts), decision provenance, execution measurement, pre-registered changes |

This bar is dramatically more reachable than the top-tier bar — because the median professional,
net of fees, is mediocre. That is not cynicism; it is SPIVA.

---

## 5. Verdict: can 107 reach it? YES — with a quantified path and honest probability

**Verdict: reaching ordinary-professional level by end-2028 is a realistic target with ~60–70%
probability** (vs the 30–50% previously quoted for the HARDER "competent-pod active IR 0.8–1.0"
bar — that answer stands for that bar; this is a different, lower bar).

The increment stack (each independently measurable, none requiring heroics):

| Increment | Mechanism | Contribution (est.) | Evidence tier |
|---|---|---|---|
| 0. Parking sleeve (lane B) | idle 75% stops being a structural short-benchmark bet | book returns ≈ benchmark baseline (Sharpe ~0.8 era-dependent) | measured (drag decomposition, RS-1) |
| 1. Execution/expectancy engineering (105 + meta-label) | cut open-auction cost, filter negative-expectancy entries | **+0.5–1.5%/yr** at unchanged risk | **POC-C measured anchor**: fills = open confirmed (N=41, 09:30:00–01); open vs close on buy days +48.6bps mean/+58.1 median, t≈1.0 — economically large, significance = S10's job; Track A verdict pending |
| 2. Modest orthogonal IC stack (106) | genuine IC 0.02–0.03 × TC 0.7 × √BR ~200 ⇒ active IR ≈ 0.2–0.3 on the active sleeve | **+1–2%/yr** alpha | gated on measured placebo-clean IC |
| 3. Risk shaping (regime overlay, DD control — partially exists) | Sharpe via drawdown reduction, not return | +0.1–0.2 Sharpe | ledger-measurable |
| **Endpoint** | | **total Sharpe 0.9–1.2, alpha +1–3%/yr net, DD ≤ 15%** — clears §4's bar | |

**Probability decomposition (responsible arithmetic):** increment 0 is near-certain (mechanism is
arithmetic); increment 1 is likely (~75% — the prize exists in the overnight-accrual evidence,
S10 verifies); increment 2 is the risky one (~50% — requires the information-set change to yield
measurable IC); increment 3 is likely (~70%). The bar needs 0 + any TWO of {1,2,3}:
P ≈ 0.6–0.7. **The single biggest risk is increment 2 = the D3 information-set bet.**

**The verification-horizon honesty (do not skip this):** SE(annualized Sharpe) ≈
√((1 + SR²/2)/T_years). At SR = 1.0 over 2 years, SE ≈ 0.87 — **we can BUILD the capability by
2028 but cannot statistically PROVE Sharpe parity on 2 years of live data.** Therefore the route
gates below are LEADING indicators (measured IC, TC, IS savings, expectancy per admitted name —
estimable in weeks-to-months), never trailing Sharpe; the trailing-Sharpe verdict matures
2029–2030. Any plan promising "proven parity by 2028" would be statistically illiterate; this one
promises built-and-tracking by 2028, proven later.

---

## 6. The development route: 105 → 106 → 107

**105 — the execution generation (2026 H2; RFC #208 + roadmap #229 M1/M2).**
Capability: 盘中 decisioning engineering, execution-quality measurement, paired pilot data.
It creates no alpha; it repairs the decision→fill leakage (the intraday half of TC).
*Exit gate G105:* Stage-1 operational acceptance clean (§9.3), S10 prize memo says the
open-auction cost is real and material at target order sizes, paired corpus ≥ the §9.4 prereg
minimum. *Kill branch:* if S10 says the prize is immaterial even at 106-era order sizes, Stage-2
is descoped to risk-exits-only modernization — recorded, not silently dropped.

**106 — the information-platform generation (2027).**
Capability: PIT multi-source store matured (revisions ≥12 months deep — why N2 cannot wait a
day), FMP-full fundamentals, D3 executed (down-cap wave or new-data-only), the orthogonal
3–5-signal stack with Barra-lite factor decomposition, meta-label overlay live if Track A GO'd,
tournament retired (R1), TC repaired to ~0.7 (lane A + R4 verified in the ledger).
*Exit gate G106 (pre-registered):* ≥2 orthogonal signals each placebo-clean IC ≥ 0.015 measured
on the S5/S8 substrate; combined ≥ 0.02; TC ≥ 0.6 measured; active IR contribution ≥ 0.2 in
shadow. *Kill branch:* if by 2027-Q4 no combination clears 0.02, thesis review #3 defaults the
book to benchmark-sleeve mode + PIT accrual continues + 107 is re-scoped to an execution-only
product (this is the honest terminal branch, stated in advance).

**107 — the real-time portfolio machine (2028).**
Capability: Stage-3 intraday-aware models where data scale genuinely supports sequence methods
(the one place they have an advantage), event-driven re-decisioning, options-based risk shaping
(protective structure on concentrated names, not speculation), full risk overlay, capacity
decision (L6 — book scaling is what makes the 105/106 plumbing pay).
*Exit gate G107 = §4's bar as pre-registered assessment (end-2028):* total Sharpe ≥ 0.7 (rolling,
point estimate), net alpha ≥ 0, DD ≤ 15%, all process audits green — judged as LEADING indicators
+ point estimates, with the statistical maturity date (2029–30) stated on the verdict.

**Timeline with probability bands:**

| Milestone | Date | P(success) | Dominant risk |
|---|---|---|---|
| G105 (execution built + prize sized) | 2026-Q4 → 2027-Q1 | ~80% | ops discipline only |
| D3 decided on evidence | 2027-Q1 | — (decision, not outcome) | thin down-cap screen evidence |
| G106 (signal stack measured ≥0.02) | 2027-Q4 | **~50%** | the information-set bet |
| G107 (bar cleared on point estimates) | 2028-Q4 | ~60–70% cumulative | sequence risk (a 2027–28 bear market resets the clock, not the thesis) |
| Statistical maturity of the Sharpe claim | 2029–30 | — | arithmetic of SE(Sharpe) |

**What is permanently out of scope (T3):** colocation/tick infrastructure, 10⁵-breadth
multi-strategy, competing with top-tier shops symmetrically. The end-state identity is a
**capacity-constrained niche book run at institutional process discipline** — which §4 shows is
enough to clear the median professional, because the median professional does not clear it
either.

---

## 7. Bounds: where the model's ceiling AND floor actually are

### 7.1 The ceiling, in three layers (and the alarm above it)

1. **IC layer** (§2.2): current set 0.02–0.04 · +orthogonal PIT 0.03–0.05 · down-cap 0.05–0.08
   gross ⇒ **~0.03–0.05 net** after 25–40bps small-cap costs at our (impact-free) size.
2. **Book layer** (IR = TC·IC·√BR). **Measured (POC-A, `poc_effective_breadth.py`): the
   current panel's effective breadth is BR_eff ≈ 131 bets/yr point estimate, interval
   [77, 500]** (participation-ratio vs equicorrelation bounds; ρ̄ ≈ 0.001 on excess labels —
   the reduction comes from residual sector/style structure, not the market mode). Anchored
   arithmetic: current universe — IC 0.03 × TC 0.7 × √131 ⇒ **active IR ≈ 0.24 ⇒ alpha ≈
   +1.2–2%/yr**; with the M8 breadth wave succeeding (~400 quality names at the measured
   N_eff/N ratio ⇒ BR_eff ≈ 370) ⇒ **IR ≈ 0.40 ⇒ +2–3.5%/yr**; if down-cap ALSO works:
   IR 0.5–0.7 ⇒ **+3–5%/yr**. Total-book ceiling ≈ benchmark Sharpe + active ⇒ **Sharpe
   ~1.2–1.5 in a normal era.** That is the ceiling of this structure — not of effort.
3. **Dollar layer (the honest one):** at the current $10.8k book, the FULL ceiling (+5%/yr) is
   ~$540/yr. The plan's monetary value is the **capability + the scaling option (L6)**, not
   near-term P&L. Written here so nobody discovers it in 2028.

**The above-ceiling alarm (responsibility cuts both ways):** any sustained measurement of
IC > 0.08 or book Sharpe > 2 at this scale/structure is treated as **presumed leakage or luck
and triggers an audit before it is believed or sized up** — the inverse discipline of hoping it
is real.

### 7.2 The floor, in three tiers

1. **Engineered floor (available at any time, by one recorded decision):** benchmark-sleeve mode
   — the book tracks SPY (or T-bill carry at β=0) minus ~0.3%/yr ops drag. Every kill branch in
   this plan lands HERE, not at zero. Caveat stated plainly: this floor is *relative*; SPY itself
   can draw down 30–50% — the floor removes *relative* failure, not market risk (the β=0 T-bill
   variant removes both, at the cost of expected return).
2. **Undisciplined floor (why the ops track is not optional):** if the safety engineering fails,
   the floor is **unbounded below in relative terms** — this system has already demonstrated the
   failure class (the 06-26 18-FAIL day from a clobbered hotfix; wash-sale mis-blocks;
   fail-closed no-trade weeks; stale-model universe zeroing). S11/R2/monitors ARE the floor's
   load-bearing wall. A plan that skipped them to chase alpha would have no floor at all.
3. **Current realized position:** live ≈ flat while SPY rallied — **we sit BELOW the engineered
   floor today.** Lane B closes that gap mechanically, which is why it is a July item and not an
   optimization.

---

## 8. Per-milestone risk register — P(success), failure modes, Plan B, downstream impact

Probabilities are stated with their basis (engineering judgment vs measured priors vs outcome
uncertainty). **"P" for OUTCOME milestones is the probability the outcome is favorable — an
unfavorable outcome executed cleanly is the process WORKING, not failing;** those rows say so.

### 8.1 NOW + SHORT (July)

| Milestone | P | Dominant failure modes | Plan B | Downstream impact if failed |
|---|---|---|---|---|
| N1 collectors live | 0.90 | scheduling/entitlement friction | manual daily invocation while fixing | 105 pilot data slips day-for-day; G105 only |
| N2 PIT accrual | 0.85 | base-data ownership unresolved; schema churn | **minimal-viable snapshotter** (raw dump + `available_at`, formalize later) — depth of history is what matters, elegance is not | every month lost is unrecoverable; <6mo history by 2027-Q2 removes the revisions signal from G106's candidate set → P(G106) 0.50→~0.40 |
| N3 FMP | 0.95 | vendor coverage gaps | RS-3 substitutes (Polygon/Sharadar — spend authorized) | minor delay only |
| S1–S3 gate repair | 0.85 | hidden path deps; margin dispute; deeper rot than mapped | **build a minimal standalone validation harness** (WF + placebo-diff only, single-purpose) instead of repairing the legacy script | D1 undecidable → model stays directive-traded, thesis #1 treats it as unvalidated (default: shrink active risk). **Key resilience: G106's measured-IC gate runs on the S5/S8 substrate, NOT the WF gate — the alpha track survives this failure** |
| S4 / D1 verdict | outcome: P(pass)≈0.25 / P(fail-substance)≈0.55 / P(inconclusive)≈0.20 (prior: Fix-4 history) | — | on FAIL: demote primary to directive-with-shrunk-sizing OR best-of-recent under #210's protocol | **a FAIL is information, not roadmap failure** — increment 2 bets on NEW signals, not this model; the route's P is nearly independent of D1 |
| S5 ledger wiring | 0.90 | schema/perf; backfill gaps | forward-only ledger (no backfill) | M3/M5/RS-2 validations delayed ~1 quarter; nothing dies |
| S6 lane A | 0.80 (deployed ≥60% in 15 sessions, A+B combined) | **measured (POC-B)**: post-retrain runs have 17–20 names above the floor with a raw-Kelly ceiling of 93–95% — scarcity does NOT bind now; the binding constraints are the shrinkage stack (×≈0.43 observed ⇒ realistic lane-A ceiling ≈ 40–43%) and gate-state volatility (fail-closed days zero the ceiling) | lane B covers the ~20pp residual AND insures deployment against fail-closed states | none on the alpha track; deployment target met via A+B |
| S7 lane B sleeve | 0.95 (mechanism is arithmetic) | sweep plumbing bugs; risk-appetite reversal | T-bill variant (β=0) or partial sleeve | floor uplift delayed; nothing else |
| S8 regen table | 0.90 | artifact rot blocks faithful re-score | forward-collect OOS predictions from the live shadow path (3–6 months) | S9 slips a quarter; G106 timeline pressure |
| S9 Track A verdict | outcome: P(GO)≈0.30 / P(NULL)≈0.70 (prior: BULL_CALM coin-flip) | — | NULL is pre-registered and lands on Track B — already the plan's expectation | on NULL, increment 1 loses its meta-label half: contribution +0.5–1.5%/yr → +0.3–0.8%/yr |
| S10 IS prize memo | 0.85 execution; outcome: P(prize material) raised ≈ 0.50 → **≈ 0.65** on the POC-C point estimate | thin historical fill sample (N=41; open-vs-close +48.6bps mean/+58.1 median but SE 47.5 ⇒ t≈1.0 — **direction measured, significance pending**) | supplement with the N1 collector corpus (weeks) | if immaterial: **G105 kill branch** — Stage-2 descoped to risk-exit modernization; increment 1 halves; 107 re-scoped away from intraday-entry emphasis |
| S11 hotfix PRs | 0.95 | none material | — | floor tier-2 stays leaky until done |
| S12 shadow freshness | 0.80 | panel-refresh root cause is deep (label-join redesign) | serve shadow at the achievable frontier with a documented-lag caveat | champion–challenger reads carry vintage caveats; no other branch |

### 8.2 MID (Aug–Sep)

| Milestone | P | Dominant failure modes | Plan B | Downstream impact if failed |
|---|---|---|---|---|
| M1 Stage-1 build + readonly | 0.75 in-quarter | 3-repo coordination + review-loop latency (the risk is calendar, not engineering) | descope: orchestrator readonly first, defer the execution-repo state machine one quarter | M2→L2 slip one quarter; no branch dies |
| M2 frozen canary | 0.70 operational-clean; **P(noise-halt) ≈ 0.4–0.5** (#223 A5.4 scenario) | loss-budget hit by market beta | **pre-committed**: halt → re-authorization is a recorded delegated decision (§1 protocol); never silent continuation | pilot corpus accrues slower; G105 slips, does not die |
| M3 conviction haircut | 0.70 | S5 dependency; replay inconclusive | ship the thin-margin *alert* (observe-only) instead of the gate change | thin-margin buys (OXY class) persist; cosmetic to the route |
| M4 BL-1 recentering | 0.75 | admission-set surprises | keep BL-4 direction gate as the permanent guard | mu absolute scale stays untrustworthy → M3 weakens; conviction semantics stay counter-based |
| M5 R1 shadow migration | 0.80 (panel admission proves safe) | delta report shows the tournament adds unique value (low prior) | keep the tournament, permanently fix its ops (timeout, monitor) — the fallback IS the status quo with better plumbing | freshness surface stays 2× larger; ops cost persists; route unaffected |
| M6 R2 fingerprints | 0.90 | migration friction | staged per-site migration | fail-closed incidents keep recurring until done |
| M7 down-cap screen | 0.85 execution; **outcome: P(positive at realistic costs) ≈ 0.35–0.45** (HXZ concentration vs 25–40bps + simple factor suite) | survivorship-clean membership data quality (RS-5) | if data inadequate: buy better membership data (authorized) before concluding | on NULL: D3 loses its universe half → new-data-only path; **P(G106) 0.50 → ~0.35–0.40** |
| M8 cluster wave-1 | **outcome: P(non-degradation) ≈ 0.50** (E34 prior) | transfer-coefficient collapse repeats | halt waves; breadth stays 142 | BR term stays ~200 → active-IR ceiling −~30%; alpha estimate in §5 shifts to its lower band |
| M9–M11 process items | 0.90 | none material | — | — |

### 8.3 LONG (2027–2028) — the composite gates

| Gate | P | How computed | Plan B | Downstream impact |
|---|---|---|---|---|
| D3 has something to act on | ≈ 0.75 | 1 − P(Track A NULL ∧ down-cap NULL ∧ revisions untestable) ≈ 1 − (0.7 × 0.6 × 0.55) | if truly empty-handed: hold + accrue PIT + re-screen in 2 quarters — a stable state, not a crisis | G106 slips ≥2 quarters |
| **G106 (≥2 orthogonal signals, combined IC ≥ 0.02, TC ≥ 0.6)** | **≈ 0.45–0.50** | ≥2-of-4 candidates (revisions, quality, residual-momentum, down-cap-derived) at individual P ≈ 0.4–0.5 each, with correlated failure (same-market confound) haircut | **the pre-registered kill branch**: benchmark-sleeve default + PIT accrual + 107 re-scoped to execution-only product | this IS the plan's central bet; §9's ladder is the answer |
| L2 §9.4 prereg feasible | 0.50 | identifiability arithmetic (#223 A5.5) | risk-acceptance path (already designed, §1 protocol) | canary expansion becomes a recorded judgment call |
| **G107 (the §4 bar, on point estimates, end-2028)** | **≈ 0.60–0.70** | increment 0 (≈1.0) + any 2 of {1: 0.75, 2: 0.45–0.50, 3: 0.70} with partial independence | fall one rung down §9's ladder | the ladder's next state is stable and pre-valued |

---

## 9. Is the roadmap reasonable? The audit, the ladder, and the confidence statement

### 9.1 Reasonableness audit (three tests)

1. **Failure-independence test:** the route survives D1 FAIL (increment 2 does not bet on the old
   model), Track A NULL (pre-registered expectation), and down-cap NULL (new-data-only path) —
   individually AND pairwise. The only failure that reaches the route's core is **all four G106
   candidates failing together** — and that lands on the pre-registered kill branch, not on
   improvisation. No milestone failure leads to an undefined state; every row in §8 has a Plan B
   column that was written BEFORE the outcome is known.
2. **Resource-realism test:** July (S1–S12) is the crunch; one operator + agents cannot do 12
   items at once. Priority order if capacity binds, fixed now: **S1–S5 (measurement substrate) >
   S8–S10 (evidence generation) > S6–S7 (drag) > S11–S12 (hygiene)** — because everything in
   MID/LONG consumes the measurement substrate, and drag has a one-decision fallback (the
   sleeve) while measurement has none.
3. **Sequence-risk test:** a 2027–28 bear market resets the *trailing* metrics clock (G107's
   point estimates), not the thesis — leading-indicator gates (IC, TC, IS) are
   regime-conditioned by construction (per-regime cuts are mandatory in every memo). BEAR also
   flips the sleeve to cash by the existing regime contract — the floor is regime-aware.

### 9.2 The master fallback ladder (the direct answer to "实现不来怎么办")

Every terminal state is stable, pre-valued, and reachable by recorded decisions — partial failure
degrades, it does not crash:

| Rung | State | When | Expected value of the state |
|---|---|---|---|
| 1 | **Full 107**: execution + signal stack + risk shaping | G105 ∧ G106 pass | Sharpe 0.9–1.2, alpha +1–3%/yr, scaling option live |
| 2 | **Execution-only product**: 105 capability + sleeve, no directional alpha claim | G105 passes, G106 kill branch | Sharpe ≈ benchmark + 0.3–0.8%/yr (execution + expectancy residue); an honest, REAL product |
| 3 | **Benchmark-sleeve + accrual**: book parks, PIT/data platform keeps compounding, screens re-run every 2 quarters | G105 also disappoints | Sharpe ≈ benchmark; zero relative bleed; the OPTION on future signals is preserved at near-zero cost |
| 4 | **Full stop of active risk** (β=0 variant) | operator risk preference or thesis review says so | capital preserved; capability + data remain |

The ladder's existence is the plan's core safety property: **the worst *designed* outcome is rung
3–4 — matching the median professional's realized alpha (≈0) at a fraction of their cost — while
the undisciplined outcome (skipping the ops track) has no floor at all.** That asymmetry is why
the boring items (S11, R2, monitors) outrank alpha work whenever they conflict.

### 9.3 Confidence statement (what I am actually claiming, and what I am not)

- P(reach rung 1 by end-2028, point-estimate basis) ≈ **0.60–0.70** — dominated by G106 ≈ 0.45–0.50.
- P(reach rung ≥2) ≈ **0.85** — G105 is mostly engineering.
- P(reach rung ≥3) ≈ **0.97** — one decision away at all times; residual risk is operational
  discipline, which is exactly what the hard-gated ops track exists to hold.
- NOT claimed: statistical proof of any Sharpe by 2028 (§5's SE arithmetic); any path to
  top-tier parity (§6 T3); that the G106 bet is likely — it is roughly a coin flip and it is the
  honest heart of the plan. What makes the plan responsible is not a high P on the bet; it is
  that **both sides of the coin land on a pre-registered, valued state.**

---

## 10. Cross-references

PR #228 (capability program: P0–P3, lanes, R1–R7) · PR #229 (H2 roadmap: N/S/M/L items, D1–D4,
RS-1…RS-6; its §9 sign-off list is superseded by §1 of this document) · #208 (105 RFC) ·
#210/#212/#213 (freshness) · #223 (review amendments, merged) · direction decision 06-28 ·
failed-experiments E27/E33/E34/E35 · #256 (persistence decomposition) · #199 (phase −1 NO-GO).
