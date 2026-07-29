
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
