# renquant105 intraday system — design proposal

2026-06-27.

> ## ⛔ CURRENT STATUS (supersedes the framing below) — H1 INTRADAY-ALPHA: PARKED
> **Phase -1 (PR #199) MEASURED the load-bearing σ_oc and the net edge is NEGATIVE at plausible
> IC** (σ_oc 152.5 std / 114-115 robust bps vs 220-367 breakeven; net −6.4 @ IC 0.03 / −3.4 @ IC
> 0.05). The H1 intraday-ALPHA stack (M1 → M2 → M3) is **PARKED** (reversible — un-park only on
> concrete IC ≫ 0.05 evidence; not deleted). The **ACTIVE path is the defensible residual: M0
> dual-use data + H2 execution-timing on the 104 book + the reliability/safety fixes** (none
> require cost-clearing alpha). The earlier "UNDETERMINED / marginal prior" framing in this doc is
> the *superseded hypothesis* Phase -1 rejected. See master §0 banner + the Revision 6 log below.

## What & why
Operator asked for a complete, professional, scientific design for an INTRADAY
trading system (renquant105) on the ~$10.6k Alpaca account: how to train the model,
get intraday data, decide; whether data/model/logic must change; speed/GPU; stricter
gating for unreliable trades; expected trade-count rise. This PR is the **design
proposal for Codex review** — no code.

## How it was grounded
Five parallel read-only research sweeps (regulatory/cost feasibility, 104→105 delta,
intraday data/latency, intraday model/training/GPU, stricter trade-vetting) + a
direct live-account check. All read-only; no git in the live tree.

## Headline findings (these shape the design)
- **PDT is gone (verified):** the $25k/3-trade rule was eliminated 2026-06-04; the
  live account shows `pattern_day_trader=False`, 4× intraday BP $37.7k. Regulation
  is no longer the blocker — **economics (cost vs tiny intraday edge) is.**
- **Not greenfield:** the intraday data + feature + model-swap infrastructure is
  already built and parked (disabled 2026-05-04). 105 is re-activation + an intraday
  model + tighter gates + a buy path.
- **No GPU needed; latency isn't the bottleneck.** The bottlenecks are IEX data
  coverage (~50% of universe lacks intraday history → liquid coverage-gated universe;
  $99/mo SIP only for live NBBO fills) and incremental ingestion.
- **QUANTITATIVE FEASIBILITY = UNDETERMINED (§A) — the §A numbers are parametric
  PRIORS, not measurement.** The edge identity `E[edge]=IC·σ_xs·factor` is a Gaussian
  scenario approximation (rank-IC treated as a Pearson coefficient), NOT an accounting
  identity, and the script holds no measured sample — so it cannot "demonstrate" a
  verdict. Unit-corrected (the round-1 bug used one 25-bps number as BOTH a 5-min-bar
  AND an open→close dispersion, which differ ~√78≈9×): **HIGH-frequency churn is
  unfavorable** (cost drag swamps any per-trade edge → rejected), but the **LOW-turnover
  open→close variant is marginal-to-plausibly-viable** at IC 0.03–0.05 and an open→close
  dispersion in the **assumed sensitivity range ~150–250 bps** (a PRIOR until M0 measures it;
  top-pick gross edge ≈ or > the ~11 bps cost; the corrected grid is 14/48 positive, not 0/36).
  So the program is: **MEASURE** the open→close variant in a cost-charged shadow harness (M1, on
  a MEASURED cost model, via the **frozen H1 policy replay** — finding 1) + intraday
  **execution-timing/risk** on the daily book (H2). Live intraday alpha stays OFF until M1's
  policy replay empirically clears net-Sharpe ≥1.0 + OOS IC ≥0.03 placebo-clean + PSR/DSR ≥0.95
  over a power/MinTRL-derived effective-N sample.
- **The decisioning is** a strict conjunctive fail-closed gate stack (cost-edge,
  conformal lower-bound, entry meta-label, CHOPPY no-trade, P&L circuit breaker →
  NO_NEW_RISK, top-k under scarcity), with a **kill condition** if the M1 measured
  net-of-cost edge isn't placebo-clean.

## Deliverable
- `doc/design/2026-06-27-renquant105-intraday-system.md` — the full design: honest
  feasibility verdict, what's reusable vs new, data/model/logic deltas, GPU verdict,
  the gate stack, shadow-first deploy, a validation-gated phased rollout with a kill
  condition, and the open decisions for the operator.

## Next
Label horizon is **RESOLVED** (open→close, intraday-only — no longer an open operator
decision); remaining operator confirmations are scoped (universe size/thresholds, SIP
go/no-go at M3, cost-edge k, kill condition, broker-contract gate). Then M0 (data + cost
instrumentation) implementation PR. Codex review on the reframed feasibility + the
validation/kill discipline.

## Revision 2 — Codex CHANGES_REQUESTED resolved (2026-06-27)
Codex (haorensjtu-dev) requested changes on PR #198 with 8 blocking findings + an
execution-plan-gaps section. Addressed substantively, not papered over:
1. **Feasibility reproducibility + math** — added `scripts/research_intraday_feasibility.py`
   (READ-ONLY, runnable; every number from explicit formulas with units: RT cost,
   `E[edge]=IC·σ_xs·factor`, cost-clearing horizon via the explicit `σ_cum(h)=σ_xs·√h`
   random-walk + independence assumption, Fundamental-Law net Sharpe, an IC×σ_xs×cost
   sensitivity grid, a block-bootstrap CI) + `tests/test_research_intraday_feasibility.py`
   (17 tests). Fixed the arithmetic: `11/(0.05·1.75)=125.7 bps` is the *required cumulative
   dispersion*, and the doc's "~3.6%/2.5-day" = the IC=0.03,k=1.75 cell (3.67%/2.76d), now
   derived. §A rewritten to cite the script as the reproducible artifact. **(NO-GO claim
   SUPERSEDED in Revision 3 — that result carried a unit bug; see below.)**
2. **One primary horizon** — standardized the whole suite on **open→close (intraday-only)**;
   every contract (label, embargo-in-bars/session-aware, cost, IC, hit-rate, killed-winner,
   shadow, DSR/PBO, attribution, monitoring) uses it; flagged daily `ticker_forward_returns`
   as insufficient → M0 builds a session-horizon return surface.
3. **Statistical bar + power** — DSR pinned as the probabilistic Deflated Sharpe (Bailey &
   LdP), require **PSR/DSR ≥ 0.95** (dropped vacuous "DSR>0"); defined the full trial
   universe carried into N; replaced raw run/date counts with a **power/MinTRL-derived
   minimum in effective-independent observations**; phase gates use CIs + effective N.
4. **Point-in-time M0 universe** — rewrote selection to as-of-date-only info (lagged ADV,
   listing eligibility, halt/delist, corp-action mapping, IPO seasoning, fail-closed
   missingness), frozen + fingerprinted per date; removed the look-ahead "complete history
   over the window" rule.
5. **Feed/cost provenance** — M0/M1 fingerprint feed/tier/venue/adjustments/bar-rule/
   retrieval; cost model from MEASURED arrival/quote/fill data (11 bps = explicit
   placeholder); historical-vs-live IEX parity asserted; SIP = fresh shadow parity/cost
   experiment before live.
6. **Triplication removed** — replaced "touch all 3 copies" with the pinned-subrepo
   ownership/paired-PR matrix (base-data owns the primitive, pipeline consumes the contract,
   umbrella pins), contract tests, pin order, compat-shim retirement; specified where
   `renquant-strategy-105` is created + the manifest/fingerprint flow.
7. **Kill-switch state machine** — defined `NO_NEW_RISK` (exits allowed) / `CANCEL_OPEN_ORDERS`
   / `FULL_HALT` (integrity only); daily-loss breaker → `NO_NEW_RISK` (NOT all-orders-off);
   pinned exit price authority + max staleness + broker/feed-disagreement behavior; made the
   loss threshold a consistent **−5%** across FMEA/metrics/M2/M3.
8. **Broker-contract milestone** — added **M0.5**: current `buying_power`/intraday-margin
   fields, rejection/deficit handling in paper/shadow, leverage caps independent of broker
   max, fail-closed on Alpaca field migration; stopped claiming "operationally clear" until
   encoded; caveated the verified live flags.
**Execution-plan gaps:** split H1 (intraday alpha) from H2 (execution-timing/risk) with
independent acceptance; defined the two comparators (pipeline parity vs strategy lift);
required per-gate ablations with multiplicity correction (gate proliferation ≠ validation);
added a minimum-live-sample + exposure-schedule ladder for M3 scaling; replaced off-PR
"research transcripts" with the committed script + primary references as the auditable inputs.

## Revision 3 — Codex ROUND-2 CHANGES_REQUESTED resolved (2026-06-27)
Codex's round-2 review showed the round-2 "demonstrated NO-GO" was **over-claimed** and
carried a **unit bug**. The verdict is NOT restored; it is reframed honestly. All 8 findings:
1. **UNITS (verdict-changing).** The script conflated a single-5-min-bar dispersion and the
   whole open→close dispersion (one `σ=25 bps` used both ways; they differ ~√78≈9×). Split
   into `sigma_xs_5m_bps` (25 bps; churn comparison only) and a measured/assumed
   `sigma_xs_open_close_bps` (~200 bps, band 150–250). The open→close edge is now computed
   from the open→close dispersion **directly (no √78 scaling)**. Added **dimensional/unit
   tests** that block horizon aliasing. **Corrected result is NOT 0/36:** at IC 0.03–0.05 /
   σ_oc~200 bps the top-pick gross edge (10.5–17.5 bps) is ≈ or > the ~11 bps cost; the
   sensitivity grid is **14/48 positive**.
2. **VERDICT REFRAMED.** The edge identity `IC·σ·factor` is a **parametric PRIOR** (Gaussian
   scenario approximation, rank-IC as Pearson), NOT an accounting identity, and the script has
   no measured sample (the bootstrap is unused) — it cannot "demonstrate" a verdict. Relabeled
   everywhere (master §A/§0, this doc, PR body, script docstring): **feasibility UNDETERMINED;
   suggestive priors, not measurement-grade evidence; only M0/M1 measured OOS data settles it.**
   Honest split: HIGH-freq churn unfavorable (rejected); LOW-turnover open→close marginal-to-
   plausibly-viable and worth measuring. "Demonstrated NO-GO" is NOT restored.
3. **Edge identity** labeled a parametric prior under explicit distributional assumptions; M1
   now estimates `E[return | score quantile]` directly from purged-OOS predictions (deferred
   to measured data) to replace the prior.
4. **Trading policy PINNED.** H1 = enter on any gated bar, exit at session close, ≤1 open
   position per name per session (bounded turnover, 0 intraday replacements); pinned decision
   timestamps, max entries/session, holding rule, overnight boundary, **turnover accounting**
   (1 round trip/name; book turnover = one rotation/day), per-decision label. The script
   (`H1Policy`) + M1 replay charge cost from the **stateful path**, not `rebalances=1`.
5. **Circular cost dependency broken.** Quote/arrival/fill capture + cost-model **calibration**
   moved into **M0** (104 fills + paper-order probes, no-live-risk), with a min sample by
   ticker × time-of-day × order-type + CI; M1 **consumes** the M0 cost model; the 11 bps
   placeholder cannot gate H1.
6. **Power/MinTRL** kept (formula + config schema + pre-registration-before-training; finding
   already in M1/§3).
7. **H2 kept + designed** — new milestone doc `…-H2-execution-timing.md`: data contract,
   comparator (104 next-open vs pre-registered timing policies on the SAME intents),
   arrival-price capture, opportunity cost for unfilled, paired-block inference, no
   selection/size change, explicit risk-exit semantics, promotion/kill criteria.
8. **Kill-state machine fixed.** `dd<−20%` → **NO_NEW_RISK + controlled flatten/reduce-only**
   (NOT FULL_HALT, which traps exits); FULL_HALT reserved for untrustworthy order-state/
   account-identity + liveness (deadman). Replaced **every** legacy `TRADING_OFF` in the
   reliability doc with a deterministic state + precedence + recovery authority, consistent
   across FMEA/§3/§4/§5/§6 and the metrics/M3 kill tables.
Also: removed DSR>0 / "40–80 dates" / horizon-as-operator-decision / WIP framing from the
progress doc + PR body. `py_compile` + `pytest` (23 tests incl. the new unit tests) green.

## Revision 4 — Codex ROUND-3 CHANGES_REQUESTED resolved (2026-06-27)
Round-3 confirmed the round-2 unit/verdict corrections held, and raised 6 new blocking
findings on whether the experiment is *executable and statistically identified*. All 6
addressed (DESIGN-level = spec text; CODE-level = script/tests):
1. **M1 estimand must match the pinned H1 policy (DESIGN).** Made the PRIMARY GO metric the
   **exact frozen H1 policy replay on NESTED outer-fold OOS predictions** (calibration + gate
   thresholds + policy selection fit ONLY inside each inner fold; outer fold replays the
   stateful path — session cap, no-reentry, barrier exits, exhausted capacity, cost charged
   from the realized path). Demoted `E[return|quantile]` to **diagnostic-only**. Added
   **replay/live parity contract tests** (timestamps, cap, no-reentry, barriers, cost) as a
   gating acceptance row. Edited M1 (F1.4b/F1.5/objective/acceptance/KPIs/deliverables) + master
   §0/§A.2/§A.4.
2. **M0 must OWN the calibrated cost model (DESIGN).** Made the calibrated cost-model artifact an
   explicit M0 deliverable + acceptance gate: stratified (ticker×ToD×order-type) estimator,
   **min-N per stratum**, **stratification fallback** for thin strata, **per-stratum CIs**,
   **out-of-sample calibration** check. Defined paper probes as **zero-live-capital** orders;
   reconciled the "no order" wording (M0 + M0.5 rejection-sequence probes are paper/zero-risk).
   Stated 104 next-open fills alone are **not H1-representative** → M0 gathers H1-representative
   probes. M1 **consumes** the artifact (11 bps is a placeholder that must NOT gate H1).
3. **Pre-register power/MinTRL + the M3 ladder (DESIGN).** M1 F1.7 now pins the **selection
   algorithm + an immutable pre-registration artifact** (target effect = Sharpe 1.0, α=0.05,
   power=0.80, return moments, block-length RULE, resulting N_eff) with a **fallback when
   required N exceeds available history → declare UNDERPOWERED / do-not-run / re-scope** (never
   shrink the bar). H2 gained a **family-wise α + multiple-comparison correction** across the K
   timing policies + **power vs a min economically-meaningful IS improvement** + a FIXED
   session-block rule. M3 now gives **exact 4-step exposure ladder, observation unit (live
   open→close session), min N=20 eff-indep sessions/step, max 6-month duration + the stop
   outcome**.
4. **H2 counterfactual fills (DESIGN).** Added H2.6: a **quote/trade-level replay + conservative
   fill model** (queue-position aware, partial-fill probability, executable-NBBO path,
   conservative impact), **calibrated on randomized/paper shadow orders**, **OOS-validated**,
   with **fill-model uncertainty propagated into the paired CI**, and a **KILL/GUARD** — if
   fills are not identified OOS, H2 does NOT promote (would be a simulator artifact).
5. **FULL_HALT must be operationally achievable (DESIGN).** Added reliability §3.9: the
   cancel/flatten on `FULL_HALT` is performed by an **out-of-process supervisor (`deadman_check`
   as a separate launchd job) and/or broker-side bracket/OCO + account-level control**, NOT the
   dead loop; a **credential/account guard** re-verifies the account BEFORE any cancel (so a
   wrong-account state can't cancel the wrong book); cancels are **idempotent**; positions stay
   covered by the **broker-side bracket** while in-process exits are paused. Updated F39, the
   kill-state table, §5 SLO, §6 blockers. Distinguished *intent* from a real *mechanism*.
6. **Script Sharpe-band label bug (CODE).** `run_feasibility()` computed `net_hi` with
   `max((*ic_band, 0.05))`, pulling the HONEST band's upper bound up to the optimistic IC=0.05
   (reporting −0.66). Split into **`honest_net_sharpe_band`** over `ic_band` ONLY (0.01→0.03 →
   **−1.30 to −0.98**; upper = 0.476−1.455 ≈ −0.98) and a SEPARATE **`optimistic_net_sharpe_ref`**
   (IC=0.05 → **−0.66**), reported distinctly in the script output, with new tests asserting the
   split. Replaced **"realistic"** with **"assumed sensitivity range"** for the 150–250 bps
   dispersion band everywhere (script + docs). Updated master §A.4, M1, this doc, the PR body.

Validation: `pytest tests/test_research_intraday_feasibility.py` → **26 passed** (23 prior + 3
new for the Sharpe-band split, plus formatter assertions added to the existing formatter test),
`py_compile` clean, `git diff --check` clean.

## Revision 5 — Codex HOLISTIC RFC-level review (18:13Z) resolved (2026-06-27)
A SEPARATE, system-level review (9 blockers) on top of the round-3 fixes — extends round-3, does
NOT duplicate it. All 9 addressed at the DESIGN level (spec text; the feasibility script needed
no change — none of the reconciled numbers are script outputs):
1. **Same-bar look-ahead → explicit EVENT-TIME CONTRACT.** Added the chain
   `bar_close_ts → data_available_ts → decision_ts → submit_ts → broker_ack_ts →
   first_eligible_fill_ts` (master §3 + M1 F1.1b); label/entry priced at the **first
   conservative next-executable quote/fill** (incl. decision latency), NEVER the closed-bar
   price; identical contract in training/replay/shadow/live; **delayed-entry sensitivity** +
   **hard parity test** added to M1; reconciled §A.2 (executable IC caveat). Sharpens round-3
   #1/#4. "Until fixed, M1 cannot measure tradable alpha."
2. **Milestone DAG cycle (M2↔H2).** Moved arrival-price + IS capture OUT of M2 into a new
   **independent H2.0** observability milestone (M0/M0.5-class; master §7.0 + M0 doc); published
   an **explicit acyclic DAG** (owners/artifacts/entry-exit) in master §7.0; M2 now CONSUMES the
   H2.0 IS module, H2 depends on H2.0+M0 (not M1/M2) — the cycle is broken.
3. **Gameable M0 coverage gate.** Added F0.1b two-stage universe: freeze `ELIGIBLE_d` from
   **LAGGED reference data only** (data-quality-blind denominator), measure coverage =
   `|TRADEABLE_d|/|ELIGIBLE_d|`, record the tradeable subset separately; require **as-of
   vintages** for corp-action/listing metadata + **raw-vs-adjusted bars** (a retrieval
   fingerprint does not stop later back-adjustment leakage). Updated N0.1/metrics/acceptance.
4. **Gate taxonomy (alpha vs safety).** Master §4 now classifies every gate
   `alpha/admission | portfolio constraint | safety invariant`; only alpha gates judged by
   nested-OOS ablation/marginal alpha; **safety invariants verified by fault injection +
   invariant/property tests + zero-tolerance incident SLOs and NEVER PnL-optimized** (M2 F2.6 +
   acceptance row).
5. **Parity must be EXACT.** M2 pipeline parity (champion-vs-itself) changed from "≥90% / ρ≥0.9"
   to **100% exact at the decision-contract level** (eligible universe, features/fingerprints,
   scores-within-tolerance, gate verdicts, sizes, intents), all allowed differences enumerated +
   reconciled; statistical thresholds kept ONLY for challenger-vs-champion strategy lift.
6. **Metric dictionary (single source of truth).** Added metrics §0: per-metric numerator/
   denominator/clock/annualization/benchmark/missing-rule/CI/action, thresholds DERIVED from the
   frozen policy + risk budget. Resolved the contradictions: **turnover** (the "<25% one-way"
   gate was WRONG for a 1-rotation/day policy → REMOVED; round-trip ≤1.0 pinned); **G1 k=1.75 ⇒
   cost/gross <36.4% per-trade + ≤30% aggregate** (replaces the inconsistent "<25%"); IC 0.03 /
   precision 0.55 / dd thresholds tied to ONE Sharpe-1.0 min-effect basis; all **alert windows
   defined**. Reconciled master §4 G1 (k=1.75) + §8.4.
7. **Risk limits matured for live capital.** Reliability §3.3b derives −5%/−20% from position
   caps × measured vol × gap risk (re-derived per ladder step), adds a per-order/per-symbol/
   per-session **exposure envelope**, a worst-case **gap/stale stress**; §3.10 adds
   **per-failure-class trigger latency**, broker-side open-order behavior, restart/reconciliation
   + fault-injection acceptance; **MTTH tied to the fastest decision cadence (≤ `bar_interval`),
   not a generic 30 min**. Wired into M3 precondition/F3.3 + metrics kill conditions + §6 blockers
   (12-13).
8. **Cross-repo RFC ownership.** Added master §6.1 "Ownership & authority": this PR is a SCOPED
   ORCHESTRATION design that **references**, not defines, the cross-repo topology; the
   authoritative change (new `renquant-strategy-105` repo role, forbidden imports, artifact
   contracts, pin/lock migration, rollback, integration test) is owned by an **umbrella ADR under
   `RenQuant/doc/arch/` that MUST land FIRST** — enumerated as a 6-item checklist. **This PR does
   NOT authorize the topology change and does NOT touch the umbrella.** (Flagged for the operator.)
9. **Bounded resource decision (Phase -1).** Added `doc/design/2026-06-27-renquant105-Phase-
   minus-1-cheap-feasibility.md`: a read-only, ≤5-analyst-day / ≤1-week, no-orders probe on
   EXISTING data measuring the causal open→close σ_oc (the number §A ASSUMES), coverage, breadth,
   and a conservative cost band, with a pre-registered STOP/GO; wired as the **FIRST gate** in the
   master DAG (before M0). STOP before building the full stack if history can't meet the
   pre-registered N_eff or the causal data contract.

Validation: `py_compile` clean; `pytest tests/test_research_intraday_feasibility.py` → 26 passed
(no script change — the reconciled numbers are doc-level, not script outputs); `git diff --check`
clean.

**Operator action item (NOT done in this PR):** umbrella **ADR #416** (the cross-repo topology,
finding 8) is **Deferred pending an alpha GO** — not created/executed while H1-alpha is parked.

## Revision 6 — REFRAMED per the Phase -1 MEASURED result + Codex round-4 resolved (2026-06-27)
Phase -1 (the FIRST gate this suite designed) was **EXECUTED** in orchestrator PR #199 (142-name
universe, 1258 sessions, read-only, no orders). It **measured** the single load-bearing assumption
§A only *assumed*, and the result refutes the marginal-alpha hypothesis:
- σ_oc = **152.5 bps std / 114-115 bps robust** (causal event-time check 200.2) — at/below the §A
  150 lower edge and far below the **220-367 bps breakeven** (σ_oc ≥ 220 @ IC 0.05 / ≥ 367 @ IC
  0.03, even at the 11-bps cost floor). **Net edge NEGATIVE at plausible IC** (−6.4 @ IC 0.03,
  −3.4 @ IC 0.05). Breadth 142/session; coverage **142/142, 0% missing (REFUTES the "~50% no
  history" disable-cause)**; cost ~11 bps (spread ~6).
- The literal "GO to M0" PR #199 printed was a **mis-specified-gate artifact** — the original
  Phase -1 gate checked σ_oc against its *own assumed 150 prior* (exactly Codex round-4 #2's
  circularity). Under the **corrected net-edge gate** it is a **STOP-for-ALPHA / data-foundation
  GO**.

**(A) Reframe (reversible park, content retained — NOT deleted):** added a prominent PARKED status
banner to the master spec §0 + M1 + M3 + this progress doc; rewrote the master DAG (§7.0) as
**Phase -1 (done, #199) → M0 (ACTIVE, dual-use) → [H1-alpha PARKED] / [H2 execution-timing +
safety ACTIVE]**; promoted the **defensible residual to the ACTIVE path** (M0 dual-use data, H2
execution-timing on the 104 book, the safety fixes — none requiring cost-clearing alpha); marked
§A as the *superseded prior*. Un-park only on a concrete reason to believe IC ≫ 0.05.

**(B) Codex round-4 (19:11:08Z, head 65b8001) — all 8 findings addressed (DESIGN-level spec text):**
1. **Phase -1 not executable from declared inputs** — added an explicit identifiability boundary:
   executable cost, fill dynamics, and "independent bets/day (N_eff)" are **NOT identifiable from
   OHLC/daily bars**; cost is a conservative **bound** (not a measured fill model) and the GO test
   **keeps the uncertainty in the verdict**; raw breadth is an upper bound on N_eff, not N_eff.
2. **Circular σ_oc gate → net-edge gate** — replaced the σ_oc-vs-its-own-prior rule with a
   **net-edge gate clearing cost with an uncertainty band**, every term given an exact definition,
   estimator, missing-data behavior, and a **deterministic decision function** (no `~30-40 / ~150 /
   ~4 / ~17 / "materially below"`); under it Phase -1 is **STOP-for-ALPHA**, "GO to M0" = dual-use
   data only.
3. **M1 pre-registration mutable + math-ambiguous** — **DELETED the false "Sharpe 1.0 ≡ IC 0.03"**
   (kept IC ≥ 0.03 as a SEPARATE threshold, no equivalence) in M1 F1.7 + metrics §0; pinned ONE
   block selector (Politis-White, session-rounded — no `n^{1/3}` alt), ONE moments window (full
   series, one pass), ONE non-normal correction (MinTRL); required-N **computed + published BEFORE
   fitting**, estimator + decision rule **frozen now**, M0 moments substituted into the same frozen
   estimator.
4. **Paper probes ≠ measured live cost** — M0 F0.7 now SEPARATES (a) quote-derived spread bounds,
   (b) paper-WORKFLOW validation (`paper_cost`, never a live number), (c) live-execution
   calibration (needs representative historical live fills OR a separately operator-approved tiny
   live experiment — deferred while alpha parked); GO uses conservative bounds + keeps uncertainty;
   nothing paper-calibrated is called "H1-representative measured cost".
5. **H2 pre-registration singular** — pinned ONE multiple-comparison correction (**studentised
   max-statistic** on the paired session-block bootstrap — Holm-Bonferroni dropped) and ONE
   hierarchical dependence model (**calendar session**, no week-block alt → underpowered/stop);
   fill-model parameter fitting is **nested DISJOINT** from policy evaluation (same probes never
   both calibrate fills AND score policy).
6. **M3 underpowered + repeated looks** — per-step **N derived from a live power calc** (the
   hardcoded 20 REMOVED); **sequential / e-value** testing with a pre-registered boundary +
   **multiplicity correction across the 4 promotion looks**; only model + cost-calibration transfer
   between exposure levels (per-step Sharpe/DD/killed-winner do NOT transfer).
7. **Risk thresholds contradictory** — committed ONE **`loss_budget.yaml` config artifact**
   (equations + parameter sources + clamps that PRODUCE the per-step −5%/−20%); the M3 KILL row,
   reliability §3.3/§3.10, metrics kill-conditions, and the stress (now with **defined `X=3` σ,
   `K=30 bps` band**) all **CONSUME** the generated values — hardcoded contradictions removed.
8. **Causal contract tied to data-availability semantics** — extended master §3 with
   `data_available_ts` capture/conservative reconstruction (p99 feed latency), which feed supplies
   executable quotes (IEX default; SIP = fresh experiment), **clock skew tolerance (250 ms)**, late
   provider corrections/revisions (as-of vintage), **auction treatment** (no auction-print entry),
   and **no-fill-before-close behavior** (no position, opportunity cost recorded — never a synthetic
   fill).
Cross-repo topology stays owned by umbrella **ADR #416**, now **authoritative-but-DEFERRED pending
an alpha GO** (master §6.1). `py_compile`/`pytest` unchanged (no script edit — the reframe + all 8
findings are doc-level; the feasibility script remains the parametric-prior artifact, superseded by
the Phase -1 measurement in #199).
