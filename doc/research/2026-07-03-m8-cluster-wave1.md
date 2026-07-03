# M8 cluster wave-1 breadth expansion — VERDICT: NO-GO (waves STOP; BR via D3 down-cap)

STATUS: research measurement, read-only on all production data. One committed
script (`scripts/m8_cluster_wave1.py`) + committed JSON evidence
(`doc/research/evidence/2026-07-03-m8/`). Selection criterion and gate were
FROZEN and committed (commit "freeze cluster wave-1 selection criterion +
non-degradation gate") BEFORE the wave was selected or any IC was measured.
No watchlist/config change — admission would be a D-gate decision, and this
verdict removes it from the table.

**VERDICT: NO-GO — the frozen gate FAILED decisively, not marginally.**
Mean paired walk-forward IC delta (augmented − baseline) over the qualifying
cuts = **−0.0477** on `fwd_60d_excess` vs the pre-registered noise band of
−0.010 (gate: PASS iff ≥ −0.010). The secondary label agrees (fwd_20d
−0.0171), the placebo-clean paired delta agrees (−0.0328), and the
date-level pooled delta is −0.0476 with naive SE 0.0037 (n=691 dates) — this
is not a band-edge miss. Per the frozen consequence: **the wave is recorded
NO-GO and waves STOP; the BR term of the master plan now comes only via the
D3 down-cap path** (the two BR paths were designed to hedge each other —
master-plan M8 row Plan B). Not re-argued.

This is the operationalized test of E34's resume condition (umbrella
`doc/research/failed-experiments-log.md` E34): cluster-based admission of
~100 structure-similar quality names instead of E34's blind 103→816
expansion. The resume condition was tested and the degradation reproduced —
E34's transfer-coefficient-collapse mechanism survives similarity-based
selection at wave size 100.

## 1. What was frozen (pre-registered before measurement)

Full spec: `doc/research/evidence/2026-07-03-m8/m8_frozen_spec.json`.

- **Candidate pool**: the E34 R1K screen dataset
  (`RenQuant/data/alpha158_816_dataset.parquet`, 816 tickers, 2016-01→
  2026-02-10, 158 alpha158 features + fwd_5/20/60d excess labels) minus the
  current `strategy_config.json` watchlist (145 entries incl. SPY/sector
  ETFs/ADRs; **133 equity incumbents are in the dataset and form the
  baseline arm**; candidates = 683). Eligibility: ≥756 dataset rows (E34
  <3y exclusion), ≥26 weekly similarity dates, ≥2 same-GICS-sector
  incumbent peers.
- **Selection criterion (outcome-free)**: feature-rank-structure similarity.
  On every 5th trading date in 2023-01-01→2024-12-31 (101 dates), rank all
  tickers cross-sectionally on each of the 158 features; similarity(c,i) =
  mean Pearson correlation between the 158-dim feature-rank vectors of
  candidate c and incumbent i; S(c) = mean over same-GICS-sector incumbents.
  **Uses features only, never forward returns → no selection-on-outcome by
  construction**, which is why in-span window overlap is admissible.
  - *Stated interpretation / rejected alternative*: E34's literal "top-IC
    per sector bucket" needs a selection window strictly disjoint from the
    2019–2025 evaluation span; 512/683 candidates start exactly 2021-05-03
    (a 5y OHLCV fetch-window artifact, not IPO dates), so no adequately
    covered disjoint window exists — any in-span outcome-based selection
    would be selection-on-outcome. Rejected; recorded in the spec.
- **Wave-1**: exactly 100 names, slots proportional to the incumbent GICS
  mix (largest remainder), per-sector top-S(c).
- **Paired evaluation**: E35-style 7-cut walk-forward (identical CUTS to
  umbrella `scripts/walk_forward_extended.py`), XGB `rank:pairwise` with
  production params (`panel_trainer.PANEL_LTR_PARAMS`: eta 0.05, depth 5,
  min_child_weight 50, subsample/colsample 0.7, seed 42, 100 rounds),
  identical featurization and cuts in both arms; metric = per-date
  cross-sectional Spearman IC over the arm's full universe.
- **Qualifying-cut rule**: a cut qualifies iff ≥50% of wave-1 names have
  ≥252 train rows and ≥100 test rows in it (the fetch-window artifact makes
  early cuts wave-empty; a paired delta of ~0 there would dilute the gate).
  Measured: cuts 5, 6, 7 qualify (test windows 2023, 2024, 2025).
- **THE FROZEN GATE** (master-plan M8 AC, not alterable): PASS iff mean over
  qualifying cuts of [IC_aug(cut) − IC_base(cut)] ≥ −0.010 on
  `fwd_60d_excess`. Placebo integrity downgrade (PASS→INCONCLUSIVE only).
  NO-GO ⇒ waves stop, BR via D3 down-cap.

## 2. Wave-1 composition (stage A output)

100 names, sector-balanced to the incumbent GICS mix: tech 35, industrial
14, finance 13, healthcare 8, consumer_disc 8, utility 5, energy 5,
consumer_staples 4, reit 4, comm 4. Similarity scores of admitted names
0.056–0.520 vs candidate median 0.055 — the wave is the structurally most
incumbent-like decile-and-a-half of the pool (ABT, ADSK, AMGN, BKNG, COF,
COP, ... full list in `m8_wave1_selection.json`). 634/683 candidates scored;
48 dropped for <2 same-sector incumbent peers (materials — 1 incumbent),
1 for short history.

## 3. Gate read (stage B, fwd_60d_excess primary)

| Cut | Test window | Baseline IC (133) | Augmented IC (233) | Δ | Qualifying |
|---|---|---:|---:|---:|---|
| 1 | 2019 | +0.0310 | +0.0224 | −0.0086 | no |
| 2 | 2020 | +0.1725 | +0.2067 | +0.0342 | no |
| 3 | 2021 | −0.0525 | −0.0845 | −0.0320 | no |
| 4 | 2022 | −0.0388 | −0.0177 | +0.0210 | no |
| 5 | 2023 | +0.1398 | +0.0634 | **−0.0764** | yes |
| 6 | 2024 | +0.0054 | +0.0214 | +0.0159 | yes |
| 7 | 2025 | +0.1276 | +0.0451 | **−0.0825** | yes |

- **Mean Δ qualifying = −0.0477 < −0.010 ⇒ NO-GO.** Wave wins 1/3
  qualifying cuts. All-7-cut mean Δ = −0.0183 (diagnostic; also outside the
  band).
- Placebo-clean paired Δ (qualifying) = −0.0328 — same sign, same
  magnitude class ⇒ the degradation is not an embargo-leakage artifact.
- Secondary fwd_20d: mean Δ qualifying = −0.0171 (cuts 5/6/7: −0.0550,
  +0.0038, −0.0001), placebo-clean −0.0288 ⇒ consistent.
- Date-level pooled Δ (fwd_60d, qualifying cuts) = −0.0476, naive SE 0.0037
  (n=691; SE is iid-biased low under fwd-label overlap — cited as scale,
  not as a test statistic).

## 4. Mechanism: training dilution hits the incumbent book itself

Incumbent-subset diagnostic (augmented-trained model, IC measured only on
the 133 incumbents):

| Cut | Baseline model on incumbents | Augmented model on incumbents |
|---|---:|---:|
| 5 | +0.1398 | +0.0663 |
| 6 | +0.0054 | +0.0250 |
| 7 | +0.1276 | +0.0615 |

Adding 100 structure-similar names degrades ranking ON THE EXISTING BOOK in
2/3 qualifying cuts by 6–8 IC points — it is not merely that the new names
are harder to rank; the diluted training panel produces a worse model for
the incumbents too. This reproduces E34's key insight ("expanding to
dissimilar tickers raises N but cuts transfer coefficient") at a much finer
selection granularity: even the most feature-structure-similar 100 names
carry enough signal-structure difference to dilute the panel fit.

Per-regime cuts (EXPLORATORY — regime series is the committed C3 evidence
series, which is NOT point-in-time; inherits all C3 substrate caveats):
fwd_60d degradation is concentrated in BULL_CALM (−0.0519, n=530 dates) and
BULL_VOLATILE (−0.0562, n=64); fwd_20d shows small positive deltas in
BEAR/BULL_VOLATILE/CHOPPY but −0.0288 in BULL_CALM. Reporting only; the gate
does not read these.

## 5. Caveats (stated up front in the frozen spec)

1. **Survivorship**: the 816 pool is May-2026 R1K membership projected back
   — inflates BOTH arms' absolute IC; the paired difference partially
   controls, but wave-1 names are the more survivorship-exposed set (bias
   FAVORS the wave — the NO-GO is conservative against this bias).
2. **Data topology**: 512/683 candidates start 2021-05-03 (5y fetch-window
   artifact) — handled by the frozen qualifying-cut rule; the gate reads
   only cuts 5–7 where wave coverage is ≥50% (measured: 100% in 5–7).
3. **Costs not modeled** — IC-level gate only, per the master-plan M8 row.
4. **alpha158-only features** (the 816 dataset has no fundamentals); the
   production scorer adds fund features. The gate reads the paired delta
   under identical featurization; a fundamentals-augmented rerun is possible
   future work but does NOT reopen the wave absent D3.
5. Absolute IC levels carry the known ~+0.04 embargo-leakage floor (placebo
   ICs of +0.02…+0.13 observed here confirm it); only paired same-cut
   differences are read, per house rule.
6. This tests ONE frozen similarity criterion at ONE wave size. E34's other
   resume alternative (sector-specific models) was NOT tested here and is
   not adjudicated by this verdict — but per the frozen plan consequence,
   any revisit routes through D3, not through re-running waves.

## 6. Consequence

- M8 wave-1 = recorded NO-GO. **No wave-2. No watchlist expansion.**
- Master-plan Term BR falls back to Plan B: **BR via the D3 down-cap
  decision** (L1 row) — D3's synthesis input from M8 is this memo.
- E34 stays 🟢 STANDS in the failed-experiments log; its resume condition
  has now been operationalized once and failed its gate at wave size 100
  under an outcome-free structure-similarity criterion.

## 7. Reproduction

```bash
# umbrella venv (xgboost); ~60s stage B on M-series
/Users/renhao/git/github/RenQuant/.venv/bin/python scripts/m8_cluster_wave1.py freeze
/Users/renhao/git/github/RenQuant/.venv/bin/python scripts/m8_cluster_wave1.py select
/Users/renhao/git/github/RenQuant/.venv/bin/python scripts/m8_cluster_wave1.py evaluate
/Users/renhao/git/github/RenQuant/.venv/bin/python scripts/m8_cluster_wave1.py verdict
```

Evidence: `doc/research/evidence/2026-07-03-m8/{m8_frozen_spec,
m8_wave1_selection, m8_paired_wf_results, m8_per_date_ics, m8_verdict}.json`.
Total stage-B runtime 62s (7 cuts × 2 arms × 2 labels real + qualifying-cut
placebos = 40 XGB trainings); the full-WF fallback staging in the dispatch
(spec-then-measure) was not needed.
