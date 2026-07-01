# Progress — observe-only real-time data plane + shadow model serving

Date: 2026-07-01
Scope: renquant105 Stage-1 operations-only pilot data collection (design
`doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md`, r11/r12).
RFC: #208. Consumes the #216 tick feed (`intraday_ticks.jsonl`).

## Why

RFC §4 names two of the six engineering pieces this PR builds: piece 2 (real-time
data plane) and piece 3 (live model serving). Stage 1 is OPERATIONS-ONLY (§9,
converged r11): before any intraday decision is trusted, we must first (a) assemble
a correct point-in-time intraday snapshot under the §6 causality/staleness contract,
and (b) accumulate a clean corpus of "what the model would score in real-time vs
what the batch scored". This PR ships exactly that data-collection scaffold — no
orders, no live decisions.

## What

`src/renquant_orchestrator/realtime_data_plane.py` — assembles a point-in-time
intraday MARKET SNAPSHOT for the watchlist from the #216 tick feed joined to the
latest daily feature reference. Row schema: `{as_of, ticker, intraday_mid,
quote_status, daily_feature_ref}` (+ provenance `source_ts`/`age_sec`/`source`/
`session_date`). Reuses the #216 freshness/session/causality rules (design §6):

- **Same-session** — only ticks whose session `date` equals the `as_of` session date
  are eligible; nothing carries across the session boundary.
- **Causality** (`source_ts <= as_of`) — a tick that arrives after `as_of` can never
  enter an earlier decision; the latest eligible tick wins. This is what makes a
  10:00 vs 12:00 snapshot differ only in newly-arrived state.
- **Freshness censoring** — if the chosen tick's age exceeds `staleness_sec` (default
  15 s, §10 hard-skip) the quote is CENSORED (`quote_status="stale"`,
  `intraday_mid=None`) so a stale tape never masquerades as fresh. `missing` covers a
  name with no eligible causal tick.

`src/renquant_orchestrator/shadow_realtime_serving.py` — given a snapshot + the daily
panel model (dependency-injected `ShadowScorer`), computes a SHADOW real-time
score/ranking and LOGS it PAIRED with the frozen batch score, as append-only JSONL
under `default_data_root()/logs/renquant105_pilot/shadow_realtime_serving.jsonl`. Each
row carries `batch_score`/`batch_rank`, `shadow_score`/`shadow_rank`, their deltas,
`quote_status`, and `daily_feature_ref`. STRICTLY A COLLECTOR: no PASS/FAIL, no
orders, no pins, no gates, no promotion, no live-state mutation.

Design points:
- **Observe-only, zero live-trading risk.** Neither module imports execution/broker
  code or touches positions, cash, pins, gates, or run state. Every record is stamped
  `observe_only: true`.
- **Dependency injection.** The tick-feed `TickFeedSource` and the `ShadowScorer` are
  Protocols. Real impls read the pinned inputs read-only: `JsonlTickFeedSource` reads
  the #216 feed; `load_pinned_panel_scorer` lazily loads the artifact via
  `renquant_common.load_scorer` (Stage-3 feature construction is an injected seam, not
  fabricated). Tests inject deterministic fakes + an explicit `as_of` and clock — no
  wall-clock, no network.
- **Off the umbrella tree.** Outputs default under `default_data_root()` (honoring
  `RENQUANT_DATA_ROOT`), never the umbrella git tree.
- **Idempotent append.** One shadow row per `(as_of, ticker)`; re-running the same
  snapshot writes zero new rows (keys reloaded from the file, survives restart).
- **Frozen-signal honesty (§6 class A).** In Stage 1 the model signal is frozen daily;
  scoring the live snapshot here is an OBSERVE-ONLY counterfactual (a Stage-3 preview),
  decoupled from every decision path so it can be measured before it is trusted.

## Tests

`tests/test_realtime_data_plane.py` (12) + `tests/test_shadow_realtime_serving.py` (7),
green under the RenQuant venv pytest: snapshot assembly (latest causal tick), causality
+ same-session + staleness censoring, missing/unpriceable handling, shadow-vs-batch
pairing logged, censored-row logging, dense-rank ties, idempotent append, injected
clock, and no-order/no-mutation invariants (only the log file is written; no
order/side/pin/gate/promote surface).

## Boundaries / not in scope

Boundary-compliant (CLAUDE.md): no broker adapter, no signal/decision internals — this
is control-plane assembly + provenance only. NOT built here: the intraday decision loop
(piece 1), live state/gate evaluation (piece 4), entry-timing (piece 5), order
idempotency (piece 6) — those are the execution/pipeline PRs (§8) and later stages.
This PR is inert data collection: it never reaches a live decision.
