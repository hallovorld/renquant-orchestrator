# Regime detector assessment — measured (2026-08-17)

STATUS: research memo (docs only). Operator-directed ("regime detector有没有提升空间？
我要的是科学的严谨的深入的research的结论"). All numbers measured in-session from repo
data; the two most damning findings were independently re-derived (double-audit) before
this memo was written. Analysis scripts + intermediate series were preserved in the
session scratchpad (`regime-research/`: run_measurements.py, measurements.json,
label_series.parquet, posterior_series.parquet) — the memo carries every decision-driving
number inline so it stands without them.

## Verdict

**Room for improvement is large, but it is mostly METROLOGY (one label plane instead of
four) and EXIT-SIDE TIMING — not a fancier model.** The BEAR pole is genuinely good and
must not be touched. The bull-side 4-way split adds nothing measurable over a single
vol threshold, and the layer that decides 63% of serving days is statistically
indistinguishable from noise.

## Detector as-built (not what its name says)

There is **no HMM in production**. Three implementations coexist:
1. **Serving**: `kernel/regime.py::detect_regime` chain Hurst → CUSUM → GMM →
   BEAR-hard-override (+ disabled TrendOverlay). BEAR override first (20d vol>0.35 OR
   20d ret<−0.08 OR 5d vol>0.25 OR 5d ret<−0.04, or GMM P(BEAR)>0.5); Hurst MOMENTUM
   (H>0.65 on a 63d R/S window) routes most days; GMM (static 3-cluster artifact,
   as_of 2026-05-22, **no CHOPPY cluster**, no refit job found) decides the remainder.
   Posteriors are computed; the label is hard; confidence feeds sizing only. Lookahead
   hygiene clean (forward filtering, causal windows) `[VERIFIED]`.
2. **Research/WF**: `renquant_common/hmm_regime_labels.py` — a self-described
   "stateless approximation": log (not simple) returns, current-bar-excluded windows, a
   DIFFERENT single-window Hurst, and a version-gated BULL_CALM rule (default flipped
   2026-06-01) `[VERIFIED]`.
3. A real Hamilton-1989 HMM (`kernel/regime_hmm.py` + trainer) exists, **undeployed**
   (no trained artifact on disk; config points at the GMM) `[VERIFIED]`.

Serving decision attribution (replica 2016-11..2026-08, 2,459 td; replica reproduces the
WF gate's production-chain replay counts EXACTLY and the 08-08 posterior snapshot within
1.4pp) `[VERIFIED]`: Hurst-momentum→bull **63.2%**, GMM 15.7%, hard-BEAR 12.6%,
Hurst+below-MAs→BEAR 4.2%, vol-cluster→CHOPPY 3.8%, Hurst-reversion 0.5%. GMM
contributes **zero** BEAR decisions beyond the hard thresholds.

## Measured pathologies

| # | pathology | the number |
|---|---|---|
| P1 | **Hurst layer ≈ noise, decides 63% of days** | kernel `compute_hurst` on 63d WHITE NOISE: 86.2% of draws H>0.65 (500 sims); **independently re-derived: 89.0% (n=300, fresh seed)** `[VERIFIED ×2]`. H<0.52 fires on ~0% of noise → the CHOPPY-via-Hurst route is dead (0.5% of days). |
| P2 | **Four label planes, 25–70% agreement** | serving vs research-default 70.0% same-day (74.4% lag-1); serving vs legacy **25.2%**. Occupancy contradictions: serving 71.5% BULL_CALM vs legacy 78.2% BULL_VOLATILE vs GMM-argmax 53/44/3 (no CHOPPY) `[VERIFIED]`. |
| P3 | **BEAR-exit prereg data plane ≠ runtime trigger plane** | prereg episodes from GMM-posterior argmax: **77 BEAR days / 9 episodes** (independently re-derived from `doc/research/data/2026-08-08-regime-posteriors.csv`: exactly 77/9 `[VERIFIED ×2]`); runtime key (production chain): **413 days / 57 episodes** — **5.4×**. The frozen eval certifies windows that do not match when the rule fires. |
| P4 | **Flicker** | 46.6% of serving episodes last ≤2 days; 25.8 switches/yr; **19.5% of days sit inside the 3-bar transition cooldown** → confidence pinned 0.5 + sizing haircut one day in five `[VERIFIED]`. |
| P5 | **BEAR exit systematically late** | vs mechanical −15%/+15% dating over the 5 real bears (2018Q4, COVID, 2022H1, 2022Q4, 2025): last-BEAR lags the trough +3/+15/+20/+25/+48 td (**mean +22**); **93 recovery days labeled BEAR** — a BEAR-keyed sell rule fires into the rebound `[VERIFIED]`. |
| P6 | Vol-spike BEARs unvalidated | 30 of 57 serving BEAR episodes (80 days) lie entirely outside even a 10% drawdown `[VERIFIED]`; in-drawdown BEAR IC 0.575 vs 0.032 outside (n=1 day, indicative only) `[DERIVED]`. |
| P7 | **Bull-side split has no validated conditional signal** | served-artifact sanity: BEAR IC +0.277 (genuine +0.339) PASSES; BULL_CALM +0.017 / BULL_VOLATILE +0.104 (placebo-failed) / CHOPPY +0.003 all FAIL `[VERIFIED from artifact]`. 4-way split η²=0.556 vs single vol20>0.18 2-way η²=0.569 (within-corpus comparison) `[VERIFIED]`. |
| P8 | Fold-corpus regime covariate version-unstable | WF window: legacy 72.6% BULL_VOLATILE vs current-default 50.7% BULL_CALM — any fold-regime-keyed conclusion flips with the 2026-06-01 library default flip `[VERIFIED days; fold attribution DERIVED]`. |

What is GOOD `[VERIFIED]`: **BEAR entry** — zero misses on the 5 real bears, mean +8 td
after the peak, 10–75 td ahead of a mechanical −15% trigger. The hard thresholds do
exactly what the 2026-05-17 fix intended. Weak spot: slow grinds (2023 −10.3%: +37 td,
9.4% coverage).

## Ranked improvements (all zero-new-data; each motivated by a measured pathology)

1. **Consolidate to ONE label plane** (the production chain; the WF sanity gate already
   replays it) — precondition for ANY regime-keyed evidence (MoE cells, admission,
   fold corpora), not an optimization. Motivated by P2/P8.
2. **Amend the BEAR-exit prereg data spec** to the production-chain plane (or re-key the
   trigger; either way ONE plane). Motivated by P3 — highest value-per-hour on the
   strongest signal. Amending a frozen prereg = operator sign-off.
3. **Drawdown-recovery BEAR-exit overlay** (SPY-derived; Lunde–Timmermann/Pagan–Sossounov
   anchors). Motivated by P5 (+22 td overhang, 93 recovery days).
4. **Confirm-2 hysteresis on switches** — measured on the serving series: episodes
   253→138, flicker −87%, BEAR days unchanged, entry cost +1 td on fast crashes
   `[VERIFIED]`; halves the P4 cooldown burden. Asymmetric (fast-in BEAR, confirmed-out).
5. **Retire the Hurst layer** (P1) — cheapest replacement is the already-shipped
   vol20<0.18 + drift>0 rule (v2026-05-31), which simultaneously advances item 1. P7
   says a threshold rule loses nothing.
6. (Only if MoE soft routing goes live) **deploy the existing undeployed HMM** —
   persistence modeled at source, calibrated posteriors for blending (current GMM
   max-posterior median 0.98, too saturated to blend).
7. Panel dispersion/breadth regime covariates (own 145-name panel) — merges with the
   "living MoE" dispersion-gating line. (FRED VIXCLS is already ingested but 115 days
   stale — refresh before any use.)

## What NOT to change

The hard BEAR entry thresholds; the BEAR→exit-side direction (only placebo-clean cell);
CUSUM cooldown semantics. Do NOT invest in GMM refit cadence or a CHOPPY specialist
(GMM decides 15.7% of days and 0% of BEAR; CHOPPY: 4.3% occupancy, median episode 2d).

## Implication for the MoE design (orch#984)

The #984 power map (BV m=2 blocks → all-champion v1) is measured on the RESEARCH label
plane; the serving plane disagrees with it on ~30% of days and even inverts the dominant
state. Two consequences: (a) after plane consolidation the power map must be RE-DERIVED
on the production-chain plane before any Stage-A batch runs; (b) fixing P1 (the
noise-Hurst layer that manufactures the one-blob geometry) may legitimately restore MoE
degrees of freedom — the detector is the MoE's critical path.

## Named gaps (not measured, not guessed)

Committed fold manifests for the 125-fold set not located on disk (fold-plane attribution
is consistency inference); no look-ahead-free per-day IC corpus reachable (phase-A
comparisons valid relatively, not in level); live_state regime history not read (replica
validated against the WF gate replay instead); no scheduled GMM-refit surface found
(asserted only as "not found").
