# Progress — observe-only entry-timing shadow evaluator (pre-registered policies)

Date: 2026-07-01
Scope: renquant105 Stage-1 operations-only pilot data collection (design
`doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md`, r11/r12).
RFC: #208. Companion feed: orchestrator #216 (`intraday_quote_logger.py`, the tick
producer). Companion consumer: #215 (`intraday_pairing_logger.py`, paired IS).

## Why

The RFC's Stage-1 open question §5.3 / §15.2 is *which* intraday entry-timing policy
to eventually act on — immediate-on-conviction is the plumbing baseline, but
confirmation logic (VWAP / breakout / pullback) is the part that could add
information (§12 Stage 2). Deciding that needs **pilot data on what each candidate
policy WOULD have chosen**, collected observe-only, before any of them touches
capital. This ships that collector. It **pre-registers** the candidate policy set so
the future experiment (§9.4) attributes every row to an exact, frozen parameterization
— no post-hoc policy tuning against the same data it will be judged on.

## What

`src/renquant_orchestrator/entry_timing_shadow.py` — an **observe-only** evaluator.
For each daily-admitted name on a session it replays the frozen candidate policies
against the #216 tick feed and logs, per name per policy, **what that policy would
have chosen**: the entry instant + the reference quote at that instant + eligibility.
It places **no** orders, makes **no** live decision, and renders **no**
shortfall / fill / execution-quality / PASS-FAIL claim (all deferred to §9.4).

Pre-registered policy set (frozen in `EntryTimingConfig`, fingerprinted onto every
row; `--print-preregistration` emits the manifest):

- `immediate_first_eligible_tick` — the first eligible tick at/after conviction (the
  §5.3 plumbing baseline). As-of correct: the first eligible tick is taken, never a
  later, more favorable one.
- `vwap_cross` — first eligible bullish cross-up of the causal running VWAP (the #216
  quote feed carries no per-tick volume, so this degenerates to a running mean of
  quote mids — documented, deterministic).
- `opening_range_breakout` — first eligible break above the opening-range high
  (`opening_range_minutes = 30`, causal — the range is built only from ticks inside
  the early window).
- `pullback_to_ref` — first eligible dip ≥ `pullback_pct` (0.30%) below the reference
  (the next-open batch ref when supplied — §9.2 — else the session's first tick mid).

Frozen params: entry window `open + 5 min` … `close − 30 min` (§11b),
class-D quote freshness hard-skip `15 s` (§6). Config fingerprint pins the corpus.

Design points:
- **Observe-only / zero live-trading risk.** A downstream, purely observational
  reader of the class-D timing quote feed. No orders, positions, cash, pins, gates, or
  run state. Every row is stamped `observe_only: true`, `places_orders: false`; a test
  asserts the module source holds no order-placement surface.
- **Pure functions + as-of causality.** Each policy is a pure function that walks the
  tick series ascending by `tick_time` and returns the FIRST tick satisfying its
  trigger — it never looks forward for a better price; running state (VWAP, opening
  range) accumulates only from ticks at/before the evaluated tick. No wall-clock is
  read on the evaluation path; every timestamp is injected via the ticks.
- **Reuse the #216 feed's rules — do not re-collect.** Consumes the same
  `intraday_ticks.jsonl` and reuses its session (RTH [09:30,16:00) ET), causality, and
  freshness rules; drops out-of-session / stale / unpriceable rows, never imputes.
- **Censoring recorded, never imputed (§9.2d).** A policy that never triggers is
  logged `eligible: false` + a `censored_reason` (`no_eligible_tick`, `no_vwap_cross`,
  `no_breakout`, `no_opening_range`, `no_pullback`, `no_ticks`, `no_reference`).
- **Output off the umbrella tree.** Default under `default_data_root()` (honoring
  `RENQUANT_DATA_ROOT`):
  `<data_root>/logs/renquant105_pilot/entry_timing_shadow.jsonl` — beside the
  #215/#216 pilot artifacts, never the umbrella git tree.
- **Idempotent append.** One row per `(date, ticker, policy)`; re-running a session is
  a no-op. Keys reload from the file so dedup survives restart.
- **Row shape (raw refs only):** `{date, ticker, policy, entry_tick_time,
  entry_ref_quote, eligible, censored_reason}` plus `entry_quote` (raw bid/ask/last
  provenance), `batch_ref`, `signal_version`, `policy_params`, `config_fingerprint`,
  and the observe-only markers. No shortfall / fill / PnL / verdict field exists.

Boundary compliance (CLAUDE.md): the orchestrator does not implement broker adapters
or decision/sizing internals — this only observes the timing feed and provenances a log.

## Tests

`tests/test_entry_timing_shadow.py` — 36 tests, hermetic (injected tick timestamps +
tmp paths, no wall-clock, no network). Covers: the frozen pre-registration (policy
set + stable fingerprint + manifest); `normalize_ticks` session/causality/freshness
(sort, out-of-session drop, stale-quote hard-skip, unpriceable skip, bid/ask mid,
ticker/date filter); each policy's correct selection **and as-of enforcement** (a
later favorable tick is not chosen) + conviction/window gating + censoring by cause;
record shape (required keys present, no fill-quality keys leak); idempotent append
(re-append = 0 new, new names append without duplicating); the **no-order invariant**
(module source has no order surface; every row `observe_only`/`places_orders=false`);
read-only loaders; end-to-end `collect` (writes nothing; missing feed → all censored);
and CLI observe-only surfaces (`--print-preregistration`, `--dry-run` write nothing).

Run: `.venv/bin/python -m pytest tests/test_entry_timing_shadow.py -q` → 36 passed.
Full suite green: 603 passed, 3 skipped.

## Proposed scheduled invocation (NOT installed)

Observe-only, one bounded pass per session after the tick feed for that day exists.
Do not wire until the operator opts in.

```bash
# after the #216 feed for the session has been collected
.venv/bin/python -m renquant_orchestrator.entry_timing_shadow \
  --date <YYYY-MM-DD> \
  --tick-source <data_root>/logs/renquant105_pilot/intraday_ticks.jsonl \
  --admitted-json <admitted.json>   # [{date,ticker,side?,signal_version?,conviction_time?}]
```

## Notes / follow-ups

- This is Stage-1 **operations-only** pilot collection: it renders no execution-quality
  verdict, ranks no policy, and gates nothing (design §9.3 / §9.4). The frozen policy
  params are starting values, pinned only so the corpus is reproducible — the §9.4
  experiment decides which policy (if any) graduates and against what bar.
- The batch reference (`batch_ref` per ticker) is optional and only feeds
  `pullback_to_ref`; the paired-IS harness (#215) owns the run-DB read of the actual
  next-open batch fill. This evaluator is deliberately decoupled from the DB — it reads
  the tick feed + a small admitted-names JSON so a bug in it cannot touch live state.
- Volume-weighted VWAP is a follow-up once the feed carries per-tick size; today it is
  an equal-weighted running mean of quote mids (documented).
