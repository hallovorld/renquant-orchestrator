# The book is at its theoretical capacity — and the research program is below its own detection floor

Date: 2026-07-24
Status: RESEARCH MEMO (decision-grade synthesis; every input measured this
session or cited to its house source)
Inputs: clean-IC measurement (this session), TC from
`2026-07-02-ic-ceiling-institutional-gap-107-route.md`, live-book stats from
the 07-24 daily run, MDE from this session's actual bootstrap CIs,
`VERDICTS.md` as the empirical record.

---

## 1. One equation explains everything observed

Grinold's fundamental law, with every term **measured**, not assumed:

```
IR_realized = IC_clean × √BR × TC
```

| term | value | source |
|---|---|---|
| IC_clean | **0.0286** | this session: production recipe OOS 0.0481 − matched shuffled-label placebo 0.0195, 5 purged folds, 60d embargo, 3 seeds |
| cycles/yr | 4.2 | 252 / 60d holding |
| effective names/cycle | ~3.9 | 140 scored names under cross-sectional residual correlation ρ≈0.25 (equicorrelation effective-N) |
| **BR** | **~16 /yr** | 4.2 × 3.9 |
| TC | **0.40** | house measurement — the constraint stack (ic-ceiling doc §2.4) |
| **IR_realized** | **≈ 0.05** | |

Expected alpha at realistic active vol:

| active vol | alpha/yr | $ on the $10.6k book |
|---|---|---|
| 12% | +0.6% | **$59** |
| 20% | +0.9% | $98 |
| 30% | +1.4% | $148 |

ρ-sensitivity (the weakest assumption): ρ ∈ [0.15, 0.35] ⇒ IR ∈ [0.06, 0.04].
The order of magnitude does not move.

### The reconciliation

This single number explains every anomaly in the standing record **at once**:

- **Live book flat at ~$10.6k** (total +5.71%, of which the market is most):
  expected alpha is $60–150/yr. The book is not broken. **It is performing
  exactly at the capacity of an IC-0.03, TC-0.4, BR-16 system.**
- **83% win rate with 0.89 payoff** (win-rate memo): at IR≈0.05 the P&L is
  market beta plus noise; a rising tape plus early winner-exits produces
  precisely this signature. The gate-calibration doc's conclusion ("beta +
  early exits + small sample, not stock-picking") is the same fact seen from
  the trade ledger.
- **Every retrain fights the WF gate**: at clean IC 0.0286 against a placebo
  floor of 0.0195, the true signal is ~1.5× the leakage floor. Gate
  borderline-rejections are the expected behaviour of an honest gate on a
  marginal signal, not a broken gate.
- **The 07-20 G1 "deploy would have won" analysis was unevaluable at its own
  horizon**: a 60d-horizon thesis on a book that exits winners in ~8d and
  turns over 69% of names in 20d cannot realize — or even measure — its
  stated edge. (Horizon mismatch documented since 2026-05-24, never closed.)

## 2. The research program is below its own detection floor

Minimum detectable effect, from **this session's actual block-bootstrap CIs**
(not a textbook formula):

| contrast actually run | 90% CI width | implied MDE |
|---|---|---|
| horizon 20d vs 60d @eval-20d (the tightest) | 0.013 | **~0.011** |
| top9-gain vs all-172 | 0.020 | ~0.017 |
| clean-7 vs all-172 | 0.042 | ~0.036 |

Plausible feature-family effects on this corpus — from the house's own wins
and losses — are **0.005–0.010**. They sit **below the floor**. The last
feature that cleared it was PEAD/SUE at **+0.022/+0.021** (E47/E49, May); it
was detectable *because* it was 2× the floor, and it was detected.

The empirical confirmation is `VERDICTS.md` itself: since PEAD landed,
**~20 consecutive adjudications** read NULL / NO-GO / REJECTED / WITHDRAWN /
INCONCLUSIVE / REFUTED. That run is not bad luck and not bad hypotheses —
it is an instrument being asked to resolve below its resolution. **Additional
same-shape experiments on this corpus have negative expected value**: each
costs compute and review bandwidth, and the prior outcome (INCONCLUSIVE) is
already known.

This session's own arc is the demonstration: three studies (regime features,
feature count, horizon) each initially "found" effects of 0.005–0.015, and
each finding died under placebo/multiplicity — exactly what a below-floor
instrument produces.

## 3. The lever table — what a marginal unit of effort buys

| lever | realized IR | Δ | nature of risk |
|---|---|---|---|
| base | 0.046 | — | — |
| **TC 0.4 → 0.7** | 0.081 | **+75%** | engineering; **zero statistical risk** — the effect is arithmetic, not a hypothesis |
| **hold 60d → 20d** (if IC holds) | 0.080 | **+73%** | one empirical question; my matched-embargo grid says clean IC at 20d eval is NOT lower (train-20d beat train-60d at every eval horizon; 2 of 9 contrasts survive Bonferroni) — but E42v2's P&L says 60d wins at the portfolio level. Cost: ~3× turnover |
| a detectable feature win (+0.005 IC) | 0.055 | +17% | **below the detection floor — cannot be verified even if real** |
| all three | 0.165 | +260% | |

The reading is stark: **the two structural levers are each worth ~4× a
feature win, and the feature win cannot even be confirmed on this corpus.**

The house already knows the first row — the ic-ceiling doc ranked TC lane A +
R4 first ("+75% IR at zero IC cost") three weeks ago. This memo's contribution
is (a) independent confirmation from a different derivation, and (b) the
second row: **the horizon question is the only open research question with a
√3 multiplier attached**, and it is currently unresolved in both directions
(IC says 20d, P&L says 60d, and the IC metric that originally chose 60d — E35
— was made on a statistic now known to reward the longest label's
self-persistence, +0.049 autocorrelation at the gate shift).

## 4. What this memo recommends

1. **Stop feature archaeology on this corpus.** Not because features don't
   matter, but because effects of the plausible size cannot be adjudicated
   here. The M-SIG frozen-prereg gate already implements this de facto; this
   memo supplies the quantitative reason. (The factorial prereg #574 should
   still run once — its primary hypotheses are *interactions*, which the OFAT
   record cannot speak to, and its cost is 87 minutes. But it should be the
   **last** IC-only study on this panel.)
2. **The one study worth designing next is the horizon P&L study** —
   `fwd_20d` vs `fwd_60d` through the FULL stack (meta-label, QP, costs,
   turnover), preregistered, reconciling this session's IC grid with E42v2.
   It is the only question whose answer moves realized IR by ~70%.
3. **TC work continues to dominate** and needs no new evidence.
4. **Say the quiet part about book size.** Alpha scales linearly with
   capital: at $10.6k the entire annual alpha is < $150 — less than the cost
   of the compute used to measure it. The book's honest present function is
   an R&D platform and live test harness, and decisions (e.g. whether a $99
   data subscription "pays for itself") should be made against the platform
   value, not the P&L.

## 5. Limitations, stated plainly

- **ρ = 0.25 is the one assumed number.** BR scales ~1/ρ; the conclusion
  survives the plausible range (§1) but a measured ρ from the decision ledger
  (once #133 wiring lands) should replace it.
- IC_clean is measured on the 292-name survivorship panel ⇒ it is an **upper
  bound**; every capacity number above is therefore optimistic, which makes
  the argument a fortiori.
- The fundamental law's independence assumptions understate the value of
  regime/timing structure if it exists; that is exactly what #574's
  interaction tests are for.
- Nothing here retracts E42v2; §4.2 is the reconciliation path, not a verdict.

---

## 6. DEPTH PROBE (same day, later) — the signal's identity, audited

One production-recipe scoring run (all_172, fwd_60d, 5 purged folds, 60d
embargo, seeds 42/43/44, real + matched placebo), then three layers of
analysis. Headline numbers were audited before being believed; the audit
changed them materially.

### 6.1 The whole clean signal is statistically fragile

Per-date clean IC (real − placebo) collapsed to 60d block means —
independent draws, no assumptions:

- n = 35 blocks, mean +0.0215, **t = 1.15 ⇒ NOT distinguishable from zero
  at 95%.**
- Measured signal IR = 0.40, but with SE ≈ 0.35 — the IR of the book's own
  signal cannot be certified positive on its full 9-year history.
- **2026 YTD clean IC = +0.0015.** The deployed model is running at zero
  this year.
- By year: the entire positive mass sits in **2017, 2020, 2023, 2025**;
  2018/2019/2024 ≈ 0; **2021 and 2022 NEGATIVE** (−0.03, −0.06). The signal
  is EPISODIC, not stationary.

### 6.2 Where the alpha lives — and the audit of the +101%/yr headline

Decile curve of real fwd_60d by score (clean = real − placebo): deciles 0–8
clean ≈ −0.03…+0.00; **decile 9 clean = +0.14/period**. The signal is
almost entirely a TOP-DECILE phenomenon — good news for a top-N book in
principle. But the headline top-10 clean spread (+0.242/60d ≈ +101%/yr
gross) did not survive winsorization:

| treatment | clean spread /60d |
|---|---|
| raw mean (headline) | +0.242 |
| median-based | +0.189 |
| winsorized ±100% | +0.092 |
| winsorized ±50% | **+0.052** |

⇒ **62% of the spread comes from names that moved > ±100% in 60 days**;
78% from beyond ±50%. The alpha is a RIGHT-TAIL, lottery-shaped object:
a handful of huge runs, not a steady edge. (Survivorship inflates exactly
this component — the 292-name panel over-contains past big winners — so
these are upper bounds.)

### 6.3 The capture curve — and the exit-stack collision

Clean top-10 spread by horizon: **+0.073 @5d (147 bp/day) → +0.145 @20d
(73 bp/day) → +0.242 @60d (40 bp/day)**. The signal is front-loaded; ~60%
of the 60d spread accrues by day 20; per-day capture at a 20d cadence is
~1.8× the 60d cadence.

Collide this with the live book's measured behaviour (win-rate memo,
exit-plane doc): winners exited at ~8d, 69% of names gone in 20d, payoff
0.89, path-dependent stops exempt from the 60d holding floor. **A
tail-driven distribution is precisely the one that path-dependent stops
monetize worst** — volatile names dip before they run, and the stop
converts the future tail into a realized small loss. The 0.89 payoff at
83% win rate is that amputation measured from the trade ledger.

### 6.4 What §6 changes

1. §1's capacity estimate (IR ≈ 0.05 via assumed ρ) was too pessimistic as
   a point estimate (measured 0.40) but the right order as a certainty
   statement: **±0.35 SE means the corpus cannot even certify the sign.**
2. The horizon question (§4.2) now has a MECHANISM: front-loaded capture
   favors ~20d cycles on spread arithmetic — while E42v2 favored 60d on
   NAV. The preregistered P&L study should be designed around the capture
   curve, and must model the exit stack, because §6.3 says the exit stack —
   not the label — is where the money is currently lost.
3. The feature-archaeology STOP (§4.1) is reinforced: average-based IC
   deltas cannot see a tail-and-episode-shaped signal.
4. **A live warning worth its own eyes: the deployed model's clean IC this
   year is ~0.** Nothing in the daily telemetry currently measures this.

---

## 7. STRUCTURAL DECOMPOSITION — three named-methodology tests (same day)

Frame: realized alpha = [skill + characteristic premia] × dispersion ×
capture (Grinold 1989; DGTW 1997). Each link measured on the cached
production scores. One prior claim of §6 is FALSIFIED below and corrected.

### 7.1 DGTW characteristic-matched benchmark — the model HAS certified skill

Cells = vol(STD60) × momentum(ROC60) × beta(BETA60) terciles per date,
self-excluded cell means:

| statistic | /60d | block-t (n=35) |
|---|---|---|
| raw top-10 spread | +0.336 | **+3.00** |
| **DGTW-adjusted (skill)** | **+0.243** | **+2.92** |
| raw winsorized ±50% | +0.067 | +2.25 |
| DGTW winsorized ±50% | +0.038 | +1.70 |

- Picks sit at the **88th vol percentile** (momentum 51st, beta 51st — the
  tilt is pure VOL). The vol tilt explains only **29%** of the spread.
- **The DGTW-adjusted spread survives at t=+2.92** — the first statistically
  certified positive statement about this model in the whole record. The
  model has genuine within-cohort selection skill: *which high-vol name
  will run*. (Winsorized skill t=1.70 — the certification is tail-carried;
  the trimmed core is marginal.)
- Theory tie-in: Bali-Cakici-Whitelaw's MAX/lottery literature says the
  high-vol cohort **underperforms on average** — the model earns inside a
  cohort with a negative average premium, which is what within-cell skill
  (not tilt) looks like.

### 7.2 The single most consequential methodological finding

**Same data, same blocks: whole-cross-section Spearman IC gives t = 1.15;
the top-10 DGTW spread gives t = 2.92.** A top-N book takes positions only
in the top decile; rank-correlating all 283 names dilutes the test with the
~90% of the cross-section where the model has no view and no position.

Every gate in the house — WF-promote, the M-SIG ≥0.015 clean-IC bar, the
placebo framework — adjudicates on the low-power statistic. Part of the
VERDICTS NULL streak is an artifact of the test statistic, not of the
hypotheses. **Recommendation: the gate metric should be a
characteristic-matched top-N spread, not cross-sectional IC.**

### 7.3 Dispersion — sizing signal, but the episodes are NOT explained

- Top-10 spread by dispersion tercile: **+0.10 → +0.19 → +0.72 /60d** (7×) —
  the Grinold σ-scaling is real and large ⇒ dispersion-scaled position
  sizing is a live, observable lever.
- But YEARLY clean IC vs yearly dispersion: **corr = −0.12.** The
  2021/2022 negative years were NOT low-opportunity years. Episode risk is
  model-specific, unexplained, and cannot currently be timed.
- **Now: trailing dispersion at the 84th percentile — a target-rich
  environment — while 2026 YTD clean IC ≈ 0.** The model is failing in
  good conditions. This sharpens §6.4's alarm from "no telemetry" to
  "actively missing a rich regime".

### 7.4 Exit-stack counterfactual — §6.3's mechanism CORRECTED

Production BULL_CALM stop params (15% stop, 12%/25% trailing) applied to
the real price paths of the actual top-10 picks (1,080 positions, 108
rebalances; model/3-strike/panel exits excluded ⇒ lower bound):

| | /position/60d |
|---|---|
| buy-and-hold 60d | +10.07% |
| through the price-stop stack | +7.38% |
| **cost of the stop layer** | **−2.69pp ≈ −11.3%/yr on the sleeve** |

- 45% of positions get stopped. **Big winners' tail capture is 86%** — §6.3's
  "the stops amputate the tail" is **FALSIFIED**; stops save 11.7pp on each
  big loser. The cost is **whipsaw in the body**: a fixed 15% stop applied
  to names selected at the 88th vol percentile is inside 1σ of 60-day noise,
  so ordinary drawdowns of eventual recoverers get converted into realized
  losses.
- The live book's 8-day winner exits therefore come from the layers this
  sim could not include (model_sell / 3-strike / panel exits) — that is
  where the remaining capture loss must live, and it is measurable with a
  model-in-the-loop replay.
- **Fix implied is σ-scaled stops** (stop at k·σ_60d, not a fixed 15%) — a
  config-level change whose effect this harness can price in advance. This
  generalizes the standing panel-exit σ-blindness finding (orch #195) to
  the whole stop layer.

### 7.5 Caveats

Survivorship inflates all LEVELS (paired/blocked t-stats are the robust
part). DGTW cells are 27/date on ~280 names (~10/cell). Test 3 is a lower
bound and BULL_CALM-parameterized (72% of days). Certified skill is
tail-dependent (winsorized t=1.70). One model family, one panel.
