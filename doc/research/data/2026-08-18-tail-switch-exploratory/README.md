# 2026-08-17/18 tail-skill ON-switch exploratory — committed formation artifact

This bundle is the formation evidence behind the vol-switch confirmatory prereg
(`doc/research/2026-08-18-vol-switch-confirmatory-prereg.md` §1). It was produced in the
2026-08-17/18 exploratory session (session scratchpad, per the repo's experiments-outside-
the-live-tree rule) and is committed verbatim here so every conclusion-bearing number the
prereg imports has an exact committed source (review round 1, finding 1;
`AGENT-RETROSPECTIVE.md` §4(b)).

## 1. Contents (all copied VERBATIM from the exploratory session, 2026-08-18)

| file | role |
|---|---|
| `DEFINITIONS.md` | frozen definitions, written 2026-08-17 BEFORE any conditional statistic (corpora, outcome variables, state variables, block inference rules, declared variants) |
| `build_series.py` | builds the per-date series (outcomes Y + ex-ante states) from the clf WF score bundle + OHLCV parquets |
| `conditional_analysis.py` | one-way tercile / two-way median-split conditional tables with non-overlapping 60-td block inference |
| `vol_matched_check.py` | vol-cohort-matched (STD60-percentile-matched) re-check of the T3 result |
| `diagnostics.py` | LOBO fragility, calendar composition, state correlations, regime cut |
| `conditional_results.txt` | main conditional tables (all-days + bull-only + phase-A secondary) |
| `volmatched_results.txt` | vol-matched results + regime / tercile cuts |
| `welch_mde.txt` | BULL_VOLATILE vs BULL_CALM Welch test, unconditional block σ, tercile edges |
| `diagnostics_results.txt` | LOBO tables, tercile calendar composition, state correlations |
| `decile_tables.txt` | top-decile (secondary N) variants of the tercile/regime tables |
| `series_clf.csv` | primary per-date series (clf WF corpus, 625 dates 2023-10-03..2026-03-31) |
| `series_phasea.csv` | secondary per-date series (phase-A xgb, LOOK-AHEAD caveat declared) |
| `series_volmatched.csv` | vol-matched construction series |

SHA-256 of the series CSVs (as committed):

```
7b416e6068db9a78e2bb54a92f5218ded9ea901c5eab8104d57ec6bf42b17dd7  series_clf.csv
1c0dd77ec18ff52dde1b5333bbb94f8fb1a17a4fe683417d1d735c824d8174c7  series_phasea.csv
2779f8a4a6210e8b4fb44abd38ffe2f965ad3f686fa783cc5709ebca04e2e812  series_volmatched.csv
```

Input data (not committed here, named in `DEFINITIONS.md`): the clf WF score bundle
`renquant-model/doc/research/data/2026-08-01-clf-wf-lineage-bundle/clf_wf_scores.parquet`,
umbrella `data/ohlcv/<T>/1d.parquet` closes, and the committed regime-day CSV
`doc/research/data/2026-08-10-bear-exit-regime-days.csv`.

## 2. Number → source map (the values the prereg imports)

| prereg claim | exact value | source |
|---|---|---|
| SPY-vol T3 spread (SD units) | +0.7556 (all-days) / +0.6656 (bull-only) | `conditional_results.txt`, spyvol20 T3_high, y_z10 |
| T3 block-t | +2.86 (all-days) / +3.10 (bull-only) | `conditional_results.txt`, spyvol20 T3 |
| vol-matched T3 survives | mean +0.1069, t=+3.12 (crit 2.78) | `volmatched_results.txt` |
| BULL_VOLATILE cohort t | +3.45 (regime cut) / +3.58 (vol-matched) | `diagnostics_results.txt` §4 / `volmatched_results.txt` |
| ON-vs-OFF NOT certified | Welch t=+1.56 (p=0.147), BV(n=6) vs BC(n=9) block means | `welch_mde.txt` |
| block σ (SD units) | 0.5343 (uncond, 10 blocks) / 0.5410 (BULL_VOLATILE) | `welch_mde.txt` |
| exploratory tercile edge → frozen 13.5% | T3 edge 0.1375 (all-days) / 0.1348 (bull-only) | `welch_mde.txt` |
| LOBO-fragile | LOBO drops keep mean > 0 but t < crit (4 of 5 drops) | `diagnostics_results.txt` §1 |
| corpus size | 625 dates; 600 enter after the ≥100-names filter | `DEFINITIONS.md` / `conditional_results.txt` headers |

## 3. Primary-corpus geometry recheck (2026-08-18, this PR's review round 1)

`geometry_check.py` (committed alongside) re-measures the prereg §2/§3 state geometry
from `data/ohlcv/SPY/1d.parquet` (SPY series start 2016-01-04) under the corrected
non-overlapping 60-TRADING-day block unit. Output
`[VERIFIED — geometry_check.py, run 2026-08-18]`:

```
corpus trading days: 1697 (2017-01-03 .. 2023-09-29)
ON days fixed (>13.5%): 821
expanding threshold first available: 2018-01-31 (504-obs warmup from series start)
ON days expanding (pre-threshold OFF): 808
complete 60-td blocks: 28 (trailing 17-td remainder dropped)
fixed:      ON-eligible(>=15)=19, ON-dominant(>=45)=8
expanding:  ON-eligible(>=15)=19, ON-dominant(>=45)=8
blocks ON-eligible under BOTH: 18
```
