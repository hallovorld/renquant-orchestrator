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
observe-only** quote poller. It samples the 104 watchlist during a real exchange
session and appends a JSONL tick feed in the exact schema the consumer reads
(`date`, `ticker`, `mid`, `tick_time`; plus raw `bid`/`ask`/`last`/`ts`, `status`,
`quote_age` and the frozen policy stamp for the future §9.4 analysis). `entry_price`
is deliberately not asserted — the consumer defaults the hypothetical intraday entry
to `mid`, the honest neutral choice for an observe-only feed; a fill model is the
future experiment's call. Midpoint-as-fill yields zero modeled shortfall by
construction, so this feed stores raw observations only and implies no executable
performance.

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
- **Modes.** `--once` (single sample) + `--json` summary, and a session loop
  (`--cadence`, default 60s) that waits before the open and self-terminates at the
  calendar close (incl. early closes). `--force` bypasses the sample gate for
  testing/off-hours, but off-hours quotes are still censored out-of-session.

Boundary compliance (CLAUDE.md): the orchestrator does not implement broker adapters
or decision/sizing internals — this only observes market data and provenances a log.

## Data-validity (addresses Codex r1 CHANGES_REQUESTED)

The r1 feed hard-coded weekday 09:30–16:00 ET and accepted `quote.ts` verbatim, so
it could log out-of-session or stale/future/crossed quotes as eligible decision
ticks. r2 makes the feed *eligibility-aware*:

- **Calendar-aware sessions.** Session boundaries now come from a dependency-injected
  `SessionCalendar`; the real `NyseSessionCalendar` is backed by
  `pandas_market_calendars` NYSE — the SAME primitive execution uses
  (`renquant_execution.preopen_cancel_gate`, and the 104 kernel `data.py` / `exits.py`
  / `t2_settlement.py`). Holidays (no session), half days / early closes (earlier
  close) and DST (tz-aware instants) are all honored. Tests inject a deterministic
  fake calendar. Out-of-session samples are censored, never logged as eligible.
- **Causality + freshness + same-session membership.** A frozen policy (`evaluate_quote`)
  requires `source_ts <= sampled_at` (small skew tolerance), a configured max age
  (`--max-quote-age`, default 120s), and that the quote's `source_ts` falls inside the
  current session. Crossed (`bid > ask`) / invalid (non-positive, non-finite) NBBO and
  unpriceable quotes are rejected. Every record carries `status` + `quote_age`; only
  `status=ok` rows reach the eligible feed (with a consumable `mid`), and every censor
  reason (`out_of_session`, `stale_quote`, `stale_prior_session`, `future_quote`,
  `crossed_nbbo`, `invalid_nbbo`, `no_source_ts`, `unpriceable`) is recorded WITH
  `mid=None` to an audit sidecar `<feed>.censored.jsonl` — auditable, never evidence.
- **Frozen eligibility-policy version.** Each record stamps `ELIGIBILITY_POLICY_VERSION`
  plus the concrete policy params (`max_quote_age_sec`, `session_open`/`session_close`),
  so a row self-identifies which policy admitted or censored it.

## Tests

`tests/test_intraday_quote_logger.py` — hermetic (fake source + fake calendar +
injected clock + tmp paths). Covers mid/NBBO + fallback, record schema, and — added
for the r1 review — the full data-validity surface: **holiday** (no session, all
censored), **early close / half day** (calendar closes at 13:00, a naive 14:00 would
be "open"), **DST boundary** (09:30 local in both EDT/EST seasons; UTC instant shifts
by the DST hour), **stale repeated prior-session quote**, **stale-by-age quote**,
**future/skewed quote**, **crossed and invalid NBBO**, **no-source-ts**, and
**partial source failures** (per-ticker miss + whole-batch failure isolation). Also:
idempotent append (incl. restart), the session loop with injected clock/sleep,
watchlist load, `--once` CLI, credential preflight, and a real NYSE-calendar
cross-check against a direct `pandas_market_calendars` schedule.

Contract test (the load-bearing integration): the tick feed is round-tripped through
the **actual #215 consumer** (`load_intraday_ticks` → `pair_records`) and asserted to
yield a non-censored pair. To keep it non-skipped and branch-independent, the #215
module is pinned VERBATIM as `tests/fixtures/intraday_pairing_logger_pr215.py` and
loaded in-process (`test_round_trip_into_vendored_pr215_consumer`, passing now); a
second `importorskip`-guarded test exercises the real installed module once #215
merges to `main`, at which point the fixture and its test are deleted.

Run: `.venv/bin/python -m pytest tests/test_intraday_quote_logger.py -q` → 45 passed,
1 skipped on `main` today (only the real-module round-trip skips; the vendored
contract test proves interop now); 46 pass once #215 is present.

## Proposed scheduled invocation (NOT installed)

Observe-only pilot collection, one bounded process per session. Do not wire until
the operator opts in; it needs read-only Alpaca market-data credentials.

```cron
# 09:30 ET, Mon–Fri — loops until the calendar close (incl. early closes), then
# exits. Holidays are self-skipping (no session -> no eligible ticks).
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

- Holidays, early closes and DST are now handled by the NYSE calendar (r2), not the
  schedule; out-of-session samples are censored to the audit sidecar rather than
  emitted as eligible ticks.
- Free-tier IEX quotes are a partial-book reference, adequate for the Stage-1
  diagnostic mid; the §9.4 experiment decides whether SIP/full-NBBO is required.
  A crossed/invalid NBBO from the partial book is censored, not emitted.
- This is Stage-1 **operations-only** data collection: it renders no execution-quality
  verdict and gates nothing (design §9.3 / §9.4).
