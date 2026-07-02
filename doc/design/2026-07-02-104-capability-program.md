# Design: 104 capability program — cash-drag remediation, prioritized experiment backlog, structural refactor candidates, and an evidence-bounded alpha program

STATUS: design / RFC for review (docs only — no code, config, broker, risk-cap, or sizing change in
this PR). Describe → discuss → Codex + operator review → then per-item config/implementation PRs.
DATE: 2026-07-02
OPERATOR DIRECTIVES (2026-07-02): (1) solve the cash drag; (2) consolidate every open problem from
this review cycle into ONE prioritized experiment/design program and file it for discussion;
(3) enumerate 104's structural problems that warrant refactoring; (4) **alpha is wanted** — the
operator is explicitly dissatisfied with current model capability; the program must contain an
alpha track, bounded by the evidence discipline already learned (MVP-alpha-first, no validation
cathedrals, no re-pitching settled NULLs).

Companion records: PR #223 (design-review amendments, merged), #210/#212/#213 (freshness
governance + monitors), #208 (renquant105 RFC), the 105 direction decision (06-28), and the
2026-07-01 OXY buy forensics (decision-tree review; run `2026-07-01-live-01c54b39`).

---

## 1. Cash drag — diagnosis and a three-lane remediation design

### 1.1 Diagnosis (measured, 2026-07-01 run)

PV $10,806, cash $8,140 = **75% idle**, 6 positions, `cash_reserve_pct = 0` (the config *wants*
full deployment — the idleness is plumbing, not policy). Contributing causes, ranked:

| # | Cause | Evidence | Class |
|---|---|---|---|
| 1 | **Redeployment throttle**: `panel_buy_top_n = 3` per session × small per-name targets (~3%) → observed deploy rate ≈ 1 buy ≈ $336/session → **~24 sessions to redeploy $8.1k** | 07-01 funnel: 14 candidates → 1 buy; target 3.1% | plumbing |
| 2 | **QP cash-drag penalty is OFF**: `qp_cash_drag_lambda = 0` in the pinned config while the solver's own default is 0.05 — the QP is told idle cash costs nothing | `portfolio_qp/tasks.py:2042` (`cfg.get("qp_cash_drag_lambda", 0.05)`), pinned config `= 0` | config |
| 3 | **Whole-share block on high-price names**: 3% target ($324) < 1 share of BLK (~$1.1k) → `size_insufficient_cash` → selection drifts toward LOW-PRICE names (OXY $48 partially won *because* it is cheap) | 07-01 funnel: BLK blocked; OXY bought | structural artifact |
| 4 | **Multiplicative sizing stack**: Kelly (7.3%) × conviction (0.50) × σ-mult (0.87) ≈ 3.1% vs the 12% BULL_CALM cap — three shrinkage factors compound with no floor | OXY trade row | design |
| 5 | **Post-freeze backlog**: weeks of frozen universe (0 candidates) accumulated sell proceeds; the throttle (cause 1) then makes recovery take a month | tournament staleness episode, unfrozen 06-30 | transient |

**Diagnosis vs. treatment — these five causes are RANKED CANDIDATE HYPOTHESES, not a confirmed
root-cause attribution.** A single observed symptom (75% idle cash) is consistent with any one of,
or some combination of, causes 1–5; the ranking reflects which mechanism looks most consistent
with the 07-01 funnel evidence, not a proof of which throttle actually binds. Lane A's per-item
isolated experiments below (§1.2) are how attribution actually gets tested — each cause's proposed
fix is validated independently against its OWN acceptance gate, not assumed correct because it is
ranked first.

The honest constraint on ALL of this: the model has **no standing WF validation** (the gate cannot
render a verdict until Fix-1/2/3 land), so "deploy more per name into single stocks" is not
automatically +EV. The remediation therefore has three lanes with different risk profiles — lane A
removes NON-economic blockers, lane B parks idle cash in beta (no stock-picking edge required),
lane C is the honest expectancy question.

### 1.2 Lane A — mechanical de-throttling (config-level experiments; no new contracts)

Per the check-existing-contract rule, every item below tunes an EXISTING knob — nothing new is
invented. **Each item is tested in ISOLATION: one parameter change at a time, factorial design,
against a FIXED admission universe held constant across every variant being compared — never
bundled into one combined rollout, so any measured effect can be attributed to that specific
change.** In addition to the item-specific acceptance criterion below, EVERY Lane A experiment is
gated on non-degradation of: turnover/cost (round-trip count and realized cost proxy do not rise
beyond a pre-registered tolerance), concentration (sector/single-name concentration caps still
bind identically), and drawdown (no worse realized/measured drawdown than the baseline window) —
deployed-fraction rising is necessary but never sufficient on its own.

- **A-1. `qp_cash_drag_lambda` 0 → solver-default 0.05** (or a swept value). Experiment: shadow
  replay N sessions (the #195 harness pattern) comparing target weights with λ ∈ {0, 0.02, 0.05}
  ONE AT A TIME (A-2/A-3/A-4 held at their current values for this experiment); acceptance =
  deployed fraction rises without forcing entries past conviction/veto gates (the QP deploys only
  among ALREADY-admitted names — the gate stack is unchanged) AND turnover/cost, concentration,
  and drawdown stay within tolerance. This knob exists precisely for this; someone set it to zero
  (recover the rationale from git blame before flipping).
- **A-2. `panel_buy_top_n` 3 → 5–6** (bounded by `max_positions_per_sector = 6` and the correlation
  gate). Experiment: decision-ledger A/B over ≥20 sessions, A-1/A-3/A-4 held fixed — count
  executable candidates blocked purely by the window; acceptance = deploy-rate rises with no
  admission-quality decline (the same gates still bind; only the *window* widens) AND
  turnover/cost, concentration, and drawdown stay within tolerance. Also directly reduces the
  "third-choice-by-default" effective-bar collapse seen in the OXY case.
- **A-3. Whole-share floor for high-price names**: allow a 1-share purchase when
  `share_price > target_notional` AND 1 share ≤ min(max_position_pct × PV, available headroom) —
  i.e., round UP to one share within caps instead of dropping the name. Removes the
  selection-by-share-price artifact (BLK vs OXY). `min_share_floor` machinery already exists in
  the QP for held names; this extends it to initiation. Fractional shares remain CLOSED per the
  2026-06-30 operator decision — this is the cheap non-fractional subset. Tested with A-1/A-2/A-4
  held fixed; acceptance = the selection-by-share-price artifact measurably shrinks (BLK-class
  names admitted at comparable rates to cheap names) AND turnover/cost, concentration, and
  drawdown stay within tolerance.
- **A-4. Sizing-stack floor**: introduce a floor on the compounded shrinkage (e.g., final target ≥
  max(2%, 0.4 × Kelly)) OR re-derive conviction scaling so it does not double-count σ (σ already
  divides Kelly AND multiplies again via sigma_mult). Needs a ledger study first (see C-1) — do
  NOT hand-tune without evidence. When run, tested with A-1/A-2/A-3 held fixed, same
  turnover/cost/concentration/drawdown non-degradation gate.

### 1.3 Lane B — benchmark parking sleeve (a real beta position, not a cash substitute)

**Design**: idle cash above a small operational reserve (proposed: reserve = 5% PV + open-order
headroom) is swept into a **benchmark sleeve** (SPY — already in the watchlist/data plane), and the
sleeve is sold FIRST to fund any admitted single-name buy. Rationale: the book's benchmark is SPY;
un-deployed cash is a structural short-SPY bet that has cost the book most of its measured
underperformance vs benchmark; parking converts "75% idle" into "75% benchmark" so stock-picking
capability is the ONLY live bet.

**Correction (Codex review): the SPY sleeve is NOT cash-equivalent — it is a large, real equity-beta
position, and an earlier draft of this section contradicted itself by calling it "cash-equivalent"
in the same breath as noting it raises book beta from ~0.25 to ~1.0.** Something that roughly
quadruples market-beta exposure is emphatically not cash. The sleeve MUST participate in every risk
control that governs real positions, even though it is excluded from single-name ALPHA RANKING
(it never competes for a "best pick" slot — that exclusion is legitimate and unchanged):

- **Total-book beta**: the sleeve's full beta contribution (~1.0 for SPY) is included in the
  book-level beta calculation, not netted out or ignored.
- **Gross/net exposure**: sleeve notional counts fully toward both gross and net exposure limits.
- **Concentration**: the sleeve is a real, large single-position concentration in SPY and must be
  checked against whatever concentration ceiling governs any other single holding of comparable
  size — it does not get a "it's the benchmark" exemption.
- **Drawdown**: sleeve mark-to-market losses count toward book-level drawdown triggers exactly like
  any other position's losses.
- **Liquidity**: the sleeve is assumed liquid (SPY is highly liquid), but that assumption is stated
  explicitly, not implied by exemption from other liquidity checks.
- **Liquidation / funding rules**: when the book needs to raise cash under stress, the sleeve is a
  normal, sellable position subject to the SAME liquidation-priority and funding rules as any other
  holding — it is not an untouchable cash-like reserve. (It IS sold first to fund an admitted
  single-name buy under normal operation, per the design above — that ordering rule stays, but is a
  distinct thing from being "cash-equivalent" for risk-accounting purposes.)
- Regime interaction: the sleeve follows the regime gates — BEAR (`cash_reserve_pct = 1`) sweeps
  the sleeve OFF (to cash), preserving the defensive semantics; CHOPPY/BULL_VOLATILE reserve
  percentages apply to the sleeve size.
- Excluded ONLY from single-name alpha ranking and the panel-exit's alpha-driven rotation logic
  (it is not a stock pick and does not compete with one) — but IS margin/settlement-aware (sell T+1
  settlement precedes buy funding — verified margin account makes same-day re-use viable).
- Wash-sale: SPY sleeve trades can wash-sale against nothing in the current book; note the rule
  anyway for the ledger.
- Risk framing for the operator: this raises book beta from ~0.25-equivalent to ~1.0 — it is a
  RISK DECISION (recorded), not a pure optimization. The alternative parking (short-duration
  T-bill ETF, e.g. BIL/SGOV) keeps beta ~0 and only harvests carry; offer both in the config.
- **Authorization bar (corrected — a plumbing check cannot authorize an economic risk change).**
  Before ANY real capital is exposed via this sleeve, a **pre-registered replay/shadow comparison**
  of at least three candidate treatments — (a) plain cash (current baseline), (b) a short-duration
  Treasury sleeve (BIL/SGOV), (c) the SPY/benchmark sleeve — covering: beta contribution, drawdown
  behavior, turnover, tax treatment (short-term realized gains from frequent cash-drag rebalancing
  vs. a more buy-and-hold-ish sleeve), settlement mechanics, and STRESSED sell-to-fund behavior
  (what happens to the sleeve's value/liquidity precisely when the book needs cash during a
  drawdown — the worst-case correlated scenario, since SPY tends to be down exactly when the book
  most needs to raise cash defensively). Completing this comparison is a PREREQUISITE for capital
  authorization, not an optional nicety. A separate 10-session shadow log MAY still run first, but
  validates ONLY operational correctness (does the sweep/fund plumbing work mechanically) — it does
  NOT, by itself, authorize the sleeve's real economic exposure; that requires the pre-registered
  comparison above plus an explicit, separately recorded capital-authorization decision.

### 1.4 Lane C — the expectancy question (evidence-gated)

Whether MORE per-name deployment is +EV is exactly what the broken validation machinery cannot
currently answer. Lane C = the P0 items of §2 (gate repair + ledger wiring + Track A). Until they
land, lanes A/B fix the drag **without** raising single-name risk beyond what the gates already
admit.

---

## 2. The prioritized program (everything from this review cycle, one table)

P0 = unblocks everything else or is time-irreversible; P1 = direct capability/expectancy; P2 =
structural; P3 = staged/downstream. Every item names its experiment and acceptance criterion.

| # | Item | What / experiment | Owner repo | Acceptance |
|---|---|---|---|---|
| **P0-1** | **PIT estimate-revision accumulation (#205)** — TIME-IRREVERSIBLE | Unblock the snapshotter (base-data ownership + scheduler); start appending daily PIT revision snapshots NOW; every month of delay is a month of unrecoverable history | base-data + umbrella ops | snapshots appending daily with liveness alert (the #212 cadence pattern) |
| **P0-2** | **FMP Starter subscription ($29/mo)** | Unlocks full fundamentals coverage + 5y history + 300/min (free tier is ~30% plan-locked); feeds P0-1 and A-track scans | operator (spend) | harvest coverage report ≥95% of watchlist |
| **P0-3** | **WF-gate repair (Fix-1/2/3 of #210)** | sim artifact path unification; scorer-kind parity vs the active `xgb` primary; placebo **difference** test (`real − placebo > margin`) replacing the absolute ceiling | backtesting/model | the gate renders a verdict (pass or fail) on the live primary — first verdict since 05-18 |
| **P0-4** | **Decision-ledger wiring (#133/#190)** | Persist per-(date,name) raw + mu + er + fwd outcomes from the live path; backfills the validation substrate for demean #145, momentum-guard #187, sizing-stack C-1, and every future config experiment | pipeline + orchestrator | ledger accrues daily; `decision_outcomes` queryable for any run |
| **P1-1** | **Cash-drag lane A** (§1.2: λ, top_n, whole-share floor) | three SEPARATE, SEQUENTIAL, one-change-at-a-time config experiments (never enabled simultaneously) — see §1.2 for the isolation/factorial design and per-item gates | strategy-104 config + pipeline | each item's own acceptance (deployed fraction + turnover/cost + concentration + drawdown non-degradation, §1.2); no combined/bundled bar |
| **P1-2** | **Cash-drag lane B** (§1.3 parking sleeve) | operator risk decision + 10-session shadow of sweep plumbing | strategy-104 + pipeline | idle cash ≤ reserve; sweep/fund round-trip clean |
| **P1-3** | **Track A regeneration PR + conditional pick-quality test** | the committed OOS pick table (`regen_oos_pick_table.py` → `data/exp/oos_pick_table_recipe_v2.parquet`) then the pre-registered meta-label conditional test (direction-decision §4, criteria UNTOUCHED) | orchestrator + umbrella (read-only) | table committed + test verdict rendered (GO or NULL, either recorded) |
| **P1-4** | **Retrospective open-auction IS measurement** | from the ledger's own historical fills: what did next-open entry cost vs same-day VWAP/close references? Sizes the 105 Stage-1/2 prize BEFORE more build | orchestrator (read-only) | a bps/trade estimate with CI; feeds the 105 §9.4 prereg |
| **P1-5** | **Run the 105 collectors** (#215/216/220/221 merged but must RUN) | launchd + cadence-lapse alerts per the #212 pattern; 105 is DATA-BOUND until these run | umbrella ops | daily collector output accruing with liveness alert |
| **P2-1** | **Conviction floor uncertainty haircut** | design: `mu_floor` compared against `mu − k·SE(mu)` (or the calibrator's band) instead of point mu; the OXY case passed by a thin 24% margin with no uncertainty penalty | strategy-104 + pipeline | ledger replay shows the haircut removes thin-margin losers ≥ winners |
| **P2-2** | **BL-1 calibration recentering** (`sign_laundered = 44/90`) | recenter the raw-score distribution so the calibrator stops mapping bearish raw to positive ER at scale; telemetry already exists (BL-2 counter); the signal-direction gate (BL-4) is the interim guard | model + pipeline | sign-laundered count → single digits |
| **P2-3** | **Structural refactors R1–R4** (§3) | per-item RFCs | various | see §3 |
| **P3-1** | **Cluster-wave breadth expansion** (E34 resume condition) | +~100 tickers/wave, cluster-based admission (top-IC per sector bucket), per-wave IC non-degradation gate before the next wave | model + strategy | wave-1 IC ≥ baseline − noise band |
| **P3-2** | **Down-cap MVP screen (Track B pilot; operator authorization)** | READ-ONLY cheap screen per the operator's own MVP-alpha rule: build a small/mid-cap panel (e.g. liquid R2K subset, ADV floor), run the existing sighunt/fundamentals scans + placebo; measure whether canonical anomalies (documented strong in small-caps) actually show up at OUR cost assumptions BEFORE any structural commitment | model (read-only) | a go/no-go evidence memo; NO production change |
| **P3-3** | **105 Stage-1 build → Stage-3 residual modeling** | per #208 §8 order, after P1-4/P1-5 data | execution → pipeline → orchestrator | #208 §9.3 operational acceptance |

Sequencing: P0-1/P0-2 this week (irreversible + cheap); P0-3/P0-4 are the critical path for
everything evidence-gated; P1-1/P1-2 deliver the operator-visible cash-drag fix inside a month;
P3-2 is the highest-expected-value ALPHA item but needs operator authorization since it points at a
structural universe change.

---

## 3. 104 structural refactor candidates (discussion)

Ranked by (risk removed × ongoing cost removed) / migration risk:

**R1 — Retire or replace the per-ticker tournament as the universe-admission gate.** The legacy
RL-Q-table/RF/per-ticker-XGB tournament (142 artifacts) gates buy admission via `trained_date`
staleness, yet its predictive contribution is unvalidated, it has NO acceptance gate of its own,
its retrain is timeout-fragile (froze the whole book for weeks; the 06-30 61d episode), and it is
the single largest source of freshness incidents. Design: admission derives from the panel scorer's
coverage + data-health (a name is admissible iff its features are fresh and the panel scores it) —
one model population instead of two. Migration: shadow the panel-based admission set against the
tournament set for N sessions in the ledger; cut over when the delta is understood; keep the
tournament read-only for one quarter as rollback. This eliminates an entire model population's
freshness/monitoring/retrain surface (#210 §1A machinery becomes unnecessary).

**R2 — Unify the triple-implemented content-fingerprint.** Three hand-copies of
`model_content_sha256` (runtime/pipeline vs calibrator-fit/model vs umbrella-local) hash different
field sets → recurring fail-closed no-trade incidents (05-27, 06-22, 07-01). One shared
implementation, imported everywhere; the re-stamp scripts become thin wrappers.

**R3 — Calibration/mu semantics** (with P2-1/P2-2): one documented contract for what `mu` means
(post-calibration, post-demean?, clipped, horizon), an uncertainty band carried alongside the
point estimate, and the recentring so downstream floors compare like with like. Today three
counters (`sign_laundered`, demean monitored-exception, veto) each patch a symptom of the same
undefined contract.

**R4 — Selection/sizing machinery**: the top_n window, whole-share drops, and the multiplicative
shrinkage stack (§1.1 causes 1/3/4) are one subsystem conceptually but live in three places.
Refactor into a single explicit "selection budget" stage whose inputs (window, floors, caps) are
config-visible and whose drops are ledger-logged with reasons (the OXY forensics required joining
three sources to reconstruct why BLK died).

**R5 — Decision ledger as a first-class output** (= P0-4): every gate/selection/sizing decision
writes its inputs and reason; the decision-tree-review skill then reads one substrate instead of
scraping logs + DB + config.

**R6 — Generated state docs + deploy SOP** (accepted in #223 A6; umbrella follow-up): the
production snapshot is machine-generated; merged→pinned→synced→verified becomes a checklist with
an audit line in the daily log (the 07-01 run ran with "newer pins NOT deployed" as a silent WARN).

**R7 — Durable PRs for live-tree hotfixes**: origin/main still ships the adapter-save NameError
that exists only as an uncommitted live-tree patch; any recovery checkout re-breaks production
(it already did once, 06-25/26). Inventory live-tree dirt → commit or discard each item.

Explicitly NOT proposed: model-architecture replacement (E27/E33: linear beats transformer at this
scale; PatchTST stays shadow), fractional shares (operator-closed 06-30), multi-horizon sleeves,
neutralization, regime-split panel-exit (all settled NULLs — not re-pitched).

---

## 4. The alpha track, honestly framed

The operator wants alpha. The evidence says: the current information set (142 US large-caps ×
price-derived features × fwd_60d) shows no robust edge under this cycle's diagnostic suite — four
honest NULLs on independently-scanned single factors (momentum, regime-conditioned momentum,
value/quality/growth, PEAD/minute — `sighunt.py`/`robustness.py`/`regimemom.py`/
`fundamentals_scan.py`, durable committed evidence), every factor combo dominated by a
regime-artifact momentum factor, and architecture swaps change nothing (E27/E33). **The live
model's own directional skill in the dominant BULL_CALM regime is a SEPARATE, UNRESOLVED
question, not part of the above.** The originally-cited "genuine (leak-controlled) IC ≈ −0.003"
("a coin flip") has NOT been confirmed by a durable reproduction: `hallovorld/RenQuant#431`
(open, unresolved) reproduces **+0.044** on the best-available committed proxy methodology instead
— sign-disagreeing with the original figure — with a **proposed, not-yet-frozen** reconciliation
protocol (Algorithm B and the adjudication slice remain open choices as of this writing) to decide
between them. Any alpha-route conclusion below that depends specifically on the
model's own BULL_CALM skill (as opposed to the four independently-scanned factor NULLs, which
stand on their own durable evidence regardless of #431's outcome) is **BLOCKED pending that
reconciliation** — this program does not pick a side. The alpha budget therefore goes to
**changing the information set**, cheapest-first, each step MVP-screened before any build:

1. **P0-1/P0-2 (data substrate)**: PIT revisions + full fundamentals — the only inputs that accrue
   value with calendar time regardless of which path wins.
2. **P1-3 (Track A)**: not new alpha — precision on the existing signal — but it is the only lever
   that can raise live expectancy THIS quarter, and its regeneration PR doubles as the durable
   evidence base for the whole 105 direction.
3. **P3-2 (down-cap MVP screen)**: the literature-supported home of cross-sectional alpha; a
   read-only screen prices the opportunity in days, without committing the book. If the screen is
   null at our costs, Track B's universe half is falsified cheaply; if it is not, THAT is the
   structural conversation worth having.
4. **P3-1 (cluster-wave breadth)**: the disciplined version of "more tickers" that E34's verdict
   permits.
5. **105 Stage-3 (intraday features)**: the only place a sequence model has a data-scale advantage
   — after the engineering scaffold and only on the execution-timing-residual estimand.

What is deliberately absent: any new factor scan on the current panel (NULL four times), any
deep-architecture bake-off (E27/E33), any validation cathedral ahead of a candidate signal
(operator's own 2026-06-28 rule).

---

## 5. Open questions for the operator

1. **Lane B risk decision**: parking sleeve in SPY (beta ≈ 1) vs T-bill ETF (carry only) vs no
   sleeve? This is the largest single lever on measured drag and is purely a recorded risk choice.
2. **Spend authorizations**: FMP Starter $29/mo (P0-2); SIP feed for 105 pilot (from #223 A5.3).
3. **Lane A appetite**: OK to run the λ/top_n/whole-share experiments while the model is still
   unvalidated (they deploy more capital through UNCHANGED gates), or hold lane A until P0-3's
   first gate verdict?
4. **R1 (tournament retirement)**: appetite for removing the legacy admission population entirely,
   given it requires a shadow-migration quarter?
5. **P3-2 (down-cap screen)**: authorize the read-only small/mid-cap screen now, or after Track A
   renders its verdict?
6. **Priority confirmation**: does the P0–P3 ordering match operator intent (cash-drag lanes A/B
   inside a month; alpha budget on information-set change, not architecture)?
