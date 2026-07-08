# Design: resolve 104/105 cash drag — evidence-first execution order

STATUS: design / RFC for cross-agent review. Docs only. No live behavior, config,
or capital-routing change ships here.

DATE: 2026-07-07
REVISION: r2 (Codex corrective review) — aligns the plan with the active multi-repo
architecture, demotes umbrella-first implementation, and separates shadow plumbing
from deploy-authorizing policy changes.

SCOPE: define the scientifically justified execution order for cash-drag work across
104 and 105, backed by measured evidence on record plus the running concentration cap
sweep. The goal is to stop solving the wrong problem first.

---

## 0. Executive summary

Four decisions:

1. **No new implementation starts in the umbrella repo.** Under the current multi-repo
   contract, cash-drag implementation belongs in `renquant-strategy-104`,
   `renquant-pipeline`, `renquant-execution`, and `renquant-orchestrator`; `RenQuant`
   stays integration/pinning/rollback only.
2. **Parking-sleeve shadow/runtime wiring is correctly an orchestrator problem.**
   It is scheduling / book-state capture / shadow-log provenance, not model or broker
   logic. `renquant-orchestrator#423` is therefore in the right repo.
3. **Lane A remains a strategy+pipeline program, not a concentration-sweep substitute.**
   The accepted S6 shape is still one-change-at-a-time A-1 / A-2 / A-3. The running
   concentration-cap sweep is useful research, but it does not replace those owned
   policy/runtime changes or authorize shipping them by implication.
4. **Fractional shares are a separate sizing-fidelity track, not the default first
   implementation phase of cash-drag remediation.** The cheaper non-fractional A-3
   one-share initiation floor and the sleeve shadow path must be exhausted or shown
   insufficient before re-opening the active-path fractional rollout.
5. **105 is NOT a live cash-drag implementation target yet.** It receives
   compatibility + instrumentation work only.

Execution order: finish orchestrator shadow plumbing → run policy/runtime experiments in
the owning repos (strategy-104 + pipeline, one change at a time) → only then decide
whether fractional shares are still worth the active-path complexity.

---

## 1. Evidence: what the data says

### 1.1 Cash drag is real and material

| Date | Source | Cash % | Key observation |
|---|---|---|---|
| 2026-06-29 | daily-full live | 54% | $827 deployed of $8,730 |
| 2026-07-01 | canonical run | 76% | trailing-5 mean 79.5% |
| 2026-07-02 | KPI scorecard | 75% | average last 10 sessions |

### 1.2 Decomposition (measured, 2026-07-01)

| Source | Contribution | Mechanism | Citation |
|---|---|---|---|
| Whole-share block | PRIMARY | BLK $1.1k > 3% target ($324) → size_insufficient_cash | OXY forensics 07-01, BLK/AVGO blocked 06-29/07-01/07-02 |
| Multiplicative sizing compression | STRUCTURAL | Kelly(7.3%) × conviction(0.50) × σ-mult(0.87) ≈ 3.1% target vs 12% cap | doc/design/2026-07-02-104-capability-program.md:31 |
| Redeployment throttle | SLOW-FILL | top_n=3, ~$336/buy → 24 sessions to deploy $8.1k | capability-program.md:28 |
| QP cash penalty = 0 | PASSIVE | Solver doesn't penalize idle cash | portfolio_qp config: qp_cash_drag_lambda=0 |
| top_up threshold too coarse | LOCKED OUT | 5% threshold at 12% cap → no top-up above 7% | kelly_sizing config; never A/B tested |

Prior session-level: 62% cash ≈ 44.4% structural Kelly + 13.8% empty slots + 3.7% underweight.

### 1.3 The 2026-06-29 replay proves it's whole-share, not slots

Raising slots from 8/3 to 10/4 on the live book:
- Added only ~$427 of deployment
- Marginal buys: CVX (low-price, OK) + ZM (low-conviction)
- **AVGO / BLK / GS selected but bought 0 shares** — target notional < 1 share price

This is a **sizing fidelity** problem, not an exposure policy problem.

### 1.4 What prior research covers vs doesn't

| Question | Covered? | Finding |
|---|---|---|
| Kelly σ-horizon cause? | YES (06-03 A/B) | NO — non-binding ceiling; ΔSharpe=0 |
| Trim winners? | YES (04-24 A/B) | NO — trim OFF beats ON by +12.7pp APY |
| max_conc=12% optimal? | **RUNNING** (07-07 sweep) | TBD — 75 variants × 3 seeds |
| top_up_threshold=5% optimal? | **RUNNING** (07-07 sweep) | TBD |
| entry cap ≠ drift cap? | **RUNNING** (07-07 sweep) | TBD |
| λ (QP cash penalty)? | PARTIAL | λ-alone in current prod config is a mechanical no-op; sensitivity exists only when `qp_min_invested_pct` also moves, so A-1 is not settled and not deploy-authorizing as currently scoped |
| Fractional shares? | DESIGNED, NOT TESTED | subrepo PRs built, closed (operator: prioritize 105) |

---

## 2. Theory: three distinct problems people call "cash drag"

### 2.1 Sizing-fidelity drag

The strategy decides name X deserves $324, but whole-share rounding gives $0 or $1,100.
**Fix**: fractional shares. Removes zero-drop on high-price names, reduces selection
bias toward cheap names, preserves admission logic.

### 2.2 Configuration drag

The sizing/gating parameters (max_concentration, top_up_threshold, trim) may be
miscalibrated relative to the model's actual output distribution.
**Fix**: data-driven parameter tuning via the concentration cap sweep. The A/B design
(doc/design/2026-07-06-concentration-cap-research.md) tests 75 configurations with
frozen seeds and 7-criterion unanimity verdict.

**Kelly theory context**: Half-Kelly (f=0.50) is standard for estimation error — reduces
geometric growth by ~25% while halving variance of terminal wealth (Thorp 2006). The
12% cap was set by operator fiat without A/B evidence. The 5% top-up threshold makes
TopUp unreachable for positions above 7% — at the model's typical 3% Kelly target,
this threshold never fires. Davis & Norman (1990) no-trade band theory suggests
threshold ∝ sqrt(round-trip cost × holding period), which for our parameters is ~2-3%.

### 2.3 Residual-idle-cash drag

After all single-name decisions, leftover cash sits uninvested.
**Fix**: parking sleeve (SGOV-first). Earns carry without changing the portfolio's beta
profile. SPY sleeve requires a separate risk decision because it silently adds
benchmark beta.

---

## 3. Repo map (multi-repo architecture; no umbrella-first implementation)

| Work item | Owning repo | Why |
|---|---|---|
| `panel_buy_top_n`, `qp_cash_drag_lambda`, `qp_min_invested_pct`, sleeve-enable / reserve config | `renquant-strategy-104` | active 104 strategy policy/config lives here |
| one-share initiation floor, QP objective changes, drop-reason ledger fields, target-notional math | `renquant-pipeline` | runtime inference / sizing / selection logic lives here |
| broker fractional capability, order validation, order-audit invariants | `renquant-execution` | broker execution and order audit live here |
| sleeve shadow scheduling, runtime book-state capture, run bundles, readiness monitors, shadow scorecards | `renquant-orchestrator` | pinned-subrepo daily orchestration and provenance live here |
| cross-repo pin advance / integration verification only | `RenQuant` umbrella | integration harness and rollback source; no new feature implementation |

Practical rule: if a PR changes *what to buy / how much to buy / which names are admitted*,
it is not an orchestrator PR. If it changes *when to run, what to log, how to stitch the
subrepos, or how to prove provenance*, orchestrator is the right home.

---

## 4. The plan: phased, each gate-checked

### Phase 1: orchestrator shadow plumbing (already the correct low-risk start)

**Why first**: it is shadow-only, repo-correct, and unblocks clean evidence collection
without forcing an active-path execution rewrite first.

Cross-repo sequence:

| Order | Repo | Change |
|---|---|---|
| 1 | renquant-orchestrator | land parking-sleeve shadow runtime wiring + default shadow-log location + run-bundle provenance |
| 2 | renquant-orchestrator | attach sleeve metrics to readiness / scorecard surfaces |
| 3 | renquant-strategy-104 | keep sleeve flags default-OFF until shadow evidence is complete |

Acceptance criteria:
- sleeve shadow runs from scheduled orchestration with no manual JSON injection
- sweep/fund shadow legs are logged with reproducible book-state provenance
- no broker mutation path is introduced
- no 105 live authorization semantics change

### Phase 2: Lane A policy/runtime experiments in the owning repos

**Why next**: these are the actual 104 exposure-policy changes, and each must be isolated.

Ordered sequence:
- **A-1**: correct the design scope first. In current production, moving `qp_cash_drag_lambda`
  alone does nothing because `qp_min_invested_pct=0`; any real A-1 experiment must either
  explicitly un-disable both together or be re-scoped before it is called evidence.
- **A-2**: `panel_buy_top_n` change, in `renquant-strategy-104`, only after A-1 is
  separately understood.
- **A-3**: one-share initiation floor, in `renquant-pipeline`, with explicit ledger
  reason codes and headroom checks.

The concentration-cap sweep is **adjacent research**, not a substitute for A-1/A-2/A-3.
If it produces a winner, that winner earns its own config PR. If it is null, Lane A still
stands or falls on its own evidence.

Acceptance criteria:
- one change at a time; no bundled rollout
- every deployment increase is attributable to the changed knob, not to sleeve or
  concentration-sweep confounding
- no gate bypass on conviction / veto / correlation / sector rules
- decision ledger records the exact drop/floor reasons touched by the change

### Phase 3: fractional shares only if the cheaper fixes still leave material error

**Why not first**: the active-path fractional rollout still carries commit-path, stop,
and broker-capability complexity. That work is justified only if A-3 plus the sleeve
leave a residual sizing-fidelity problem large enough to matter.

Acceptance criteria:
- residual sizing error remains material after A-3 / sleeve
- active-path stop / broker / lifecycle contract is proven before any enablement
- the implementation lands in execution / pipeline / strategy, not as umbrella-first code

### Phase 4: optional concentration-cap PR, if and only if the sweep actually wins

If the running 75-variant sweep finds a real winner under its pre-registered criteria,
ship that winner as its own config change. If not, record the null and move on.

### Phase 5: 105 compatibility and instrumentation only

105 is NOT a mature live strategy with a proven edge. The current record:
- Stage 1 operations-only, default-OFF, frozen canary envelope
- Phase -1 feasibility: net edge −6.4 bps @ IC 0.03 (soft NO-GO on intraday alpha)
- parking-sleeve shadow/runtime integration is a 105/orchestrator compatibility task, not
  a 105 economic authorization

This RFC does NOT authorize live cash-drag deployment for 105. Instead:
1. Make 105 compatible with 104's sleeve-shadow contracts
2. Add measurement fields (target notional, zero-drop count, residual idle cash)
3. No 105 live-capital expansion on cash-drag grounds until economics authorized

---

## 5. Non-goals

This RFC does not authorize:
- bundled "turn every cash-drag knob at once" rollout
- SPY-first sleeve rollout
- using the running concentration sweep as a silent replacement for S6 Lane A
- new feature implementation in the umbrella repo
- 105 deployment push before 105 economics are authorized
- claim that higher deployment alone implies higher expected value

---

## 6. Merge and implementation rule

After this design PR merges:
1. Orchestrator sleeve-shadow plumbing can merge as soon as review is complete
2. Lane A work proceeds only in `renquant-strategy-104` + `renquant-pipeline`
3. Fractional shares require a fresh active-path justification after A-3 / sleeve evidence
4. Concentration-cap changes ship only if the sweep data supports them
5. 105 receives compatibility/instrumentation only

Running sweep status: 75 variants × 3 seeds, ~20-50h ETA from 2026-07-07 09:13.
Results will be published as a data-only memo when complete. If the sweep produces
a clear winner, that earns a separate config PR; it does not silently redefine the
cash-drag implementation order.
