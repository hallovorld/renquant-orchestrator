# renquant105 execution reconciler — §7 safety core (OBSERVE-ONLY, Stage-1)

STATUS: Stage-1 observe-only / advisory. Detects + reports drift; places/cancels NO orders.

WHAT: New `src/renquant_orchestrator/execution_reconciler.py` implementing the three §7 /
§10 safety pieces of the merged 105 design
(`doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md`):

1. **Order-lifecycle state machine** (`LifecycleMachine` over `OrderState`
   NONE→INTENDED→SUBMITTED→ACCEPTED→PARTIALLY_FILLED→FILLED plus CANCELED/REJECTED/EXPIRED/
   STALE_PENDING) with legal-transition rules, a raw Alpaca `order.status` → canonical-state
   map, and the two-level §7 idempotency identity: stable `parent_intent_id =
   hash(account, symbol, trading_day, side, signal_version)` (the dedup key) + per-attempt
   `child_order_id = parent:attempt_n` (the unique broker client-order-id). `IntentRegistry`
   makes a re-run / redelivery of the same decision a no-op → no duplicate order.
2. **Quantity accounting** (`QuantityAccount`, `account_from_children`) splitting the §7
   *economic* invariant (`cum_filled + open_qty <= target_qty`; over-fill = breach) from the
   *audit* invariant (`gross_submitted_qty`, which may exceed target via canceled/rejected
   retries). Under-fill and whole-share-vs-fractional are *detected* read-only (Stage-1 is
   whole-share; §11 defers fractional to Stage-2) — never rounded.
3. **Broker/local reconciliation** (`ExecutionReconciler`) — diffs local vs
   broker-authoritative positions/orders/accounts, classifies each divergence
   (`DivergenceKind`: MISSING_LOCAL_FILL, PHANTOM_LOCAL_POSITION, QUANTITY_MISMATCH,
   ORPHAN_BROKER_ORDER, UNTRACKED_LOCAL_ORDER, ORDER_STATE_DRIFT, STALE_PENDING_ORDER,
   OVER_FILL, UNDER_FILL, FRACTIONAL_QUANTITY) with a `Severity`, and returns a structured,
   JSON-serialisable `ReconciliationReport`. The report carries the §7 *advisory*
   `halt_new_entries_advised` (CRITICAL or open-order ledger mismatch → advise halting new
   entries, exits still allowed) — **advice only, never enforced**. An ntfy alert
   (`maybe_alert`) fires only behind an explicit `enabled` flag; default is silent.

Loaders are dependency-injected `Protocol`s (`LocalStateLoader` / `BrokerStateLoader`) so the
whole module is pure and unit-testable with fixtures — **no live broker calls anywhere**, and
it imports no broker runtime (passes `test_import_boundaries`). Broker-row normalisation
(`Position.from_broker` / `OrderRecord.from_broker`) matches the real Alpaca / live-104 field
names (`symbol`/`ticker`, `qty`/`quantity`, `filled_qty`, `filled_avg_price`,
`client_order_id`, `id`, `status`, `submitted_at`), read from
`RenQuant/backtesting/renquant_104/live_state.alpaca.json` (read-only) and `live/alpaca_broker.py`.

WHY: §7 dedup-vs-pending is the RFC's #1 failure mode. Per §8 the *enforcing* state machine
lives in the execution repo; this orchestrator-side library is the independent, observe-only
audit that rides alongside it — the Stage-1 reconciliation-green precondition (§9.3
"broker state == ledger == run-bundle every session") without touching the order path.

EVIDENCE: `tests/test_execution_reconciler.py` — 34 tests green
(`RenQuant/.venv/bin/python -m pytest tests/test_execution_reconciler.py -q` → 34 passed).
Covers legal happy-path + partial-chains, illegal transitions (terminal reuse / skip /
backwards), two-level idempotency (same key → no dup), the cancel/retry worked example
(target 10, gross 16, never over-fills), over/under-fill, whole-share vs fractional, every
divergence class + its severity, the §7 halt advisory, stale-pending vs injected `as_of`,
Alpaca field-name normalisation, report serialisation, flag-gated ntfy suppression, and a
no-mutation (observe-only) assertion.

SCOPE / BOUNDARY: orchestrator does NOT implement the broker adapter (execution) or
sizing/decision internals (pipeline) — this is read-only diff + report only. Inert until the
execution + pipeline slices (§8 orders 1–2) are merged and pinned; nothing here is wired into
the daily/intraday loop in this PR.

NEXT: wire the reconciler into the intraday run-bundle as a readonly per-tick audit once the
execution-repo state machine (§8 order 1) lands; surface `halt_new_entries_advised` to the
control plane (advisory) alongside the §10 kill switch. No expansion of scope beyond
observe-only until then.
