# Per-ticker data completeness registry (task #15 — measurement, no pipeline change)

**BOTTOM LINE:** every one of the 9 non-COMPLETE ACTIVE names is on the LIVE
WATCHLIST, and every one of the 9 degradations is in the SEC-fundamentals
source (SPCX additionally has only 39 OHLCV bars). Zero ACTIVE names are
BROKEN. OHLCV, earnings-surprise, and sentiment are clean for all 147 active
names. The 148-name delisted/dropped corpus tail falls out of the
classification naturally as BROKEN-inactive, with no special-casing.

**NUMBER:** 9/145 active watchlist names DEGRADED (all SEC-fundamentals).
**CONFIDENCE:** [VERIFIED — `scripts/data_completeness_registry.py` run
2026-08-10 against the umbrella tree; spot checks re-derived independently
with direct pandas reads of each source file]

## Scope

- Universe: 295 = 292 corpus tickers
  (`RenQuant/data/alpha158_291_fundamental_dataset.parquet`) ∪ 145-name live
  watchlist from the PINNED strategy-104 config
  (`.subrepo_runtime/repos/renquant-strategy-104/configs/strategy_config.json`)
  [VERIFIED — both files read 2026-08-10; watchlist-only names: CRWV, RKLB,
  SPCX].
- Watchlist pin validation (PR #963 review fix — the runtime checkout is a
  MUTABLE working tree): before any data read, the script asserts the
  checkout HEAD equals the `subrepos.lock.json` pin AND that the config bytes
  read are byte-identical to the blob committed at that HEAD (dirty tree
  fails); any mismatch exits nonzero naming both identifiers, and the control
  tests in `tests/test_data_completeness_registry.py` prove both the failure
  and the matching-pin positive path. Recorded provenance for THIS registry
  [VERIFIED — script run 2026-08-10, echoed in the CSV `#` header]:
  - `strategy104_lock_pin` = `e00d9356ac620426df031e0c08ce66301c50c22e`
  - `strategy104_checkout_head` = `e00d9356ac620426df031e0c08ce66301c50c22e`
  - `strategy_config_sha256` =
    `43cbb9b2021a1c68d45ad937ef2ed3854778e743713babe329929abf21901d77`
- Window: 2023-01-01..2026-08-07 = 902 SPY trading days [VERIFIED — SPY
  `1d.parquet` calendar].
- Sources: OHLCV (`data/ohlcv/<T>/1d.parquet`), SEC fundamentals
  (`data/sec_fundamentals_daily.parquet`), earnings surprise
  (`data/earnings_surprise/<T>.parquet`), sentiment
  (`data/news_sentiment_alpaca/<T>.parquet` — the read path of
  `scripts/build_alpha158_fund_panel.py::_add_sentiment_features`
  [VERIFIED — script source, line 353]).
- Derivation: `scripts/data_completeness_registry.py` (committed with this
  note). Registry: `doc/research/data/2026-08-10-data-completeness-registry.csv`
  (295 rows × 31 cols; the file starts with `#`-comment provenance lines —
  read it with `pandas.read_csv(path, comment='#')`). All thresholds are
  frozen constants in the script. Rev2 (pin validation + metadata header)
  re-derived byte-identical data rows vs rev1 [VERIFIED — `diff` of the
  comment-stripped rev2 CSV against the rev1 CSV at commit `ea875c2c`:
  zero differences].

## Counts by class

| class | all 295 | active 147 | notes |
|---|---|---|---|
| COMPLETE | 138 | 138 | includes the 10 ETFs (SEC/earnings not expected) |
| DEGRADED | 9 | 9 | ALL on the live watchlist; all SEC-fundamentals reasons |
| BROKEN | 148 | 0 | entirely the inactive corpus tail (see cross-check) |

[VERIFIED — registry CSV, `class` value_counts]

## The 9 DEGRADED names (all ACTIVE, all WATCHLIST — the worst offenders)

| ticker | reason | detail |
|---|---|---|
| SPCX | OHLCV short history + SEC absent | 39 bars since 2026-06-12 IPO — the 60d alpha158 feature windows cannot warm up; no SEC filings yet; 1 earnings row (2026-08-04) |
| C | SEC stale — a missed filing cycle | latest `fiscal_period_end` 2025-12-31 (`available_at` 2026-02-20): the Q1-2026 10-Q was never ingested; 219d old vs 129d median across active names |
| AEP | SEC absent (anomalous) | US large-cap utility with ZERO rows in `sec_fundamentals_daily.parquet` — unlike the foreign names below, this is a harvest gap, not a filer-type limitation |
| CRWV | SEC absent | IPO 2025-03; has filed 10-Qs since, so rows should exist by now — harvest never picked it up |
| ASML | SEC absent (foreign filer) | 20-F filer; median-impute documented as by-design in the panel builder |
| TSM | SEC absent (foreign filer) | same |
| SPOT | SEC absent (foreign filer) | same |
| V | SEC fund vector majority-null | 3/5 cols null on latest row: earnings_yield, book_to_price, gross_profitability |
| SPG | SEC fund vector majority-null | 3/5 cols null on latest row: earnings_yield, gross_profitability, roe (REIT tagging) |

[VERIFIED — registry CSV `reasons`; each detail re-derived by direct read of
the source parquet on 2026-08-10]

Impact channel: the panel builder left-joins fundamentals and fills NaN with
the per-date cross-sectional median (fallback 0), so these names are scored
on an imputed fund vector — silently, with no per-ticker receipt
[VERIFIED — `build_alpha158_fund_panel.py` merge + imputation block].

## What is clean (active names)

- OHLCV: 147/147 active names have last bar exactly 2026-08-07, zero missing
  trading days within their alive-span, longest gap 0 [VERIFIED — registry].
- Earnings surprise: all 137 active non-ETF names have a file; last quarter
  age ≤ 94 days (threshold 140) [VERIFIED — registry `earn_age_days`].
- Sentiment: 145/145 watchlist names have a file; staleness ≤ 17 days
  (threshold 30) [VERIFIED — registry `sent_age_days`].
- 28 further active names carry 1–2 null fund cols (e.g. gross_profitability
  for financials) — structural, recorded in the CSV, deliberately not flagged
  [VERIFIED — registry `sec_null_fund_cols_last`].

## Cross-check: the 148/292 active-vs-total split

The corpus panel shows 144–153 distinct tickers on its last ten dates
(2026-04-24..2026-05-07) [VERIFIED — groupby on the corpus parquet],
consistent with the ≈144–158 range discovered on 08-09. The registry's
independent activity criterion (OHLCV last bar ≥ 2026-08-03, the 5th-from-last
SPY trading day) marks 144/292 corpus names active + all 145 watchlist names
(147 union). The remaining **148 corpus names** all classify
BROKEN-inactive **naturally** — the uniform freshness rule catches them; no
delisted-list special-casing exists in the script. Verified: all 148 BROKEN
rows carry the `inactive:` reason and zero BROKEN rows are active
[VERIFIED — registry invariant check].

Precision on "inactive": 139 of the tail names' bars end 2026-05-12 and 9 end
2026-07-22/29 (NXPI, PCTY, ESTC, NVO, HUBS, OKTA, SHOP, PGR, ...) — these are
the dates the OHLCV harvest narrowed its coverage, so most of the tail is
*harvest-dropped*, not corporately delisted (GOOGL still trades; its bars
stop 2026-05-12 after the GOOG switch). Either way they are unusable for
scoring at the window end, which is what BROKEN measures
[VERIFIED — registry `ohlcv_last` distribution].

## Evidence block (§4(b))

```
artifact:      doc/research/data/2026-08-10-data-completeness-registry.csv
prod or exp:   measurement over prod data (read-only; no prod path written)
existing data: 08-09 session found ≈144-158 active names on recent corpus
               dates vs 292 total; this registry reproduces the split (144
               corpus-active) from an independent criterion (OHLCV freshness)
best-known?:   first per-ticker × per-source completeness registry (no prior
               variant exists)
scope:         "this is the 295-name union universe over 2023-01-01..
               2026-08-07, 4 sources, vs the prior coarse active-count only"
```

## Named follow-up (NOT in this PR)

**Enforcement hook — pipeline pre-scoring completeness gate:** the daily run
should consume this registry's derivation (not the frozen CSV) and refuse to
score a watchlist name whose fund vector would be silently median-imputed,
or surface a per-run DEGRADED receipt in the bundle. Tracked as a follow-up
issue in this repo. Separately actionable data fixes: (a) ingest C's missing
Q1-2026 10-Q, (b) add AEP + CRWV to the SEC harvest, (c) V/SPG XBRL tag
mapping.
