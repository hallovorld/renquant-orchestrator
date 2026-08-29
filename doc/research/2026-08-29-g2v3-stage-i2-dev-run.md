# GOAL-2v3 Stage I-2 — the DEV RUN: FAIL-B (M_xgb block-t −1.1058; M0 4.0471; best base B3 4.26; s₀ 2.8854); the line pauses for an operator decision

Date: 2026-08-29 13:25:28–13:33:39 UTC (process clock, `provenance.timestamps_utc`).
Executed with `--dev-run` from the clean main commit **5269e593** in a fresh worktree,
bound to the Stage I-1 DEV_RUN bundle `i1-dev-20260829T113813Z-666484a7` (#1088) and the
Stage I-0 GATE_RUN bundle `i0-gate-20260829-f3d5bf7b` (PASS, #1083), with the prereg merged
in #1089 and the harness merged in #1090. This document is DESCRIPTIVE ONLY: it reports what
the bundle says, evaluated against the prereg text as written. It recommends nothing.

**Run ID `i2-dev-20260829T132528Z-5269e593`.** Bundle:
`doc/research/data/2026-08-29-g2v3-i2/i2-dev-20260829T132528Z-5269e593/` (`report.json` +
`g2v3_stage_i2_audit.json.gz`). Provenance validates with zero problems
`[VERIFIED — validate_i2_provenance(report, audit, repo_root) == []` from this worktree AND from a
fresh `git worktree add` at another absolute path: path identity is checked repo-relatively after
codex r1 — command in the progress doc, "Review r1"]`; the two I-2 test files pass
`[VERIFIED — pytest tests/test_g2v3_stage_i2_binding.py tests/test_g2v3_stage_i2_harness.py: 99 passed]`.

Tag convention: `[VERIFIED report <key>]` = read from `report.json`; `[VERIFIED audit <key>]` =
read from the gz audit; `[DERIVED …]` = recomputed here from the audit with the harness's own
functions (not a number the report states); `[VERIFIED log]` = the launcher's stdout capture.

## 1. Bottom line

**Outcome register row, quoted verbatim from the report (`outcome.register_row`), which quotes
the prereg §4.4 row it landed on:**

> | FAIL-B | ¬(P1 ∧ P2) | record as a failed attempt; line pauses for an operator decision |

`[VERIFIED report outcome.verdict == "FAIL-B", outcome.condition, outcome.consequence,
outcome.register == "doc/design/2026-08-29-goal2v3-stage-i2-prereg.md §4.4", outcome.binding == true]`.

| P | rule (as the report states it) | numbers | passes |
|---|---|---|---|
| **P1** | M_xgb block-t ≥ 1.0 overall @ h=13 on dependence-adjusted units AND BEAR n_eff_adj ≥ 30 on M_xgb's own OOF IC | block-t **−1.1058** vs bar 1.0 → margin **−2.1058**; BEAR n_eff_adj **98.0** vs 30 → margin +68.0 (`life: false`, `bear_ok: true`) | **false** |
| **P2** | M_xgb block-t > max(B0, B1, B2, B3 block-t) on the common sample | −1.1058 vs best base **B3 4.26** (B0 2.5681, B1 3.8038, B2 2.3995) → margin **−5.3658**; `all_bases_established: true` | **false** |
| **P3** | M_xgb block-t > s₀ block-t on the common sample | −1.1058 vs s₀ **2.8854** → margin **−3.9912** | **false** |

`[VERIFIED report pass_bar.P1, pass_bar.P2, pass_bar.P3, pass_bar.stage_i2_pass == false]`.
The report's own note: "strict inequalities on point estimates; no margin is claimed and none
is required (§4)" `[VERIFIED report pass_bar.note]`. Since P1 is false, the condition
¬(P1 ∧ P2) holds and the verdict is FAIL-B; FAIL-A (P1 ∧ P2 ∧ ¬P3) did not occur.

## 2. The determinism guard — exact reproduction of I-1

The §1.1 guard ran after the base re-fit and BEFORE any meta fit (harness order of refusal
step 7, #1090). Status **PASS**, tolerance "block-t equal to 4 decimals and n_blocks equal"
`[VERIFIED report base_refit.determinism_guard.status, .tolerance]`:

| series | expected (I-1 bundle) | observed (this re-fit) | match |
|---|---|---|---|
| B0 | 3.5042 / 622 | 3.5042 / 622 | true |
| B1 | 3.1837 / 511 | 3.1837 / 511 | true |
| B2 | 3.5915 / 622 | 3.5915 / 622 | true |
| B3 | 3.2394 / 619 | 3.2394 / 619 | true |
| s₀ | 4.1861 / 622 | 4.1861 / 622 | true |

`[VERIFIED report base_refit.determinism_guard.per_series.*.expected_block_t / observed_block_t /
expected_n_blocks / observed_n_blocks / match]`; the provenance copy is identical
`[VERIFIED report provenance.determinism_guard == base_refit.determinism_guard (validator)]`.
The consumed-bar aggregate of this re-fit equals the I-1 bundle's:
`4addcbe25f164a57afc0ea9fb0fd4e8e368a17fc292e2fe62b80fff5219d3883`, count 1508,
`matches_i1_bundle: true` `[VERIFIED report inputs.consumed_bar_check,
provenance.consumed_bar_manifest]`. The imported I-1 harness hashes to
`13c31d1266e6753bbf2890862fd8afe66081d7c351746177360d770a22775e20`, the blob at 666484a7
`[VERIFIED report provenance.i1_bundle.harness_sha256; validator]`. The re-fit's 88 fit
records and five fold row counts (train 3,389,414 / 4,908,442 / 6,432,659 / 7,893,967 /
9,194,391; OOF 1,519,028 / 1,524,217 / 1,461,308 / 1,300,424 / 1,292,613) are carried in
the audit `[VERIFIED audit base_fits (88), fold_row_counts; report base_refit.fold_row_counts]`.
The block series of every re-fitted base and s₀, passed through the harness's own
`episodes_of` + `ess_stats`, reproduce the guard's observed values exactly
`[DERIVED audit base_refit.*.block_series → 3.5042/622, 3.1837/511, 3.5915/622, 3.2394/619, 4.1861/622]`.

## 3. The stack as fitted (`report.meta`) `[VERIFIED report meta]`

| meta-fold | meta-train halves | meta-OOF half | seed | n_train_raw | n_train_used | capped | n_purged | n_oof |
|---|---|---|---|---|---|---|---|---|
| M1 | 2022H1 | 2022-07-01..2022-12-31 | 20261829 | 1,519,028 | 1,519,028 | false | 0 | 1,524,217 |
| M2 | 2022H1–2022H2 | 2023-01-01..2023-06-30 | 20262829 | 3,043,245 | 3,043,245 | false | 0 | 1,461,308 |
| M3 | 2022H1–2023H1 | 2023-07-01..2023-12-31 | 20263829 | 4,504,553 | **4,000,000** | **true** | 0 | 1,300,424 |
| M4 | 2022H1–2023H2 | 2024-01-01..2024-06-30 | 20264829 | 5,804,977 | **4,000,000** | **true** | 0 | 1,292,613 |

All four `fitted: true`. Meta-OOF rows total **5,578,562** (= 1,524,217 + 1,461,308 +
1,300,424 + 1,292,613) `[VERIFIED report meta.n_meta_oof_rows, inputs.n_meta_oof_observations]`.
The 11 meta-features are `p_B0, p_B1, p_B2, p_B3, n_abstain, regime_{BEAR,BULL_CALM,BULL_VOLATILE,CHOPPY},
b3_slow_sign, slot`; `s0_is_a_feature: false` `[VERIFIED report meta.features, meta.s0_is_a_feature]`.
NaN counts on the meta-OOF rows: `p_B1` 265,468, `p_B3` 7,844, every other feature 0;
`regime_undefined_rows` 0; `b3_slow_missing_rows` 0 `[VERIFIED report meta.feature_nan_counts_on_meta_oof,
meta.regime_undefined_rows, meta.b3_slow_missing_rows]`. B2's post-fold OOF states: 6 in folds
0–1 (OTHER, ai_chip, consumer, finance, industrial, software), 10 in fold 2 (+ datacenter_hw,
energy, giant_tech, healthcare), 11 in folds 3–4 (+ utility) `[VERIFIED report meta.b2_oof_states_by_fold]`.

**Common sample** `[VERIFIED report common_sample]`: meta-OOF rows 5,578,562; M_xgb-scored rows
5,578,562 (all of them); common **5,305,250**; excluded 273,312 = **0.048993**; attributed
`p_B1` 265,468, `p_B3` 7,844, `p_B0` 0, `p_B2` 0, `s0` 0; M0 line 5,305,250 (M0-only extra
exclusion 0, fraction 0.0).

## 4. Every series on the common sample (`report.series`)

### 4.1 Overall `[VERIFIED report series.*.overall]`

All seven common-sample series share one block set: n_blocks **472**, n_episodes 35, pairs 437,
estimator "ok" `[VERIFIED report series.*.overall.n_blocks/n_episodes/pairs/estimator]`.

| series | sample | mean block IC | sd | ρ̂₁ raw → used | n_eff_adj | **block-t** | n_scored_rows | gating |
|---|---|---|---|---|---|---|---|---|
| **M_xgb** | common | −0.002451 | 0.048154 | −0.0442 → 0.0 | 472.0 | **−1.1058** | 5,305,250 | **true** |
| M_xgb_full_meta_oof_DIAGNOSTIC_ONLY | all 5,578,562 meta-OOF rows (498 blocks, 37 episodes, 461 pairs) | −0.001730 | 0.048013 | −0.0284 → 0.0 | 498.0 | −0.8043 | 5,578,562 | false |
| M0 (unweighted z-sum) | common | 0.012307 | 0.066065 | −0.0159 → 0.0 | 472.0 | **4.0471** | 5,305,250 | false |
| B0 | common | 0.008220 | 0.069542 | −0.0272 → 0.0 | 472.0 | **2.5681** | 5,305,250 | false |
| B1 | common | 0.012098 | 0.069098 | −0.0090 → 0.0 | 472.0 | **3.8038** | 5,305,250 | false |
| B2 | common | 0.006700 | 0.060667 | −0.0115 → 0.0 | 472.0 | **2.3995** | 5,305,250 | false |
| B3 | common | 0.012289 | 0.062675 | −0.0006 → 0.0 | 472.0 | **4.26** | 5,305,250 | false |
| s₀ = −r13 | common | 0.010194 | 0.074771 | +0.0262 → 0.0262 | 447.9 | **2.8854** | 5,305,250 | false |

`passes_life_bar_DIAGNOSTIC_ONLY` is false for M_xgb and for the full-meta-OOF diagnostic,
true for M0, B0, B1, B2, B3 and s₀ `[VERIFIED report series.*.passes_life_bar_DIAGNOSTIC_ONLY]`.

### 4.2 Per regime `[VERIFIED report series.*.per_regime]` — informational per the prereg ("Per-regime block-t is reported for every series and never gates")

Shared per-regime block structure on the common sample: BEAR 98 blocks / 5 episodes / 93 pairs;
BULL_CALM 288 / 13 / 275; BULL_VOLATILE 59 / 8 / 51; CHOPPY 27 / 9 / 18; every cell "ok".

| series | BEAR (block-t / mean IC / ρ̂₁ raw / **n_eff_adj**) | BULL_CALM | BULL_VOLATILE | CHOPPY |
|---|---|---|---|---|
| M_xgb | 0.1547 / 0.000876 / −0.2170 / **98.0** | −1.7284 / −0.004818 / 0.0257 / 273.6 | −2.2898 / −0.011268 / −0.1632 / 59.0 | 3.2771 / 0.029986 / −0.2571 / 27.0 |
| M_xgb full-meta-OOF (diag; 102/290/59/47 blocks) | 0.1909 / 0.001046 / −0.2100 / 102.0 | −1.7877 / −0.004966 / 0.0282 / 274.1 | −2.2898 / −0.011268 / −0.1632 / 59.0 | 3.5233 / 0.024180 / −0.0387 / 47.0 |
| M0 | 1.4448 / 0.011747 / −0.0469 / 98.0 | 2.9486 / 0.010592 / −0.0008 / 288.0 | 1.6517 / 0.014559 / 0.0573 / 52.6 | 2.1547 / 0.027706 / −0.2189 / 27.0 |
| B0 | 0.4719 / 0.004437 / −0.1214 / 98.0 | 2.4776 / 0.008993 / 0.0134 / 280.4 | 0.8244 / 0.008508 / 0.1911 / 40.1 | 0.9714 / 0.013079 / −0.1458 / 27.0 |
| B1 | 1.9215 / 0.013215 / −0.0599 / 98.0 | 2.0597 / 0.008727 / 0.0217 / 275.8 | 1.9553 / 0.016483 / −0.0455 / 59.0 | 2.6640 / 0.034412 / −0.2675 / 27.0 |
| B2 | 0.5353 / 0.004358 / −0.0623 / 98.0 | 2.4879 / 0.007865 / 0.0079 / 283.5 | 0.2328 / 0.001932 / 0.1036 / 47.9 | 1.1324 / 0.013202 / −0.0370 / 27.0 |
| B3 | 1.7690 / 0.013266 / 0.0471 / 89.2 | 3.1280 / 0.010891 / 0.0004 / 287.8 | 1.8986 / 0.015738 / −0.1303 / 59.0 | 1.2061 / 0.016121 / −0.0262 / 27.0 |
| s₀ | 2.5366 / 0.022663 / −0.0455 / 98.0 | 1.2715 / 0.005803 / 0.0768 / 246.9 | 0.8207 / 0.006138 / −0.0878 / 59.0 | 1.2815 / 0.020645 / −0.1823 / 27.0 |

M_xgb's BEAR n_eff_adj on the common sample is **98.0** (≥ 30, `bear_ok: true`)
`[VERIFIED report series.M_xgb.per_regime.BEAR.n_eff_adj, pass_bar.P1.bear_n_eff_adj]`; the
prereg §6 anticipated that BEAR blocks after dropping 2022H1 would be fewer than I-1's 191.

### 4.3 Per meta-fold `[DERIVED audit series.*.block_series + harness episodes_of/ess_stats, sessions restricted to each meta-fold's OOF window]`

The report does not carry per-meta-fold block-t. The table below is a descriptive
decomposition: the audit's per-session block series for each series was filtered to each
meta-fold's OOF window and passed through the I-1 harness's own `episodes_of` + `ess_stats`
(same census same-day K5 episode mapping from `k5_regime_daily` on the run's SPY daily parquet,
same AR(1) floor, same ≥ 8-pair fail-close). Applied to the unfiltered series, this
recomputation reproduces the report's overall block-t, n_blocks and n_eff_adj exactly for all
eight series and every per-regime cell `[VERIFIED — recomputation == report to 4 dp, all 8
series overall + 32 per-regime cells]`. Caveat as in the I-1 record: an episode spanning a
fold boundary is split, ρ̂₁ is re-estimated within the fold, and the overall number is not the
mean of the fold numbers.

| meta-fold (OOF window) | census regime mix of the common-sample sessions | M_xgb | M_xgb full (diag) | M0 | B0 | B1 | B2 | B3 | s₀ |
|---|---|---|---|---|---|---|---|---|---|
| M1 (2022-07..12) | BEAR 95, CHOPPY 4, BULL_VOL 3 | 102 blk / IC 0.0012 / **0.2205** | 126 / 0.0038 / 0.7767 | 102 / 0.0125 / **1.5431** | 102 / 0.0035 / **0.3763** | 102 / 0.0152 / **2.2868** | 102 / 0.0046 / **0.5648** | 102 / 0.0147 / **1.9065** | 102 / 0.0246 / **2.8002** |
| M2 (2023-01..06) | BULL_CALM 106, CHOPPY 18 | 124 / 0.0034 / **0.6849** | 124 / 0.0034 / 0.6849 | 124 / 0.0074 / **1.1806** | 124 / 0.0078 / **1.3057** | 124 / 0.0064 / **0.8507** | 124 / 0.0048 / **0.9014** | 124 / 0.0070 / **1.3338** | 124 / 0.0041 / **0.5951** |
| M3 (2023-07..12) | BULL_CALM 100, BULL_VOL 14, CHOPPY 5, BEAR 3 | 122 / −0.0051 / **−1.3536** | 124 / −0.0054 / −1.4376 | 122 / 0.0164 / **3.2144** | 122 / 0.0122 / **2.0388** | 122 / 0.0138 / **2.5483** | 122 / 0.0144 / **3.1472** | 122 / 0.0126 / **2.3260** | 122 / 0.0109 / **1.4827** |
| M4 (2024-01..06) | BULL_CALM 82, BULL_VOL 42 | 124 / −0.0087 / **−2.2206** | 124 / −0.0087 / −2.2206 | 124 / 0.0131 / **2.4270** | 124 / 0.0086 / **1.7110** | 124 / 0.0136 / **2.2718** | 124 / 0.0027 / **0.5811** | 124 / 0.0153 / **2.6689** | 124 / 0.0038 / **0.7045** |

(cell = n_blocks / mean block IC / block-t; ρ̂₁ raw and n_eff_adj per cell are in the
recomputation and omitted here except where ρ̂₁ was floored above 0: M_xgb M2 ρ̂₁ 0.068 →
n_eff 108.2, M3 0.030 → 114.9; M0 M4 0.0551 → 111.0; B0 M3 0.0827 → 103.4; B1 M4 0.0495 →
112.3; B2 M3 0.016 → 118.2, M4 0.0351 → 115.6; B3 M1 0.0735 → 88.0, M3 0.0433 → 111.9;
s₀ M2 0.0325 → 116.2, M3 0.0668 → 106.7 `[DERIVED, same function]`.)

Fold-level reading, stated without interpretation: M_xgb is below 1.0 in every meta-fold and
negative in M3 and M4; M0 is above 1.0 in every meta-fold; B3 and B1 are above 1.0 in every
meta-fold except B1 in M2 (0.8507); s₀ is the largest series in M1 (2.8002) and below 1.0 in
M2 and M4. In M2 and M4 no session is excluded by the common sample (124 blocks each way), and
the base and s₀ cells coincide to 4 dp with the I-1 record's fold-2 and fold-4 cells (e.g. B0
1.3057 / 1.7110, s₀ 0.5951 / 0.7045) `[DERIVED; cf. I-1 record §2.3]`.

### 4.4 The common-sample session set `[DERIVED audit series.*.block_series set comparisons]`

The seven common-sample series share an identical 472-session block set. The full-meta-OOF
diagnostic has 498 sessions; the 26 sessions it has and the common sample lacks are 9 in
2022-08, 1 in 2022-11, 14 in 2022-12, 1 in 2023-07 (2023-07-05) and 1 in 2023-11 (2023-11-27);
by census regime CHOPPY 20, BEAR 4, BULL_CALM 2. Every one of the 26 lies in the union of the
re-fit's (B0 − B1) and (B0 − B3) block-session sets (23 in B0 − B1 within the meta-OOF period,
3 in B0 − B3: 2022-11-28, 2023-07-05, 2023-11-27) — the I-1 record's B1 ABSTAIN sessions
(§3.3) and B3 no-block sessions (§3.4; the same 7,844 unscored rows). Regime mix of the common sample: BEAR 98, BULL_CALM 288,
BULL_VOLATILE 59, CHOPPY 27; of the full meta-OOF set: BEAR 102, BULL_CALM 290,
BULL_VOLATILE 59, CHOPPY 47.

### 4.5 Secondary horizons for M_xgb — DIAGNOSTIC ONLY, never gating `[VERIFIED report series.M_xgb.secondary_horizons_DIAGNOSTIC_ONLY]`

h=1: block-t −0.5288 (472 blocks, mean IC −0.000632, ρ̂₁ 0.0994 → n_eff 386.7);
h=3: −0.2146 (mean IC −0.000354, ρ̂₁ 0.0558 → n_eff 422.1); h=39 "not computed: no
within-session 39-bar forward window on the 39-slot grid". Interpretation 6 removes the
secondary block from every other series `[VERIFIED report: only series.M_xgb carries it]`.

## 5. Descriptive facts, plainly stated

1. **M_xgb's block-t is NEGATIVE: −1.1058** on the common sample (mean block IC −0.002451
   over 472 blocks) and −0.8043 on all 5,578,562 meta-OOF rows `[VERIFIED report
   series.M_xgb.overall.block_t, series.M_xgb_full_meta_oof_DIAGNOSTIC_ONLY.overall.block_t]`.
   The fitted stack is anti-predictive out of sample on the meta-OOF period 2022-07-01..2024-06-30
   `[VERIFIED report frozen.meta_oof_period]`. Its per-regime sign is negative in BULL_CALM
   (−1.7284) and BULL_VOLATILE (−2.2898), near zero in BEAR (0.1547), positive in CHOPPY
   (3.2771, 27 blocks) `[VERIFIED report series.M_xgb.per_regime.*.block_t]`; per meta-fold it
   is 0.2205 / 0.6849 / −1.3536 / −2.2206 `[DERIVED §4.3]`.
2. **The unweighted M0 z-sum scores 4.0471**, within 0.21 of the best base (B3 4.26 − 4.0471 =
   0.2129) and above B1 (3.8038), s₀ (2.8854), B0 (2.5681) and B2 (2.3995) on the same rows
   `[VERIFIED report series.M0.overall.block_t, series.B3.overall.block_t; difference DERIVED]`.
   M0 is a diagnostic; the prereg §3 says "M0 is never the pass decision" and the report carries
   it with `gating: false` `[VERIFIED report series.M0.gating]`.
3. **The ordering of the bases and s₀ on the meta-OOF common sample differs from the I-1
   full-OOF ordering.** I-1 (2022-01..2024-06, each series on its own OOF rows; #1088):
   s₀ 4.19 > B2 3.59 > B0 3.50 > B3 3.24 > B1 3.18. Here (2022-07..2024-06, common sample):
   B3 4.26 > M0 4.05 > B1 3.80 > s₀ 2.89 > B0 2.57 > B2 2.40 `[VERIFIED report series.*.overall.block_t;
   I-1 values VERIFIED report base_refit.bases.*.overall.block_t, base_refit.s0_reference.overall.block_t
   of this same bundle]`. The bases and s₀ are the same predictions in both views (the
   determinism guard reproduced I-1 exactly, §2). The only change between the two views is the
   row set: 2022H1 is excluded (it is never meta-scored, prereg §2) and the common-sample
   exclusion removes a further 4.8993% of the meta-OOF rows (§3, §4.4). This record states that
   difference and does not explain it.
4. Every base and s₀ is above the 1.0 life bar on the common sample (2.3995–4.26)
   `[VERIFIED report series.{B0,B1,B2,B3,s0}.passes_life_bar_DIAGNOSTIC_ONLY == true]`; the life
   bar is not the pass decision for any series but M_xgb.
5. The BEAR re-verification passed for M_xgb (98.0 ≥ 30); P1 failed on the life bar alone
   `[VERIFIED report pass_bar.P1.life == false, pass_bar.P1.bear_ok == true]`.

## 6. The 14 declared interpretations, as applied `[VERIFIED report interpretations == prereg_interpretations (6) + harness_interpretations (8) == provenance.frozen_parameters.interpretations == module INTERPRETATIONS (validator)]`

1. "Surviving bases" = every base whose I-1 `passes_life_bar` is true; all four survived, so all four enter the stack. — Applied: `frozen.surviving_bases = [B0, B1, B2, B3]`; four `p_B*` meta-features.
2. Base abstain rows become NaN meta-features, never imputed; `n_abstain` carries the count; the common-sample comparison excludes rows where any series lacks a prediction. — Applied: `p_B1` NaN 265,468 and `p_B3` NaN 7,844 on the meta-OOF rows; 273,312 rows excluded (0.048993), attributed to exactly those two bases.
3. Sector code for the slow state = the B2 post-fold mapping of the fold in which the row is OOF. — Applied: `meta.b2_oof_states_by_fold` (6 / 6 / 10 / 11 / 11 states).
4. M0's per-row z-scoring uses the cross-section present at that session×slot; a row with fewer than `MIN_NAMES_PER_IC` names has no M0 value. — Applied: `n_common_m0 == n_common == 5,305,250`; M0-only extra exclusion 0.
5. Determinism guard tolerance: block-t equal to 4 decimals and n_blocks equal. — Applied: PASS on all five series (§2).
6. Secondary horizons h=1, h=3 reported for M_xgb, diagnostic only. — Applied: §4.5; absent from every other series.
7. [harness] `meta_fold` in the seed formula is the M-number: seeds 20261829, 20262829, 20263829, 20264829; `random_state` 20260829 for every meta-fit. — Applied: `meta.folds[*].seed` as listed; `frozen.meta_xgb_params.random_state = 20260829`.
8. [harness] The guard additionally requires s₀ to reproduce 4.1861 / 622, the consumed bars to aggregate to the I-1 manifest, and the I-1 harness to be byte-identical to the blob at 666484a7. — Applied: s₀ match true; `consumed_bar_check.matches_i1_bundle: true`; `harness_sha256 13c31d12…` (§2).
9. [harness] Undefined prior-close regime → all four indicators 0; `b3_slow_sign` NaN passed as missing; both counts reported. — Applied: `regime_undefined_rows: 0`, `b3_slow_missing_rows: 0`.
10. [harness] Meta-training rows = every base-OOF row of the training halves; no row dropped for abstains; purge via `apply_purge`. — Applied: `n_train_raw` = the cumulative sum of the base-OOF fold row counts (1,519,028; 3,043,245; 4,504,553; 5,804,977) `[DERIVED from report base_refit.fold_row_counts]`; `n_purged: 0` in every meta-fold.
11. [harness] M0 = the plain sum of the available per-base z's; a base with < 2 finite values or zero spread contributes nothing. — Applied: M0 line 5,305,250 rows; no separate trace beyond interpretation 4.
12. [harness] P1 is evaluated on the common sample; M_xgb on its full meta-OOF rows is reported beside it, never gating; unestablished fails. — Applied: P1 on the common sample (−1.1058, BEAR 98.0); `M_xgb_full_meta_oof_DIAGNOSTIC_ONLY` −0.8043 with `gating: false`; every estimator "ok", nothing unestablished.
13. [harness] The sector code is carried as the per-fold list of post-fold B2 OOF states; enters the stack only through `p_B2`. — Applied: `meta.b2_oof_states_by_fold`; no sector feature in `meta.features`.
14. [harness] The excluded fraction is reported over the meta-OOF rows where M_xgb has a prediction (every meta-OOF row), attributed per base; the M0-only extra exclusion separately. — Applied: `n_mxgb_scored_rows == n_meta_oof_rows == 5,578,562`; `excluded_by_series`; `m0_only_extra_excluded: 0`.

## 7. Provenance `[VERIFIED report provenance unless noted]`

| item | value |
|---|---|
| run_id / status | `i2-dev-20260829T132528Z-5269e593` / `DEV_RUN`; `outcome.binding: true` |
| source | commit `5269e5939e239c32f79f3c907782356aa0b7d578` (main at the time of the run; `origin/main` at write-up), `clean_tree: true`, `n_dirty: 0` (git status ignoring only the bar store and the output root) |
| invocation | `scripts/experiments/g2v3_stage_i2_stack.py --dev-run`, cwd = the worktree, python `/Users/renhao/git/github/RenQuant/.venv/bin/python` 3.10.20, `G2V3_BAR_STORE` = the audited store under `wt-gate/scripts/experiments/g2v3_bars` (the store #1088 consumed) |
| versions | xgboost 2.1.4, numpy 2.0.2, pandas 2.3.3, scipy 1.13.1 `[VERIFIED report versions]` |
| UTC start / end | `2026-08-29T13:25:28Z` / `2026-08-29T13:33:39Z` (process clock); `generated_at 2026-08-29T13:33:39+00:00`; launcher log stamps 13:25:27Z start / 13:33:40Z end, exit 0 `[VERIFIED log]` |
| gate bundle bound | `i0-gate-20260829-f3d5bf7b`, frozen commit `f3d5bf7bd75ffa9c0fb59f8c3bfa98fa509e8779`, verdict PASS, BEAR n_eff_adj 191.0; report `da41a706…`, audit `dd5127d7…`, provenance `6103cb25…`, input-manifest aggregate `a878f1ca…` count 2124 — each equal to the file on disk `[VERIFIED validator]` |
| I-1 bundle bound | `i1-dev-20260829T113813Z-666484a7`, source commit `666484a7ab37dc9f88dd5692f8d9e90f3aab9332`; report sha256 `666d9c6a9a2286af4215399aebbd07a2fda8efafc6b5440d8d39ea6b9e1e1542`, audit gz `d124d8f2a8766edf7d4a6f767206444467f05fa3bb8dec1818a76b01b2cd3082`, consumed-bar aggregate `4addcbe25f164a57afc0ea9fb0fd4e8e368a17fc292e2fe62b80fff5219d3883` over 1508 files, harness `13c31d12…`, expected block-t/n_blocks as in §2, surviving bases all four — each equal to the bound constants and to the files on disk `[VERIFIED validator]` |
| store manifest check | strict; n_needed 1512, n_required_in_audit 1508, **n_hashed 1508**, missing 0; absent_from_audit = expected = {TLT, XLC, XLRE, XLV} |
| consumed-bar manifest | count **1508**, aggregate `4addcbe2…` == the I-1 bundle's (`matches_i1_bundle: true`); rebuilt from `audit.consumed_sha256` with the recorded method `[VERIFIED validator]` |
| other inputs | census audit = the gate bundle's audit (sha256 `dd5127d7…`); pinned `renquant-strategy-104/configs/strategy_config.json` sha256 `78e0d727ab3facd554ab2dfa20ab42c13f00b34e08b804921ced951ac9006d45`; sector_map `43e919e2…`; sector_etf_map `29dd6259…`; SPY daily `763580bd…` — all identical to the I-1 run's |
| panel | 983 sessions (2020-08-03..2024-06-28), 1,508 names, 10,487,004 observations, 7,097,590 base-OOF, 5,578,562 meta-OOF `[VERIFIED report inputs]` |
| `report.json` | 66,036 bytes, sha256 `8a2804fd0df7de3665c6f568b6dfe9ff3db91b5643096ddedc4addfcb8ac0a87` `[VERIFIED shasum -a 256]` |
| `g2v3_stage_i2_audit.json.gz` | 529,055 bytes, sha256 `6629d29a7b071342a20b188e15cf40c9c6c219ebabb4a4eafbd85921ecd9d128`; uncompressed 1,529,481 bytes, sha256 `ca3e6dc3d1333c3cd8b3f41b72bb785fb72fb72637da6328b107f8ae325b14be` `[VERIFIED shasum -a 256]` (the harness writes the audit gzipped; nothing in the bundle exceeds 5 MB, so no file was re-packed — the I-0/I-1 convention) |
| validation | `validate_i2_provenance(report, audit, repo_root)` → `[]` from any checkout: reproduced from this worktree and from a fresh `git worktree add <tmp> research/g2v3-stage-i2-dev-run` at another absolute path (command in the progress doc, "Review r1"); `tests/test_g2v3_stage_i2_binding.py` + `tests/test_g2v3_stage_i2_harness.py` → 99 passed `[VERIFIED pytest, 2026-08-29]` |

Frozen block as run `[VERIFIED report frozen]`: the I-1 block verbatim (h=13, 39 slots, screen
slots 13..25, dev window 2020-08-01..2024-06-30, seed base 20260828, I-1 XGB params, row cap
4,000,000, min_sector_rows 50,000, five folds, purge 13, ≥ 100 names per IC, ≥ 8 pairs, life
bar 1.0, 11 features, B1 lag 1, vz 60 / 48, B3 slow 60) plus the I-2 constants: meta folds
M1..M4 as in §3, meta-OOF period 2022-07-01..2024-06-30, purge 13, seed base 20260829 with
formula "20260829 + 1000*meta_fold", meta XGB params (reg:squarederror, max_depth 2,
n_estimators 200, learning_rate 0.05, subsample 0.8, colsample_bytree 1.0, min_child_weight 50,
hist, random_state 20260829, n_jobs 8), row cap 4,000,000, 11 meta-features, label horizon 13,
secondary {1, 3}, P1 bar 1.0, BEAR min 30.0, series [M_xgb, M0, B0, B1, B2, B3, s0], the
outcome register verbatim. The validator checks every one of these against the module
constants and the prereg-bound blocks.

## 8. What this does not show

- **Development window only.** Every number is meta-out-of-fold inside 2022-07..2024-06 on
  bases fitted out-of-fold inside 2022-01..2024-06. The evaluation window 2024-07-01..2026-06-30
  remains sealed: no fit, no score, no peek.
- **No live implication.** No serving path, no rq105 change, no strategy-config change, no pin
  advance, no production path written. The run wrote only
  `doc/research/data/2026-08-29-g2v3-i2/<run_id>/`.
- **No cost.** Block-t on OOF IC is a signal-quality screen, not a net-of-cost claim (prereg
  §6); the standing Phase −1 prior (intraday alpha net-edge NEGATIVE at IC 0.03) is untouched
  by this run.
- **Point estimates only.** P1/P2/P3 are strict inequalities on point estimates; no uncertainty
  on any difference (M0 − B3, B3 − B1, s₀ − B0, …) is defined by the prereg and none is computed.
- **One meta-learner, one attempt.** The prereg allows "No third meta-learner, no feature added
  to the stack, and no change to the bar after observing the run"; nothing here says what a
  different stack would do.
- **The base/s₀ ordering on the meta-OOF period is stated, not explained** (§5.3). The
  common-sample rows are 95.1% of the meta-OOF rows and the meta-OOF period is 4 of the 5
  base-OOF halves; no decomposition of the ordering change is attempted.
- **M0 is a diagnostic.** Its 4.0471 is not a pass, was not gated, and is not preregistered as
  a candidate for anything.

## 9. NEXT — the register's consequence, and the questions it leaves for the operator

By the prereg §4.4 row the run landed on, the consequence is: **"record as a failed attempt;
line pauses for an operator decision."** This PR is the record. The line is paused. Nothing
else is unblocked by this document; no rerun is planned; the sealed window stays untouched.

The prereg anticipates, without choosing among them, the following options. They are listed
here as questions for the operator, not as recommendations:

1. **A second I-2 attempt?** The prereg: "A second I-2 attempt (if the operator asks for one)
   is a new prereg with its own number." Does the operator want a new I-2 preregistration
   (its own PR, frozen before any fit), and if so with what changed — inputs, meta-learner,
   folds, or bar?
2. **Promote a single base or the unweighted M0 to a confirmatory prereg?** The parent design's
   PASS branch is "write the confirmatory prereg against the SEALED window"; this run did not
   PASS. The FAIL-A row names "promote s₀ itself to a confirmatory prereg" as a candidate for
   the operator's decision; FAIL-B names no candidate. On the common sample the highest series
   are B3 (4.26), M0 (4.0471, diagnostic) and B1 (3.8038); on the I-1 full-OOF rows the highest
   is s₀ (4.1861). Does the operator want any single series carried to a confirmatory
   preregistration on the sealed window, and if so which one and on what preregistered bar?
3. **Close the line?** The FAIL-A row lists "close the line" as the other candidate. Does the
   operator close GOAL-2v3's intraday-granularity line here, with this record as its closeout?

Whichever the operator chooses, the S3-c live flip remains an explicit operator ask (prereg
§6) and is not touched by any of the above.

## Corrections

- **2026-08-29, review r1 (Codex, MED).** The first version of this document (and of the
  progress doc) stated `validate_i2_provenance(report, audit, repo_root) → []` unconditionally.
  That reproduces only from the run's own worktree: the harness compares the recorded
  `inputs.census_audit.path` string against the importing checkout's `GATE_AUDIT`, so from any
  other checkout the validator returns exactly one line (the path string) while every hash
  check passes — the recorded sha256 `dd5127d7…` is the committed gate audit's. The claim is
  now stated with that condition in the header, in §7 "validation", and in the progress doc.
  No number in the bundle changed; `report.json` and the audit are untouched (sha256 as in §7).
  The harness is the preregistered #1090 module at the run's source commit `5269e593`; the
  bundle was produced by that commit and is untouched.
- **2026-08-29, review r1 fix (same PR, next commit).** The checkout-independent check landed:
  `validate_i2_provenance` now resolves the recorded `inputs.census_audit.path` against the
  recorded `provenance.source.repo_root` and requires the repo-relative path to be the gate
  bundle's `<dir>/<audit_file>` and the file at `<repo_root>/<relative>` to hash to the recorded
  and bound sha256 (`gate_bundle.dir` / `i1_bundle.dir` likewise; future runs also record
  `inputs.<x>.path_relative`). The claim in the header and in §7 "validation" is unconditional
  again — `[]` from this worktree and from a fresh `git worktree add` at another absolute path
  `[VERIFIED 2026-08-29]` — with the command in the progress doc, "Review r1". The same defect in
  `validate_i1_provenance` (the merged I-1 bundle, #1088) is corrected by
  `g2v3_stage_i2_stack.validate_i1_provenance`, because the I-1 harness file is frozen by the §1
  binding `I1_HARNESS_SHA256` and cannot be edited without un-binding this line. The validator
  is not fit code: no number in the bundle changed (sha256 as in §7).
