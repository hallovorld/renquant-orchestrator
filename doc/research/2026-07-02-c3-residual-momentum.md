# C3 — regime-conditioned residual momentum: frozen-spec measurement — VERDICT: MISS

STATUS: research measurement (read-only on all production data; one committed script +
committed JSON evidence). First formally-voting candidate of the merged M-SIG stack
(`doc/design/2026-07-02-m-sig-signal-stack-spec.md`, PR #243) to be measured under its
frozen thresholds.

**VERDICT: MISS — recorded and dropped per design rule 5. Not KILL.**
The conditioned cell does no better than ~zero placebo-clean IC (−0.004 vs a frozen bar of
+0.015), and the conditioned-minus-unconditioned improvement (+0.0086) has a CI that includes
zero at every convention tested. C3 casts no GO vote toward G106. Because the conditioned
cell is still point-wise BETTER than unconditional (the dispatch KILL trigger
`conditioned <= unconditioned` does not fire) and the conditioned upper bound (+0.048) is not
below the bar, the spec-vocabulary outcome is INCONCLUSIVE-not-GO with the n>=600 sample
floor fully met (1,833 conditioned dates) — i.e. a genuine, adequately-sampled miss, not a
data-starved one. Under design rule 5 ("a candidate that misses its bar is recorded and
dropped") C3 is now closed; do not re-pitch without a new, materially different hypothesis.

## 1. What was measured (frozen estimand, spec section 1.3)

`mom_12_1` (252-trading-day price return excluding the most recent 21 days), cross-sectionally
rank-z scored per date, then orthogonalized per date to sector + market beta by OLS; the
residual is the C3 score. Evaluated ONLY in the pooled `BULL_CALM + BULL_VOLATILE` regime
cell, on placebo-clean differences (never absolute IC), verdict on fwd_60d excess-vs-SPY.

Frozen decision rule applied exactly as merged (spec sections 1.3 + 2a):

- GO iff (a) conditioned-cell placebo-clean IC one-sided 98.33% (Bonferroni k=3) CI lower
  bound > 0.015, AND (b) the conditioned-minus-unconditioned paired-difference one-sided
  98.33% CI lower bound > 0 — on all seeds {42, 43, 44}.
- KILL iff the conditioned 98.33% upper bound < 0.015 (spec), or conditioned <= unconditioned
  point-wise (measurement-dispatch frozen rule).
- Otherwise MISS/INCONCLUSIVE — recorded, not re-argued. **This is the outcome.**

No threshold was altered. Where the measurement dispatch and the merged spec differed on
non-threshold mechanics, the MERGED SPEC governs the verdict and the dispatch variant is
reported as a labeled sensitivity (section 4 below); the verdict is identical under both.

## 2. Headline numbers (gating configuration: fwd_60d, daily cadence, beta 252d, block 60)

| Cell | n dates (clean) | mean real IC | mean placebo IC | mean placebo-clean IC | hit rate |
|---|---:|---:|---:|---:|---:|
| **Conditioned (BULL_CALM+BULL_VOLATILE)** | **1,833** | +0.0253 | +0.0275 | **−0.0040** | 0.531 |
| Unconditional (all regimes) | 2,266 | +0.0214 | +0.0323 | −0.0126 | 0.504 |
| BULL_CALM alone | 1,662 | +0.0271 | +0.0293 | −0.0031 | 0.533 |
| BULL_VOLATILE alone | 171 | +0.0094 | +0.0103 | −0.0125 | 0.509 |
| BEAR alone | 327 | −0.0037 | +0.0673 | −0.0719 | 0.343 |
| CHOPPY alone | 106 | +0.0290 | +0.0071 | +0.0210 | 0.538 |

Conditioned − unconditioned difference: **+0.0086**.

Block-bootstrap CIs (block=60, n_boot=2000; all three seeds reported, none cherry-picked):

| Seed | Conditioned clean: 95% CI | 98.33% one-sided LB | Difference: 95% CI | 98.33% one-sided LB |
|---|---|---:|---|---:|
| 42 | [−0.0492, +0.0444] | −0.0549 | [−0.0031, +0.0235] | −0.0039 |
| 43 | [−0.0476, +0.0435] | −0.0513 | [−0.0035, +0.0244] | −0.0043 |
| 44 | [−0.0486, +0.0428] | −0.0530 | [−0.0028, +0.0231] | −0.0038 |

- Leg (a): FAILS decisively — the conditioned point estimate (−0.0040) is below zero, let
  alone the +0.015 bar; every seed's 98.33% LB is ~−0.05.
- Leg (b): FAILS — the difference is positive (+0.0086) but every CI (95% two-sided AND
  98.33% one-sided) includes zero.
- KILL triggers: none fire (conditioned > unconditioned point-wise; conditioned UB ~+0.048
  is not < 0.015).
- Sample floor: met (1,833 conditioned clean dates >= 600; ~31 effective 60-day blocks).

**Reading**: the raw real IC in the bull cell (+0.0253) would naively look promising — and is
entirely explained by the placebo (+0.0275). Residual momentum's apparent bull-regime IC is
overlapping-horizon / regime-persistence label structure, not stock-selection alpha. This is
the placebo-clean-differences discipline (design rule 2, the ~+0.04 embargo-floor lesson)
doing exactly its job. The one cell where conditioning genuinely changes the picture is BEAR
(placebo-clean −0.072 — the classic momentum crash), which the conditioned cell excludes; that
exclusion is what produces the positive-but-not-significant +0.0086 difference.

## 3. Supporting horizon fwd_20d (never gates; block=20)

Conditioned +0.0029 vs unconditional +0.0004 (difference +0.0025, 95% CI [−0.0077, +0.0124]).
Same shape: nothing anywhere near the bar. Per-regime (clean): BULL_CALM +0.0116,
BULL_VOLATILE −0.0730, BEAR −0.0058, CHOPPY −0.0229.

## 4. Sensitivities (labeled; none gate; all agree with the verdict)

| Variant | n cond. dates | cond. clean | uncond. clean | diff | diff 95% CI |
|---|---:|---:|---:|---:|---|
| GATING (beta252, daily, block60) | 1,833 | −0.0040 | −0.0126 | +0.0086 | [−0.0031, +0.0235] |
| Dispatch bundle (beta120, stride-21, block13, 5000 boots, seed 42) | 89 | −0.0141 | −0.0133 | −0.0009 | [−0.0114, +0.0124] |
| block13 on gating series (daily, seed 42) | 1,833 | −0.0040 | −0.0126 | +0.0086 | [−0.0010, +0.0194] |
| beta120, daily, block60 | 1,833 | −0.0030 | −0.0120 | +0.0090 | [−0.0032, +0.0243] |

The verdict is NOT convention-fragile: under the dispatch's own stated convention the result
is if anything weaker (the stride-21 grid flips the difference slightly negative), and the
narrower block=13 CI still includes zero.

## 5. Interpretations resolved (every one stamped into the evidence JSON)

1. **block=60, not 13**: the measurement dispatch said "block=13, the A1 convention — state as
   resolved interpretation." Resolution: the merged spec r2/r3 explicitly resolved this open
   question (spec section 4 Q2) to block=60 = the fwd_60d label horizon, noting block=13 "was
   never actually adopted anywhere in this codebase as a block-size convention." block=13 is
   reported as a sensitivity; identical verdict.
2. **Beta window 252d** (spec-frozen fit window, section 1.3); the dispatch-stated 120d is a
   sensitivity; identical verdict.
3. **Daily decision dates**, per the spec's shared default ("daily Spearman rank IC", n>=600
   floor — a stride-21 grid structurally cannot meet the floor: it yields 89 conditioned
   dates); dispatch's stride-21 is a sensitivity.
4. **n_boot=2000, seeds {42,43,44} all reported** (spec shared default) for the gate;
   dispatch's 5000/seed-42 used in its sensitivity bundle.
5. **CI level**: one-sided 98.33% (Bonferroni k=3, spec section 2a) governs; two-sided 95%
   reported alongside. GO requires the rule to hold on all three seeds.
6. **Residualization form**: the spec 1.3 formula is realized as per-date cross-sectional OLS
   of the rank-z momentum on [const + sector dummies + trailing-window beta]: the "sector
   factor" is the per-date sector mean and the "market factor" the per-date cross-sectional
   premium on beta. Residuals verified orthogonal to beta per date (corr ~1e-15).
7. **Labels**: fwd_20d/fwd_60d PRICE-return excess vs SPY, clipped ±0.5 (repo label
   convention); verdict on fwd_60d, the strategy horizon; fwd_20d supporting only.
8. **Placebo**: label shifted +horizon within ticker (the fwd_h window starting at t+h);
   placebo-clean = real − placebo per date, defined only where both exist (the clean series
   therefore ends ~2×horizon before the last bar, 2026-01 for fwd_60d).
9. **Conditioned cell pooled** (BULL_CALM ∪ BULL_VOLATILE) per spec 1.3; per-regime cuts
   reported as mandatory diagnostics only.
10. **Difference CI is paired** (spec 1.3 leg (b)): blocks are resampled from the FULL dated
    series and mean(in-cell) − mean(all) recomputed per resample — not two separate CIs
    compared by eye. The conditioned-cell-only CI resamples blocks over the conditioned
    subseries in date order (this repo's regime-sliced convention).
11. **Min 30 names per date** for both the 17-parameter cross-sectional regression and each
    IC (~2× parameters; the reference diagnostic's min_names=5 would be meaningless under a
    17-regressor residualization).
12. **Beta min_periods = window/2**; names with less paired history are excluded from that
    date's cross-section (no imputation), consistent with the spec's missingness stance.

## 6. Regime-label reconstruction fidelity

Labels come from TODAY'S production regime task chain — `HurstTask → CUSUMTask → GMMTask →
BEAROverrideTask → RegimeFinalizeTask` — imported from the PINNED
`.subrepo_runtime/repos/renquant-pipeline` sources and driven exactly as
`renquant_backtesting.analysis.analyze_manifest_sanity_placebo::build_regime_series` drives
them (same ctx contract, same sequential expanding-history replay), with the PINNED strategy
config (`.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`, which
carries the 2026-06-11 false-BEAR-fix keys the umbrella copy lacks) and the production GMM
artifact (`backtesting/renquant_104/artifacts/prod/spy-gmm-regime.json`). All input hashes
are stamped in the evidence manifest. Known fidelity gaps, stated honestly:

- The GMM artifact was trained 2026-05-22 on the full SPY history — regime labels for dates
  before that are IN-SAMPLE for the GMM component (a limitation shared by every historical
  regime reconstruction with today's pinned artifact, including the reference diagnostic).
- The replay carries `RegimeState` forward sequentially from a fresh state at 2016, rather
  than the states production actually persisted day by day; and it replays TODAY'S pinned
  code/config over history, not the (older) code production ran on those dates.
- Resulting mix over 2,386 scored dates: BULL_CALM 1,744 / BEAR 329 / BULL_VOLATILE 196 /
  CHOPPY 117 — the conditioned cell is 81.3% of dates, consistent with the known "~79% of
  live time" BULL_CALM-dominance prior.

## 7. Substrate + survivorship limitation

- **Substrate deviation, stated**: spec design rule 1 prescribes the S5/S8 durable
  pick-table + ledger substrate. That ledger has no multi-year history (it began collecting
  in June 2026), so this measurement — as directed by the measurement dispatch — runs on the
  durable committed umbrella OHLCV parquets (`data/ohlcv/<T>/1d.parquet`) over the 142
  unique tickers of `data/transformer_v4_wl200_clean.parquet`. This is committed, durable
  data (not an ad-hoc /tmp panel), but it is NOT the pick-table substrate.
- **Survivorship**: the 142-name universe is fixed as of the 2026 panel and applied over the
  full 2017–2026 window; names are in the panel partly because they survived and mattered in
  2026. Momentum ICs measured on survivors are, if anything, OPTIMISTIC — which makes the
  MISS conservative in direction (a bar the signal cannot clear even with survivorship help).
- Prices are split-adjusted but not dividend-adjusted (price returns on both legs; the
  residual cross-sectional dividend-yield tilt is a stated, second-order limitation).
- Data hygiene: 142/142 tickers loaded; 8 single-day |return|>40% events across 10.5 years
  (AFRM/AMD/APP/OXY/RBLX/SMCI/SOFI/ZM — all verified earnings/news gaps, no split seams;
  NFLX's 10:1 2025-11-17 split shows no price seam).

## 8. Prospectivity affirmation (required by spec section 1.3)

**Affirmed: no prior script in this repo's git history computed this exact
residual×regime×block-bootstrap combination before 2026-07-02.** The two nearest prior
artifacts are materially different measurements: `scripts/experiments/2026-06-23-residual-audit.py`
residualized the LABEL (fwd_60d_excess on sector+BETA60) to test an XGB retrain hypothesis —
no momentum signal, no regime conditioning, no block bootstrap; `scripts/regimemom.py`
conditioned RAW (un-residualized) mom_12_1 on a NON-production regime label (SPY 200-DMA
trend × expanding vol terciles), horizons fwd_20d/fwd_5d, Newey-West t-stats — no
residualization, no production BULL_CALM/BULL_VOLATILE labels, no block bootstrap, no fwd_60d.
This result is therefore genuinely prospective/confirmatory under the freeze: the specific
conditioned residual×regime cell had not been computed or inspected before this measurement.

## 9. Reproduce

```
/Users/renhao/git/github/RenQuant/.venv/bin/python \
    scripts/c3_residual_momentum.py --out doc/research/evidence/2026-07-02-c3
```

(Umbrella venv required — the production regime chain is Python>=3.10. Runtime ~4 minutes.
Deterministic: fixed seeds, pinned inputs; input SHA-256 hashes in the evidence manifest.)

Evidence: `doc/research/evidence/2026-07-02-c3/c3_results.json` (full stats, CIs, verdict,
manifest, interpretations), `c3_per_date_ic_fwd60.json` (per-date real/placebo/clean IC +
regime — sufficient to recompute every bootstrap independently), `c3_regime_series.json`
(the full reconstructed regime series).

## 10. Consequence for the M-SIG stack

C3 resolves as a recorded MISS: no GO vote. Per spec section 2a's operational order the stack
now rides on C4 (trend-scanning label, gated on S3 landing) and C2 (quality composite, gated
on the N3 coverage verdict, 2026-Q4) — G106 GO still requires 2 of the 3 voting candidates to
clear. C3 is closed under design rule 3/5: the residual×regime cell was the last untested
momentum combination; momentum-family candidates should not be re-pitched absent a genuinely
new instrument.
