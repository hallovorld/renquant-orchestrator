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
FIX ROUND (codex CHANGES_REQUESTED on PR #752, 2026-08-02): correct, and
fixed with a distinct observation state. A single machine check under a
multi-clause `clears_when` (the live 1-of-3 batch-export row) returned
condition=met, so the audit reported MET_*/EXPIRED_CONDITION_MET while the
FULL condition was unmet/unevaluated — a misleading verdict under a more
authoritative name. `clears_check` now carries `scope: "clause" | "full"`
(default "clause", failing toward the WEAKER claim): a met clause-scoped
check yields CLAUSE_MET / EXPIRED_CLAUSE_MET, info-grade states that say the
full condition was NOT evaluated; CONDITION_MET / EXPIRED_CONDITION_MET are
reserved for scope=full predicates. UNMET is unchanged under either scope —
one failed clause already falsifies the conjunction — so
EXPIRED_CONDITION_UNMET keeps its problem grade (conditional-retrain104
still fires it). Unknown scope fails closed like an unknown kind. Ledger:
scope=full on conditional-retrain104 + rq104-liveness (the exit IS the whole
stated condition); scope=clause on rq105-batch-scores-export (1-of-3),
shadow-ab-daily (pin-sync AND PRECHECK), rq105-liveness + rq105-shadow-
serving (clears_when names upstream deploys beyond the exit). Live re-measure
`[VERIFIED — audit run, 2026-08-02]`: rq105-batch-scores-export moved
MET_UNEXPIRED -> CLAUSE_MET; all other rows unchanged. Regression added:
a synthetic mirror of the 1-of-3 row asserts CLAUSE_MET in both expiry
columns and asserts CONDITION_MET is NEVER reported; the live pin test adds
the host-independent invariant that clause-scoped rows cannot reach
CONDITION_MET. Targeted suites 171 passed `[VERIFIED — pytest, 2026-08-02]`;
full suite 5415 passed, 8 skipped `[VERIFIED — make test, 2026-08-02]`.

NEXT: at the next ledger review, remove the condition-met row
(rq104-liveness) — the audit now names it — judge the CLAUSE_MET
batch-export row against its remaining two clauses (#733's pinned/clean-
session gap), and disposition the four manual expired rows. Adding
clears_check to every row is a schema migration like orch#641: all ten stamp
lags read stale, the honest state (re-stamping would assert reviews that
never happened); the updated pin tests document this. AC6 gate-design rule:
N/A — ops telemetry, no capital-admission gate.
