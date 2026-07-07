# 2026-07-07 — Cash Drag Comprehensive Fix (Strategy 104 / 105)

**Status**: Design — for discussion with other agents before implementation.
**Owner**: Claude. **Prior art**: [kelly-sizing-audit](../../doc/research/2026-06-03-kelly-sizing-audit.md), [σ-horizon A/B verdict](../../doc/research/2026-06-03-kelly-sigma-horizon-ab-verdict.md), [cash-drag-root-cause](../../doc/research/2026-06-03-cash-drag-root-cause-and-fix.md), [cash-overlay-feasibility](../../doc/research/2026-06-03-cash-overlay-feasibility-study.md), [concentration-cap-research](2026-07-06-concentration-cap-research.md).

---

## 0. Bottom line

**Live 104 is 81% cash in BULL_CALM.** 100% of candidate buys have been
blocked since June 1 — 45+ trading days of zero new positions entering the
portfolio. The two dominant blockers are **VetoWeakBuys rank floor** (48%)
and **regime admission gate** (38%). Kelly sizing is confirmed non-binding
(σ-horizon A/B: ΔSharpe = 0.000). The concentration cap (12%) and top-up
threshold (5%) are secondary constraints affecting existing holdings, not
new entries.

Sim BULL_CALM median cash is also 57.4% — this is structural, not
live-specific. But sim at least has a 7.6% candidate pass rate vs live's
0.0%.

**Proposed fix**: a layered intervention targeting each binding constraint
in order of impact, with A/B evidence gates at every step.

---

## 1. Evidence base — where is capital stuck?

### 1.1 Live pipeline funnel (June 1 – July 6, 2026)

| Stage | Count | % of total |
|---|--:|--:|
| Total candidates evaluated | 2,088 | 100% |
| Blocked: `veto:rank_score_below_floor` | 991 | 47.5% |
| Blocked: `regime_admission:failed:BULL_CALM` | 801 | 38.4% |
| Blocked: `conviction:mu_below_floor` | 91 | 4.4% |
| Blocked: other (fundamentals missing, broker pending, etc.) | 205 | 9.8% |
| **Selected for execution** | **0** | **0.0%** |

**Source**: `data/runs.alpaca.db`, `candidate_scores` table joined on
`pipeline_runs` for `run_type='live'` since 2026-06-01.

### 1.2 Live cash % time series

| Date range | Avg cash % | Regime | N buys |
|---|--:|---|--:|
| 2026-07-06 | 80.9% | BULL_CALM | 0 |
| 2026-07-01 – 07-02 | 77.7% | BULL_CALM | 0 |
| 2026-06-23 – 06-30 | 84.3% | BULL_CALM | 0 |
| 2026-06-01 – 06-22 | 84.2% | BULL_CALM / CHOPPY | 0 |
| 2026-05-22 (last buys) | 74.3% | BULL_CALM | 3 |

**45 trading days with zero new candidates passing admission.**

### 1.3 Sim comparison (BULL_CALM)

| Metric | Sim | Live |
|---|--:|--:|
| Median cash % | 57.4% | 81.0% |
| Candidate pass rate | 7.6% (5,779 / 75,993) | 0.0% (0 / 2,088) |
| Avg buys per run | 0.19 | 0.00 |
| Top blocker | `tier` (tiered rank threshold) | `veto:rank_score_below_floor` |

Sim also has structural cash drag (57.4%) but at least buys intermittently.
Live is completely shut out.

### 1.4 Prior research verdict

| Study | Finding | Status |
|---|---|---|
| Kelly σ-horizon A/B (06-03) | Kelly targets moved +0.021 in BULL_CALM; portfolio **byte-identical**. Kelly is a non-binding ceiling. | **REJECTED** as cash-drag fix |
| Trim A/B (04-24) | Trim OFF beats all variants by +12.7pp APY | **CONFIRMED** — leave OFF |
| Cash overlay feasibility (06-03) | Proposed SPY/QQQ fill for idle cash | **SUPERSEDED** — fix pipeline first |
| Cash-drag root-cause (06-03) | Diagnosed buy pipeline availability as root cause, not sizing | **CONFIRMED** by this analysis |
| Concentration cap research (07-06) | 12% cap set by operator fiat without A/B | **CONFIRMED** — sweep needed |

---

## 2. Root cause decomposition — five layers

### Layer 1: VetoWeakBuys rank floor (BINDING — 48% of blocks)

**Mechanism**: `VetoWeakBuys` computes a dynamic floor = `mean(rank_scores) + 1 × std(rank_scores)` across all candidates. Any candidate below this floor is vetoed.

**Current state** (2026-07-06): mean=0.514, std=0.051 → floor=0.565. Only 7/35 candidates (20%) pass. Of those 7, further gates (regime admission, conviction) block most remaining.

**Problem**: The floor is calibrated for a universe where the model has high dispersion. With the current PatchTST scorer on 142 tickers, rank_score dispersion is narrow (std ≈ 0.05). A 1σ cutoff eliminates ~84% of the population by construction (assuming roughly normal), leaving only the extreme tail.

**Theory**: The rank floor should select candidates with statistically significant positive expected returns, not just the tail of a distribution. A fixed-percentile or score-distribution-aware floor would be more robust than mean+kσ. See: Grinold & Kahn (2000) *Active Portfolio Management* §4 — signal-to-noise ratio determines optimal breadth. A narrower floor admits more names but with lower average alpha; the optimal floor depends on the cross-sectional IC and portfolio construction capacity.

### Layer 2: Regime admission gate (BINDING — 38% of blocks)

**Mechanism**: `RegimeModelAdmissionTask` requires walk-forward gate metadata (trade monotonicity, Sharpe beat) to be present and passing. When WF artifacts lack this metadata, ALL candidates are blocked.

**Current state**: 801 blocks on `regime_admission:failed:BULL_CALM` since June 1. This gate is fire-and-forget — one day's WF metadata failure blocks the entire portfolio for that day.

**Problem**: This is a binary kill switch with no hysteresis. The gate fails intermittently due to stale/missing WF metadata, not because the regime signal itself has deteriorated. A one-day metadata gap should not stop the portfolio for 24 hours.

**Theory**: Circuit-breaker pattern (Nygard 2007) — a failed dependency should trip a breaker with a recovery test, not permanently block. The gate should degrade to "last known good" status when metadata is temporarily unavailable.

### Layer 3: Concentration cap × top-up threshold interaction (BINDING for existing holdings)

**Mechanism**: `max_concentration=0.12` caps Kelly target at 12%. `top_up_threshold=0.05` requires `kelly_target - current_weight ≥ 5%` to trigger a top-up. Combined: any position above 7% cannot be topped up.

**Current state**: MU at 9.2% weight, kelly_target=12% → delta=2.8% < threshold=5% → blocked. The 12% cap was set by operator mandate (2026-06-09) without A/B evidence.

**Problem**: The cap was set reactively when Kelly emitted 21-23% targets (pre-σ fix). Now that Kelly targets are structurally lower (BULL_CALM avg=0.068-0.089), the 12% cap is rarely binding on new entries but permanently blocks top-ups for successful positions.

**Theory**: Position sizing literature (Thorp 2006, Kelly 1956) distinguishes between entry sizing (conservative) and position management (drift-tolerant). Asymmetric caps — lower for entry, higher for drift — let winners run while limiting initial risk. The 04-24 trim A/B already confirmed that letting winners drift beats trimming (+12.7pp APY).

### Layer 4: Whole-share sizing on small portfolio (CONTRIBUTING)

**Mechanism**: On a $10.8k portfolio with whole-share-only execution, each share of a high-priced stock is 2-6% of NAV. AVGO at $374 = 3.5% per share. Maximum practical allocation = 3 shares = 10.4%.

**Problem**: The rounding error is large relative to NAV. Even if the QP targets 12%, whole-share rounding may deliver only 10.4% (AVGO) or 6.8% (CRWD at $680). This systematic downward bias contributes ~2-3% of cash drag per position.

**Theory**: Bertsimas & Lo (1998) show that integer programming (IP) sizing outperforms rounding for small portfolios. However, fractional shares (already designed as S-FRAC, PR deferred per operator priority) are the clean fix. This is a known issue with a deferred solution.

### Layer 5: Sim structural cash (BACKGROUND)

Even in sim with all gates passing, BULL_CALM median cash is 57.4%. 39% of BULL_CALM sim runs have >70% cash. This is because:
- The model generates few high-conviction candidates per day (avg 0.19 buys/run)
- `max_concurrent_positions=8` at 12% cap = 96% theoretical max, but realized ≈ 40-50%
- Cross-sectional spread of scores is narrow → Kelly targets are small

This layer cannot be fixed by gate tuning alone — it requires better alpha signal or structural portfolio construction changes (outside scope of this PR).

---

## 3. Proposed interventions

### 3.1 [P0] Fix regime admission gate — add hysteresis + fallback

**Change**: When `RegimeModelAdmissionTask` fails due to missing/stale WF metadata (not due to actual regime deterioration), fall back to last-known-good verdict with a staleness timer.

**Config**:
```json
{
  "regime_admission": {
    "fallback_to_last_good": true,
    "max_staleness_days": 3,
    "log_fallback": true
  }
}
```

**Expected impact**: Unblocks ~800 candidate evaluations per month in live. 38% of current blocks removed.

**Risk**: Low — the fallback is bounded by staleness timer. If WF metadata is stale >3 days, the gate still blocks. The regime detector itself is not changed.

**Validation**: Shadow-mode first. Log what would have been admitted under fallback for 2 weeks. Check: do fallback-admitted candidates have comparable realized returns to normally-admitted ones?

**Implementation**: Pipeline repo, `RegimeModelAdmissionTask`. Orchestrator wires config.

### 3.2 [P0] Relax VetoWeakBuys floor — percentile-based

**Change**: Replace `mean + 1×std` dynamic floor with a percentile-based floor using the historical score distribution from `score_distribution` table in `data/runs.alpaca.db`.

**Options** (to be A/B tested):
- **A**: Status quo — `mean + 1×std` (floor ≈ 0.565, passes ≈ 20%)
- **B**: `p75` percentile of trailing 20-day rank scores (passes ≈ 25%)
- **C**: `p50` percentile (passes ≈ 50%)
- **D**: Absolute floor at base_rate + 0.05 (0.273 + 0.05 = 0.323, passes ≈ 95%)

**Expected impact**: B passes ~25% vs current 20% (+25% more candidates). C doubles candidate pool. D essentially removes the veto.

**Risk**: Relaxing the floor admits weaker candidates, potentially reducing average alpha. The A/B must measure Sharpe and win rate, not just capital utilization.

**Theory**: The optimal rank floor depends on the trade-off between breadth (more positions → diversification benefit) and depth (higher average alpha per position). Grinold (1989) IR = IC × √BR shows that doubling breadth (BR) requires IC/√2 per additional position to maintain IR. If the marginal candidates have IC > 0, relaxing the floor is net positive.

**Validation**: 27-month OOS sim sweep across A/B/C/D. Primary metric: Sharpe. Secondary: APY, MaxDD, cash%. The sweep script from PR #405 can be extended with a rank_floor dimension.

**Implementation**: Pipeline repo, `VetoWeakBuysTask`. Orchestrator extends sweep script.

### 3.3 [P1] Concentration cap + top-up threshold sweep

**Change**: A/B sweep over `max_concentration` × `top_up_threshold` grid.

**Grid** (from PR #403/#405, already designed):
- entry_cap: {8%, 10%, 12%, 15%, 20%}
- topup_threshold: {2%, 3%, 5%}
- 15 variants × 3 seeds = 45 sim runs

**Expected impact**: Raising cap from 12% → 15-20% with lower threshold (2-3%) should increase invested% by 5-15pp in BULL_CALM (based on MU-like top-up blocks becoming unblocked).

**Risk**: Higher concentration = higher single-name risk. The sweep must track MaxDD and worst-single-name-drawdown alongside Sharpe.

**Theory**: The asymmetric entry/drift cap aligns with the trim A/B finding — letting winners run (+12.7pp APY) means the drift cap should be higher than the entry cap. Ang (2014) *Asset Management* ch.7: concentrated portfolios outperform diversified ones when IC is positive, but tail risk increases non-linearly.

**Validation**: Already designed in PR #405. Execute the sweep, analyze results.

**Implementation**: Pipeline repo for config wiring; sweep script already built.

### 3.4 [P2] Increase max_concurrent_positions (conditional)

**Change**: If 3.1-3.3 increase candidate pass rate but cash drag persists because max_concurrent_positions=8 is binding, raise to 10-12.

**Expected impact**: At 12% cap × 10 positions = 120% theoretical max (never reached due to Kelly < cap). At 10% realized average, 10 positions = 100% invested.

**Risk**: More positions = more monitoring overhead. The pipeline runs ~35 times/day; more positions = more top-up/exit evaluations.

**Validation**: A/B sweep: {6, 8, 10, 12} concurrent positions. Only worthwhile if 3.1-3.3 have already been implemented.

### 3.5 [DEFERRED] Operational fallback overlay

Per the 06-03 root-cause analysis, an SPY/QQQ fallback overlay is the **last resort** — only deploy if 3.1-3.4 still leave >50% cash in BULL_CALM. The 06-03 design (§3) remains valid but should not be implemented until the pipeline blockers are resolved.

---

## 4. Execution plan

### Phase 1: Data collection + sweep (this week)

1. Run concentration cap sweep (PR #405 script, ~4h wall clock)
2. Extend sweep to include rank_floor variants (A/B/C/D)
3. Analyze combined results

**Deliverable**: Evidence document with sweep results + recommendation.

### Phase 2: Implementation PRs (after Phase 1 analysis)

Each intervention ships as a separate PR with its own A/B evidence:

| PR | Repo | Change | Gate |
|---|---|---|---|
| 3.1 Regime admission hysteresis | pipeline | Add fallback + staleness timer | Shadow 2 weeks |
| 3.2 Rank floor relaxation | pipeline | Percentile-based VetoWeakBuys | Sim A/B Sharpe ≥ status quo |
| 3.3 Concentration cap change | strategy-104 config | Adjust max_conc + top_up_threshold | Sweep result |
| 3.4 Max positions | strategy-104 config | Conditional on 3.1-3.3 | Sweep result |

### Phase 3: Live activation (after Phase 2 merge + shadow)

Each change activates via config change (no code deploy needed for cap/threshold). Rank floor and regime admission changes require pipeline deploy.

**Staging**: Enable one change at a time, 1-week soak per change, monitor cash% + trade count + PnL daily.

---

## 5. Success criteria

| Metric | Current | Target | Method |
|---|--:|--:|---|
| Live candidate pass rate | 0.0% | ≥ 5% | Gate relaxation |
| BULL_CALM cash % (live) | 81% | ≤ 50% | More entries + top-ups |
| BULL_CALM cash % (sim) | 57% | ≤ 40% | Sweep optimization |
| Sharpe (sim, 27-mo OOS) | 1.54 | ≥ 1.54 | No regression |
| MaxDD (sim) | 6.1% | ≤ 8% | Bounded tail risk |
| Avg positions held (live) | ~2 | ≥ 4 | More entries |

---

## 6. What this design does NOT do

- Does not change the model or scorer (out of scope)
- Does not implement fractional shares (S-FRAC deferred)
- Does not implement cash overlay (conditional on pipeline fix)
- Does not change Kelly formula (confirmed non-binding)
- Does not change trim behavior (A/B confirmed OFF)
- Does not bypass branch protection or WF gates
- Does not write to production data paths

---

## 7. Decision needed

1. **Approve the layered intervention approach** (fix gates → fix caps → increase positions → conditional overlay)?
2. **Priority**: Should 3.1 (regime admission) and 3.2 (rank floor) ship in parallel or sequentially?
3. **Cap sweep**: Use the existing PR #405 grid, or expand to include rank_floor variants in the same sweep?
