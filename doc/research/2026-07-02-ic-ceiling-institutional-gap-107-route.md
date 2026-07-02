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
2. **Orthogonal stacking — the only theory-supported IC growth**: combined IC ≈ √(Σ IC_i²) for
   independent signals; three orthogonal 0.02s ≈ 0.035. Candidate stack, by evidence: estimate
   revisions (PIT store, N2), quality/fundamentals (FMP, N3), regime-conditioned residual
   momentum (#176 — our one "relatively promising" lead).
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
| 1. Execution/expectancy engineering (105 + meta-label) | cut open-auction cost, filter negative-expectancy entries | **+0.5–1.5%/yr** at unchanged risk | S10 measures the prize; Track A verdict |
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

## 7. Cross-references

PR #228 (capability program: P0–P3, lanes, R1–R7) · PR #229 (H2 roadmap: N/S/M/L items, D1–D4,
RS-1…RS-6; its §9 sign-off list is superseded by §1 of this document) · #208 (105 RFC) ·
#210/#212/#213 (freshness) · #223 (review amendments, merged) · direction decision 06-28 ·
failed-experiments E27/E33/E34/E35 · #256 (persistence decomposition) · #199 (phase −1 NO-GO).
