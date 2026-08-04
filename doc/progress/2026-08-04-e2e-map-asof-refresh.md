# 2026-08-04 — e2e map AS-OF refresh (15:10 PT): the day the chain got exercised

Per the map's own discipline (refresh the timestamp with any update), this
records the delta between 11:25 PT and 15:10 PT — the densest four hours the
chain has had:

- RFC#210: ARMED → **EXERCISED end-to-end** (manual 11:31 promotion ended 44d
  staleness; the 13:00 scheduled run ran PIT→retrain→gate FAIL→REFUSE-on-fresh
  correctly); reject notification state-aware (RQ#568).
- Stage-2 lineage: WIRED → **LIVE with the first stamp** (124/125 scored, final
  window refused by design).
- P-WF-GATE: learned the RFC#210 serving license (both twins) after the
  measured sell-only session; the 14:42 rerun hard-PASSED with governance
  provenance and placed 3 buys + 1 sell (broker-ACCEPTED).
- Step 5b S1 lane: DORMANT → ACTIVE; two consumer misses found by running and
  fixed same-day (pipeline#263/#264).
- New cross-cutting lesson row: license changes must enumerate consumers
  (three `passed`-consumers re-taught in one day); fingerprint identity is
  schema-scoped, runtime-authoritative.
- Honest-gaps rewritten with one measured NEGATIVE: R4 `wf_gate_provenance`
  is ABSENT from today's successful full-run bundle (9,154 B, no key) — the
  R4 requirement is deployed-but-dark on the daily path; orch#564 AC6 stays
  OPEN and now carries a measurement instead of an expectation.

No behavior changes in this PR — documentation of measured state only.
