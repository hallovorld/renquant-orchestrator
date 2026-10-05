# GOAL-2v3 Stage I-1 — the DEV RUN: all four bases pass the life screen (block-t 3.18–3.59); the I-2 trigger fires by 0.087; the naive s₀ reference scores 4.19

Date: 2026-08-29 11:38:13–11:45:05 UTC (process clock, `provenance.timestamps_utc`).
Executed with `--dev-run` from the clean main commit **666484a7** in a fresh worktree,
authorized by the Stage I-0 GATE_RUN bundle `i0-gate-20260829-f3d5bf7b` (PASS, #1083),
with the harness merged in #1084 and the preregistration merged in #1076. This document
is DESCRIPTIVE ONLY: it reports what the bundle says, evaluated against the prereg text
as written. It recommends nothing.

**Run ID `i1-dev-20260829T113813Z-666484a7`.** Bundle:
`doc/research/data/2026-08-29-g2v3-i1/i1-dev-20260829T113813Z-666484a7/` (`report.json` +
`g2v3_stage_i1_audit.json.gz`). Provenance validates with zero problems
`[VERIFIED — validate_i1_provenance(report, audit, repo_root) == []]`; the three provenance /
gate-binding / gate-bundle test files pass `[VERIFIED — pytest: 49 passed]`.

Tag convention: `[VERIFIED report <key>]` = read from `report.json`; `[VERIFIED audit <key>]` =
read from the gz audit; `[DERIVED …]` = recomputed here from the audit with the harness's own
functions (not a number the report states); `[VERIFIED log]` = the launcher's stdout capture.

## 1. Bottom line

| base | block-t @ h=13 (overall) | passes life bar (≥ 1.0) | beats B0 | source |
|---|---|---|---|---|
| **B0 pooled (control)** | **3.5042** | true | — | `[VERIFIED report bases.B0.overall.block_t]` |
| B1 regime-conditioned | 3.1837 | true | false | `[VERIFIED report bases.B1.overall.block_t, base_vs_b0.B1]` |
| **B2 sector-conditioned** | **3.5915** | true | **true** | `[VERIFIED report bases.B2.overall.block_t, base_vs_b0.B2]` |
| B3 macro-trend-conditioned | 3.2394 | true | false | `[VERIFIED report bases.B3.overall.block_t, base_vs_b0.B3]` |
| s₀ = −r13 (naive reference, not a base, not gated) | 4.1861 | (not gated) | — | `[VERIFIED report s0_reference.overall.block_t]` |

**(a) Preregistered life-screen verdict, per base.** The prereg's bar (design doc, "Stage I-1"
section): "life bar: block-t ≥ 1.0 at h=13 on dependence-adjusted units, reported overall AND
per regime … A base passes only on the overall bar". Every base's `passes_life_bar` is `true`
`[VERIFIED report bases.*.passes_life_bar]`; the report's own bar string is
"block-t >= 1.0 overall @ h=13 on dependence-adjusted units" `[VERIFIED report bases.*.life_bar]`.

**The prereg's Stage I-2 trigger, quoted as written** (design doc, last paragraph of the Stage
I-1 section): *"**Stage I-2 trigger:** at least one of B1/B2/B3 passes AND beats B0's block-t
(conditioning must earn its complexity over the pooled control). Otherwise I-1 is recorded as
a failed attempt and the line pauses for an operator decision."* Evaluated literally:
B2 passes (3.5915 ≥ 1.0) and 3.5915 > 3.5042, so the trigger fires. The report records
`stage_i2_trigger.fired: true` with rule text "at least one of B1/B2/B3 passes the life bar AND
beats B0's block-t" `[VERIFIED report stage_i2_trigger]`. The margin is
**B2 − B0 = 3.5915 − 3.5042 = 0.0873 block-t units** `[DERIVED from the two report values]`.
The prereg's rule contains no margin, no minimum difference, and no significance requirement
on the comparison; it is a strict inequality on two point estimates. B1 and B3 pass the bar but
do not beat B0 (3.1837 and 3.2394 < 3.5042).

**Kill-margin re-verification the I-0 section asked for.** The I-0 text says "the Stage I-1
report must re-estimate ρ̂₁ on each real base's own OOF IC and re-verify the kill margin (a base
whose own n_eff_adj falls below the bar fails regardless of the I-0 proxy)"; the bar is BEAR
n_eff_adj ≥ 30. Each base's own BEAR n_eff_adj: B0 191.0, B1 105.0, B2 191.0, B3 190.0
`[VERIFIED report bases.*.per_regime.BEAR.n_eff_adj]` — all ≥ 30. (B1's 105 is lower than
the others' 191 because B1 abstained on the whole fold-0 BEAR half-year; §3.)

## 2. The tables

### 2.1 Overall, per base and s₀ (`report.bases.*.overall`, `report.s0_reference.overall`) `[VERIFIED report]`

| series | n_blocks | episodes | pairs | mean block IC | sd | ρ̂₁ raw → used | n_eff_adj | **block-t** | n_scored_rows |
|---|---|---|---|---|---|---|---|---|---|
| B0 | 622 | 48 | 574 | 0.010911 | 0.077655 | −0.0281 → 0.0 | 622.0 | **3.5042** | 7,097,590 |
| B1 | 511 | 42 | 469 | 0.010403 | 0.073539 | +0.0044 → 0.0044 | 506.5 | **3.1837** | 5,732,324 |
| B2 | 622 | 48 | 574 | 0.009603 | 0.066687 | −0.0235 → 0.0 | 622.0 | **3.5915** | 7,097,590 |
| B3 | 619 | 48 | 571 | 0.009506 | 0.073007 | −0.0364 → 0.0 | 619.0 | **3.2394** | 7,089,746 |
| s₀ | 622 | 48 | 574 | 0.014444 | 0.086051 | −0.0111 → 0.0 | 622.0 | **4.1861** | 7,097,590 |

Estimator = "ok" on every row (≥ 8 episode-internal pairs) `[VERIFIED report *.overall.estimator]`.
Note that B2's higher block-t than B0 comes with a LOWER mean block IC (0.009603 vs 0.010911)
and a lower sd (0.066687 vs 0.077655); the ordering is a ratio effect, not a mean-IC effect.

### 2.2 Per regime (`report.bases.*.per_regime`, `report.s0_reference.per_regime`) `[VERIFIED report]` — informational per the prereg ("per-regime numbers inform Stage I-2 weighting, never the pass decision")

| regime | B0 | B1 | B2 | B3 | s₀ |
|---|---|---|---|---|---|
| BEAR — n_blocks / n_eff_adj / block-t | 191 / 191.0 / **1.5629** | 105 / 105.0 / **1.0640** | 191 / 191.0 / **1.7233** | 190 / 190.0 / **0.4468** | 191 / 191.0 / **2.8967** |
| BULL_CALM | 290 / 285.0 / **2.6269** | 290 / 285.3 / **2.2000** | 290 / 286.0 / **2.6283** | 288 / 287.8 / **3.1280** | 290 / 253.2 / **1.4156** |
| BULL_VOLATILE | 94 / 94.0 / **1.7393** | 89 / 76.6 / **1.0878** | 94 / 94.0 / **1.5718** | 94 / 94.0 / **1.4186** | 94 / 94.0 / **1.5640** |
| CHOPPY | 47 / 39.9 / **0.8938** | 27 / 27.0 / **2.6640** | 47 / 39.9 / **1.1028** | 47 / 47.0 / **2.5112** | 47 / 47.0 / **3.0463** |

Mean block IC per regime (same keys): BEAR B0 0.010525 / B1 0.008295 / B2 0.010117 /
B3 0.002845 / s₀ 0.021077; BULL_CALM 0.009472 / 0.009157 / 0.008285 / 0.010891 / 0.006389;
BULL_VOLATILE 0.016393 / 0.009665 / 0.012052 / 0.012169 / 0.015419; CHOPPY 0.010392 /
0.034412 / 0.010754 / 0.022612 / 0.035230. ρ̂₁ was floored to 0 in 13 of the 20 regime cells
(raw values from −0.2675 to +0.0818) `[VERIFIED report *.per_regime.*.rho1_raw]`. B3's BEAR
cell (0.4468) and B0's CHOPPY cell (0.8938) are below 1.0; the prereg gates on the overall
number only, so these are recorded, not adjudicated.

### 2.3 Per fold `[DERIVED audit bases.*.block_series + harness ess_stats/episodes_of, sessions restricted to each fold's OOF window]`

The report does not carry per-fold block-t. The table below is a descriptive decomposition:
the audit's per-session block series was filtered to each fold's OOF window and passed
through the harness's own `episodes_of` + `ess_stats` (same K5 episode mapping, same AR(1)
floor, same ≥ 8-pair fail-close). Applied to the unfiltered series, this recomputation
reproduces the report's overall block-t exactly for all five series (3.5042 / 3.1837 / 3.5915 /
3.2394 / 4.1861) `[VERIFIED — recomputation == report to 4 dp]`. Caveat: an episode that
spans a fold boundary is split; ρ̂₁ is re-estimated within the fold; the overall number is not
the mean of the fold numbers.

| fold (OOF window) | census regime mix of the window's sessions | B0 | B1 | B2 | B3 | s₀ |
|---|---|---|---|---|---|---|
| 0 (2022-01..06) | BEAR 89, BULL_VOL 35 | 124 blk / IC 0.0202 / **2.1745** | **36 blk** / IC −0.0130 / **−0.6357** | 124 / 0.0195 / **2.5147** | 124 / −0.0040 / **−0.4219** | 124 / 0.0239 / **2.2030** |
| 1 (2022-07..12) | BEAR 100, CHOPPY 24, BULL_VOL 3 | 126 / 0.0048 / **0.5968** | **103** / 0.0144 / **2.1676** | 126 / 0.0058 / **0.8246** | 125 / 0.0166 / **2.6182** | 126 / 0.0281 / **3.6685** |
| 2 (2023-01..06) | BULL_CALM 106, CHOPPY 18 | 124 / 0.0078 / **1.3057** | 124 / 0.0064 / **0.8507** | 124 / 0.0048 / **0.9014** | 124 / 0.0070 / **1.3338** | 124 / 0.0041 / **0.5951** |
| 3 (2023-07..12) | BULL_CALM 104, BULL_VOL 14, CHOPPY 5, BEAR 3 | 124 / 0.0133 / **2.2387** | 124 / 0.0147 / **2.7433** | 124 / 0.0153 / **3.3568** | 122 / 0.0126 / **2.3260** | 124 / 0.0122 / **1.6949** |
| 4 (2024-01..06) | BULL_CALM 82, BULL_VOL 42 | 124 / 0.0086 / **1.7110** | 124 / 0.0136 / **2.2718** | 124 / 0.0027 / **0.5811** | 124 / 0.0153 / **2.6689** | 124 / 0.0038 / **0.7045** |

(cell = n_blocks / mean block IC / block-t; regime mix = census same-day K5 mapping of every
session in the window, `[DERIVED harness k5_regime_daily on the SPY daily closes the run read]`.)
Fold-level reading, stated without interpretation: no series is above 1.0 in every fold; B0
is below 1.0 in fold 1; B2 is below 1.0 in folds 1, 2 and 4; B1 and B3 are negative in fold 0;
s₀ is below 1.0 in folds 2 and 4 and is the largest series in fold 1 (3.6685).

### 2.4 Per-state cells: what was fitted, what was scored (`audit.fits`, 88 records) `[VERIFIED audit fits]`

The report carries no per-sector or per-macro-state block-t; the only per-state cells that
exist are the fit records (training rows, OOF rows, cap, seed). 86 of the 88 cells fitted a
model; 2 abstained; 8 fitted cells had zero OOF rows (§3).

Row cap 4,000,000: **binds in 9 cells** — B0[ALL] folds 1–4 (raw 4,908,442 / 6,432,659 /
7,893,967 / 9,194,391 → 4,000,000 each), B2[OTHER] folds 1–4 (4,453,469 / 5,585,391 /
6,795,163 / 7,893,799 → 4,000,000), B1[BULL_CALM] fold 4 (4,982,860 → 4,000,000). B3 is
never capped (largest cell 3,528,406). Every cap is the prereg's seeded without-replacement
subsample; seeds are in the audit (`fits[*].seed`, formula
`20260828 + 1000·fold + 100·base_code + state_index` `[VERIFIED report frozen.seed_formula]`).

Fold row counts `[VERIFIED report fold_row_counts]`: train 3,389,414 / 4,908,442 / 6,432,659 /
7,893,967 / 9,194,391; OOF 1,519,028 / 1,524,217 / 1,461,308 / 1,300,424 / 1,292,613
(sum 7,097,590 = `inputs.n_oof_observations`).

B2 sector states per fold (states with ≥ 50,000 training rows; everything else in OTHER):
folds 0–1: OTHER, ai_chip, consumer, finance, industrial, software (6 states); fold 2: + datacenter_hw,
energy, giant_tech, healthcare (10); folds 3–4: + utility (11). OTHER holds 86–91% of each
fold's training rows (e.g. fold 4: 7,893,799 of 9,194,391) `[DERIVED audit fits]`. sec13 is
NaN for the healthcare / bond / defensive_bonds / real_estate / telecom sectors because the
gate census never fetched XLV / TLT / XLRE / XLC `[VERIFIED report inputs.sec13_etf_available_by_sector, inputs.absent_from_audit]`.

B1 regime cells per fold (train / OOF rows): f0 BEAR 0 / 1,099,798 (ABSTAIN), BULL_CALM
2,702,852 / 0, BULL_VOL 686,562 / 419,230; f1 BEAR 1,099,798 / 1,222,446, BULL_CALM
2,702,852 / 0, BULL_VOL 1,105,792 / 36,303, CHOPPY 0 / 265,468 (ABSTAIN); f2 BEAR 2,322,244 / 0,
BULL_CALM 2,702,852 / 1,220,762, BULL_VOL 1,142,095 / 0, CHOPPY 265,468 / 240,546; f3 BEAR
2,322,244 / 34,100, BULL_CALM 3,923,614 / 1,059,246, BULL_VOL 1,142,095 / 151,938, CHOPPY
506,014 / 55,140; f4 BEAR 2,356,344 / 0, BULL_CALM 4,982,860 (capped) / 844,244, BULL_VOL
1,294,033 / 448,369, CHOPPY 561,154 / 0.

B3 macro-state cells per fold (train / OOF rows): f0 S+F+ 1,968,728 / 57,684, S+F−
1,314,760 / 123,254, S−F+ 59,187 / 607,499, S−F− 39,171 / 730,591; f1 2,026,412 / 254,420,
1,438,014 / 286,445, 666,686 / 520,782, 769,762 / 460,734; f2 2,280,832 / 718,603,
1,724,459 / 531,785, 1,187,468 / 83,448, 1,230,496 / 127,472; f3 2,999,435 / 528,971,
2,256,244 / 383,502, 1,270,916 / 176,255, 1,357,968 / 205,688; **f4 3,528,406 / 727,189,
2,639,746 / 565,424, 1,447,171 / 0, 1,563,656 / 0**.

### 2.5 Secondary horizons — DIAGNOSTIC ONLY, never gating (`report.*.secondary_horizons_DIAGNOSTIC_ONLY`) `[VERIFIED report]`

The h=13-trained prediction ranked against the within-session forward 1-/3-bar label at the
same bar-times (Interpretation 10). block-t at h=1: B0 11.1047, B1 7.4756, B2 10.5016,
B3 11.0802, s₀ 6.2414; at h=3: B0 6.0774, B1 4.9224, B2 5.6905, B3 6.1344, s₀ 3.0342.
h=39: "not computed: no within-session 39-bar forward window on the 39-slot grid". These are
reported because the prereg requires them in every attempt record; the prereg forbids their
promotion to primary.

## 3. Anomalies (recorded, not rationalized)

**3.1 Fold-4 `B3[S-F+] oof=0` and `B3[S-F-] oof=0`** `[VERIFIED log; VERIFIED audit fits]`.
Both cells FITTED a model (1,447,171 and 1,563,656 training rows, `fitted: true`) and then had
zero OOF rows to score. Mechanism, from the harness and the SPY closes the run read: the B3
slow leg is `sign(close_daily[D−1] / close_daily[D−61] − 1)`; on every one of the 124 sessions
of 2024-01-01..2024-06-30 that sign is +1 (SPY's close the prior day was at or above its close
61 sessions earlier), so no fold-4 OOF row carries an S− state
`[DERIVED harness b3_slow_state on the run's SPY daily parquet: fold-4 slow-state counts {+1: 124}]`.
What a zero-OOF cell means for the block-t: nothing is unscored — every fold-4 OOF row was
routed to S+F+ or S+F− and scored by those two models, so B3 still forms all 124 fold-4
blocks (§2.3) and `n_scored_rows` is unaffected by these two cells. What it means for the
evidence: B3's fold-4 number is an S+-only number; the two S− models contributed no
out-of-sample evidence in that half-year, and B3's overall block-t (3.2394) rests on S− states
scored only in folds 0–3. Did the prereg anticipate it? The prereg's B3 text covers a
**MISSING** state ("⇒ state MISSING ⇒ the row is excluded … B3 abstains") and Interpretation 8
covers **zero TRAINING rows** ("A conditioned state with zero training rows in a fold fits no
model and its OOF rows are unscored (abstain), never re-routed to another state"). Neither
text addresses a state that is present in training but absent from an OOF window; no declared
interpretation covers it. The harness's behaviour in that case (fit, score nothing, record
`n_oof: 0`) is what the code does, not what the prereg says. Slow-state counts per fold, for
scale: f0 {−1: 108, +1: 16}, f1 {−1: 80, +1: 47}, f2 {+1: 107, −1: 17}, f3 {+1: 90, −1: 36},
f4 {+1: 124} `[DERIVED, same function]`.

**3.2 The same phenomenon in B1, six cells** `[VERIFIED audit fits]`: f0 BULL_CALM, f1 BULL_CALM,
f2 BEAR, f2 BULL_VOLATILE, f4 BEAR, f4 CHOPPY all fitted and scored nothing (the lagged K5
regime never took that value inside the OOF half-year: f0 {BEAR 88, BULL_VOL 36}, f1 {BEAR 101,
CHOPPY 23, BULL_VOL 3}, f2 {BULL_CALM 105, CHOPPY 19}, f4 {BULL_CALM 82, BULL_VOL 42}
`[DERIVED harness regime_per_session lag 1]`). Same status as 3.1: not covered by any
declared interpretation.

**3.3 Two ABSTAIN cells, the reason B1 has 511 blocks instead of 622** `[VERIFIED audit fits;
VERIFIED report bases.B1.overall.n_blocks, n_scored_rows]`. Fold 0 `B1[BEAR]` had 0 training
rows (no BEAR session before 2022-01-01 in the panel) against 1,099,798 OOF rows; fold 1
`B1[CHOPPY]` had 0 training rows against 265,468 OOF rows. Per Interpretation 8 those
1,365,266 OOF rows (19.2% of the 7,097,590) are unscored. Consequence for the screen: on the 88
fold-0 sessions whose lagged regime is BEAR and the 23 fold-1 sessions whose lagged regime is
CHOPPY, no B1 row is scored at all, so B1 forms no block on those 111 sessions (the counts
match the lagged-regime session counts exactly); by the census same-day episode mapping those
111 sessions are BEAR 86, CHOPPY 20, BULL_VOLATILE 5
`[DERIVED audit block_series set difference B0 − B1; harness regime_per_session lag 1]`. **B1's 3.1837 is therefore computed on a
different (smaller, less-BEAR) session set than B0's 3.5042**, and its BEAR cell (105 blocks)
is not the same sample as the other bases' BEAR cell (190–191). The prereg's trigger compares
the two point estimates as they are; it does not specify a common-session comparison, and none
is reported here. The fold-0 B1 number (−0.6357 on 36 BULL_VOLATILE-only blocks) is the
fold-level face of the same fact.

**3.4 B3: 7,844 OOF rows unscored (0.11%) and 3 sessions with no B3 block** `[VERIFIED report
bases.B3.n_scored_rows vs inputs.n_oof_observations; DERIVED audit block_series B0 − B3]`. The
three sessions are 2022-11-28, 2023-07-05 and 2023-11-27, each the session after an NYSE
early close (2022-11-25, 2023-07-03, 2023-11-24 — which are themselves the only three
OOF-window sessions on which NO series forms a block: 625 OOF-window sessions, 622 blocks).
The prereg's B3 rule makes the fast state MISSING when "the prior session's slot [is] absent",
which is the case for the afternoon slots after an early close; the row-level state codes are
not in the audit, so this mechanism is read from the rule and the calendar, not re-derived
from the rows `[DERIVED]`.

**3.5 Row cap** — binds in 9 of 86 fitted cells (§2.4), all in the pooled / catch-all cells; no
state-specific B1/B2/B3 model other than B1[BULL_CALM] fold 4 was capped.

## 4. The s₀ reference vs the learned bases — descriptive, unpreregistered

The naive frozen proxy s₀ = −r13 scores **4.1861** overall; every learned base scores lower
(B2 3.5915, B0 3.5042, B3 3.2394, B1 3.1837) `[VERIFIED report s0_reference.overall.block_t,
bases.*.overall.block_t]`. s₀'s mean block IC (0.014444) is also higher than every base's
(0.009506–0.010911), with a higher sd (0.086051 vs 0.066687–0.077655). Per regime, s₀ is the
largest series in BEAR (2.8967 vs 0.45–1.72) and CHOPPY (3.0463 vs 0.89–2.66) and the smallest
in BULL_CALM (1.4156 vs 2.20–3.13). Per fold (§2.3) s₀ leads in fold 1 (3.6685) and trails in
folds 2 and 4.

The prereg does not define any comparison against s₀. Its only statements are: "s₀ (the A1
proxy, −r13) is carried as the naive reference, not a base" (Stage I-1 section) and, in I-0,
that s₀ exists so the dependence structure can be measured on the same blocks "as any later
base". The report accordingly carries s₀ outside `base_vs_b0` and outside the trigger
`[VERIFIED report base_vs_b0 keys = B1, B2, B3]`. The observation above is therefore
**descriptive only**; it is not a pass/fail and it is not an input to the preregistered
trigger. No I-2 design is proposed here.

## 5. The 12 declared interpretations, as applied `[VERIFIED report interpretations == provenance.frozen_parameters.interpretations == module INTERPRETATIONS (validator)]`

1. All bar returns (r1, r3, r13, m13, sec13, label) are LOG returns; rel13 = r13 − sec13 in log units. gap, vz and rng13 use the spec's literal arithmetic formulas.
2. rv13 = sqrt(sum of squared 1-bar log returns over the 13 bars t−12..t); NaN unless closes t−13..t are all present.
3. rng13 window = 13 bars t−12..t on high/low; NaN if any high/low is missing or max high == min low.
4. vz denominator = mean of the PRESENT same-slot volumes over the 60 sessions strictly before D; NaN when fewer than 48 (80%, the frozen eligibility coverage fraction) are present. A literal all-60-present rule would void the feature on the thin IEX feed.
5. gap uses the prior session's LAST present RTH close (the census's IEX session-close convention) and requires the slot-0 open of D; prior session = previous entry of the census session list.
6. B1 state for session D = the K5 regime computed at the prior session's close (regime.shift(1), the pure upsample of the post-close 104 regime series; no same-day close information, consistent with the B3 'as-of prior close' rule). Regime EPISODES for the screen use the census's unshifted same-day mapping so block structure is identical to the I-0 artifact.
7. B2: names absent from config sector_map are assigned to OTHER (the spec's catch-all) rather than dropped; small sectors fold into OTHER per fold; OTHER is itself never re-folded.
8. A conditioned state with zero training rows in a fold fits no model and its OOF rows are unscored (abstain), never re-routed to another state.
9. The 13-bar purge is implemented literally (training label-end bar + 13 <= first OOF observation bar) and is satisfied by construction on the A1 grid (within-session labels; first OOF row at slot 13).
10. Secondary horizons: h=1 and h=3 are scored DIAGNOSTICALLY by ranking the h=13-trained prediction against the within-session forward 1-/3-bar log label at the same bar-times; h=39 is NOT computed (no within-session 39-bar forward window exists on the 39-slot grid).
11. s0 = −r13 (the A1 proxy) is scored on the same OOF rows as a naive reference; it is not a base and not gated.
12. A bar-time IC whose Spearman is undefined (constant predictions) is treated as missing, so that session forms no block.

Applied consequences visible in the bundle: 8 (two ABSTAIN cells, §3.3); 6 (B1 cells keyed by
the lagged regime, §3.2, while episodes use the same-day mapping so B0/B2/s₀ share the census's
622-block structure); 7 (OTHER holds most of B2's rows, §2.4); 10 (h=39 absent, §2.5); 11 (s₀
outside the trigger, §4). 12 leaves no visible trace: B0, B2 and s₀ share one 622-session
block set and B1/B3 are strict subsets of it, every missing session being accounted for in §3
`[DERIVED audit block_series set comparisons]`.

## 6. Provenance `[VERIFIED report provenance unless noted]`

| item | value |
|---|---|
| run_id / run_status | `i1-dev-20260829T113813Z-666484a7` / `DEV_RUN` |
| source commit | `666484a7ab37dc9f88dd5692f8d9e90f3aab9332` — `clean_tree: true`, `n_dirty: 0` (git status ignoring only the bar store and the output root) |
| invocation | `scripts/experiments/g2v3_stage_i1_bases.py --dev-run`, cwd = the worktree, python `/Users/renhao/git/github/RenQuant/.venv/bin/python` 3.10.20, `G2V3_BAR_STORE` = the audited store under `wt-gate/scripts/experiments/g2v3_bars` |
| versions | xgboost 2.1.4, numpy 2.0.2, pandas 2.3.3, scipy 1.13.1 `[VERIFIED report versions]` |
| UTC start / end | `2026-08-29T11:38:13Z` / `2026-08-29T11:45:05Z` (process clock, `datetime.now(UTC)`); launcher log stamps 11:38:12Z start / 11:45:05Z end, exit 0 `[VERIFIED log]` |
| gate bundle bound | `i0-gate-20260829-f3d5bf7b`, frozen commit `f3d5bf7bd75ffa9c0fb59f8c3bfa98fa509e8779`, verdict PASS, BEAR n_eff_adj 191.0 |
| gate bundle hashes | report `da41a706f31b3f39b9ccc9631b93a76a6cb994c8877f112ce49989916634cf44`, audit `dd5127d7326919b777acd0a6bf819dcc158c9cd02a44cd76ef7ca71fa844f3a9`, provenance `6103cb25a05d861a8a58dfaeb0b3fe0fc416b217e7ab822daa109e4ab0169002` — each equal to the file on disk under `doc/research/data/2026-08-29-g2v3-i0-gate-run/` `[VERIFIED sha256sum]`; input-manifest aggregate `a878f1caeaee863cc06c2f9b3ab0d6eba4389d656a4b4dabd731a1844cdfd4d9`, count 2124 |
| store manifest check | strict; n_needed 1512, n_required_in_audit 1508, **n_hashed 1508**, missing 0; absent_from_audit = expected = {TLT, XLC, XLRE, XLV} |
| consumed-bar manifest | count **1508**, aggregate `4addcbe25f164a57afc0ea9fb0fd4e8e368a17fc292e2fe62b80fff5219d3883`; rebuilt from `audit.consumed_sha256` (1508 entries) with the gate's method — equal `[VERIFIED manifest_aggregate(audit) == report]`; every consumed hash equals the census audit's `bar_store_sha256` for that name `[VERIFIED validator, no "not the census-audited files" problem]` |
| other inputs | census audit = the gate bundle's audit (sha256 `dd5127d7…`); pinned `renquant-strategy-104/configs/strategy_config.json` sha256 `78e0d727ab3facd554ab2dfa20ab42c13f00b34e08b804921ced951ac9006d45`; sector_map `43e919e2c9d69aa1289cca9bdaf7d64c0c7e77d6d784bd71f494b4512f63e237`; sector_etf_map `29dd6259bb85b4eb8e0975bf75fb4edd317db61cfcc261a09632c28a60367cff`; SPY daily `763580bde0075340c2cc00fc1949419376692bcdd4a47c693befb74669b25c91` |
| panel | 983 sessions (2020-08-03..2024-06-28), 1,508 names, 10,487,004 observations, 7,097,590 OOF `[VERIFIED report inputs]` |
| `report.json` | 28,451 bytes, sha256 `666d9c6a9a2286af4215399aebbd07a2fda8efafc6b5440d8d39ea6b9e1e1542` `[VERIFIED sha256sum]` |
| `g2v3_stage_i1_audit.json.gz` | 271,331 bytes, sha256 `d124d8f2a8766edf7d4a6f767206444467f05fa3bb8dec1818a76b01b2cd3082`; uncompressed 746,174 bytes, sha256 `a27da06563e9eff1a6286fd9529045f2b3169d930fa54bbd5004131f774c6c90` `[VERIFIED sha256sum]` (the harness writes the audit gzipped; nothing in the bundle exceeds 5 MB, so no file was re-packed) |
| validation | `validate_i1_provenance(report, audit, repo_root)` → `[]`; `tests/test_g2v3_stage_i1_provenance.py` + `tests/test_g2v3_stage_i1_gate_binding.py` + `tests/test_g2v3_gate_run_bundle_provenance.py` → 49 passed `[VERIFIED pytest, 2026-08-29]` |

Frozen block as run `[VERIFIED report frozen]`: h=13, 39 slots, screen slots 13..25, dev window
2020-08-01..2024-06-30, seed base 20260828, XGB params verbatim (max_depth 3, n_estimators 300,
learning_rate 0.05, subsample 0.8, colsample_bytree 0.8, min_child_weight 20, hist,
random_state 20260828, n_jobs 8), row cap 4,000,000, min_sector_rows 50,000, five folds as
preregistered, purge 13, ≥ 100 names per IC, ≥ 8 pairs, life bar 1.0, secondary {1, 3, 39},
11 features, B1 lag 1 session, vz 60 / 48, B3 slow 60 sessions / fast lag 39 slots. The
validator checks every one of these against the module constants and the prereg-bound
`_DEV_ONLY_FROZEN` block.

## 7. What this does not show

- **Development window only.** Every number is out-of-fold inside 2020-08..2024-06. The
  evaluation window 2024-07-01..2026-06-30 remains sealed: no fit, no score, no peek.
- **No transformer, no meta-learner exists.** Stage I-2 has not been designed in numeric
  detail, let alone run; nothing here is a stacked-model result.
- **No live implication.** No serving path, no rq105 change, no strategy-config change, no
  pin advance, no production path written. The run wrote only
  `doc/research/data/2026-08-29-g2v3-i1/<run_id>/`.
- **Point estimates only.** The trigger is a strict inequality on two block-t point estimates;
  no uncertainty on the B2 − B0 difference (0.0873) is defined by the prereg and none is
  computed here.
- **Not a common-sample comparison.** B1 (511 blocks) and B3 (619) are scored on subsets of
  B0's 622 sessions (§3.3–3.4); the prereg compares the numbers as reported.
- **Nothing about s₀** beyond the descriptive fact in §4; the prereg defines no s₀ comparison.
- **Survivorship residual** of the seed universe (I-0 §3) is unchanged and affects absolute IC
  levels more than base-vs-base differences, as the I-0 design records.
