# Regime detector assessment — measured (2026-08-17)

STATUS: research memo (docs only). Operator-directed ("regime detector有没有提升空间？
我要的是科学的严谨的深入的research的结论"). All numbers are measured from repo data by
the three committed, deterministic, read-only derivation scripts under
`doc/research/data/` (see **Reproducibility** below); the two most damning findings were
independently re-derived (double-audit) before this memo was written.

**Provenance tags** (LONG row 10). Every number cites its artifact key or command.
Abbreviations, all committed alongside this memo and regenerated in-session:
- `M:` = `doc/research/data/2026-08-17-regime-detector-measurements.json`
- `P:` = `doc/research/data/2026-08-17-regime-detector-posteriors-ic.json`
- `R:` = `doc/research/data/2026-08-17-regime-detector-replication.json`
- `MF:` = `doc/research/data/2026-08-17-regime-detector-manifest.json` (source paths +
  sha256, date bounds, detector/config versions, seeds, algorithms, commands)

## Verdict

**Room for improvement is large, but it is mostly METROLOGY (one label plane instead of
four) and EXIT-SIDE TIMING — not a fancier model.** The BEAR pole is genuinely good and
must not be touched. The bull-side 4-way split adds nothing measurable over a single
vol threshold, and the layer that decides 63% of serving days
`[VERIFIED — P:posterior_and_attribution.decision_source_pct.hurst_momentum_bull = 63.2]`
is statistically indistinguishable from noise.

## Detector as-built (not what its name says)

There is **no HMM in production**. Three implementations coexist:
1. **Serving**: `kernel/regime.py::detect_regime` chain Hurst → CUSUM → GMM →
   BEAR-hard-override (+ disabled TrendOverlay). BEAR override first (20d vol>0.35 OR
   20d ret<−0.08 OR 5d vol>0.25 OR 5d ret<−0.04, or GMM P(BEAR)>0.5); Hurst MOMENTUM
   (H>0.65 on a 63d R/S window) routes most days; GMM (static 3-cluster artifact,
   as_of 2026-05-22 `[VERIFIED — R:gmm_artifact.as_of_date]`, **no CHOPPY cluster**
   `[VERIFIED — R:gmm_artifact.cluster_labels = BULL_CALM/BULL_VOLATILE/BEAR]`, no
   refit job found `[VERIFIED — grep for spy-gmm over launchd plists + scripts/;
   absence claim]`) decides the remainder. Posteriors are computed; the label is hard;
   confidence feeds sizing only. Lookahead hygiene clean (forward filtering, causal
   windows) `[VERIFIED — code read: kernel/regime.py::detect_regime]`.
2. **Research/WF**: `renquant_common/hmm_regime_labels.py` — a self-described
   "stateless approximation": log (not simple) returns, current-bar-excluded windows, a
   DIFFERENT single-window Hurst, and a version-gated BULL_CALM rule (default flipped
   2026-06-01) `[VERIFIED — code read: renquant_common/hmm_regime_labels.py]`.
3. A real Hamilton-1989 HMM (`kernel/regime_hmm.py` + trainer) exists, **undeployed**
   (no trained artifact on disk; config points at the GMM) `[VERIFIED — code read:
   kernel/regime_hmm.py + artifact absence under artifacts/prod/]`.

Serving decision attribution (replica 2016-11-01..2026-08-14, 2,459 td
`[VERIFIED — M:span, M:stats_S.n_days]`). Replica validity: reproduces the WF gate's
production-chain replay counts EXACTLY (replica 454/41/41/55 vs served artifact
per-regime n_dates over the sanity window `[VERIFIED — R:wf_replay_counts.exact_match
= true]`) and the committed 08-08 posterior snapshot within 1.42pp max per-regime
occupancy difference `[VERIFIED — R:snapshot_agreement.max_abs_diff_pp = 1.42]`.
Attribution `[VERIFIED — P:posterior_and_attribution.decision_source_pct]`:
Hurst-momentum→bull **63.2%**, GMM 15.7%, hard-BEAR 12.6%, Hurst+below-MAs→BEAR 4.2%,
vol-cluster→CHOPPY 3.8% (= 3.1 + 0.7), Hurst-reversion 0.5%. GMM contributes **zero**
BEAR decisions beyond the hard thresholds `[VERIFIED — P:posterior_and_attribution.
final_by_source has no gmm_bear source]`.

## Measured pathologies

| # | pathology | the number |
|---|---|---|
| P1 | **Hurst layer ≈ noise, decides 63% of days** | kernel `compute_hurst` on 63d WHITE NOISE: 84.6% of draws H>0.65 (n=500, seed 42); **independently re-derived: 89.0% (n=300, seed 20260817)** `[VERIFIED ×2 — R:hurst_null; seeds committed in MF:seeds]`. H<0.52 fires on 0.2%/0.0% of noise draws `[VERIFIED — R:hurst_null.share_H_lt_0.52]` → the CHOPPY-via-Hurst route is dead (0.5% of days `[VERIFIED — P:posterior_and_attribution.decision_source_pct.hurst_reversion]`). |
| P2 | **Four label planes, 25–70% agreement** | serving vs research-default 70.0% same-day, 74.4% lag-1 `[VERIFIED — M:agreement.S_vs_V_same_day = 0.6999, .S_vs_V_lag1 = 0.7442]`; serving vs legacy **25.2%** `[VERIFIED — M:agreement.S_vs_L = 0.2517]`. Occupancy contradictions: serving 71.5% BULL_CALM `[VERIFIED — M:stats_S.occupancy_pct]` vs legacy 78.2% BULL_VOLATILE `[VERIFIED — M:stats_L.occupancy_pct]` vs GMM-argmax 53/44/3 (no CHOPPY) `[VERIFIED — P:posterior_and_attribution.gmm_dominant_occupancy_pct]`. |
| P3 | **BEAR-exit prereg data plane ≠ runtime trigger plane** | prereg episodes from GMM-posterior argmax: **77 BEAR days / 9 episodes** (re-derived deterministically from the committed `doc/research/data/2026-08-08-regime-posteriors.csv`: exactly 77/9 `[VERIFIED ×2 — R:prereg_plane.bear_days_argmax = 77, .bear_episodes_argmax = 9]`); runtime key (production chain): **413 days / 57 episodes** `[VERIFIED — M:stats_S.occupancy.BEAR = 413; M:bear_episodes_serving (57 rows)]` — **5.4×** `[DERIVED — 413/77; R:prereg_plane.ratio_days]`. The frozen eval certifies windows that do not match when the rule fires. |
| P4 | **Flicker** | 46.6% of serving episodes last ≤2 days `[VERIFIED — M:stats_S.flicker_share_of_episodes = 0.466]`; 25.8 switches/yr `[VERIFIED — M:stats_S.switches_per_year]`; **19.5% of days sit inside the 3-bar transition cooldown** `[VERIFIED — M:confidence_stats.share_days_in_transition = 0.1952]` → confidence pinned 0.5 + sizing haircut one day in five `[VERIFIED — code read: kernel/regime.py transition handling]`. |
| P5 | **BEAR exit systematically late** | vs mechanical −15%/+15% dating over the 5 real bears (2018Q4, COVID, 2022H1, 2022Q4, 2025): last-BEAR lags the trough +3/+15/+20/+25/+48 td `[VERIFIED — M:bear_lag_S_vs_15pct.last_bear_minus_trough_td]` (**mean +22** `[DERIVED — mean of those five]`); **93 recovery days labeled BEAR** (trough day through +15% recovery exit; 88 strictly after the trough) `[VERIFIED — R:recovery_days.total_from_trough_incl = 93, .total_strictly_after = 88]` — a BEAR-keyed sell rule fires into the rebound. |
| P6 | Vol-spike BEARs unvalidated | 30 of 57 serving BEAR episodes (80 days) lie entirely outside even a 10% drawdown `[VERIFIED — M:false_alarms_S_vs_10pct (30 rows, 80 days)]`; BEAR IC 0.575 in validated episodes (n=37 phase-A days) vs 0.032 in false-alarm episodes (n=1 day, indicative only) `[VERIFIED — R:bear_ic_split; DERIVED split definition documented there]`. |
| P7 | **Bull-side split has no validated conditional signal** | served-artifact sanity: BEAR IC +0.277 (genuine +0.339) PASSES; BULL_CALM +0.017 / BULL_VOLATILE +0.104 (placebo-failed) / CHOPPY +0.003 all FAIL `[VERIFIED — artifacts/prod/panel-ltr.alpha158_fund.json metadata.wf_gate_metadata.sanity_regime_ic; mirrored R:wf_replay_counts.artifact_sanity_regime_ic]`. 4-way split η²=0.556 vs single vol20>0.18 2-way η²=0.569 (within-corpus comparison) `[VERIFIED — P:phase_a_ic.by_serving_regime._eta2 = 0.5559, .by_vol_2way_fixed018._eta2 = 0.5693]`. |
| P8 | Fold-corpus regime covariate version-unstable | WF comparability window (2019-01-14..2026-03-02, 1,792 td): legacy 78.1% BULL_VOLATILE vs current-default 54.5% BULL_CALM `[VERIFIED — M:occ_wf_window_pct.L.BULL_VOLATILE = 78.1, .V.BULL_CALM = 54.5]` — any fold-regime-keyed conclusion flips with the 2026-06-01 library default flip `[VERIFIED days; fold attribution DERIVED — committed fold manifests not on disk, see Named gaps]`. |

What is GOOD: **BEAR entry** — zero misses on the 5 real bears, mean +8 td after the
peak `[VERIFIED — M:bear_lag_S_vs_15pct.lag_vs_peak_td = 14/3/12/5/6; mean DERIVED]`,
10–75 td ahead of a mechanical −15% trigger `[VERIFIED — M:bear_lag_S_vs_15pct.
lag_vs_trigger_td = −49/−10/−75/−23/−26]`. The hard thresholds do exactly what the
2026-05-17 fix intended. Weak spot: slow grinds (2023 −10.3%: +37 td, 9.4% coverage
`[VERIFIED — M:bear_lag_S_vs_10pct 2023-07-31 episode: depth −0.1029,
lag_vs_peak_td 37, decline_coverage 0.094]`).

## Ranked improvements (all zero-new-data; each motivated by a measured pathology)

1. **Consolidate to ONE label plane** (the production chain; the WF sanity gate already
   replays it) — precondition for ANY regime-keyed evidence (MoE cells, admission,
   fold corpora), not an optimization. Motivated by P2/P8.
2. **Amend the BEAR-exit prereg data spec** to the production-chain plane (or re-key the
   trigger; either way ONE plane). Motivated by P3 — highest value-per-hour on the
   strongest signal. Amending a frozen prereg = operator sign-off.
3. **Drawdown-recovery BEAR-exit overlay** (SPY-derived; Lunde–Timmermann/Pagan–Sossounov
   anchors). Motivated by P5 (+22 td overhang, 93 recovery days).
4. **Confirm-2 hysteresis on switches** — measured on the serving series (symmetric
   confirm-2, rule spec in `MF:algorithms.hysteresis`): episodes 253→138, flicker −87.3%,
   BEAR days 413→414 (+1), entry cost +1 td on fast crashes
   `[VERIFIED — R:hysteresis]`; halves the P4 cooldown burden. Recommended production
   shape is asymmetric (fast-in BEAR, confirmed-out) — that variant's numbers would need
   their own measurement before implementation.
5. **Retire the Hurst layer** (P1) — cheapest replacement is the already-shipped
   vol20<0.18 + drift>0 rule (v2026-05-31), which simultaneously advances item 1. P7
   says a threshold rule loses nothing.
6. (Only if MoE soft routing goes live) **deploy the existing undeployed HMM** —
   persistence modeled at source, calibrated posteriors for blending (current GMM
   max-posterior median 0.98 `[VERIFIED — P:posterior_and_attribution.gmm_max_posterior.
   median]`, too saturated to blend).
7. Panel dispersion/breadth regime covariates (own 145-name panel) — merges with the
   "living MoE" dispersion-gating line. (FRED VIXCLS is already ingested but 115
   calendar days stale — last row 2026-04-24 vs memo date 2026-08-17
   `[VERIFIED — R:vixcls_staleness]` — refresh before any use.)

## What NOT to change

The hard BEAR entry thresholds; the BEAR→exit-side direction (only placebo-clean cell);
CUSUM cooldown semantics. Do NOT invest in GMM refit cadence or a CHOPPY specialist
(GMM decides 15.7% of days and 0% of BEAR `[VERIFIED — P:posterior_and_attribution.
decision_source_pct, .final_by_source]`; CHOPPY: 4.3% occupancy, median episode 2d
`[VERIFIED — M:stats_S.occupancy_pct.CHOPPY, M:stats_S.episode_stats.CHOPPY.
median_len]`).

## Implication for the MoE design (orch#984)

The #984 power map (BV m=2 blocks → all-champion v1) is measured on the RESEARCH label
plane; the serving plane disagrees with it on ~30% of days `[DERIVED — 1 −
M:agreement.S_vs_V_same_day (0.6999)]` and even inverts the dominant state. Two
consequences: (a) after plane consolidation the power map must be RE-DERIVED on the
production-chain plane before any Stage-A batch runs; (b) fixing P1 (the noise-Hurst
layer that manufactures the one-blob geometry) may legitimately restore MoE degrees of
freedom — the detector is the MoE's critical path.

## Corrections (2026-08-17, review round 1 — visible per LONG row 10)

The first committed version of this memo carried these numbers from the (then
uncommitted) session scratchpad; re-derivation under the committed scripts corrects:

1. **P1 primary null share**: was "86.2% (500 sims)". The original session seed was not
   preserved; under the committed seed 42 (n=500) the share is **84.6%**. The
   independent re-derivation (n=300) reproduces **89.0%** exactly under committed seed
   20260817. The claim (Hurst-MOMENTUM indistinguishable from white noise at the 0.65
   threshold) is unchanged.
2. **P8 percentages**: were "legacy 72.6% BULL_VOLATILE vs current-default 50.7%
   BULL_CALM". Those divided the WF-window occupancy counts (1399 / 977) by an
   inconsistent denominator (1927); the window holds 1,792 serving-aligned trading days,
   giving **78.1% / 54.5%** `[VERIFIED — M:occ_wf_window, M:occ_wf_window_n_days]`.
   The raw counts were and are correct; the contradiction the row demonstrates gets
   stronger, not weaker.
3. **Replica-vs-snapshot agreement**: was "within 1.4pp"; the measured max per-regime
   occupancy difference is **1.42pp**.
4. **Item 4 hysteresis**: was "BEAR days unchanged"; precisely **413→414 (+1 day)**.
5. **P5 "93 recovery days"**: definition made precise — 93 counts BEAR-labeled days
   from the mechanical trough day (inclusive) through the +15% recovery exit; strictly
   after the trough it is 88.

## Reproducibility

Committed, deterministic, read-only derivation scripts (run in order; ~4 min total):

```
~/git/github/RenQuant/.venv/bin/python doc/research/data/2026-08-17-regime-detector-measurements.py
~/git/github/RenQuant/.venv/bin/python doc/research/data/2026-08-17-regime-detector-posteriors-ic.py
~/git/github/RenQuant/.venv/bin/python doc/research/data/2026-08-17-regime-detector-replication.py
```

- Inputs are clamped to 2026-08-14, so later SPY bars do not change results; a re-run on
  2026-08-17 (after two more bars landed) reproduced every original measurement key
  value-for-value (0 diffs across all keys of the measurements JSON).
- `MF:` (the manifest) records every source path + sha256 (SPY parquet whole-file and
  clamped-slice, strategy config, GMM artifact, served panel artifact, 08-08 posterior
  snapshot, phase-A corpus, VIXCLS), date bounds, detector params, code-repo git heads,
  the Hurst-null seeds, and the bear-dating / hysteresis / episode / prereg-plane
  algorithms.
- Intermediate series are committed as CSV:
  `2026-08-17-regime-detector-label-series.csv` (serving/research/legacy labels,
  confidence, transition flag) and `2026-08-17-regime-detector-posterior-series.csv`
  (per-day GMM posteriors, Hurst, decision source).
- The phase-A IC corpus (`experiments/phase_a_data`, ~4.7 MB) is a local extraction and
  is NOT committed; `MF:sources.phase_a_*` pins it by path + sha256. Phase-A-derived
  rows (P6, P7 η²) are relative comparisons within that corpus (see Named gaps).
- The serving replica imports production code read-only (`kernel/regime.py` from the
  umbrella, `renquant_common.hmm_regime_labels`); no production path is written.

## Named gaps (not measured, not guessed)

Committed fold manifests for the 125-fold set not located on disk (fold-plane attribution
is consistency inference); no look-ahead-free per-day IC corpus reachable (phase-A
comparisons valid relatively, not in level); live_state regime history not read (replica
validated against the WF gate replay instead); no scheduled GMM-refit surface found
(asserted only as "not found").
