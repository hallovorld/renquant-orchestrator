# 2026-06-11 Decision-Tree Audit — False-BEAR Buy-Suppression Cascade

**Status:** RFC / awaiting review (do not implement until approved)
**Run audited:** `run_id=2026-06-11-live-f68231b0` (daily_104 full, broker=alpaca, 14:05–14:18 PT)
**Author:** decision-tree forensic audit
**Severity:** P0 — the system emitted **no trade** in a healthy bull market because of a
mislabeled regime, not because the model judged stocks unattractive.

---

## 0. Executive summary

Today's daily full ran **clean** — every recently-merged fix is live (μ-gate,
Kelly σ-horizon match, model protection, cross-day persistence; the preflight
shows `P-KELLY-SIGMA-HORIZON [HARD] sigma_horizon_days=60 (matches μ horizon)`).
Yet the cycle decision was **`no trade`**.

The cause is **not** the model. It is the **regime detector firing a false
`hard_bear`** off a single short-horizon volatility blip, which then cascaded
through **three redundant buy-blocking gates**. The "never-buy" failure mode that
we previously traced to the `raw>0` gate has **re-surfaced through a new
mechanism** (the regime layer). The μ-gate/protection fixes work but **never got
to act** — the regime gate short-circuits the pipeline upstream of scoring.

This document (1) reproduces the full decision trace with every number verified,
(2) independently checks the regime call against **real SPY price data**, and
(3) proposes prioritized, testable fixes with theoretical support. **No code is
changed here** — implementation follows review.

---

## 1. Verified decision trace (`run_id=2026-06-11-live-f68231b0`)

Each figure below was read from the run log and cross-checked against config /
source / independent computation.

### 1.1 The model's *input* data is correct (not a data bug)

| Quantity | Model reported | Independently recomputed from `data/ohlcv/SPY/1d.parquet` | Match |
|---|---|---|---|
| SPY 5-day cumulative return | −2.57% | **−2.57%** | ✅ |
| SPY 5-day annualized realized vol | 0.26 | **26.1%** | ✅ |

So the regime detector is fed correct data; the defect is in the **decision
rule**, not the feed.

### 1.2 What actually fired `hard_bear`

`kernel/pipeline/task_regime.py::BEAROverrideTask` fires `state.hard_bear` on the
**OR** of four conditions:

| Condition | Threshold | Actual (2026-06-11) | Fired? |
|---|---|---|---|
| 20-day vol > `bear_vol_threshold` | 0.35 | 15.2% | ✗ |
| 20-day cum-ret < `bear_return_threshold` | −0.08 | −0.63% | ✗ |
| 5-day vol > `bear_vol_threshold_5d` | **0.25** | **26%** | **✓** |
| 5-day cum-ret < `bear_return_threshold_5d` | −0.04 | −2.57% | ✗ |

**The entire BEAR label hangs on a single 1-point overshoot of the 5-day vol
threshold (26% vs 25%).** 26% annualized ≈ **1.64 %/day** realized — routine
pullback chop, not crisis-level dispersion.

`RegimeFinalizeTask: regime=BEAR conf=0.50 transition=True` → `conf=0.50` is the
floor; the detector is itself maximally *uncertain*.

### 1.3 The cascade — three redundant buy-blocks

1. **`DrawdownGateTask` (Gate 0):** in BEAR, `regime_params.BEAR.drawdown_halt_pct = 0.05`.
   Portfolio drawdown = 10421.53 / 11079.22 − 1 = **−5.94%** > 5% → circuit
   breaker latched, **buys blocked**. In BULL_CALM the halt is **0.35**, so the
   *same* 5.94% DD would be a non-event — the false BEAR tightens the halt **7×**.
   The breaker latches until DD recovers to `drawdown_resume_pct=0.025`, so one
   false BEAR can freeze buying for **days**.
2. **`TransitionWindowTask` (Gate 1):** `in_transition=True` → buys blocked. This
   is the proximate reason logged: `DECISION | no trade (transition_window)`.
3. **`ApplyKellySizingTask`:** `cands=0/12 non-zero … zero_reasons[capped_zero=12]`
   — every surviving candidate sized to **0** under the bear branch.

`Phase 2b (buy scan): buy_blocked=True; … order-emission remains gated` — buys
were blocked **before scoring even ran**; the model scored only "for decision
audit."

### 1.4 Downstream gates that would *also* have suppressed buys

- **`VetoWeakBuysTask`:** floor = `max(0.20, mean+1.00·std) = 0.536` → **dropped
  71/83 candidates (86%)**. With a Platt-compressed calibrator
  (`rank_score IQR=0.039`, `CALIBRATOR-SATURATED`), a `mean+1σ` floor sits at
  ≈ the 84th percentile → the rule **structurally cannot admit more than ~16% of
  the universe**, regardless of edge.
- **Wash-sale (`DROP_WashSaleFilter`):** BA, BAC, D, DUK, FTNT, WFC were
  **binary-blocked on "P/L unknown"** (sold 15–27 d ago). IRC §1091 applies
  **only to loss sales**; binary-blocking unknown-P/L sales over-blocks
  gain-sale re-entries. (META −$12.57 / VRT −$82.97 are genuine losses with tiny
  NPV cost $0.35 / $2.31 — those are defensible; the unknown-P/L blocks are not.)
- **`RealizedVolGateTask`:** dropped 19/102 over the 60% annualized vol cap
  (AMD 79%, ANET 62%, COHR 89%, …) — defensible, but removes core semis.

### 1.5 Signal-quality observations (separate track)

- `HFPatchTSTPanelScorer … val_ic=0.0307` — the live checkpoint's validation IC is
  **3%** (pool calibration IC is 0.131, a different statistic).
- Raw scores `mean=−0.1899 std=0.0287`; calibrator `neutral_raw=−0.1981`;
  **48/83 candidates have raw vs calibrated-μ of opposite sign** — the known
  benign-offset structure; signal is near-flat / weakly dispersed.
- **`fundamentals feed STALE: max date 2026-02-10 is 121 days before as-of`** — 5
  fundamental features are a frozen snapshot on every live bar.
- `ApplyShadowScoringTask … artifact not found: panel-ltr.alpha158_fund.json`
  (shadow only; non-blocking).

---

## 2. Independent reality check — is this actually a bear market?

Computed directly from `data/ohlcv/SPY/1d.parquet`, as-of 2026-06-11:

| Metric | Real value | Reading |
|---|---|---|
| 60-day return | **+9.97%** | strong 3-month uptrend |
| Price vs **200-day MA** | **+7.56%** | textbook bull |
| Price vs 50-day MA | **+2.30%** | uptrend intact |
| Drawdown from 52-week high | **−2.88%** | hugging the highs |
| 20-day annualized vol | **15.2%** | normal |
| Last 5 closes | 757 → 737 → 739 → 737 → **725 → 737** | the dip **already bounced +1.7% on 06-11** |

A market **+7.56% above its 200-day moving average**, **−2.9% off its high**, with
**normal 20-day vol**, that **closed up +1.7% on the audit day**, is **not a bear
market** by any standard trend or drawdown definition. The `hard_bear` label is a
**false positive** driven entirely by one week of elevated-but-ordinary realized
vol.

---

## 3. Root-cause analysis & proposed solutions (prioritized)

> Implementation is **out of scope for this RFC**; each fix lists the change site,
> the rationale with literature, and a validation. Sequencing in §4.

### P0 — False `hard_bear` from an over-sensitive single-condition 5-day-vol route
**Site:** `renquant-pipeline kernel/pipeline/task_regime.py::BEAROverrideTask`;
thresholds in `renquant-strategy-104 configs … regime.*`.
**Problem:** A lone `5d_vol > 0.25` (OR-combined) flips the whole book to BEAR. The
task's own docstring concedes the thresholds are "exploratory … will tune via
A/B," and notes SVB / DeepSeek / Aug-2024 distress peaked at 18–22% — i.e. real
stress barely exceeds the very level we trip on routine chop.
**Proposed (combine):**
- **(a) Trend confirmation gate:** suppress `hard_bear` when SPY is above its
  long trend filter (e.g. > 200-day SMA, or > 50-day SMA). A market above its
  200-day MA should never be hard BEAR. *Theory:* Faber (2007), "A Quantitative
  Approach to Tactical Asset Allocation" (200-DMA timing); Moskowitz, Ooi &
  Pedersen (2012), "Time Series Momentum," *JFE* — trend sign is the dominant
  regime axis.
- **(b) Require persistence on the short-horizon vol route:** demand the 5-day
  condition hold for ≥ N consecutive bars (or pair vol **AND** return, not OR).
  *Theory:* Bollerslev (1986) GARCH — volatility clusters *persist*; a single-bar
  spike is not a regime. Hamilton (1989) Markov-switching — regimes have
  expected duration, motivating debounce (already used elsewhere via CUSUM/SPRT,
  Page 1954 / Wald 1945).
- **(c)** Optionally raise `bear_vol_threshold_5d` toward the 20-day GFC level so
  the short route catches genuine spikes, not 1.64%/day chop.
**Validation:** replay the trailing ~60 trading days; assert `hard_bear` only
fires when SPY < 200-DMA *or* the 20-day GFC route trips; confirm 2026-06-11 is
labeled non-BEAR.

### P1 — Drawdown circuit breaker tightened 7× and latched by the false regime
**Site:** `kernel/pipeline/task_gates.py::DrawdownGateTask`; `regime_params.BEAR.drawdown_halt_pct`.
**Problem:** A normal **5.94%** portfolio DD halts buying only because BEAR drops
the halt from 0.35 → 0.05; the latch then persists until DD < 2.5%.
**Proposed:** gate the breaker on a **confirmed** bear (trend-filtered, per P0),
not the noisy override; and/or raise `BEAR.drawdown_halt_pct` to a level that does
not trip on single-digit DD inside an uptrend. **Validation:** A/B the
buy-admission count with P0 applied — the breaker should not latch on 06-11.

### P2 — `VetoWeakBuys` `mean+kσ` floor on a compressed calibrator
**Site:** `kernel/panel_pipeline/scoring … VetoWeakBuysTask`.
**Problem:** `mean+1σ` on `IQR=0.039` admits ≤ ~16% of names by construction;
under calibrator saturation it is a near-constant high bar unrelated to edge.
**Proposed:** replace with a **dispersion-aware / rank-quantile** floor (e.g.
top-K or top-q by cross-sectional rank, or scale k by realized score dispersion).
*Theory:* Grinold's Fundamental Law (IR = IC·√BR) — throttling breadth to ~16%
caps achievable IR; the floor should track *relative* rank, not an absolute
saturated score. **Validation:** count admitted names vs. score dispersion across
the replay window; floor should not collapse breadth when scores are compressed.

### P3 — Wash-sale binary-block on unknown P/L
**Site:** `kernel/pipeline/candidates … DROP_WashSaleFilter`.
**Problem:** §1091 disallows **loss** sales only; binary-blocking unknown-P/L
re-entries over-blocks gain-sale names.
**Proposed:** resolve realized P/L from broker tax-lots; block only genuine
losses; route marginal cases through the existing NPV-cost model already present
for META/VRT. **Validation:** confirm gain-sale names (e.g. BA/BAC if sold green)
are admissible; losses still blocked within 30 d.

### P4 — Data / model hygiene (parallel track)
- Refresh `sec_fundamentals_daily` — fundamentals are 121 days stale.
- `val_ic=0.0307` is weak; route to the model-quality / retrain track (separate
  from this decision-tree audit).

---

## 4. Severity, sequencing, and risk

**Sequence:** **P0 first** — it is the actual gate that blocked buys on 06-11;
nothing downstream matters until the regime label is correct. Then **P1** (so a
confirmed-bull DD doesn't latch the breaker), then **P2**, then **P3**. **P4** in
parallel.

**Risk of P0/P1 (loosening bear detection):** could delay protection in a genuine
crash. **Mitigations:** keep both 20-day routes (35% vol / −8% ret) and the
return-based 5-day route intact; only fix the **single-condition 5-day-vol** path;
add **trend confirmation** so a true bear (price < 200-DMA *and* elevated vol)
still fires immediately. Net effect: genuine bears still trip; bull-market vol
blips no longer do.

**Validation harness:** trailing-window replay (existing diag/replay tooling)
toggling each fix, measuring (i) regime-label agreement with the trend filter,
(ii) buy-admission count, (iii) net-of-cost PnL. Promote only on A/B improvement.

---

## 5. One-line conclusion

Today's `no trade` was a **false-BEAR buy-suppression cascade**, not a model
verdict: a 2.6% pullback in a market +7.6% above its 200-day MA was mislabeled
`hard_bear` off a 1-point 5-day-vol overshoot, which tripped three redundant
buy-blocks. **Fix the regime detector's trend-blindness (P0) first** — only then
can we observe whether the (now-working) model actually buys in a bull tape.
