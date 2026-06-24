# 2026-06-23 — Data-freshness audit for the daily-full pipeline

STATUS: landed (script + tests); daily_104.sh wiring + ntfy is a follow-up umbrella change.

WHAT: New read-only `scripts/data_freshness_audit.py` that audits the freshness
(and fundamental completeness) of the data sources the renquant_104 daily-full
pipeline depends on — ohlcv / news-sentiment / SEC fundamentals — and emits a
compact one-line summary suitable for an ntfy push
(`DATA FRESHNESS 🔴 | ohlcv ✅0d | sentiment ✅0d | fundamentals 🔴91d`).
Per-source warn/critical day thresholds; defensive (missing file → UNKNOWN, no
throw); exit 0 by default, `--fail-on-critical` opt-in. 18 unit tests.

WHY-DIR: 2026-06-23 the daily-full scored + traded on a `sec_fundamentals_daily`
parquet that was 91 days stale (last row 2026-03-24) with only 57/829 tickers
fundamentally complete — and nothing surfaced it, because price/sentiment were
fresh. Operator mandate: the pipeline must check data freshness and report it via
ntfy each daily-full run. This is the universe-level layer; a per-candidate /
per-holding `DataIntegrityJob` (block/flag on completeness) is the next PR.

EVIDENCE:
- `[VERIFIED]` 18/18 tests pass: `pytest tests/test_data_freshness_audit.py -q` → `18 passed`.
- `[VERIFIED]` live run vs the umbrella data root prints
  `fundamentals CRITICAL 91d last=2026-03-24, 57/829 tickers complete`;
  ohlcv + sentiment FRESH 0d.

NEXT: (1) wire into `daily_104.sh` as a Step-1c notify; (2) per-candidate +
per-holding `DataIntegrityJob` (warn+downweight candidates, flag holdings);
(3) safe fundamentals backfill (staging verified 7%→42% complete, date-coverage
fix pending before a prod swap).
