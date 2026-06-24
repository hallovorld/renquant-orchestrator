# 2026-06-23 — Data-freshness audit for the daily-full pipeline

STATUS: PR diagnostic layer. Not a complete daily-full safety control until
`daily_104.sh` / ntfy wiring and per-candidate integrity gates land.

WHAT: New read-only `scripts/data_freshness_audit.py` that audits the freshness
(and fundamental completeness) of the data sources the renquant_104 daily-full
pipeline depends on — ohlcv / news-sentiment / SEC fundamentals — and emits a
compact one-line summary suitable for an ntfy push
(`DATA FRESHNESS 🔴 | ohlcv ✅0d | sentiment 🔴42d | fundamentals 🔴91d`).
Per-source warn/critical day thresholds; active-watchlist coverage for
per-ticker stores; defensive (missing file → UNKNOWN, no throw); exit 0 by
default, `--fail-on-critical` / `--fail-on-unknown` opt-in. 22 unit tests.

WHY-DIR: 2026-06-23 the daily-full scored + traded on a `sec_fundamentals_daily`
parquet that was 91 days stale (last row 2026-03-24) with only 57/829 tickers
fundamentally complete — and nothing surfaced it, because price/sentiment were
fresh. Operator mandate: the pipeline must check data freshness and report it via
ntfy each daily-full run. This PR is a universe-level diagnostic only; it does
not close the incident by itself. A per-candidate / per-holding
`DataIntegrityJob` (block/flag on completeness) and scheduler notification
wiring are required before this becomes an operational control.

EVIDENCE:
- `[VERIFIED]` 22/22 tests pass:
  `/Users/renhao/miniconda3/envs/renquant/bin/python -m pytest -q tests/test_data_freshness_audit.py`
  → `22 passed`.
- `[VERIFIED]` live run vs the umbrella data root prints
  `fundamentals CRITICAL 91d last=2026-03-24, 57/829 tickers complete`;
  active-watchlist ohlcv is FRESH 0d with 145/145 present.
- `[DESIGN QUESTION]` Active-watchlist sentiment now reports CRITICAL 42d
  because the oldest ticker-level latest news row is 2026-05-12. That may be a
  real coverage gap or simply "no recent news" for a valid quiet ticker. Do not
  use this as a hard fail gate until the desired sentiment acceptance criterion
  is explicit.

NEXT: (1) wire into `daily_104.sh` as a Step-1c notify; (2) per-candidate +
per-holding `DataIntegrityJob` (warn+downweight candidates, flag holdings);
(3) define source-specific acceptance rules: ohlcv should use worst active
watchlist freshness; fundamentals should use panel date + active-candidate
completeness; sentiment needs separate feed-ingestion freshness vs per-ticker
news-presence semantics; (4) safe fundamentals backfill (staging verified
7%→42% complete, date-coverage fix pending before a prod swap).
