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
  §5.3 plumbing baseline; also the frozen **primary** policy). As-of correct: the
  first eligible tick is taken, never a later, more favorable one.
- `vwap_cross` — first eligible bullish cross-up of the causal running VWAP (the #216
  quote feed carries no per-tick volume, so this degenerates to a running mean of
  quote mids — documented, deterministic).
- `opening_range_breakout` — first eligible break above the opening-range high
  (`opening_range_minutes = 30`, causal — the range is built only from ticks inside
  the early window, anchored on the calendar-resolved session open).
- `pullback_to_ref` — first eligible dip ≥ `pullback_pct` (0.30%) below a **causal,
  known-as-of** reference: a prior close / frozen daily level (`prior_close_ref`,
  known pre-market) when supplied, else the **observed opening print** (first
  in-session eligible tick mid — the §9.2c arrival reference). The next-open **batch
  reference is NOT used to trigger** (look-ahead); it is recorded as provenance only.

Frozen params: entry window `open + 5 min` … `close − 30 min` (§11b, scaled to the
calendar-resolved session — no hard-coded clock), class-D quote freshness hard-skip
`15 s` (§6). Config fingerprint (`2d5527caff70f91f`, schema v2) pins the corpus and
now also pins the frozen confirmatory-analysis design (below).

Frozen confirmatory-analysis design (§9.4) — declared in the manifest, **computed by
none of Stage-1** (observe-only renders no verdict), so the deferred experiment
inherits an immutable spec and cannot post-hoc pick a winner against the same data:

- **primary policy / endpoint** — `immediate_first_eligible_tick`; implementation
  shortfall vs the arrival reference, deferred to §9.4;
- **analysis unit** — session-level;
- **censoring** — recorded by cause, never imputed (§9.2d);
- **cost/fill model** — arrival-mid reference, zero modeled shortfall by construction;
- **minimum dates** — ≥ 20 disjoint pilot sessions before any confirmatory inference
  is designed (a floor; the final power-based N is set against real variance in §9.4);
- **multiplicity control** — Holm–Bonferroni, secondary policies vs the primary;
- **period** — pilot period is selection-only; the confirmatory evaluation period is
  held out and untouched during pilot collection.

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
- **Reuse the #216 feed's certification — do not re-collect, do not re-derive.**
  Consumes the same `intraday_ticks.jsonl` and reuses #216's frozen eligibility rather
  than reimplementing weaker rules: admits ONLY rows the producer stamped
  `status = "ok"` (a censored / legacy / unverified row is dropped, never evidence);
  reads the **calendar-resolved** session bounds #216 stamps (`session_open` /
  `session_close`, from the shared NYSE `pandas_market_calendars` primitive — holiday
  / half-day / DST aware), so the §11b window **scales to the actual session with no
  hard-coded 09:30–16:00 weekday rule**; requires **proven freshness** (drops a row
  whose quote age is unknown, and one staler than the 15 s class-D hard-skip); skips
  unpriceable rows. Carries the producer's frozen `eligibility_policy_version` onto
  every shadow row.
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
  provenance), `causal_reference` / `causal_reference_kind` (the known-as-of level a
  reference-relative policy triggered on), `prior_close_ref`, `batch_ref` +
  `batch_ref_used_for_trigger: false` (provenance only, never a trigger),
  `feed_eligibility_policy_version`, `signal_version`, `policy_params`,
  `config_fingerprint`, and the observe-only markers. No shortfall / fill / PnL /
  verdict field exists.

Boundary compliance (CLAUDE.md): the orchestrator does not implement broker adapters
or decision/sizing internals — this only observes the timing feed and provenances a log.

## Tests

`tests/test_entry_timing_shadow.py` — 46 tests, hermetic (injected tick timestamps +
tmp paths, no wall-clock, no network). Covers: the frozen pre-registration (policy
set + stable fingerprint + manifest **incl. the frozen confirmatory design**, and
that the fingerprint pins the design not just the policy knobs); `normalize_ticks`
eligibility/causality/freshness (sort, session-bounds membership, stale-quote
hard-skip, unpriceable skip, bid/ask mid, ticker/date filter, **status≠ok drop**,
**missing-status drop**, **unknown-quote-age drop**, **missing-session-bounds drop**,
**stamped-age preferred over recompute**); each policy's correct selection **and
as-of enforcement** (a later favorable tick is not chosen) + conviction/window gating
+ censoring by cause; the **causal pullback reference** (prior-close, opening-print
fallback, and that `batch_ref` is provenance-only and never triggers); the **§11b
window scaling to an early-close session**; record shape (required keys present, no
fill-quality keys leak); idempotent append; the **no-order invariant**; read-only
loaders; end-to-end `collect` (writes nothing; missing feed → all censored; threads
the causal prior-close ref); and CLI observe-only surfaces.

Run: `.venv/bin/python -m pytest tests/test_entry_timing_shadow.py -q` → 46 passed.
(The full-suite `renquant_pipeline` / `renquant_execution` collection errors on an
isolated worktree are the sibling-repo PYTHONPATH env, not this change — they fail
identically on the pristine branch.)

## Review response — Codex CHANGES_REQUESTED (2026-07-01)

1. **Blocking look-ahead in `pullback_to_ref`.** The next-open batch reference is no
   longer used to trigger — it is not known at the decision instant. The pullback
   reference is now strictly **causal / known-as-of**: a `prior_close_ref` (frozen
   daily level, pre-market) when supplied, else the **observed opening print** (first
   in-session eligible tick mid, §9.2c). `batch_ref` is recorded for provenance only,
   flagged `batch_ref_used_for_trigger: false`, and cannot drive an online entry (a
   test proves a `batch_ref` alone never triggers).
2. **Session handling now consumes #216, not a hard-coded weekday clock.**
   `normalize_ticks` requires the producer's `status = "ok"`, reads the
   calendar-resolved `session_open` / `session_close` #216 stamps (holiday / early
   close / DST aware) so the §11b window scales with no hard-coded 09:30–16:00, and
   drops any row whose quote age is unknown or that lacks calendar bounds. The old
   `market_phase` / `is_market_hours` weekday-RTH helpers are removed; the
   `status`/`eligibility_policy_version` constants bind to #216 when importable.
3. **Real pre-registration, not four names in code.** `EntryTimingConfig` now freezes
   the primary policy/endpoint, session-level analysis unit, censoring rule,
   cost/fill model, minimum pilot dates, Holm–Bonferroni multiplicity control, and a
   held-out confirmatory period (pilot = selection only). All are in the fingerprint
   and the `--print-preregistration` manifest; Stage-1 still computes none of them
   (observe-only, deferred to §9.4).

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
- The causal pullback reference (`prior_close_ref` per ticker — a frozen daily level
  known pre-market) is optional and only feeds `pullback_to_ref`; absent it, the
  policy uses the observed opening print. The next-open `batch_ref` (owned by the
  paired-IS harness #215's run-DB read) is recorded for provenance only and never
  triggers. This evaluator is deliberately decoupled from the DB — it reads the tick
  feed + a small admitted-names JSON so a bug in it cannot touch live state.
- Volume-weighted VWAP is a follow-up once the feed carries per-tick size; today it is
  an equal-weighted running mean of quote mids (documented).
