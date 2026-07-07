# Design: resolve 104/105 cash drag — evidence-first execution order

STATUS: design / RFC for cross-agent review. Docs only. No live behavior, config,
or capital-routing change ships here.

DATE: 2026-07-07

SCOPE: define the scientifically justified execution order for cash-drag work across
104 and 105, backed by measured evidence on record plus the running concentration cap
sweep. The goal is to stop solving the wrong problem first.

---

## 0. Executive summary

Four decisions:

1. **104 primary fix = fractional shares.** The measured binding constraint is
   whole-share quantization on high-price names, not slot count or concentration caps.
2. **104 secondary fix = concentration cap tuning.** The 75-variant 3D sweep
   (entry_cap × drift_buffer × topup_thresh) is running; if a variant dominates the
   incumbent on all 7 criteria across 3 seeds, it ships. If null, incumbent stays.
3. **104 tertiary fix = parking sleeve (SGOV-first).** Residual idle cash earns
   carry without silently turning the book into a benchmark-beta product.
4. **105 is NOT a live cash-drag implementation target yet.** It receives
   compatibility + instrumentation work only.

Execution order: fix sizing fidelity → tune concentration parameters (data-driven)
→ monetize residual idle cash → then re-measure whether policy knobs still need to move.

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
| λ (QP cash penalty)? | YES (A-1 sweep) | NULL — no significant change |
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

## 3. The plan: phased, each gate-checked

### Phase 1: fractional shares (104 sizing fidelity)

**Why first**: the measured binding constraint. Fractional shares are justified by
mechanical error reduction, not PnL.

Cross-repo sequence:

| Order | Repo | Change |
|---|---|---|
| 1 | RenQuant umbrella | preserve fractional fill quantities end-to-end; capability gate before live emission |
| 2 | renquant-execution | fractional validation on live broker path |
| 3 | renquant-pipeline | wire stage-2 fractional sizing path, default OFF |
| 4 | renquant-strategy-104 | config block default-OFF, enable after gate proven |
| 5 | renquant-orchestrator | sizing-fidelity scorecard + monitoring |

Acceptance criteria:
- `size_insufficient_cash` for fractionable names → 0 on canonical full runs
- median |realized − target notional| / target ≤ 1%
- no fractional dust remains after full sell lifecycle
- no unsupported fractional order reaches broker
- no regression in stops, live-state, or cash accounting

**Explicitly NOT in Phase 1**: changing top_n, qp_cash_drag_lambda, or other exposure
knobs. Those confound "better plumbing" with "more exposure."

### Phase 2: concentration cap tuning (data-driven, if sweep shows signal)

**Pre-condition**: sweep completes with ≥1 variant dominating incumbent on all 7 criteria
(net-of-cost Sharpe, max DD, Calmar, per-regime no-regression, turnover ≤ 1.25×,
unanimity across 3 seeds).

If the sweep result is NULL (no variant dominates), the incumbent parameters stay and
this phase produces only a data-only memo documenting the null result.

If a winner emerges:
- Ship as a monitored exception (same pattern as demean, 2026-06-25)
- 8-week revert window
- Decision-ledger wiring for forward validation

**Theory support**: the sweep's 3D grid (entry_cap × drift_buffer × topup_thresh)
tests H1 (entry cap ≠ drift tolerance improves by letting winners run) and H2
(top_up_threshold should scale with max_concentration). The no-trade-band literature
supports both hypotheses directionally.

### Phase 3: parking sleeve (SGOV-first)

**Pre-condition**: Phase 1 live or merge-ready.

First live contract:
- vehicle = SGOV
- shadow first, live second
- sweep only cash above operational reserve + pending order headroom + planned equity buys
- sell sleeve first to fund admitted single-name buys
- no benchmark-beta claims

Acceptance criteria:
- idle cash at close reduced to reserve band on canonical full runs
- sweep/fund round trips reconcile cleanly
- sleeve never blocks admitted single-name buys
- sleeve attribution visible separately from alpha positions

### Phase 4: revisit exposure-policy knobs (only on new baseline)

After Phases 1-3 measured on a stable baseline, then revisit:
- `qp_cash_drag_lambda`
- `panel_buy_top_n`
- any remaining sizing-stack de-throttling

At that point the experiment is clean: zero-drop is gone, residual cash has a separate
owner, and any deployment increase can be attributed to policy, not plumbing.

---

## 4. 105: compatibility and instrumentation only

105 is NOT a mature live strategy with a proven edge. The current record:
- Stage 1 operations-only, default-OFF, frozen canary envelope
- Phase -1 feasibility: net edge −6.4 bps @ IC 0.03 (soft NO-GO on intraday alpha)
- Fractional shares = Stage-2 dependency, not Stage-1 blocker

This RFC does NOT authorize live cash-drag deployment for 105. Instead:
1. Make 105 compatible with 104's fractional/sleeve contracts
2. Add measurement fields (target notional, zero-drop count, residual idle cash)
3. No 105 live-capital expansion on cash-drag grounds until economics authorized

---

## 5. Non-goals

This RFC does not authorize:
- bundled "turn every cash-drag knob at once" rollout
- SPY-first sleeve rollout
- 105 deployment push before 105 economics are authorized
- claim that higher deployment alone implies higher expected value

---

## 6. Merge and implementation rule

After this design PR merges:
1. Phase 1 (fractional shares) implementation starts immediately
2. Phase 2 (concentration cap) ships only if sweep data supports it
3. Phase 3 (sleeve) proceeds in parallel or immediately after Phase 1
4. Phase 4 (exposure knobs) stays blocked until new baseline exists
5. 105 receives compatibility/instrumentation only

Running sweep status: 75 variants × 3 seeds, ~20-50h ETA from 2026-07-07 09:13.
Results will be published as a data-only memo when complete. If the sweep produces
a clear winner, Phase 2 implementation follows this design's merge.
