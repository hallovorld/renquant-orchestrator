# Unify §7 intent identity + terminal classification onto renquant-execution (campaign B3)

STATUS: DONE — code + tests, PR opened from `fix/intent-id-unify`.
FIXES:  audit #296 findings OR-1 / OR-2 (compliance campaign B3, PR #297 plan).

WHAT: `src/renquant_orchestrator/execution_reconciler.py` re-implemented the §7
parent-intent identity DIVERGENT-BY-CONSTRUCTION from renquant-execution
(`pi_`+sha256[:16], `|` separator, lower-cased side vs the canonical
`pi-`+sha256[:20], `\x1f` separator, upper-cased side) and carried a parallel
Alpaca status map already drifted in-repo (`done_for_day` -> ACCEPTED/open vs
execution's CANCELED/terminal). Two systems computing "the same" identity that
never matches — the calibrator-fingerprint triple-impl failure mode reborn.

FIX:
- Deleted the local `make_parent_intent_id` / `make_child_order_id`; the module now
  imports (and re-exports) `compute_parent_intent_id` / `child_order_id` from
  `renquant_execution.order_state_machine` — the same top-level-import seam
  `intraday_live_executor.py` already uses (renquant-execution is a declared dep).
- Terminal broker-status classification now routes through execution's canonical
  `classify_terminal_status` / `TERMINAL_STATUS_MAP`; only the NON-terminal
  (open/in-flight) Alpaca vocabulary + the REPLACED lineage state stay local
  (execution's Stage-1 terminal map deliberately does not own them). An import-time
  guard raises if execution's terminal vocabulary ever grows to overlap the local
  open map — cross-repo drift fails loudly instead of silently re-diverging.
- `done_for_day` resolved to execution's semantics (CANCELED): per Alpaca, the order
  is done executing for the day and receives no further fills; under the Stage-1
  TIF=DAY-only regime that is the broker's close-out, not a live order consuming
  exposure/reserved cash. Side effect of the canonical map: `failed` -> REJECTED
  (previously UNKNOWN/fail-closed).

MIGRATION DECISION: CLEAN CUT, no read shim. Evidence: no `*.db` / `*.sqlite`
anywhere in the orchestrator or orchestrator-run trees; `SqliteIntentStore` is
instantiated ONLY in tests (pytest tmp dirs); no CLI/daily/scheduler wiring of
`execution_reconciler`; the umbrella never imports it; no run bundle contains a
`parent_intent` id. Old-format `pi_` ids were never persisted outside throwaway
test databases, so there is no historical row to translate.

PROTECTION CONTRACT: the reconciler is observe-only and UNWIRED today (audit OR-2:
"observe-only and unwired", hence P1 not P0) — its output (`ReconciliationReport`,
optional flag-gated ntfy alert) feeds no live decision path. Nothing live-behavioral
changes; the invariance bar is the library's own tests.

EVIDENCE: `tests/test_execution_reconciler.py` 60 passed (was 53) — new coverage:
identity-is-the-same-function lockstep, golden id vectors pinned against execution's
recipe (e.g. `pi-32c5702b604fc035b2eb`), OrderIntent.build == executor id,
terminal-map lockstep, `done_for_day` terminal + no-orphan-divergence, `failed`.
A/B full suite: pristine origin/main 1861 passed / 3 skipped; this branch
1868 passed / 3 skipped (+7 new tests, zero regressions). Doctor import check green.
Sibling `renquant-execution` checkout verified byte-identical to its origin/main
for `order_state_machine.py` before running.
