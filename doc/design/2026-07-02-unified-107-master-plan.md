# Unified 107 master plan — goal-decomposed, evidence-tiered, POC-anchored

STATUS: **DRAFT — dependency-index, NOT an execution source of truth, and NOT authoritative for
anything — structure included — while its source plans and core IC evidence remain unresolved or
blocked** (Codex review, 2026-07-02; refreshed 2026-07-02 r4). **#228** (capability program) and
**#230** (IC ceiling / route) have both MERGED to `main` as of this revision. What remains open:
- **`hallovorld/RenQuant#430`** (durable OOS pick-table generator/manifest) and
  **`hallovorld/RenQuant#431`** (an audit reporting the output of the nearest committed proxy
  method, `analyze_manifest_sanity_placebo.py`'s `aligned_real_ic` decomposition — NOT verified
  equivalent to the deleted original injection-test methodology — currently an UNRESOLVED
  discrepancy: the proxy's +0.044 vs the originally-cited −0.003 for BULL_CALM; #431's own latest
  round downgrades its reconciliation protocol further, to EXPLORATORY/RETROSPECTIVE — its
  parameters were chosen after seeing the already-observed results on the same table, so even
  fully "frozen" it cannot serve as a confirmatory test; a genuine confirmatory run needs either
  future unobserved dates or a sealed historical partition, neither of which exists yet) remain
  open and unresolved.

Until RenQuant#430/#431 resolve, treat every number in §0's state vector and every POC-derived AC
in §1 that depends on the disputed BULL_CALM figure as **provisional**, even though #228/#230
themselves are now merged. design / RFC for review (docs only). **Does NOT supersede PR #229**
(the H2 execution roadmap) — #229 remains the current execution plan; this document is a
non-authoritative draft/index alongside it, not a replacement. Once `RenQuant#430`/`RenQuant#431`
resolve, this document should be republished as a clean, authoritative revision — reconciled
against #229 at that point, not before.
**Companion to PR
#230** (the route/evidence layer: IC ceiling, institutional gap, bounds, risk register, fallback
ladder, POC verification — its gates and evidence are UNCHANGED and cited here, not restated; this
document inherits #230's own provisional/confirmed status for every cited number, it does not
independently upgrade them).
DATE: 2026-07-02
OPERATOR DIRECTIVE (2026-07-02): apply the POC standard (every claim measured or theory-backed,
reproducible) to ALL roadmap content; unify it; re-derive every short/mid/long-term task with one
explicit objective — **107 reaches ordinary-professional-institution level.**

---

## 0. The objective function and the measured state vector

**Target G\* (end-2028, a PLANNING target per #230 §4 — NOT yet a preregistered target; it becomes one only once #230's own IC/TC/BR measurement contract is frozen and an immutable baseline measurement exists, per #230 §5 — judged on point estimates + leading
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
| IC_combined (placebo-clean) | **DISPUTED, not settled** — A1's original read: ≈0 (CI [−0.031,+0.129] ∋ 0; BULL_CALM −0.003, "coin flip"). `RenQuant#431` ran the nearest COMMITTED PROXY method (`analyze_manifest_sanity_placebo.py`'s `aligned_real_ic` decomposition) against a now-durable table and got BULL_CALM **+0.044** — opposite sign — but this proxy is explicitly NOT verified equivalent to the deleted original injection-test methodology, so neither figure is "the" genuine/leak-controlled IC. A reconciliation protocol is PROPOSED in #431 but still incomplete (not yet frozen or executed). **Do not treat either figure as the current state until #431 resolves.** | **0.02–0.03** (POC-D-adjusted stacking: 3 signals ⇒ 0.028–0.033 at ρ≈0.2; #230's own provisional status applies) | S5/S8 substrate, per-regime cuts |
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
| S8 | Track A regeneration PR (durable OOS pick table) | evidence base for expectancy filter AND the 105 direction | `regen_oos_pick_table.py` → `data/exp/…parquet`, manifest per protected-path contract (`RenQuant#430`) | table durably regenerated, row/date/window counts reconciled exactly against the original A1 audit (**done**, `RenQuant#430`); the ORIGINAL "reproduces genuine_ic ±0.001" bar is **not met as stated** — `RenQuant#431`'s reproduction disagrees with the cited genuine_ic (see IC_combined row, §0) — so this AC is revised to "table is durable and row/date-window-exact; genuine_ic reconciliation is a SEPARATE, still-open gate (#431), not implied by table regeneration alone" | 0.90 for table durability (met); IC reconciliation itself unscored, pending #431 | forward-collect from shadow (3–6 mo) → S9 slips; IC reconciliation stalls → S9 runs on provisional/flagged inputs only, never a silent GO |
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

## 1.5 Gate specifications

Codex requirement: every true decision GATE (a point where continuing depends on a Y/N or
threshold outcome, not just an engineering deliverable) states an immutable artifact/recipe link,
its evidence tier, owner, input dependencies, stop rule, rollback, capital authority, and whether
failure kills the branch or merely defers it. The task table in §1 already carries AC/P/Plan-B for
every row; this section makes the seven rows that are actual GATES (not tasks) fully explicit.
Ordinary engineering tasks (S1-S3, S5-S7, S10-S12, M1, M3-M9, N1-N3, R4, RS-1/2/3) are deliverables
with acceptance criteria, not decision gates, and are not repeated here.

| Gate | Immutable artifact/recipe | Evidence tier | Owner | Input dependencies | Stop rule | Rollback | Capital authority | Kill or defer |
|---|---|---|---|---|---|---|---|---|
| **D1 / S4** — first verdict on live primary since 05-18 | the repaired WF gate (S1-S3: Fix-1 path, Fix-2 parity, Fix-3 placebo-difference test) run against the live primary's current artifact; no committed corpus reference exists until S1-S3 land | validation → production once S1-S3 land (currently the gate itself is mid-repair) | backtesting/model repos (S1-S3 PRs) | S1-S3 must merge first | none — this task is designed to produce a recorded verdict regardless of outcome (pass/fail/inconclusive), it does not itself gate on a threshold | n/a — observational; if the repaired gate is later found buggy, the fix is further gate repair, not reverting this verdict | **none** — "information, not P&L" (stated in §1) | neither — routes downstream per outcome (FAIL ⇒ shrink-sized directive trading or #210 best-of-recent; PASS ⇒ primary confirmed) |
| **Track A GO/NULL — S9** | `regen_oos_pick_table.py` output (S8, `RenQuant#430`) scored against the direction-decision doc §4's pre-registered (a)-(e) criteria (unmodified) | validation (pre-registered test on held-out window) — but its INPUT (genuine_ic) is currently disputed, see §0 | not yet assigned — TBD, whichever repo runs the direction-decision §4 spec | S8 (durable table, done) **and** `RenQuant#431`'s reconciliation (this test's read of "genuine_ic" must not proceed on a disputed number without flagging it explicitly in the result) | the direction-decision doc §4 (a)-(e) criteria, unmodified, zero post-hoc edits | n/a — observational test, no capital deployed by the test itself | **none** for the test; a GO unlocks BUILDING a meta-label filter (a further engineering decision), not capital deployment | **kill** (of this specific test spec) if NULL under the frozen criteria — the direction-decision doc §4 is explicit that this routes to "Track B is the only remaining path", not a retry of the same test; a genuinely NEW hypothesis (e.g. the BEAR risk-switch per #223 A7.2) would need its own separate frozen prereg, never a revival |
| **Frozen canary — M2** | RFC #208 §9.3a envelope, once `renquant-orchestrator#224` (broker envelope) and `#227` (measurement pins) land | production (real fills, real capital, bounded) | execution + pipeline + orchestrator repos per RFC #208 §8's decomposition | #224, #227, and M1 (Stage-1 build, readonly K=5 sessions clean) must ALL land/pass first | duration cap (20 sessions) **or** loss budget (1.5% of equity) breached, with **no** recorded §9.3a authorizing decision → HARD halt (RFC #208 §9.3a, already frozen) | kill switch default-OFF, revert to the 盘后 batch path (RFC #208 §9.3a) | bounded strictly to the pre-declared canary envelope (1-2 names, ≤20 sessions, 1.5% loss budget); **any** expansion requires a SEPARATE, explicitly recorded §9.3a authorization — reaching this gate authorizes ONLY the frozen envelope, nothing more | **defer** — halt-on-exhaustion routes to "recorded re-authorization → G105 slips not dies" (§1), not a permanent kill |
| **D3 / L1** — Track B structural decision | synthesis memo of S9 (Track A verdict) + M7 (down-cap MVP screen) + M8 (cluster-wave BR result) + ≥120 days of accrued PIT data (N2) | mixed: exploratory (M7) + validation (S9) + accruing production data (N2 ≥120d) — explicitly not a single-tier read | operator (delegated decision, #230 §1 protocol) | S9, M7, M8, N2 reaching ≥120 days accrued | n/a — this IS the decision point, not gated by a further threshold; its OUTCOME routes downstream | "hold + re-screen in 2 quarters" (already the stated Plan B) | the decision itself does not spend capital directly; a down-cap outcome authorizes STARTING a staged-migration RFC process (itself a future, separate spend/capital decision), not spend at this gate | **defer** — explicitly "hold + re-screen in 2 quarters" is a stable hold state, not a program kill |
| **Book-scaling decision — L6** | the capability scorecard: D1 verdicts flowing + deployment ≥60% + canary (M2) clean + thesis review #1 (M10) not terminal | production (observed live operational metrics) | operator (delegated decision, #230 §1 protocol) | D1 (S4), S6/S7 (deployment ≥60%), M2 (canary clean), M10 (thesis #1 not terminal) | scorecard fails to clear → stay small (already the stated Plan B) | not addressed in this doc — reversing an already-authorized capital increase is a distinct, currently-unspecified operational question; flagged as **TBD**, not silently assumed | **explicit** — this is the clearest capital-authority gate in the plan: passing it is the operator authorizing additional capital into the book beyond the current ~$10.8k | **defer** — "stay small; capability retains option value" (§1) is a hold, not a kill of the program |
| **Thesis reviews #1/#2 — M10/L7** | #230 §9.2's fallback ladder (cited, not restated) | mixed — a synthesis/judgment review across whatever evidence has accrued by that point, deliberately not pre-specified to one tier | operator ("the macro kill/pivot forum") | whatever has accrued via §9.2's ladder by the review date — intentionally not itemized further here | none pre-specified — "signed reviews; next criteria dated" (§1) means the review itself SETS the next checkpoint's criteria, it is a recurring judgment forum, not a single pass/fail test | n/a | **highest in this plan** — a thesis review can authorize killing or pivoting the entire program direction, not just an incremental scale-up (contrast with L6, which is incremental) | **either** — this is explicitly a kill-OR-pivot forum; both outcomes are live by design |
| **M-SIG kill branch** (the 3-signal stack) | per-signal placebo-clean IC scripts on the S5/S8 substrate | validation (per-signal placebo-clean IC with CI), building toward production once combined and confirmed | model/pipeline repos (signal-build PRs, one at a time) | S5 (ledger wiring), S8 (durable table), N2/N3 (new cross-family data sources) | composite fails to reach ≥2 signals ≥0.015 individually AND combined ≥0.02 | n/a — a build/research task; nothing already live is rolled back if it fails | none directly (research/build only); the downstream G106 gate (2027-Q4, §2) is what would eventually authorize live use | **branch kill, not program kill** — explicitly "benchmark-sleeve default + PIT keeps accruing + 107 re-scoped execution-only" (§1): the alpha-stacking branch dies, the EXEC-only path continues |

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

---

## Dated addendum — 2026-07-02 (evening): SHORT-tier closure audit + forward-pull re-baseline

Per §4's re-baseline rule (dated addendum, stated reasons, never silent edits). Operator standing
instruction (2026-07-02): when a tier completes, adjust the plan autonomously and keep advancing
toward G*.

### SHORT-tier audit (one day in)

DONE (merged or collecting): N1/N2/N3 (7 launchd jobs; PIT day-1; FMP verified — quarterly
plan-locked above Starter, annual suffices) · S1/S2 (Codex) · S10 (material-but-unproven; true-VWAP
cohort) · S11 · S-TC (exploratory) · RS-1/2/3/5/6 · S6 as re-scoped (A-1 = production no-op
confirmed mechanically; A-2 deferred by design; A-3 built flag-off #156) · S7 built (#157 + config
#39; shadow AC pending enable).
IN REVIEW: S3 (#61, D1 chain ready: common#21 → caps #63/#30/#11 → #61) · S5 coverage (bt#60,
97–98% measured) · S8 front half (#59).
REMAINING EXECUTABLE GAPS (all dispatched this evening): S8 driver (run-gated pre-build) · S12
panel-refresh diagnosis · S4/D1 (gate run after the chain merges + pin-align — the unblock clause
covers a verdict-only run) · S9 (gated on S8).

### Forward-pulled from MID (reasons)

M1 slice 1 (the #208 §7 execution state machine) — the largest MID build, zero dependency on the
review queue, pulled to now. M3/M4/M5 dispatched same evening (ledger substrate matured; the
−0.29 calibrator-neutral warning made M4's evidence live; M5 is observe-only). M6 stage-2
(pipeline fingerprint migration + re-stamp plan) queued next — its prerequisite (0.9.1 shims)
shipped today. M7 awaits Norgate at kickoff (unchanged). M8 wave-1 queued behind the current
agent burst.

### State-vector deltas recorded today (feed the 2026-08-01 re-measurement)

C3 = MISS (G106 now 2-of-3: C1/C2/C4; composite ≈0.35–0.45) **[CORRECTED — see the 2026-07-03
dated addendum below (S-REL V4): the governing memo's verdict is UNADJUDICATED, not MISS; G106
composition and composite restored]** · S-TC buy-side number retracted in
review (exploratory diagnostic; n=4) · ledger coverage 86.2% → 97–98% measured post-#60 · the
OXY order was CANCELED pre-open (never filled) — the #253 pairing fix records such cases as
censored observations · sizing-fidelity KPI defined (S-FRAC §7): |realized−target|/target,
baselines 100% drop / ≈190% A-3 overshoot / ≈11% undershoot.

### New standing item

S-FRAC (fractional v2, operator-reopened 2026-07-02) enters the SHORT tier: stage 0 active-path
contract (the `runner.py:1372` int() truncation is a live pre-existing defect) → stages 1–3 per
the merged design PR. Supersedes A-3's round-up when enabled; A-3 remains fallback.

---

## Dated addendum — 2026-07-03: V4 correction — C3 is UNADJUDICATED, not MISS; G106 composition and composite restored

Per §4's re-baseline rule (dated addendum, stated reasons, never silent edits). This is the
S-REL V4 reconciliation (a reconciliation of recorded adjudications, NOT a recompute — the C3
numbers were already recomputed twice under Codex review and are not in dispute).

### The conflict

The 2026-07-02 addendum above recorded, in its state-vector deltas:

> C3 = MISS (G106 now 2-of-3: C1/C2/C4; composite ≈0.35–0.45)

The governing measurement memo (`doc/research/2026-07-02-c3-residual-momentum.md`) records the
opposite adjudication, in its title and verdict block:

> VERDICT: UNADJUDICATED — substrate/provenance limitations, NOT a tested-and-failed MISS.

and, in its §10 consequence section:

> This run casts NO formal vote (neither GO nor a design-rule-5 recorded MISS) … C3 remains
> OPEN pending either: (a) a rerun on genuinely point-in-time regime labels and universe
> membership … or (b) an explicit operator/design decision to accept this substrate as a
> permanent limitation and re-adjudicate C3 under an amended, honestly-scoped protocol.

### The ruling: the memo governs

The memo is the evidence source of truth; this plan is a consumer of verdicts, never their
origin. The memo did not declare the mechanical MISS binding — it explicitly withdrew it
("the prior round's 'C3 resolves as a recorded MISS' language is withdrawn", §10): the
mechanical rule output was computed on a substrate (replayed regime labels + a fixed 2026
survivorship universe) that is not point-in-time, so the confirmatory test the M-SIG spec
calls for was never actually run. A MISS presumes a validly-run test that failed its bar;
that is not what happened. **The honest recorded state is UNADJUDICATED-pending-clean-
substrate. The 2026-07-02 delta line is corrected accordingly (marked in place above).**

### Corrected G106 composition

- **C3 is OPEN (unadjudicated), not dead.** The #230 §8.3 probability calculus returns to its
  published basis: **≥2-of-4 candidates** (revisions, quality, residual-momentum,
  down-cap-derived) at individual P ≈ 0.4–0.5 each with the correlated-failure haircut — NOT
  2-of-3 with C3 removed.
- **The M-SIG Bonferroni family is unchanged on either reading**: per the spec (§2a), the
  voting family is {C2, C3, C4} at k=3, frozen at spec time; per-candidate α = 0.05/3 is
  spent per candidate and is not re-derived when a candidate resolves.
- **The corrected line also removes a second error**: the 07-02 delta named the surviving
  vote as "2-of-3: C1/C2/C4". C1 never votes (M-SIG spec §1.1/§2a/§3 — informative-only,
  excluded from the stack vote). Had C3 truly been a MISS, the stack vote would have fallen
  to **2-of-2 on C2/C4** — a strictly harsher composition than the one recorded. The line
  was wrong in both directions at once: too pessimistic on C3, too optimistic on the
  remaining family.

### Corrected composite (recomputed from the plan's own per-channel priors)

Basis: #230 §8.3's stated per-channel prior — individual P ≈ 0.4–0.5 per candidate, ≥2-of-4,
correlated-failure haircut. Simple independent binomial, haircut applied after:

- **All four live (C3 pending, the corrected state)**: P(≥2 of 4) = 1 − (1−p)⁴ − 4p(1−p)³
  = 0.52 (p=0.4) to 0.69 (p=0.5); with the same-market correlated-failure haircut → the
  plan's published **≈0.45–0.50. RESTORED.**
- **Had C3 been dead (the 07-02 premise)**: P(≥2 of 3) = 1 − (1−p)³ − 3p(1−p)²
  = 0.35 (p=0.4) to 0.50 (p=0.5); haircut → ≈0.35–0.45 — i.e. the 07-02 arithmetic was
  internally consistent; only its premise (C3 = MISS) was unfaithful to the evidence.
- **Qualifier (stated, not priced)**: C3's individual prior now carries adjudication-
  feasibility risk on top of signal risk (see disposition below), so the honest read sits at
  the lower edge of the restored 0.45–0.50 band. No new number is invented here; the
  published band stands.

### C3 disposition (what would adjudicate it)

Per the memo's §10, either path casts C3's formal vote:

- **(a) A genuinely point-in-time rerun** — PIT regime-label history + PIT universe/delisting
  membership. Neither exists anywhere in this codebase (memo §6/§7 search: no
  production-emitted regime-label history, no PIT universe/delisting data); building them is
  a materially larger data-engineering task (a walk-forward regime model retrained per
  historical date + a reconstructed historical universe), not a quick fix.
- **(b) An explicit operator/design decision** to accept the current substrate as a permanent
  limitation and re-adjudicate under an amended, honestly-scoped protocol.

**V4 decision on scoping the PIT rerun: NOT worth a dedicated near-term task.** The
exploratory read is discouraging — conditioned placebo-clean IC ≈ −0.0040 vs the +0.015 bar
(the naive +0.0253 bull-cell IC is entirely explained by its +0.0275 placebo), and the only
positive lever (conditioned-minus-unconditioned +0.0086) has every CI spanning zero. Spending
a large data-engineering budget to confirmatorily adjudicate a candidate whose best
exploratory point estimate is below zero has poor expected value. The S5/S8 ledger (the
spec's intended substrate) accrues PIT-quality data by construction, but it began collecting
June 2026 and cannot reach the n≥600 daily-decision-date floor by 2027-Q3 — per M-SIG §3's
missing-data rule, C3 then resolves **INCONCLUSIVE** (excluded from the stack denominator;
not a KILL, and not a MISS) unless path (a) or (b) happens first. Planning consequence,
stated honestly: absent an operator path-(b) decision, the likely 2027-Q4 stack vote is over
C2/C4 needing 2-of-2 — the plan should anticipate that harsher composition rather than the
mis-recorded "2-of-3 with C1 voting".

### Ledger

`doc/research/VERDICTS.md` (S-REL PR #265, unmerged at this writing) carries the C3 row that
flagged this conflict; its V4 pointer resolves to this addendum on rebase.

---

## Dated addendum — 2026-07-03 (dawn): the alpha-frontier synthesis after the measurement burst

Per §4 (dated, reasons stated, no silent edits). This addendum records what the 2026-07-02/03
measurement burst — 6 pre-registered verdicts + 6 adversarial verifications (S-REL) — did to
the plan's strategic geometry. Every input below is a merged-or-open PR with committed evidence.

### The evidence table (all S-REL-audited or S-REL-native)

| Channel | Verdict | Verification | Net position |
|---|---|---|---|
| Track A (conditional picking, S9) | NULL — 0/3 candidates pass the frozen 5-gate | UPHELD (#263, exact reproduction; kill distance 9.5pp) | DEAD on this corpus |
| Breadth waves (M8) | NO-GO, decisive (−0.048 vs −0.010 band) | UPHELD (#264) + interpretive correction: dilution is similarity-specific, random waves near-pass | waves STOP; BR only via D3 |
| M-SIG C2 (quality) | NON-VOTING (precondition unmet by −0.02% vs +20% bar; clean IC ≈ −0.0005) | S-REL-native (3 positive controls) | dead + its only reopening route measured-closed (#275) |
| M-SIG C3 (residual momentum) | UNADJUDICATED (non-PIT substrate) | V4 reconciliation (#268) fixed the ledger's double error | open, low-priority (exploratory read negative) |
| M-SIG C4 (trend-scan) | INCONCLUSIVE ×3 seeds; deployment-era edge ≈ nil; BULL_VOLATILE mechanical KILL | S-REL-native (GO and KILL branches both proven live) | open but power-limited; not fundable at current n (#278) |
| M-SIG C1 (revision drift) | pending by design | — | the PIT clock matures ~2027-01 (started 2026-07-02) |
| M3 haircut | AC FAIL → V3: strong claim OVERTURNED as statistics, weak claim UPHELD | WEAKENED (#269) | config change stays blocked; per-name uncertainty band is the true prerequisite |

G106 arithmetic after this burst (V4-corrected 2-of-4 family): resolved GO = 0; the #278 memo
estimates P(≥2 GO by 2027-Q4) ≈ 0.01–0.03 under current protocols. G106 tracks its kill branch
unless a pre-registered reopening lands (4 routes stand in the M-SIG spec §13).

### What this does NOT mean

Not "the program failed" — the program did exactly what it was built to do: it measured the
alpha hypotheses honestly and they came back empty ON THIS DATA at THIS breadth/cost scale.
The #230 route analysis anticipated this branch explicitly (§9.2's ladder). The distinction
matters: an unmeasured belief in alpha would have kept burning capital on thin-margin
contrarian picks (the OXY class); a measured empty is an asset.

### The re-weighted frontier (where marginal effort now goes)

1. **EXEC lane (the controllable win)** — S10's true-VWAP cohort accumulating; the Phase-−1
   finding stands (returns accrue overnight; cut the entry leak, don't chase intraday alpha);
   105 Stage-1 shipped across all three repos — the shadow-session clock (§9.3 K=5) starts on
   install. This lane's wins are engineering-certain, not hypothesis-contingent.
2. **PROCESS lane** — the 07-03 P1 incident (silent scorer rollback, #274/#437/#277) is the
   argument from reality: a 0.05-IC model gains nothing while the machine can silently run
   the wrong booster for 7 days. Identity monitoring, fingerprint unification (M6 stage-0/2),
   S-REL verification discipline: these compound.
3. **D3 down-cap (Term BR, the one live model decision)** — M8's verified verdict + the
   random-wave near-pass hint make the D3 synthesis memo the next model-side deliverable;
   its decision space now includes "shrink to the high-separability core" with real evidence.
4. **C1 + calendar patience** — the only alpha channel with an untested, theoretically-sound
   mechanism; its clock runs regardless. No new alpha hunts are funded before C1 resolves or
   a pre-registered reopening triggers (the discipline that killed re-pitching).
5. **Sleeve (deployment)** — S7 shipped; the cash-drag fix does not depend on any alpha
   hypothesis. Enable path per RS-1 §4.

### Fallback-ladder position (honest)

On today's evidence the book is one rung above "execution-only + benchmark-sleeve" (#230
§9.2). The rung above (full 107 with in-house alpha) requires C1 or a D3-core showing
genuine separability. This is the position to hold with patience, not to escape with
unfunded hypothesis hunts: the ladder was pre-registered for exactly this reading.
