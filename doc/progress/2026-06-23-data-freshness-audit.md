# 2026-06-23 — Data-freshness audit for the daily-full pipeline

STATUS: PR diagnostic layer. Not a complete daily-full safety control until
`daily_104.sh` / ntfy wiring and per-candidate integrity gates land.

WHAT: New read-only `scripts/data_freshness_audit.py` that audits the freshness
(and fundamental completeness) of the data sources the renquant_104 daily-full
pipeline depends on — ohlcv / news-sentiment / SEC fundamentals — and emits a
compact one-line summary suitable for an ntfy push
(`DATA FRESHNESS 🔴 | ohlcv ✅0d | sentiment ✅0d | fundamentals 🔴91d`).
Per-source warn/critical day thresholds; active-watchlist coverage for
per-ticker stores; defensive (missing file → UNKNOWN, no throw); exit 0 by
default, `--fail-on-critical` / `--fail-on-unknown` opt-in. Per-source
freshness basis: ohlcv = oldest (every name must be current); sentiment =
newest/feed-ingestion (a quiet valid ticker is not a stale feed). Fundamentals
status combines DATE freshness AND active-watchlist completeness — a current-
dated but mostly-empty panel cannot show green (pre-registered thresholds:
WARN < 90% active complete, CRITICAL < 50%; panel-wide completeness reported
alongside). 28 unit tests.

WHY-DIR: 2026-06-23 the daily-full scored + traded on a `sec_fundamentals_daily`
parquet that was 91 days stale (last row 2026-03-24) with only 57/829 tickers
fundamentally complete — and nothing surfaced it, because price/sentiment were
fresh. Operator mandate: the pipeline must check data freshness and report it via
ntfy each daily-full run. This PR is a universe-level diagnostic only; it does
not close the incident by itself. A per-candidate / per-holding
`DataIntegrityJob` (block/flag on completeness) and scheduler notification
wiring are required before this becomes an operational control.

EVIDENCE:
- `[VERIFIED]` 28/28 tests pass:
  `/Users/renhao/miniconda3/envs/renquant/bin/python -m pytest -q tests/test_data_freshness_audit.py`
  → `28 passed`.
- `[VERIFIED]` live read-only run vs the umbrella data root (2026-06-24) prints
  `DATA FRESHNESS 🔴 | ohlcv ✅1d | sentiment ✅0d | fundamentals 🔴1d` —
  fundamentals is CRITICAL because only **58/145 active names (40%)** have a
  complete latest fundamental row (panel-wide 58/829), even though the panel
  DATE is now current. This is the correct, non-green result: the completeness
  half of the 2026-06-23 incident is no longer hidden.
- `[RESOLVED]` Codex's sentiment-semantics concern: the earlier `sentiment 🔴42d`
  was a quiet-ticker artifact (oldest active-ticker news was 2026-05-12), not a
  stale feed. Sentiment now classifies on feed-ingestion recency (newest), with
  the oldest/quiet date and missing coverage reported in the detail rather than
  hard-failing. Missing files still downgrade FRESH→STALE so a coverage gap is
  not a silent green.
- `[RESOLVED]` Codex's fundamentals false-green concern: status now combines
  date freshness with active-watchlist completeness (worst-of), so a fresh-dated
  but mostly-empty panel turns CRITICAL. The detail separates active (58/145)
  from panel (58/829) completeness so the operator sees the traded-universe view.

NEXT (follow-ups, out of scope for this read-only diagnostic): (1) wire into
`daily_104.sh` as a Step-1c notify; (2) per-candidate + per-holding
`DataIntegrityJob` (warn+downweight candidates, flag holdings) — this is the
real fail-closed gate, NOT this universe-level summary; (3) per-ticker
news-presence policy (quiet → neutral vs noted) once DataIntegrityJob defines
candidate-level semantics; (4) safe fundamentals backfill / date-coverage
verification before any prod swap.
