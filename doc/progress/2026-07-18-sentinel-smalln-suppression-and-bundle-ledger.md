# Progress: smalln_guard_suppressed sentinel rule + run-bundle ledger write

Date: 2026-07-18

## What

The orchestrator side of the approved eligibility-ledger amendment
(renquant-pipeline #207, normative spec
`doc/design/2026-07-18-smalln-guard-eligibility-ledger.md`; pipeline
implementation PR renquant-pipeline#208). Two deliverables:

1. **Sentinel check (f)** — `ops/renquant104/rq104_degradation_sentinel.py`
   gains the amendment's NAMED deliverable: a `smalln_guard_suppressed`
   LOUD pattern. The deployed #545 rule (check e) fires only on
   all-veto ∧ small-n and would MISS a suppressed-but-partially-admitting
   day; check (f) alarms on the suppression itself. Two independent
   surfaces, either fires:
   - today's daily log carries the `smalln_guard_suppressed(reason=...)`
     ERROR tag that pipeline's `VetoWeakBuysTask` logs on a NOT-CLEAN
     small-n scan;
   - the newest live run's persisted `smalln_eligibility` gate_verdicts
     row (pipeline #208 §3 persistence) records
     `branch_action = suppressed:<first failing class>`.
   Distinct alarm key ("small-n guard SUPPRESSED: ..."), ack-proof (the
   ack ledger keys launchd job labels only — same construction as #545),
   absent-tolerant (no gate_verdicts table / no rows = the explicit
   absent state for pre-#207 pipelines, never an alarm or a crash), and
   the log surface runs even when the runs DB is unreadable so a
   suppression cannot hide behind a DB problem. Latest-row-wins so an old
   suppression stops paging once newer runs record a clean
   branch_action.
2. **Run-bundle write** — the run-bundle path IS orchestrator-side
   (finding from the pipeline PR): the daily bridge bundle is built by
   `build_bridge_live_bundle(ctx)` from the committed runner context.
   It now carries `smalln_ledger`: the schema-versioned §3 block read
   from `ctx._smalln_eligibility` (attached by pipeline #208 every
   session), JSON-sanitized; ABSENT-TOLERANT per §3 — old pipelines
   yield the literal `"absent"`, never a KeyError and never a
   validation failure (`validate_live_run_bundle` tolerates the extra
   key, same as the existing `metadata` key). The decision-ledger write
   needs no orchestrator change: pipeline #208 forwards the block
   through the existing `format_gate_verdicts` / gate-registry
   (`record_gate_verdicts`) adapter paths.

## Tests

`tests/test_rq104_degradation_sentinel.py` +9 (fixture gains an optional
`gate_verdicts` table, created only when given, so legacy-DB degradation
stays proven): DB suppression row alarms; log tag alarms without a DB
row; acted / not_small_n / deconfigured quiet; latest-row-wins over an
old suppression; absent table quiet; ack ledger cannot silence it; log
surface fires with an unreadable DB (alongside the DB-unreadable alarm);
unit ordering of `latest_smalln_ledger`. `tests/test_bridge_live_bundle.py`
+4: block forwarded verbatim + contract-valid; absent for old pipelines;
malformed attribute degrades to absent; JSON write round-trip. Suite:
4036 passed, 3 skipped.

## Not in this PR

Pipeline-side partition/CLEAN/suppression (renquant-pipeline#208);
strategy-104 shadow keys (strat-104#61); pins/deployment — the sentinel
change reaches the machine through the normal orchestrator checkout
sync, not by hand-editing the live tree.

Shadow-only evidence collection continues under strat-104#61; production
activation of the guard remains gated on the amendment §4 frozen shadow
verdict plus explicit operator authorization on the record.
