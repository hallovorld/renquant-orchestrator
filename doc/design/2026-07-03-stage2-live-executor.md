# Stage-2 live executor — built dark behind the quadruple authorization gate (sprint D2)

STATUS: design note for `src/renquant_orchestrator/intraday_live_executor.py`.
Companion to RFC #208 (`doc/design/2026-06-30-renquant105-intraday-decisioning-architecture.md`
§7 / §9.3a / §10). The operator directive for this sprint: **ALL of the
Stage-2 live-mode code lands now; ENABLEMENT stays behind the pre-registered
§9.3a authorization gate.** That separation is a hard boundary and is
restated at the end of this note.

## 1. What this ships

The `mode: "live"` tick path the Stage-1 scheduler deliberately did not
implement (its `resolve_mode` downgrades `live` → shadow with a counter —
untouched by this PR):

- **`LiveTickExecutor`** — order INTENTS from the slice-2 pipeline tick
  (renquant-pipeline `intraday_decisioning`, consumed via the same
  normalized payload the shadow log records) → registered as parent intents
  in slice 1's `OrderStateBook`
  (`renquant_execution.order_state_machine` — consumed, never
  reimplemented) → submitted through the REAL `AlpacaBrokerPort` adapter,
  OWNED by renquant-execution (see next bullet) →
  fills/cancels reconciled back into the book → the book snapshot persisted
  after every tick to `data/rq105/order_state_book.json` in slice 1's exact
  `to_snapshot()`/`from_snapshot()` shape (a STATE file under the operator
  data root — not canonical prod data, never the umbrella git tree; the
  Stage-1 reader `load_order_state_reservations` parses it, pinned by test).
- **`AlpacaBrokerPort` — owned by renquant-execution, NOT this repo**
  (architecture fix, codex round 2: this repo's CLAUDE.md forbids
  implementing broker adapters here, and `BrokerPort`'s own docstring
  reserved "Alpaca adapter implements this later" for the execution repo).
  It lives in `renquant_execution.alpaca_broker_port`
  (renquant-execution#21): slice 1's `BrokerPort` protocol over the Alpaca
  trading REST API — `client_order_id` = the slice-1 child id (broker-side
  idempotency), DAY time-in-force always (§11b no-carry), limit vs market
  pre-declared in the authorization artifact (A5.2 — never per-order:
  entries default marketable-limit at the class-D reference price ±
  `limit_price_offset_bps`, exits default market). GET-only reads
  (`open_orders`, `order_status`) follow the `AlpacaLiveStateSource`
  lazy-env-credential pattern. This module only injects it as the CLI's
  DEFAULT `port_factory`, through a LAZY import
  (`_load_alpaca_broker_port_cls`) executed inside the factory — which the
  runner invokes only AFTER the §9.3a quadruple gate arms. Both
  consequences are pinned by test: merge order with renquant-execution#21
  is free (an execution checkout without the adapter cannot break module
  import, shadow sessions, or this suite), and a session that ARMS without
  the adapter fails closed with `Stage2ContractError` — never silently.
- **`LiveSessionRunner`** — the session loop: evaluates the quadruple gate
  at session start; if armed, drives live ticks (same §5/§11b windows,
  calendar, class-A/B/C input discipline as the shadow scheduler); if ANY
  gate is missing, delegates to the UNCHANGED Stage-1 `SessionScheduler`
  (shadow, counted). `python -m renquant_orchestrator.intraday_live_executor`
  is a drop-in replacement for the shadow scheduler entrypoint: while
  unarmed it behaves identically to today.

## 2. The quadruple authorization gate (§9.3a)

Live submission arms **iff ALL FOUR** hold (`resolve_stage2_arming`,
evaluated independently every session, every gate recorded in the manifest):

| # | Gate | Source of truth |
|---|------|-----------------|
| 1 | `intraday_decisioning.mode == "live"` (enabled, error-free) | the PINNED strategy config — strategy-104's own test currently pins `mode == "shadow"`; rewriting that pin IS part of the authorization act |
| 2 | a valid, schema-checked, unexpired authorization FILE | `data/rq105/stage2_authorization.json` |
| 3 | env `RENQUANT_INTRADAY_LIVE=1` | the session environment (distinct from the Stage-1 `RENQUANT_INTRADAY_DECISIONING` flag) |
| 4 | the kill-switch file ABSENT | `data/rq105/intraday_decisioning.KILL` (same file the shadow scheduler re-checks every cycle) |

**ANY missing gate ⇒ shadow (counted)** — `live_mode_downgraded_count` plus
the per-gate arming record land in the session manifest. The broker-port
factory is invoked only AFTER the gate arms: an unarmed session can never
construct a submitting client.

### 2.1 The authorization-file schema

```json
{
  "authorized_by": "<the accountable human>",
  "date": "YYYY-MM-DD",
  "evidence": {
    "shadow_sessions_clean": 5,
    "replay_audits_green": true,
    "entry_timing_report": "<path/URI of the reviewed readout>"
  },
  "daily_entry_notional_cap": 500.0,
  "expiry": "YYYY-MM-DD",
  "order": {
    "entry_order_type": "limit",
    "exit_order_type": "market",
    "limit_price_offset_bps": 0.0
  }
}
```

Validation (every violation reported, not just the first —
`Stage2Authorization.from_payload`): `authorized_by` non-empty;
`date` not post-dated; `expiry` not passed; `expiry − date ≤ 31 days`
(§9.3a's ~one-month/20-session duration cap — an open-ended grant is
production by inertia, not a canary); `daily_entry_notional_cap` positive
finite (**default proposal $500** — the binding value is always the file's);
`evidence.shadow_sessions_clean ≥ 5` (§9.3 K); `evidence.replay_audits_green`
literally `true`; `evidence.entry_timing_report` non-empty; order types in
`{limit, market}`, offset in `[0, 100]` bps.

## 3. The §9.3a authorization protocol — VERBATIM

Quoted verbatim from RFC #208 §9.3a ("Canary envelope + economic
authorization — what it takes to expand or go live (converged r12)"):

> **Operational-correctness acceptance (§9.3: safety / idempotency /
> reconciliation / Tier-1 halt) gates whether the frozen canary may RUN AT
> ALL; it NEVER authorizes expansion or go-live.** The two are kept
> deliberately separate so the engineering RFC stays shippable without
> reviving the (deferred) statistics.
>
> **No expansion beyond the frozen canary envelope, and no general go-live,
> until EITHER:**
> - the deferred **simplified experiment-prereg PR (§9.4)** consumes the
>   collected pilot data and supplies an **EXPLICIT AUTHORIZING decision**
>   (its execution-quality / economic read clears its own pre-registered
>   bar, decided against real pilot variance), **OR**
> - the **operator explicitly accepts the economic risk in a SEPARATE,
>   RECORDED decision** — a distinct decision artifact, **not** implied by
>   Stage-1's operational PASS.
>
> **Bounded canary envelope — so "extend to collect data" cannot become
> indefinite production by inertia** (proposed Stage-1 defaults, sized to
> the ~$10.5k book; operational, debatable — see open question §15.7):
>
> | Bound | Proposed default | Meaning |
> |---|---|---|
> | Canary allowlist | **1–2 pre-declared names** | frozen; not widened without §9.3a authorization |
> | Canary notional cap | **pre-declared, within §10's 15%-of-equity deployment cap** | frozen; not raised without §9.3a authorization |
> | **Maximum canary DURATION** | **20 live canary sessions** (≈ one month) | a hard clock on the data-collection window |
> | **Cumulative LOSS BUDGET** | **1.5% of equity**, canary-attributable realized + unrealized | a hard loss cap on the data-collection window |
> | **STOP CONDITION** | duration cap reached **or** loss budget breached, with **no §9.3a authorizing decision recorded** | → **HARD halt: kill switch default-OFF, revert to 盘后 batch** |
>
> Reaching the duration cap or the loss budget **without** a recorded §9.3a
> authorizing decision → **HARD halt and revert to the 盘后 batch path
> (kill switch default-OFF)** — **never** silent continuation, and
> **never** an automatic extension. Extending the window to keep collecting
> data is itself a decision that requires an explicit recorded
> authorization; the default on envelope-exhaustion is to **stop**, not to
> drift into production.

The `stage2_authorization.json` file IS that "separate, recorded decision"
artifact, machine-validated; the quadruple gate is its enforcement.

## 4. Safety invariants — runtime-asserted, tested

1. **Entry-notional cap, never exceeded.** The day's entries may never push
   past the authorization's `daily_entry_notional_cap`: per-intent pre-check
   PLUS a hard assertion (`assert_entry_cap` → `EntryCapExceededError`)
   before AND after every BUY submit. The cap binds on **GROSS submitted
   entry notional** recomputed from the persisted book (canceled/rejected
   attempts still count — conservative, monotone, restart-safe; a
   consequence: BUY remainders are NOT chased in the canary). **Exits are
   NEVER capped.**
2. **One open child per parent.** Slice 1's `OrderStateBook.submit_child`
   enforces it; every submission is routed through the book (consumed, not
   re-implemented) — pinned by test through this driver.
3. **Reconcile-before-emit on session start.** `begin_session` ALWAYS runs
   slice 1's `reconcile_on_restart` against broker open-orders — fresh book
   included (a fresh state file is not evidence the broker is quiet). A tick
   before `begin_session` raises. A reconcile mismatch halts entries for the
   session; exits continue.
4. **Write-ahead action journal.** Every MUTATING broker call
   (submit/cancel) is journaled to
   `logs/renquant105_pilot/intraday_live_actions.jsonl` BEFORE the call
   (flushed + fsync'd) and its outcome after. The broker can never know
   about an order the journal does not. GET reads are not journaled.
5. **Dead-man switch.** ≥ 3 CONSECUTIVE broker rejects/errors → entries
   halted for the rest of the session (sticky, persisted via the book's
   `entries_halted`); exits continue to the bell (§10
   exits-always-allowed). A success resets the consecutive counter only.

Plus, consumed from the existing slices: the §7 economic invariant
(`cum_filled + open_qty ≤ target_qty`, remainder sizing), the §10
stale-pending watchdog (10 min, cancel+reconcile before the tick acts), the
§11b entry windows (`apply_entry_window_policy`) and close-cancel (DAY-only
no-carry), the §6 class-A/B leak guards, and the parent-intent-id
BYTE-LOCKSTEP guard (pipeline id ≠ execution id ⇒ hard halt — the
calibrator-fingerprint triple-impl lesson, enforced not assumed).

## 5. Tests (tests/test_intraday_live_executor.py — no live broker call anywhere)

- the quadruple gate: **all 16 combinations** — only all-four arms live;
- authorization-file schema rejection cases (15 parametrized + missing /
  malformed / non-object files);
- `mode: "live"` WITHOUT the file still shadows (counted), port factory
  never invoked, no actions journal, no book file — the st104 config flip
  ALONE cannot go live;
- cap enforcement incl. the exit exemption and cross-tick gross accounting;
- write-ahead ordering observed AT the broker-call boundary (journal line
  exists, outcome does not, at the moment the port is called) + error
  outcomes journaled;
- dead-man: 3 consecutive errors halt entries (no broker touch afterwards),
  exits continue; success resets the counter;
- fake-broker round trip: submit → partial fill → snapshot → restore (
  refuses ticks until reconciled) → reconcile → full fill → FILLED, with
  the snapshot parsed by Stage-1's `load_order_state_reservations`
  (slice-1 shape parity) and a book/broker mismatch restore halting entries;
- `AlpacaBrokerPort` request shaping against an injected fake TradingClient
  (client id = child id, DAY tif, limit/market per config, marketable-limit
  offset, limit-entry-without-price fails closed) — MOVED, verbatim, to
  `renquant-execution/tests/test_alpaca_broker_port.py` with the adapter
  (renquant-execution#21); this suite instead pins the seam: the default
  port factory's import is lazy, returns the execution-owned class, and
  fails closed (`Stage2ContractError`) at arming when it is unavailable;
- id lockstep violation halts loudly; one-open-child consumed from slice 1.

Full suite: 1521 passed, 3 skipped.

## 6. The future authorization act — exactly three steps

Enablement is NOT a code change. When (and only when) a §9.3a authorizing
decision exists, the act is:

1. **Flip the pinned config**: strategy-104 PR setting
   `intraday_decisioning.mode: "live"` — which must first rewrite
   strategy-104's own shadow-only test pin (the test cites §9.3a and
   requires the recorded decision alongside) — then bump the strategy-104
   pin in the orchestrator and sync the pinned run checkout.
2. **Write the signed authorization file** `data/rq105/stage2_authorization.json`
   with the operator's identity, the evidence block (≥ 5 clean shadow
   sessions, green replay audits, the reviewed entry-timing report), the
   `daily_entry_notional_cap` (proposed $500), and an expiry ≤ 31 days out.
3. **Set `RENQUANT_INTRADAY_LIVE=1`** in the session-scheduler job
   environment (machine landing — ask-first, per the standing landing
   policy).

Gate 4 (kill-switch file absent) is the standing default, not an act — and
touching `data/rq105/intraday_decisioning.KILL` at ANY time reverts the next
session to shadow (gates re-evaluated every session; the file is also
re-checked every cycle mid-session by both loops).

## 7. HARD BOUNDARY (restated)

This PR makes Stage-2 live mode POSSIBLE, not ENABLED. Nothing merged here
changes any running behavior: strategy-104 still pins `mode: "shadow"` (its
test enforces it), `RENQUANT_INTRADAY_LIVE` is unset, no authorization file
exists, and the unarmed executor is byte-equivalent to the Stage-1 shadow
scheduler. Expansion beyond the frozen canary envelope — or any general
go-live — remains governed by §9.3a: an explicit authorizing decision from
the §9.4 prereg experiment, or the operator's separate recorded acceptance
of the economic risk. Operational cleanliness never authorizes economics.
