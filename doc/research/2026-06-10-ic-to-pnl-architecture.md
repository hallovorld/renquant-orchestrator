# From IC to Sharpe: a ground-up redesign of the signal→portfolio path

**Date:** 2026-06-10 · **Author:** Claude (research proposal) · **Status:** RFC v4 — DESIGN, not a verdict. v4: experiment prerequisites/time (§5.5), pre-registered falsification outcomes (§5.6), credibility ledger (§A.5), storage design (§A.6). v2: revised per codex review (evidence appendix §A, prod/shadow correction, hypothesis downgrades, bibliography). v3: §A.4 reproduction discrepancy **RESOLVED** (it was a log-line-ordering + tax-basis misread by the author, not an infrastructure fault; three independent paths produce bit-identical ledgers) — per-cut numbers corrected throughout.
**Mandate:** Operator: "PatchTST IC ≈ 0.1 but realized APY/Sharpe are terrible — the decision tree wastes the IC. Forget the current architecture; propose something more scientific."

> **Scope discipline.** This document answers a *conditional* question: **IF** a panel model has a real, placebo-clean cross-sectional IC of ~0.10, what is the smallest, most theoretically grounded portfolio-construction path that converts that IC into Sharpe? It does **not** assert the IC is real. The 2026-06-02 validity audit found the PatchTST `B_tuned` IC leak-contaminated (timeshift placebo +0.067 > real +0.044). **IC reality is a hard prerequisite gate (§7), measured independently. A clean architecture on a fake signal is worth zero.**

---

## 1 · The symptom, stated precisely

> **Which lane these forensics describe (corrected per the 2026-06-07 prod/shadow audit).** Per `RenQuant/doc/research/2026-06-07-patchtst-prod-shadow-status-audit.md`, the current production primary is **hf_patchtst** and XGB/GBDT is the **shadow** lane. The forensics below are from the **GBDT (shadow-lane) walk-forward gate run** — the only lane with WF trade forensics, because `weekly_wf_promote` gates the GBDT incumbent via `strategy_config.shadow.json`. Live trading is currently **sell-only** for both lanes (P-WF-GATE unstamped), so neither lane "currently trades" buys in production. Where the ledger's `entry_model_type` column says `Manual/XGBoost/QLearning`, that is the **known stale per-ticker attribution** the 2026-06-07 audit lists as a follow-up bug ("rows … silently inherit stale per-ticker XGB labels") — it is *not* evidence about which model selected the trade (see §6.3).

The complaint "IC is high but Sharpe is terrible" has a precise name in the literature: a **low transfer coefficient**. The 2026-06-10 WF forensics (full provenance + reproduction commands in **§A**; reproducibility **confirmed across three independent paths**, §A.4) show the fingerprint:

| Layer | Observation (cut C, 2025-04→2026-03) | Source (§A) |
|---|---|---|
| Per-trade economics | win rate 49%, mean P&L +2.38%/trade, ~49-day mean holds | A.2 |
| Holding period | median 35–62d across cuts — matched to the 60d label | A.2 |
| Breadth realized | 29 distinct names traded in a year, of a 142 watchlist | A.2 |
| Portfolio result (annual-net basis) | cut A(2024) +0.691, cut B +0.394, cut C +0.037; mean +0.374, 0/3 beat SPY | A.1, A.4 |

**Hypothesis H1 (the headline claim, to be tested by E1):** the individual bets carry positive expectancy at the label horizon, and the portfolio layer — not the forecast — is where the information is lost. If H1 survives E1, this is definitionally a transfer-coefficient problem, not an alpha problem.

---

## 2 · The theory the current architecture is hypothesized to violate

### 2.1 The Fundamental Law, with the term everyone forgets

Grinold & Kahn (2000) give the headline IR = IC·√BR. The operational form is Clarke, de Silva & Thorley (2002), which inserts the **Transfer Coefficient**:

> **IR = TC · IC · √BR**

TC ∈ [0,1] is the cross-sectional correlation between signal-implied active weights and actually-held active weights. CDST's empirical result: realistic long-only + turnover + cap constraints drive TC to **0.3–0.6**.

**Back-of-envelope (explicitly an upper-bound sketch, NOT a verdict):**

- Naive bet count: 29 names × 252/49 ≈ 148/yr → √BR ≈ 12.2. **This overstates BR**: 60d labels overlap, rankings are serially persistent, and names are cross-correlated — the 2026-06-08 overlapping-label RFC (`RenQuant/doc/research/2026-06-08-overlapping-label-and-gate-architecture/`) documents material autocorrelation at the gate shift. True effective BR is lower; the honest statement is "TC·√BR_eff jointly explain the gap," and E1 measures TC directly instead of inferring it.
- IF IC = 0.10 and BR were as naive as stated: ideal IR ≈ 1.22 (gross). Observed IR ≈ 0.37 → implied TC ≈ 0.30. **Status: hypothesis-generating sketch only.** The per-date TC distribution from E1 is the deliverable.

### 2.2 Where TC plausibly leaks — the gates between rank and weight

The current `JointPortfolioQPJob` interposes: admission rank-floor (0.55) → ER-horizon/floor gates → QP μ-contract → exposure/conviction caps → no-trade bands → sector/correlation caps → emission-side stops + soft-sell horizon guards + calibrator-saturation abstain. Each is individually defensible; composed, they are hypothesized to act as a low-pass filter on the alpha. Three candidates, each tied to a measurable E1 step:

1. **Long-only.** IC measures the full cross-section; long-only discards the short leg. CDST show this alone caps TC near ~0.5 for a symmetric signal. PatchTST's *claimed* edge is strongest in tails (BEAR +0.22, operator-override note 2026-06-09 — itself unverified, §7).
2. **Hard admission floors (rank ≥ 0.55).** A monotone signal's value is the full ordering; a hard floor coarsens it and collapses breadth (142→29 observed). Qian-Hua-Sorensen (2007): IC is a continuous quantity.
3. **Daily path-dependent stops on a 60-day thesis.** Han, Zhou & Zhu ("Taming Momentum Crashes: A Simple Stop-Loss Strategy", SSRN 2407199) show stop-loss value concentrates in **momentum-crash / downside states**; extrapolating to "stops are a TC tax in calm-bull" is *our hypothesis*, supported so far only by this repo's small-sample live post-exit regret measurement (+3.6pp mean over 13 exits, §A.3) — small n, overlapping windows, suggestive only.

### 2.3 The structural critique

The current design fuses **alpha capture** (track the forecast faithfully) and **risk control** (cut exposure, stop losses) in one optimizer + emission stage. The objectives fight, and the blend makes TC unmeasurable — you cannot attribute "trim for risk" vs "signal weakened." Whatever E1 finds, *measurability* of TC is itself an architectural requirement the current design fails.

---

## 3 · The proposal: a two-stage architecture that measures its own transfer coefficient

```
 panel forecast (z-scored cross-sectional rank, per day)
        │
        ▼
 ┌─────────────────────────────┐   STAGE A — ALPHA PORTFOLIO
 │  α_i = IC · σ_i · z_i        │   (Grinold 1994: the honest map
 │  target_w ∝ α / (γ·Σ)        │    from a rank to an active weight)
 │  long-short, horizon-held    │
 └─────────────────────────────┘
        │  w_alpha (the signal's own opinion, nothing else)
        ▼
 ┌─────────────────────────────┐   STAGE B — RISK OVERLAY
 │  vol-target scale, drawdown  │   (intended to scale the book, not
 │  halt, gross/net caps, costs │    re-pick names — see H-B below)
 │  GP-2013 cost-aware glide    │
 └─────────────────────────────┘
        │  w_final
        ▼  orders
```

Stage A is a deterministic monotone function of the forecast; its TC versus the raw rank is measurable and near 1.0 by construction.

### 3.1 Stage A — three variants, ranked by ambition

| Variant | Construction | Harvests | Reference |
|---|---|---|---|
| **A0 — rank-decile L/S (the ceiling)** | long top decile, short bottom decile, equal-weight, rebalance at horizon | full IC, both tails, max breadth | Fama-French sorts; Gu-Kelly-Xiu 2020 |
| **A1 — α-proportional L/S** | w_i ∝ IC·σ_i·z_i, dollar-neutral, vol-scaled | continuous ordering | Grinold 1994 |
| **A2 — long-only α-tilt** | A1 projected onto w ≥ 0, Σw = 1 | the production-feasible point | CDST 2002 §long-only |

A0 is **not a deployable strategy** — it is the **measurement instrument**: its Sharpe is the empirical ceiling the IC implies. If A0 is weak, the IC is not tradeable at this horizon/universe and no architecture saves it (→ §7). If A0 is strong and A2 weak, the long-only constraint is the quantified tax.

### 3.2 Stage B — risk overlay, stated as a testable hypothesis (revised per review)

**Hypothesis H-B:** a *uniform positive per-date scalar* on all active weights leaves the same-date cross-sectional TC unchanged.

This holds by construction **only** under narrow conditions: the scalar is strictly positive and uniform across names on each date, TC is measured cross-sectionally on dates with nonzero gross exposure, and no stock-level clipping/partial-trade effects intervene. Two Stage-B components **do not satisfy this automatically** and must be measured, not asserted:

- **Vol targeting / drawdown throttle** (Moskowitz-Ooi-Pedersen 2012; Grossman-Zhou 1993): per-date uniform scalars → same-date TC preserved, but they change the *time aggregation* of active risk; realized multi-period IR can shift. Measure: per-date TC distribution + IR before/after.
- **GP-2013 cost-aware glide:** trading a fraction toward the aim portfolio is **not** a scalar when per-name costs/turnover bind name-by-name. Measure: per-date TC of (held vs aim) during glide.

**TC measurement definition (fixed for all experiments):** per-date Spearman correlation between the actually-held active-weight vector and the Stage-A signal-implied active-weight vector, over the union universe, reported as a distribution across dates with gross exposure > 0; pooled mean ± std and per-regime breakdown (Pearson-on-weights as robustness column).

Hard risk exits (true blow-up stop, wash-sale law, liquidity) remain as a thin safety layer — exception path, logged as TC-leakage events.

---

## 4 · Mapping the operator's complaint to measurable fixes

| Suspected waste (hypothesis) | Fix | Verified by |
|---|---|---|
| Long-only discards short leg + tail edge | A0/A1 vs A2 spread | E1 step +2, E4 |
| Rank-floor 0.55 collapses 142→29 names | continuous α-weighting | E1 step +4, E3 |
| Daily stops shred a 60d thesis | GP-2013 glide; stops → safety-only | E1 step +5 |
| Risk trims indistinguishable from alpha trims | Stage B scalar + TC metric | H-B measurement |
| Stale attribution hides who selects (§6.3) | scorer-identity stamping (already a 2026-06-07 audit follow-up) | pipeline telemetry PR |

---

## 5 · Experiment design (falsifiable, placebo-clean, existing WF harness)

All runs on the existing walk-forward manifold (point-in-time models), per-regime PRIMARY then pooled, DSR/PBO on every number (Bailey-López de Prado 2014), shuffled-label + timeshift placebo on every claim (§5.2 battery). Reproducibility precondition: **met** — §A.4 confirms three independent execution paths produce bit-identical trade ledgers; all experiment reports must state which tax basis (annual-net vs event-level) every Sharpe uses, since the two diverge by up to 1.0 Sharpe on these windows (§A.4).

**E1 — Transfer-coefficient decomposition (the headline experiment).**
Start from A0 and add one production constraint at a time, measuring Sharpe and per-date TC (§3.2 definition) at each step:

```
A0  rank-decile L/S, horizon-held, no costs        → IC ceiling Sharpe
+1  realistic costs (κ, impact)                    → cost drag
+2  long-only projection (A2)                      → long-only tax
+3  vol-target + drawdown overlay (Stage B)        → H-B test
+4  admission floors                                → floor tax
+5  daily stops                                     → stop tax
=   current architecture                            → should reproduce gate Sharpe
```

The largest single-step drop is the ranked answer to "what wastes the IC." If the full stack does NOT reproduce the gate's Sharpe, the decomposition is incomplete — that is also a finding.

**E2 — Horizon sweep** {20, 40, 60, 90}d: IC-decay curve (Qian-Hua-Sorensen), confirms the holding horizon.
**E3 — Breadth restoration:** A2 with/without rank floor; report effective breadth via eigenvalue count on the position-correlation matrix, not naive name-count (BR-overlap caveat, §2.1).
**E4 — Short-sleeve value:** A2 vs A1 vs 130/30 at realistic borrow/costs; measured decision, likely NO at current NAV.

### 5.5 Prerequisites and time budget (per experiment)

Measured baseline: one 12-month sim cut ≈ **1.5–4 min wall** on this machine (warm OHLCV/feature caches; 2026-06-10 runs). Engineering estimates assume the PR-review cadence, one engineer-agent.

| Item | Prerequisites | Compute (wall) | Engineering |
|---|---|---|---|
| **P0: clean-IC artifact** (§7.1) | renquant-model leakage investigation closed; placebo-clean OOS per-date IC series exported per model | — (consumes existing eval outputs) | owned by renquant-model; **blocking everything below** |
| **A0/A1/A2 allocator impl** | ConstraintSnapshot seam (exists); step-4g replay harness (exists) | — | 1–2 days incl. tests |
| **TC metric + per-date logging** | §3.2 definition; equity/weights trace already emitted | — | 0.5 day |
| **E1** (7 stack steps × 3 windows = 21 sims) | A0–A2 + TC logging + §A.6 storage | ~1–2 h | 1 day driver + verdict doc |
| **E2** (4 horizons × 3 windows = 12 sims) | E1 infra; per-horizon labels exist in panel | ~45 min | 0.5 day |
| **E3** (2 variants × 3 windows) | E1 infra | ~20 min | 0.25 day |
| **E4** (3 variants × 3 windows + borrow-cost model) | E1 infra; borrow-cost assumptions doc'd | ~30 min | 0.5 day (cost model) |

**Critical path:** P0 (external, days–weeks) ∥ allocator impl (1–2 d) → E1 (1 d) → E2–E4 (1–2 d combined). **Total post-P0: roughly one working week.** If P0 stalls, E1 can run early on the GBDT signal (its placebo status is the known M6 issue — results would carry that caveat) purely to validate the E1 machinery; no promotion decision may cite those numbers.

### 5.6 Falsification outcomes — what we do when the data refuses the hypothesis

Pre-registered, so failure cannot be reinterpreted after the fact (Bailey-LdP selection-bias discipline). No outcome authorizes a gate bypass.

| Observation | Verdict | Next action |
|---|---|---|
| **A0 ceiling weak** (DSR ≤ 0 vs SPY on clean IC) | the IC is not tradeable at this universe/horizon — H1 dead, architecture irrelevant | stop all Stage-A/B work; route to signal research (M6 leakage closure, alternative models/universes/horizons via E2) |
| **A0 strong, A2 ≈ A0** | long-only tax small; current gates are the loss | proceed: replace gates per E1 ranking, keep long-only |
| **A0 strong, A2 weak** | long-only constraint is the dominant tax | operator decision with quantified menu: accept A2's lower ceiling / E4 short-sleeve / change mandate |
| **E1 stack reproduces gate Sharpe but no single step dominates** | loss is distributed (death by a thousand cuts) | redesign is holistic: fewer, softer constraints (CDST §soft-constraints); re-run E1 on the redesign |
| **E1 stack does NOT reproduce gate Sharpe** | decomposition incomplete — an unmodeled mechanism exists | finding in itself; bisect the unexplained gap before any architecture claim |
| **H-B fails** (overlay measurably cuts TC) | "scalar overlay" is wrong as built | fix or drop the offending component; re-test; Stage B ships only TC-neutral-as-measured pieces |
| **Results don't survive DSR/PBO or placebo** | overfit or leakage | discard, log in `failed-experiments-log.md`, do NOT iterate toward the test set |

---

## 6 · Relationship to the existing codebase

### 6.1 Build order
1. A0/A1/A2 as `AlphaPortfolioAllocator` variants behind the existing `ConstraintSnapshot` seam (renquant-pipeline) — additional baselines in the **step-4g replay harness**, which exists precisely to adjudicate allocators.
2. Stage B as post-allocator scalar overlay (vol-target already exists in `ApplyExposureScalingTask` — reuse).
3. E1–E4 through WF + replay; verdict doc; promotion per §7 only.

### 6.2 What survives
ConstraintSnapshot, WF gate, sanity battery, vol-target, cost model, regime detector. Re-wiring of selection→sizing, not a teardown.

### 6.3 Correction of v1's "most damning finding" (review finding #2)

v1 claimed "the panel IC never reaches the optimizer — per-ticker trees select instead," based on `entry_model_type ∈ {Manual, XGBoost, QLearning, Classification}` in the round-trip ledger. **That inference was wrong.** The same ledger rows show `entry_source_job=JointPortfolioQPJob`, `entry_order_type=QP_BUY`, with populated `entry_rank_score`/`entry_panel_score` — selection/sizing in the WF sim **is** panel-score-driven through the QP; `model_type` is the stale per-ticker attribution label the 2026-06-07 audit already flags as a telemetry bug. What remains true and material: (a) the **live** sell path is driven by per-ticker models (live logs, sell-only era), and (b) attribution staleness makes IC-usage *unauditable* — itself a §2.3 measurability failure. The "waste" claim therefore rests on the gates (§2.2), not on "the panel is unused."

---

## 7 · Hard prerequisite gate (the 2026-06-09 lesson — do not skip)

1. **IC reality.** Close the PatchTST leakage investigation (2026-06-02 audit). Stage A consumes the *placebo-clean OOS* IC — not the calibrator fit-window `pool_ic=0.13` (in-sample), not the override note's recent-window numbers (unverified). If clean OOS IC is 0.03–0.04, the ceiling is computed on that, honestly.
2. **Reproduction.** Met — §A.4 resolved; E1 reports must declare the tax basis of every metric.
3. **A0 sanity.** If the decile ceiling on the clean signal is not materially > SPY on a DSR basis — stop; the architecture cannot manufacture alpha.

---

## 8 · References (with stable links)

- Grinold & Kahn 2000, *Active Portfolio Management*, 2nd ed., McGraw-Hill. ISBN 978-0070248823.
- Clarke, de Silva, Thorley 2002, "Portfolio Constraints and the Fundamental Law of Active Management," *FAJ* 58(5):48–66. doi:10.2469/faj.v58.n5.2468 ← central reference.
- Grinold 1994, "Alpha is Volatility times IC times Score," *JPM* 20(4):9–16. doi:10.3905/jpm.1994.409482.
- Qian, Hua, Sorensen 2007, *Quantitative Equity Portfolio Management*, Chapman & Hall/CRC. ISBN 978-1584885580.
- Gârleanu & Pedersen 2013, "Dynamic Trading with Predictable Returns and Transaction Costs," *JF* 68(6):2309–2340. doi:10.1111/jofi.12080.
- Gu, Kelly, Xiu 2020, "Empirical Asset Pricing via Machine Learning," *RFS* 33(5):2223–2273. doi:10.1093/rfs/hhaa009.
- Moskowitz, Ooi, Pedersen 2012, "Time Series Momentum," *JFE* 104(2):228–250. doi:10.1016/j.jfineco.2011.11.003.
- Grossman & Zhou 1993, "Optimal Investment Strategies for Controlling Drawdowns," *Mathematical Finance* 3(3):241–276. doi:10.1111/j.1467-9965.1993.tb00044.x.
- Han, Zhou, Zhu, "Taming Momentum Crashes: A Simple Stop-Loss Strategy," SSRN 2407199. doi:10.2139/ssrn.2407199. (Scope: momentum-crash/downside protection — §2.2 caveat.)
- Bailey & López de Prado 2014, "The Deflated Sharpe Ratio," *JPM* 40(5):94–107. doi:10.3905/jpm.2014.40.5.094.

---

## §A · Evidence appendix (added per review finding #1)

### A.1 WF gate run — provenance

- **Run:** weekly_wf_promote, staging `20260610T144100Z`, verdict logged 2026-06-10 08:10:18–08:11:26 PT; trade traces under `20260610T150039Z`.
- **Log:** `RenQuant/logs/weekly_wf_promote/2026-06-10.log` — verdict block: `WF result: FAIL: … mean Sharpe +0.374, 3/3 cuts > 0; SPY mean Sharpe +1.081 … beat SPY Sharpe 0/3`. ⚠ **Log lines print in cut-completion order (cuts run in parallel), not window order** — the SPY-Sharpe column keys each line to its window. Correct per-window mapping (annual-net basis, from the equity JSON traces): **cut A (2024) Sharpe +0.691 / APY +7.34%; cut B (2024-07→2025-06) +0.394 / +3.24%; cut C (2025-04→2026-03) +0.037 / −0.13%**.
- **Code/config state:** renquant-backtesting `eac1c71`; renquant-pipeline runtime `2ccc7fd`; renquant-strategy-104 `97c1cd6` (shadow `rotation.target_horizon_days=60`); WF manifest `backtesting/renquant_104/artifacts/sim/walkforward_manifest_v2_20260602.json`; derived eval config `backtesting/renquant_104/artifacts/diagnostics/wf_eval_configs/strategy_config.sim_wl200_gbdt_prod_recipe_calibrated.prod_semantic.json` (recipe fingerprint `sha256:cfdd6cb8e950da0f`, 172 features).

### A.2 Per-trade statistics — exact reproduction

Ledgers: `RenQuant/backtesting/renquant_104/artifacts/diagnostics/wf_trade_traces/20260610T150039Z/{2024-01-02_to_2024-12-31,2024-07-01_to_2025-06-30,2025-04-01_to_2026-03-28}.round_trips.csv`

```bash
cd /Users/renhao/git/github/RenQuant
python3 - <<'EOF'
import csv, statistics as st, collections
T='20260610T150039Z'
for w in ('2024-01-02_to_2024-12-31','2024-07-01_to_2025-06-30','2025-04-01_to_2026-03-28'):
    f=f'backtesting/renquant_104/artifacts/diagnostics/wf_trade_traces/{T}/{w}.round_trips.csv'
    rows=[r for r in csv.DictReader(open(f))]
    hd=[float(r['hold_days']) for r in rows]; pnl=[float(r['pnl_pct']) for r in rows]
    print(w, 'n=',len(rows), 'hold med/mean=',st.median(hd),round(st.mean(hd)),
          'win%=',round(100*sum(p>0 for p in pnl)/len(pnl)),
          'mean_pnl%=',round(100*st.mean(pnl),2),
          'names=',len(collections.Counter(r['ticker'] for r in rows)))
EOF
```

Output (2026-06-10): cut A n=49, hold med 62d, win 59%, mean +12.79%; cut B n=40, hold med 52d, win 48%, mean +9.97%; cut C n=55, hold med 35d, win 49%, mean +2.38%, 29 names.

### A.3 Live post-exit regret (+3.6pp) — source

13 live exits 2026-05-15→06-03 from `RenQuant/data/runs.alpaca.db` (`trades` table; the 05-26/27 and 06-04 sells are absent from the table — recording gap documented in the 2026-06-09 decision-trace analysis — and were taken from `live_state.alpaca.json::last_sell_dates`), post-exit prices from `ticker_forward_returns` + LEAN daily zips, SPY-adjusted per matching windows. Result: mean +3.6pp/exit, 9/13 positive, dominated by GE +15.8pp and FTNT +10.0pp. **Small n, overlapping windows, sector-correlated — suggestive only.** To be re-emitted as a standalone reproducible script in the E1 PR.

### A.4 ✅ RESOLVED: the apparent cut-C irreproducibility was an author misread — reproducibility is in fact confirmed across three independent paths

v2 of this doc reported the gate's cut C as "+7.34%/Sharpe +0.691, irreproducible" against two re-runs at "−4.0%/Sharpe −0.35". The trade-level diff resolved it completely; **there was no infrastructure fault**:

1. **Log-line ordering.** The gate runs cuts in parallel and logs `→ Sharpe=…` lines in *completion* order. The "+0.691/+7.34%" line belongs to **cut A (2024)** — identified by its SPY-Sharpe column (+1.778 = the 2024 window) — not cut C. Cut C's true gate metric is **+0.037/−0.13%**.
2. **Tax basis.** The gate (by design — `_sim_metrics_from_trace`, runner.py:806) consumes the equity-JSON **annual-net** metrics; the sim console footer prints **event-level** (tax cash debited at event time). For cut C: annual-net **+0.037/−0.13%** vs event-level **−0.355/−4.05%**. My re-runs' console numbers match the gate's own event-level JSON to the third decimal.

**Verification (all three windows, both bases, from `…/20260610T150039Z/<window>.equity.json`):**

| Window | annual-net Sharpe / APY | event-level Sharpe / APY |
|---|---|---|
| 2024-01-02→2024-12-31 (A) | +0.691 / +7.34% | +0.412 / +3.91% |
| 2024-07-01→2025-06-30 (B) | +0.394 / +3.24% | −0.080 / −1.24% |
| 2025-04-01→2026-03-28 (C) | +0.037 / −0.13% | −0.355 / −4.05% |

**Determinism/reproducibility confirmed:** gate run, direct `sim_driver` re-run, and umbrella-native `run_sim_104.py` with the pre-2026-06-10 pipeline (`02bb077`) produce **bit-identical 55-trade ledgers** for cut C (entry sets identical; totals gross **+$2,474** / net-after-tax **−$3,978** in all three). Ledgers: gate `…/20260610T150039Z/2025-04-01_to_2026-03-28.round_trips.csv`, `/tmp/gatepath_cutC_rt.csv`, `/tmp/xcheck_cutC_rt.csv`.

**Residual finding worth keeping:** the annual-net vs event-level bases diverge by up to **~1.0 Sharpe** on these windows (cut B: +0.394 vs −0.080) because gross P&L is small relative to tax-cash timing. Every future report must name its basis explicitly; E1 will report both.

### A.5 Credibility ledger — how much to trust each number in this doc

| Claim | Trust | Basis |
|---|---|---|
| Per-cut WF Sharpe/APY, both tax bases (§A.1/A.4) | **HIGH** | three independent execution paths, bit-identical 55-trade ledgers; machine-readable traces on disk |
| Per-trade stats: win%, holds, 29 names (§A.2) | **HIGH** | direct recomputation from committed ledgers; command + output in §A.2 |
| Ledger `entry_model_type` labels | **NOT TRUSTED** | known stale-attribution bug (2026-06-07 audit follow-up); v1 was misled by it (§6.3) |
| Live post-exit regret +3.6pp (§A.3) | **LOW / suggestive** | n=13, overlapping windows, sector-correlated, partial recording gaps in `trades` table |
| "PatchTST IC ≈ 0.1" (operator premise) | **UNVERIFIED** | nearest artifacts: calibrator fit-window `pool_ic=0.13` is **in-sample**; 2026-06-02 audit found B_tuned OOS IC leak-contaminated; override-note recent-window numbers unaudited. This is exactly the §7.1 gate |
| BR ≈ 148, implied TC ≈ 0.30 (§2.1) | **SKETCH ONLY** | naive independence assumptions; superseded by E1's direct per-date TC measurement |
| CDST TC range 0.3–0.6, long-only ≈ 0.5 cap | **LITERATURE** | external result; applies to symmetric signals under their assumptions, not yet measured on ours |

### A.6 Experiment data storage (so every future number is one command from its evidence)

Follows the repo's existing conventions (`doc/research/evidence/<date>-<slug>/` in the umbrella; manifests-not-blobs per `RENQUANT_REPOS.md`):

1. **Raw traces** (equity JSON, trades/round-trips CSV, per-date TC series CSV) → `RenQuant/backtesting/renquant_104/artifacts/diagnostics/ic_to_pnl/<EXP>/<RUN_ID>/` — RUN_ID = UTC timestamp; **append-only, never overwritten**; not committed to git (large), referenced by fingerprint.
2. **Run manifest** (small JSON, committed): one per run — command line, repo pins (all subrepo SHAs), config path + sha256, manifest path + recipe fingerprint, tax basis, wall time, output-file sha256s. Schema mirrors §A.1's provenance block so the appendix is generated, not hand-written.
3. **Results table** (committed): one tidy CSV per experiment — one row per (variant, window, tax_basis, regime) with sharpe/apy/TC mean±std/DSR/PBO + the RUN_ID it came from. This is the only file analysis notebooks read; raw traces are for audits.
4. **Verdict doc** (committed): `doc/research/evidence/<date>-ic-to-pnl-E<k>/verdict.md` — pass/fail vs §5.6 pre-registered outcomes, with the results-table rows inlined. Same style as the 2026-06-02 validity audit.
5. **DB:** summary rows additionally appended to `sim_runs.db::experiment_results` (keyed by RUN_ID) so the control panel can query progress without parsing docs. The DB is a cache; **the committed manifest+CSV is the source of truth** (DBs are not source code, per repo rules).

---

**Next action (requires review approval — not self-merged):** (1) ~~close §A.4~~ done (v3); (2) implement A0; (3) run E1 on the clean signal, reporting both tax bases.

Agent-Origin: Claude
