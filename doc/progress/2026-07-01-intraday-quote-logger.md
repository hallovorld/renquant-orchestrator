# Progress — decoupled observe-only intraday quote logger (tick feed)

Date: 2026-07-01
Scope: renquant105 Stage-1 operations-only pilot data collection (design
`doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md`, r11/r12).
RFC: #208. Companion consumer: orchestrator PR #215 (`intraday_pairing_logger.py`).

## Why

The paired-IS harness (#215) needs a **structured intraday tick feed** to pair the
batch next-open entry against the decision-time intraday reference (design §9.1 /
§9.2c: the class-D timing-only quote — the decision-time NBBO midpoint). Until that
feed exists, `intraday_pairing_logger.load_intraday_ticks` returns empty and **every
pair is censored `no_intraday_tick`**. This PR ships the missing producer.

## What

`src/renquant_orchestrator/intraday_quote_logger.py` — a **standalone, decoupled,
observe-only** quote poller. It samples the 104 watchlist during RTH and appends a
JSONL tick feed in the exact schema the consumer reads (`date`, `ticker`, `mid`,
`tick_time`; plus raw `bid`/`ask`/`last`/`ts` and provenance for the future §9.4
analysis). `entry_price` is deliberately not asserted — the consumer defaults the
hypothetical intraday entry to `mid`, the honest neutral choice for an observe-only
feed; a fill model is the future experiment's call.

Design points:
- **Decoupled / zero live-trading risk.** A separate process, NOT embedded in the
  decision/intraday runner. Read-only market data only: no orders, no positions,
  cash, pins, gates, or run state. It cannot affect a live trade.
- **Dependency-injected quote source.** `QuoteSource` protocol; the real impl
  `AlpacaQuoteSource` mirrors the umbrella construction
  (`backtesting/renquant_104/kernel/data.py`): lazy `alpaca-py`, `ALPACA_API_KEY` /
  `ALPACA_SECRET_KEY`, forced IEX feed, data client only (no trading client). Tests
  inject a deterministic fake — no network, no wall-clock.
- **Output off the umbrella tree.** Default under `default_data_root()` (honoring
  `RENQUANT_DATA_ROOT`): `<data_root>/logs/renquant105_pilot/intraday_ticks.jsonl`
  — mirrors the consumer's `DEFAULT_TICK_SOURCE` name, rooted at the operator data
  root, never the umbrella git tree.
- **Idempotent append.** One row per distinct quote observation
  `(date, ticker, tick_time)`; re-polling an unchanged quote or re-running a session
  is a no-op. Dedup survives restart (keys reloaded from the file).
- **Best-effort robustness.** A whole-batch fetch failure or any single-ticker miss
  is logged and skipped — never crashes the loop.
- **Modes.** `--once` (single sample) + `--json` summary, and a market-hours loop
  (`--cadence`, default 60s) that waits before the open and self-terminates at the
  16:00 ET close. `--force` bypasses the RTH gate for testing/off-hours.

Boundary compliance (CLAUDE.md): the orchestrator does not implement broker adapters
or decision/sizing internals — this only observes market data and provenances a log.

## Tests

`tests/test_intraday_quote_logger.py` — 27 tests, hermetic (fake source + injected
clock + tmp paths). Covers: mid/NBBO + fallback, record schema, market-hours gating,
per-ticker and whole-batch failure isolation, idempotent append (incl. restart),
loop with injected clock/sleep, watchlist load, `--once` CLI, credential preflight.
A round-trip test loads the feed through the **real** `intraday_pairing_logger`
consumer and asserts a non-censored pair; it is `importorskip`-guarded because #215
is not yet on `main` (skips until #215 merges, then asserts real interop — verified
locally by dropping the #215 module in: all 27 pass, round-trip included).

Run: `.venv/bin/python -m pytest tests/test_intraday_quote_logger.py -q` → 26 passed,
1 skipped on `main` today (round-trip skip); 27 passed once #215 is present.

## Proposed scheduled invocation (NOT installed)

Observe-only pilot collection, one bounded process per session. Do not wire until
the operator opts in; it needs read-only Alpaca market-data credentials.

```cron
# 09:30 ET, Mon–Fri — loops until the 16:00 ET close, then exits.
30 9 * * 1-5  cd <orchestrator> && RENQUANT_DATA_ROOT=<data_root> \
  .venv/bin/python -m renquant_orchestrator.intraday_quote_logger \
    --env-file <path>/.env --cadence 60
```

Then the paired-IS harness (#215) consumes it by pointing its `--tick-source` at the
same file:

```bash
.venv/bin/python -m renquant_orchestrator.intraday_pairing_logger \
  --date <YYYY-MM-DD> --tick-source <data_root>/logs/renquant105_pilot/intraday_ticks.jsonl
```

## Notes / follow-ups

- Holidays are not excluded (weekday + 09:30–16:00 ET only); a holiday yields
  stale/empty quotes that are logged and skipped — harmless for an observe-only feed.
  The schedule governs which days it runs.
- Free-tier IEX quotes are a partial-book reference, adequate for the Stage-1
  diagnostic mid; the §9.4 experiment decides whether SIP/full-NBBO is required.
- This is Stage-1 **operations-only** data collection: it renders no execution-quality
  verdict and gates nothing (design §9.3 / §9.4).
