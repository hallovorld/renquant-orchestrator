# Stage-2 canary enforcement: allowlist + loss budget + session ceiling (campaign A4)

Date: 2026-07-03
Scope: renquant-orchestrator only — `src/renquant_orchestrator/intraday_live_executor.py` + its tests.
Origin: compliance fix campaign (PR #297), Group A item A4 = audit #296 finding **OR-3** (P1, top-5 by risk).
Status: PRE-ARMING BLOCKER — must be merged before any Stage-2 authorization is signed.

## The finding (OR-3)

The Stage-2 live executor enforced the notional cap and the 31-day
authorization window, but (a) the canary allowlist was parsed and stamped
yet NEVER enforced — `process_tick` submitted any BUY subject only to the
cap, and `Stage2Authorization` had no allowlist field; (b) the RFC #208
§9.3a cumulative loss budget (proposal 1.5% of equity) and the 20-live-
session duration cap were unimplemented (calendar expiry was the only
clock). Dark today; the day it armed, "canary" would have meant
watchlist-wide live trading under only a $500/day cap.

## Enforcement semantics chosen

1. **Allowlist — required, no unrestricted mode.** `Stage2Authorization`
   gains a REQUIRED `canary_allowlist`. Absent, `null`, and `[]` ALL fail
   schema validation: RFC #208 §10 says "canary allowlist required" and
   §9.3a pre-declares 1–2 names, so absence does NOT mean "no canary
   restriction" and no `null` acknowledgment bypass exists — there is no
   unrestricted-canary mode to acknowledge. Entries submit ONLY for
   allowlisted symbols: non-allowlisted BUY intents are skipped with the
   counted, journaled reason `stage2_canary_allowlist`, and
   `assert_canary_allowlist` hard-asserts around every BUY submit (defense
   in depth). Exits are NEVER allowlist-blocked (§10 exits-always-allowed).
   Size is validated ≥ 1 and warn-logged above the §9.3a proposed 2 (the
   RFC marks size an open operational question, §15.7 — the signed file is
   itself the recorded decision). If the pinned config ALSO declares an
   allowlist, the authorization's must be a subset, else gate 2 fails
   (ambiguity fails closed).
2. **Cumulative loss budget.** REQUIRED `max_cumulative_loss_usd`
   (positive finite USD). `CanaryEnvelopeTracker` (state:
   `data/rq105/stage2_canary_state.json`, keyed to the authorization's
   content hash) tracks realized + mark-to-market P&L of Stage-2-originated
   positions from the executor's own fills (average-cost basis; broker
   `fill_price`/`filled_avg_price` preferred, child limit price fallback;
   marks from intent prices, `marks`/`quotes` tick payloads, and fills;
   exits of positions the canary did not originate contribute zero). On
   breach: entries HALT (book halt reason `stage2_cumulative_loss_budget`,
   STICKY across sessions — §9.3a HARD halt), exits continue, one CRITICAL
   ntfy fires (priority 5, `RENQUANT_NO_NOTIFY` honored), and the trip is
   journal-stamped.
3. **Session ceiling.** Live sessions are counted per authorization
   (idempotent per date, stamped into the action journal at session begin
   and surfaced in every arming record / begin report). Optional
   `max_live_sessions`, default AND hard cap 20 per §9.3a's "maximum
   canary DURATION" (a larger declared value fails validation, like the
   31-day window rule). At the ceiling, arming fails closed to shadow —
   re-authorization required; `begin_session` also hard-refuses a new
   session beyond the ceiling (defense in depth).
4. **Arming gate: 4 → 5.** `resolve_stage2_arming` gains the required
   `canary_state_path` and a fifth gate `canary_envelope_available` (budget
   not tripped AND sessions below ceiling). Corrupt/unreadable envelope
   state fails the gate (and executor construction) LOUDLY — a loss ledger
   is never silently reset. A NEW authorization file (new content hash =
   new recorded §9.3a decision) starts a fresh envelope; the exhausted one
   is archived inside the state file (audit trail preserved).

## Tests

The 16-combination quadruple-gate arming matrix is extended with three
dimensions — allowlist consistency, budget tripped, session ceiling — to a
128-combination matrix, plus targeted tests: schema rejections for the new
fields (absent/null/empty/malformed allowlist; missing/zero/negative loss
budget; out-of-range session ceiling), allowlist enforcement (blocked BUY
never reaches the broker; exits flow), realized and MTM trip paths (halt
entries + exits continue + single CRITICAL notification + journal stamp),
sticky-trip persistence across sessions and arming refusal,
counter idempotency per date, ceiling arming refusal + begin_session
backstop, fresh-envelope-on-new-authorization with archival, and
corrupt-state fail-closed. Suite: 187 pass in the file; full repo suite
1861 passed / 3 skipped.

## Protection contract

All of this is DARK until an authorization file exists: gate 2 (the
authorization file) fails today, so every session still resolves to
shadow, exactly as before. No live behavior changes with this PR; it only
makes the future arming act enforce the envelope it stamps.
