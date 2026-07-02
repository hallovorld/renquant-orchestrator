# Unified 107 master plan — goal-decomposed, evidence-tiered, POC-anchored

STATUS: design / RFC for review (docs only). **Supersedes the task tables of PR #229** (the H2
execution roadmap) — recommend closing #229 in favor of this document. **Companion to PR #230**
(the route/evidence layer: IC ceiling, institutional gap, bounds, risk register, fallback ladder,
POC verification — its gates and evidence are UNCHANGED and cited here, not restated).
DATE: 2026-07-02
OPERATOR DIRECTIVE (2026-07-02): apply the POC standard (every claim measured or theory-backed,
reproducible) to ALL roadmap content; unify it; re-derive every short/mid/long-term task with one
explicit objective — **107 reaches ordinary-professional-institution level.**

---

## 0. The objective function and the measured state vector

**Target G\* (end-2028, pre-registered in #230 §4, judged on point estimates + leading
indicators; statistical maturity 2029–30):**
total book Sharpe ≥ 0.7 · net benchmark-relative alpha ≥ 0 · max DD ≤ 15% · institutional
process (a gate that renders verdicts, full decision provenance, measured execution,
pre-registered changes).

**The value equation every task must serve** (Grinold–Kahn / Clarke–de Silva–Thorley):

```
Book = β(FLOOR: sleeve + ops discipline)
     + Active:  IR = TC × IC_combined × √BR_eff        [alpha term]
     + EXEC:    entry/exit implementation gain          [expectancy term]
     − LEAK:    process failures (fail-closed days, stale models, bugs)
```

**Current vs target state vector** (every row measured or dated fact — the plan IS the gap):

| Term | Current (measured, 2026-07-02) | Target (2028) | Standing metric |
|---|---|---|---|
| IC_combined (placebo-clean) | **≈ 0** (A1: CI [−0.031,+0.129] ∋ 0; BULL_CALM −0.003) | **0.02–0.03** (POC-D-adjusted stacking: 3 signals ⇒ 0.028–0.033 at ρ≈0.2) | S5/S8 substrate, per-regime cuts |
| TC | **≈ 0.4 (reasoned — measurement is task S-TC)**; shrinkage stack ×0.43 measured (POC-B) | **≥ 0.6 measured** | corr(target weights, unconstrained Kelly weights) per run |
| BR_eff | **131/yr point [77, 500] (POC-A)** | **≥ 300/yr measured** | POC-A method, quarterly |
| EXEC leak | fills = open confirmed; **+23–49 bps/entry point est., t≈1.0, N=41 (POC-C)** | **< 10 bps/entry, CI-backed** | S10 + collector corpus |
| Deployment | **25% deployed / 75% idle** (07-01); lane-A realistic ceiling 40–43% (POC-B) | **≥ 95% incl. sleeve** | daily KPI |
| FLOOR | **below benchmark** (live flat vs SPY rally) | benchmark-tracking ± ops drag | weekly vs SPY |
| PROCESS | gate mute since 05-18; ledger unwired; pins-behind warning live | weekly verdicts; 100% decision provenance | gate-verdict age; ledger coverage |
| Overnight/intraday context | **62/38 split; buy-day intraday −49 bps (POC-C)** | (context, not a target) | refreshed with S10 |

Implied endpoint if targets land: active IR ≈ 0.6×0.025×√300 ≈ **0.26 on the active sleeve**
(+1–2%/yr) + EXEC +0.5–1.5%/yr + β floor ⇒ **Sharpe 0.9–1.2, alpha +1–3%/yr — clears G\***.
With M8/D3 breadth-and-IC upside: +3–5%/yr (#230 §7.1). P(G\*) ≈ 0.60–0.70 (#230 §9.3).

---

## 1. Task plan, decomposed by objective term

Format per task: **ID · moves · Δ(basis tier) · guidance · AC · P · Plan B → downstream.**
IDs retain #229 numbering for traceability; NEW tasks are marked. Horizons: N ≤72h · S = July
· M = Aug–Sep · L = Q4'26→2028.

### Term PROCESS — make the system able to KNOW (prerequisite to every other term)

| ID | Task | Δ / basis | Guidance | AC | P | Plan B → downstream |
|---|---|---|---|---|---|---|
| S1–S3 | WF-gate repair (Fix-1 path, Fix-2 parity, Fix-3 placebo **difference** test, margin frozen pre-impl at 0.02 vs the measured +0.04 embargo floor) | unlocks IC measurement on the live path (measured floor: wf-gate corpus) | 3 PRs in backtesting/model, in order | 3 clean weekly runs; fixture: passes known-clean, fails known-leaked | 0.85 | minimal standalone harness (WF+placebo-diff only) → G106 measurement is ledger/S8-based, survives this failure |
| S4 | **D1: first verdict on live primary since 05-18** | information, not P&L | run repaired gate; escalation memo on FAIL | a recorded verdict either way | outcome: pass 0.25 / fail 0.55 / inconclusive 0.20 | FAIL ⇒ shrink-sized directive trading or #210 best-of-recent → route unaffected (increment 2 bets on NEW signals) |
| S5 | Decision-ledger wiring (R5) | 100% provenance; the substrate for TC/IC/expectancy measurement | pipeline+orchestrator PRs; OXY 07-01 as canonical fixture | every live run writes; fwd-outcome join ≥95% for aged decisions | 0.90 | forward-only (no backfill) → M3/S-TC/RS-2 delayed one quarter |
| S11 | Durable hotfix PRs (live-tree dirt → main) | closes the tier-2 UNBOUNDED floor (#230 §7.2) | inventory dirt; commit NameError + live_state fixes; recovery drill doc | live tree clean or fully ticketed | 0.95 | — |
| S12 | Shadow freshness impl (#212 ph2–4) + panel-refresh root-cause memo | trustworthy champion–challenger | diagnosis FIRST (builder-not-run vs dropna clip) | served pin advances via validated promote | 0.80 | serve at achievable frontier w/ documented lag |
| M6 | R2: one shared content-fingerprint impl | kills the recurring fail-closed no-trade class (3 incidents) | extract to renquant-common; fixture: identical hashes across 3 sites | 0 mismatch fail-closes in 30d | 0.90 | staged per-site |
| M9 | #210/#212 text alignment + generated `strategy-104.md` snapshot + CI staleness check | doc/impl divergence closed (#223 A1/A6) | amendment PRs per #223 | RFC text = #213 semantics; CI fails on stale snapshot | 0.90 | — |

### Term FLOOR — stop losing to plumbing (fastest guaranteed win)

| ID | Task | Δ / basis | Guidance | AC | P | Plan B → downstream |
|---|---|---|---|---|---|---|
| S7 | Lane B parking sleeve (RS-1 memo decides SPY vs T-bill vs split — delegated decision, §1 protocol of #230) | closes the measured below-benchmark gap; **also insures deployment against fail-closed states (POC-B: gate-state zeros the stock ceiling)** | config-flag impl after RS-1; 10-session shadow of sweep/fund; BEAR sweeps off | idle ≤ reserve+1% at every close; BEAR sim test passes | 0.95 | T-bill (β=0) or partial sleeve → floor uplift delayed only |
| S6 | Lane A de-throttle: λ 0→0.05 shadow-swept; top_n 3→5–6; one-share floor for high-price names | **POC-B measured**: raw ceiling 93–95% post-retrain; shrinkage-realistic 40–43% ⇒ lane A ≈ +15–18pp deployment; kills the BLK selection-by-price artifact | 3 config experiments, gates unchanged, ledger-verified | deployed ≥60% (A+B) in 15 sessions; zero gate bypass | 0.80 | sleeve absorbs residual → none |

### Term EXEC — the expectancy engine (POC-C promoted this term)

| ID | Task | Δ / basis | Guidance | AC | P | Plan B → downstream |
|---|---|---|---|---|---|---|
| N1 | 105 collectors live + liveness | data for everything in this term | launchd per #212 pattern | 3 sessions of complete output + lapse-alert test-fire | 0.90 | manual invocation → day-for-day slip |
| S10 | Full open-auction IS study | **POC-C anchor: +23–49 bps/entry point, t≈1.0** → CI the prize | extend POC-C to all history + collector corpus; liquidity splits | bps/entry with CI; feeds §9.4 prereg | 0.85; P(material) ≈ 0.65 | if immaterial: G105 kill branch — Stage-2 → risk-exit modernization; increment 1 halves |
| S8 | Track A regeneration PR (durable OOS pick table) | evidence base for expectancy filter AND the 105 direction | `regen_oos_pick_table.py` → `data/exp/…parquet` | reproduces genuine_ic ±0.001; ~147k rows | 0.90 | forward-collect from shadow (3–6 mo) → S9 slips |
| S9 | Track A conditional test (criteria FROZEN) | meta-label expectancy: P(GO) ≈ 0.30 | run the direction-decision §4 spec unmodified | recorded GO or NULL, CIs, zero post-hoc edits | outcome | NULL pre-registered → increment 1 = execution-only (+0.3–0.8%/yr) |
| M1 | 105 Stage-1 build → readonly K=5 | the intraday half of TC/EXEC | #208 §8 order + #223 pins (census, order type, intraday-margin envelope, exits-always-allowed) | per-repo ATs green; 5 readonly sessions, replay green, census complete | 0.75/quarter | orchestrator-readonly first → M2 slips a quarter |
| M2 | Frozen canary (delegated start per #230 §1) | real paired fills within the #208 §9.3a envelope | 1–2 names, ≤20 sessions, 1.5% budget; **P(noise-halt) ≈ 0.4–0.5 — response pre-committed** | §9.3 ops acceptance every session; halt honored on exhaustion | 0.70 | halt → recorded re-authorization → G105 slips not dies |
| L2 | §9.4 simplified experiment prereg | powered-or-honest | pilot paired-residual variance, cluster unit, α/power, attrition, blinded re-estimation (#223 A5.5) | frozen prereg; underpowered ⇒ **risk-acceptance labeling** | 0.50 feasible | risk-acceptance path (designed) |
| L3 | Stage-2 timing policies (shadow-first) | conditional timing residual ONLY (phase −1 NO-GO not re-litigated) | pre-register policies in the #220 evaluator; ≥60 shadow sessions | live flip only with shadow CI | gated on G105+L2 | descope |

### Term IC — the alpha bet (the plan's honest coin flip, P ≈ 0.45–0.50)

| ID | Task | Δ / basis | Guidance | AC | P | Plan B → downstream |
|---|---|---|---|---|---|---|
| N2 | PIT revision accrual starts (time-irreversible) | candidate signal #1; **POC-D says orthogonality lives ACROSS data families** — this is the cross-family leg | minimal-viable snapshotter OK; write-time `available_at`; no backfill | 3 consecutive daily appends + missed-day alert | 0.85 | raw-dump fallback → every lost month permanently narrows G106 |
| N3 | FMP Starter + harvest (SPEND AUTHORIZED) | candidate signal #2 substrate | subscribe, re-harvest, 5y history | ≥95% coverage; 0 plan-locked errors | 0.95 | RS-3 substitutes |
| RS-3 | Data-vendor stack memo (1 week) | buys the data layer of the gap (#230 §3: "partly catchable with money") | deep-research: FMP tier vs Polygon vs Sharadar/Norgate for PIT+tape+small/mid membership | subscription list + monthly total + per-item roadmap mapping | 0.90 | — |
| M4 | BL-1 recentering (sign_laundered 44/90) | measured-IC fidelity (mu scale trustworthy) | recenter raw per bar; BL-4 stays interim guard; shadow replay first | laundered count → single digits; admission delta = laundered names only | 0.75 | keep BL-4 permanent → M3 weakens |
| **M-SIG (NEW)** | Build + measure the 3-signal stack (revisions, quality, regime-conditioned residual momentum) on the S5/S8 substrate | **the G106 core**: target combined 0.028–0.033 (POC-D-adjusted); gate ≥0.02 | one signal PR at a time; per-signal placebo-clean IC with CI; cross-family ρ measured (extends POC-D) | ≥2 signals ≥0.015 individually; combined ≥0.02; ρ matrix committed | **0.45–0.50 composite** | **G106 kill branch: benchmark-sleeve default + PIT keeps accruing + 107 re-scoped execution-only** |
| M7 | Down-cap MVP screen (read-only; RS-5 panel spec) | the literature-supported IC+BR upside | frozen thresholds BEFORE running; 25–40bps costs; survivorship documented | go/no-go memo | exec 0.85; P(signal) 0.35–0.45 | null ⇒ D3 = new-data-only; P(G106) → 0.35–0.40 |
| L1 | **D3: Track B structural decision** (delegated, §1 protocol) | selects the 106/107 information set | synthesis of S9+M7+M8+≥120d PIT | recorded decision + staged-migration RFC if down-cap | P(something to act on) ≈ 0.75 | hold + re-screen in 2 quarters (stable state) |

### Term TC — keep what the model earns (cheapest IR, zero IC cost)

| ID | Task | Δ / basis | Guidance | AC | P | Plan B → downstream |
|---|---|---|---|---|---|---|
| **S-TC (NEW)** | Measure TC directly, per run | replaces the reasoned 0.4 with a measured baseline; the term's standing metric | script: corr(actual target weights, unconstrained Kelly weights) from candidate_scores; committed like the POCs | TC time series on the ledger; baseline memo | 0.90 | approximate from POC-B counterfactuals |
| M3 | Shrinkage-stack review + conviction uncertainty haircut | **POC-B measured: ×0.43 compounding halves deployment**; haircut kills thin-margin (OXY-class) entries | ledger replay: `mu−k·SE(mu) > floor`, k∈{0.5,1}; re-derive σ double-count | replay shows losers removed ≥ winners; thin-margin buys → ~0 | 0.70 | observe-only alert instead |
| R4 (M) | Selection-budget refactor (top_n + whole-share + shrinkage in ONE ledger-logged stage) | makes TC inspectable and tunable in one place | pipeline refactor RFC after S6 data | every drop reason a ledger field | 0.80 | keep 3-site logic, ledger-log only |
| M5 | R1 tournament retirement (shadow migration ≥20 sessions) | removes a whole freshness-incident class + admission artifacts | panel-based admission logged parallel; delta report; rollback quarter | cutover merged; per-ticker monitoring surface retired | 0.80 | keep tournament, fix its ops permanently |

### Term BR — breadth (PROMOTED by POC-A: current BR_eff=131 caps IR at 0.24)

| ID | Task | Δ / basis | Guidance | AC | P | Plan B → downstream |
|---|---|---|---|---|---|---|
| M8 | Cluster-wave 1 (+~100 quality names, E34 resume condition) | **POC-A: BR_eff 131 → ~370 at measured N_eff/N ratio ⇒ IR 0.24 → 0.40 at same IC/TC** — now a first-class term, not P3 | cluster-based admission; paired WF per wave; halt on degradation | wave-1 IC within noise band of baseline | outcome 0.50 (E34 prior) | halt waves; BR via D3 down-cap instead (the two BR paths hedge each other) |
| L1 | (D3 also serves BR — down-cap adds names AND documented-stronger IC) | coupling stated | see Term IC | | | |

### Term SCALE — convert capability to dollars

| ID | Task | Δ / basis | Guidance | AC | P | Plan B |
|---|---|---|---|---|---|---|
| L6 | Book-scaling decision (delegated, §1 protocol) | at $10.8k the full ceiling ≈ $540/yr (#230 §7.1) — capability only pays at scale | scorecard: D1 verdicts flowing, deployment ≥60%, canary clean, thesis #1 not terminal | recorded decision + capability scorecard | — | stay small; capability retains option value |
| M10/L7 | Thesis reviews #1/#2 (pre-registered criteria BEFORE evidence) | the macro kill/pivot forum | #230 §9.2 ladder is the decision space | signed reviews; next criteria dated | — | — |

---

## 2. Horizon view (same tasks, time-sequenced)

- **NOW (≤72h):** N1 · N2 · N3 — all three feed IC/EXEC data that cannot be backfilled.
- **SHORT (July):** S1–S5 (PROCESS core) → S-TC · S6 · S7 (FLOOR/TC) · S8–S10 (EXEC/IC evidence)
  · S11–S12 (floor tier-2) · RS-1/RS-2/RS-3 memos. **Capacity priority (unchanged, #230 §9.1):
  S1–S5 > S8–S10 > S6–S7 > S11–S12.**
- **MID (Aug–Sep):** M1→M2 (EXEC build) · M-SIG start (IC core) · M3/M4/M5/R4 (TC/IC fidelity)
  · M6/M9 (PROCESS) · M7/M8 (IC/BR upside) · M10 thesis #1.
- **LONG (Q4'26→2028):** L1/D3 → M-SIG completion → **G106 read (2027-Q4)** → L2/L3 (EXEC
  maturity) → 107 assembly (Stage-3 conditional on D3; risk shaping; L6 scaling) → **G107 =
  G\* assessment (end-2028)** → L7 thesis #2.

Decision gates (D1–D4), the bounds (§7), the per-milestone risk register (§8), the fallback
ladder (§9.2), and the probability calculus (P(rung 1) ≈ 0.60–0.70 dominated by G106 ≈ 0.45–0.50;
P(rung ≥2) ≈ 0.85; P(rung ≥3) ≈ 0.97) are all inherited from #230 unchanged.

---

## 3. What the POCs changed in this unification (the delta log)

1. **BR promoted from P3 afterthought to a first-class term** — POC-A measured BR_eff = 131
   caps current-universe IR at 0.24; M8 and D3 are now the two hedging paths to ≥300.
2. **EXEC term promoted** — POC-C's +23–49 bps/entry point estimate (on N=41 real fills, fills =
   open confirmed) makes execution the fastest measurable win after the floor; P(S10 material)
   0.50 → 0.65.
3. **Lane A/B rationale rewritten from measurement** — POC-B refuted "conviction scarcity";
   the binding constraints are the ×0.43 shrinkage stack and gate-state volatility; sleeve
   retained for corrected reasons (residual + insurance).
4. **IC stacking target discounted** — POC-D: plan on 0.028–0.033 (ρ = 0.217 intra-family),
   G106 gate ≥ 0.02 unchanged; cross-family data (N2/N3) is where orthogonality lives, raising
   their criticality.
5. **New tasks:** S-TC (measure the transfer coefficient — the last reasoned-tier number in the
   state vector) and M-SIG (the explicit 3-signal build+measure that was implicit in "106").
6. **Every task now names the term it moves and the basis tier of its Δ** — the operator's
   standard applied to the whole plan.

## 4. Standing measurement plan

The §0 state vector is re-measured and appended to this doc (dated addendum) **monthly**:
IC_combined (S5/S8 substrate, per-regime) · TC (S-TC series) · BR_eff (POC-A method) · EXEC leak
(S10/collector corpus) · deployment · floor gap vs SPY · gate-verdict age · ledger coverage.
The POC scripts are the standing instruments — they are already committed and re-runnable.
Monthly re-baseline may move tasks between horizons with a stated reason; only thesis reviews
may change direction (#229 cadence rules carry over).
