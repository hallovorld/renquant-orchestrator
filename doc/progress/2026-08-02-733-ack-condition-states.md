# GOAL-1/#733: an ack's expiry now carries a verdict — MET vs UNMET vs UNEVALUABLE

STATUS: complete (the #733 ask; ledger populated in the same PR).
WHAT: new structured `clears_check` per ack row — a CLOSED kind set
(`launchctl_exit_zero` / `path_exists` / `manual`+why) evaluated read-only by
`ack_ledger_audit.py` with FAIL-CLOSED dispatch (an unknown or malformed kind
is a FINDING, never a silent pass). The verdict combines with expiry into
distinct states: `MET_UNEXPIRED` and `EXPIRED_CONDITION_MET` are info-grade
remove-the-row states; `EXPIRED_CONDITION_UNMET` is the PROBLEM finding (#733's
core point: the fix never shipped); launchctl-unavailable is `UNEVALUABLE`, a
distinct state that is never met or unmet. The narrative-only `clears_when`
lint is upgraded into the mandatory-clause finding; the bare-ref prose lint
stays. All 10 live rows populated: 6 `launchctl_exit_zero` on their own jobs,
4 `kind=manual` with a why (two open-ended WF-gate passes, the #75 redesign,
the sentinel's self-referential exit 1).
WHY/DIR: #733 measured the gap on the live ledger: an ack whose 3-clause
clearing condition was 1-of-3 satisfied, with nothing able to say so — "the
fix landed early" surfaced as nothing, and "expired with the fix never
shipped" surfaced as a plain "expired". One machine-evaluable clause is now
mandatory per row (or an honest manual declaration), so the two outcomes are
different words.
EVIDENCE:
  artifact:      ops/renquant104/ack_ledger_audit.py (evaluate_clears_check,
                 combine_state, the condition x expiry findings),
                 ops/renquant104/sentinel_acks.json (10/10 rows carry
                 clears_check `[VERIFIED — json scan on this branch]`),
                 tests/test_ack_ledger_audit.py (+15 tests: per-kind units,
                 fail-closed unknown-kind, the state matrix, live pins)
  prod or exp:   prod — the scheduled ack-ledger audit (ops_audit member;
                 additions are read-only, `test_no_member_writes` green)
  existing data: live audit at --today 2026-08-02 on the run machine
                 `[VERIFIED — audit run on this branch, 2026-08-02]`:
                 rq104-liveness EXPIRED_CONDITION_MET (launchctl last exit 0 —
                 aged out after the fix; remove at next review),
                 conditional-retrain104 EXPIRED_CONDITION_UNMET (last exit 1 —
                 the fix never shipped; the new PROBLEM finding fires),
                 rq105-batch-scores-export MET_UNEXPIRED (last exit 0 — the
                 issue's own 1-of-3 row, its exit-0 observation now
                 interpreted instead of just recorded),
                 rq105-liveness / rq105-shadow-serving / shadow-ab-daily
                 UNMET_UNEXPIRED (exits 1/1/3 — active suppression, correct),
                 monthly-meta-label-retrain / retrain-panel104 /
                 rq104-degradation-sentinel / weekly-wf-promote MANUAL_*
                 (not machine-evaluable by design, each with its why).
                 Raw statuses `[VERIFIED — launchctl list, 2026-08-02]`:
                 conditional-retrain104=1, rq104-liveness=0,
                 rq105-batch-scores-export=0, rq105-liveness=1,
                 rq105-shadow-serving=1, shadow-ab-daily=3.
                 CI shape `[VERIFIED — audit run with launchctl_text=None]`:
                 all six launchctl rows read UNEVALUABLE and zero
                 condition-UNMET findings fire — could-not-check never
                 impersonates a verdict.
  best-known?:   yes — supersedes the narrative-only clears_when lint (its
                 6-row finding count moves to 0 by declaration, pinned in the
                 updated test); the 9-expired disposition itself stays #733's
                 open review item, unchanged here by design
  scope:         ops/renquant104 audit + ledger + tests; targeted suites
                 168 passed (test_ack_ledger_audit, test_ack_expiry,
                 test_rq104_degradation_sentinel, test_sentinel_ack_exit_codes,
                 test_ack_names_the_exit_code, test_sentinel_liveness_receipt)
                 `[VERIFIED — pytest, 2026-08-02]`; full suite 5412 passed,
                 8 skipped `[VERIFIED — make test, 2026-08-02]`
NEXT: at the next ledger review, remove the two condition-met rows
(rq104-liveness, rq105-batch-scores-export) — the audit now names them —
and disposition the four manual expired rows. Adding clears_check to every
row is a schema migration like orch#641: all ten stamp lags read stale, the
honest state (re-stamping would assert reviews that never happened); the
updated pin tests document this. AC6 gate-design rule: N/A — ops telemetry,
no capital-admission gate.
