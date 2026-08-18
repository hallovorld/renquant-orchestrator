# Silent-refusal sentinel — a refusal must never read as acted (4 measured defects)

STATUS:    fix for review. Monitor logic + tests only; the sentinel is observe-only
           (READ-ONLY over job logs, no state, no write, alert-or-exit-code).

WHAT:      `ops/renquant104/rq104_silent_refusal_sentinel.py` + its emitter contract +
           tests, against defects measured 2026-08-18 over the REAL dated logs in
           `/Users/renhao/git/github/RenQuant/logs/{weekly_wf_promote,
           conditional_retrain_104,retrain_panel}/`.

           **D1 (the false clear — the blindness this module exists to prevent).**
           `conditional-retrain104` and `retrain-panel104` print their success lines
           (`Gated WF promote chain complete` / `delegated weekly_wf_promote PASS`)
           from `if bash scripts/weekly_wf_promote.sh; then` — the CHILD'S EXIT CODE.
           Since the 2026-08-04 operator directive, `weekly_wf_promote.sh`'s
           CALM_FRESH branch (`:513-520`) **exits 0 on a REFUSAL** (gate rejected, the
           served model is fresh under RFC#210, "governance nominal, calm notify,
           exit 0"). So a pure refusal reads as ACTION and a single such run clears
           the whole streak. Fixed by corroboration: a delegator's claim is `acted`
           only when the CHILD's own dated log for that date carries the child's own
           action evidence — the SAME pattern constant the child lane is watched on
           (`WEEKLY_WF_PROMOTE_ACTION_RE`, hoisted so the three uses cannot drift).
           Two new non-acting outcomes keep the failure modes distinguishable:
           `uncorroborated` (child log exists, shows no promotion) and `unwitnessed`
           (child wrote NO dated log — the `exit 2` at `:211` fires BEFORE the
           `exec >> "$LOG"` redirect at `:235`, so no log is ever opened).

           **D2 (14/14 false CRASHED).** `classify_run` tested `crash_re` before the
           verdicts, and the WF gate DELIBERATELY logs caught tracebacks as sanity
           evidence before deciding. A crash claim now requires the ABSENCE of a
           decision verdict (`_reached_a_decision`).

           **D3 (the one real crash was invisible).**
           `logs/weekly_wf_promote/2026-06-06.log:7` — SIGSEGV in the pre-flight smoke
           test — produces neither a traceback nor `^\w*Error:`. `crash_re` now
           carries signal-death/abort signatures (`HARD_KILL_RE`, signal-number or
           `(core dumped)` REQUIRED so log prose cannot trip it). The wrapper's
           follow-on `Smoke test FAILED — aborting weekly promote (no train).` is an
           ABORT, not a decision (`abort_re`), so it does not suppress the crash.

           **D4 (8 real failures dropped).** `failure_re` omitted `Training FAILED`,
           so 8 Step-3 failures (07-31, 07-23, 07-17, 07-16, 07-11, 07-10, 07-09,
           07-04) matched nothing, classified `undecided` and were dropped — a defect
           that SHRINKS the streak the module counts. Added, along with the other
           unmatched terminal verdicts read off the current wrapper and the corpus.

WHY/DIR:   GOAL-5 AC5. This module's founding incident was a job that exited 0 while
           declining, for months, with every liveness checker green. D1 is that exact
           incident re-created one layer up: the wrapper that watches the watcher was
           reading an exit code that stopped meaning "promoted" on 2026-08-04. D2/D3
           are attribution defects (the alarm still fired, saying the wrong thing);
           D4 is a counting defect (runs silently left out of the tally).

EVIDENCE:
  artifact:      `ops/renquant104/rq104_silent_refusal_sentinel.py`,
                 `ops/renquant104/emitter_contract.json`,
                 `tests/test_rq104_silent_refusal_sentinel.py`,
                 `tests/fixtures/silent_refusal/*.log`. No production path written.
  prod or exp:   **neither** — monitor logic + tests. The sentinel is observe-only:
                 it reads dated job logs and emits an alert / exit code, keeps no
                 state, and touches no artifact, config or live surface.
  existing data: [VERIFIED — classifier re-run over the three REAL log dirs,
                 as_of=2026-08-18, default 90-day window, read-only]

                 `weekly-wf-promote` (n=47 dated logs)
                   before: refused 23  failed  1  crashed 14  undecided 9  streak 38
                   after:  refused 32  failed 13  crashed  1  undecided 1  streak 46

                 `conditional-retrain104` (n=65)  unchanged: failed 25, undecided 40,
                 streak 25 — no delegator has EVER claimed success in the corpus,
                 which is exactly why D1 went unnoticed (see the counterfactual).
                 `retrain-panel104` (n=13) unchanged: failed 11, crashed 1,
                 undecided 1, streak 12.

                 The 14→1 crash move is D2: 13 of the 14 had printed `WF gate
                 REJECTED staged model — production unchanged.` (→ refused) and one
                 (2026-05-24) `WF gate FAILED — production unchanged.` (→ failed).
                 The surviving crash is 2026-06-06, the SIGSEGV, which D3 promoted
                 from `failed`. The undecided 9→1 move is D4 (8 `Training FAILED`
                 runs recovered); the survivor is 2026-07-01, a hand-written operator
                 note in the log directory that genuinely reached no verdict.

                 [VERIFIED — D1 counterfactual, real bytes: the real
                 `conditional_retrain_104` corpus copied to a temp dir with ONE
                 delegator success claim injected, corroborated against the REAL
                 `logs/weekly_wf_promote/` dir]
                   claim on 2026-08-18 (weekly wrote no dated log that day):
                     before `acted`        → streak 0  → NO ALARM (25-run streak
                                                          cleared, nothing promoted)
                     after  `unwitnessed`  → streak 26 → ALARM
                   claim on 2026-08-04 (weekly's REAL CALM_FRESH exit-0 refusal):
                     before `acted`          → streak 3   (25 → 3)
                     after  `uncorroborated` → streak 26  → ALARM
  best-known?:   yes. Corroborating against the child's own action line is the
                 strictly stronger evidence available without adding state — it is
                 the same evidence the child lane is already watched on, so the two
                 cannot disagree. Keying the crash verdict on the ABSENCE of a
                 decision (rather than deleting the traceback markers) keeps genuine
                 pre-decision deaths visible, which is what D3 needed. Accepted and
                 recorded: (a) if the child ran twice on one date its dated log is
                 append-mode and an earlier genuine promotion corroborates a later
                 delegation — not a false clear, the served artifact really did
                 change that day, which is the estimand; (b) classification is
                 per-DATE while the log is append-mode per RUN, so a day holding
                 several runs classifies on the first matching class — 2026-08-04
                 holds four runs and moves `refused` → `failed` because two of them
                 ended on `Training FAILED` (a D4 recovery: those two were invisible
                 before), and 2026-06-07 holds an abort plus two later decisions and
                 classifies on the decision. Both classes are non-acting and are
                 counted identically, so the streak is unaffected either way.
  scope:         classification only. No threshold moved: `STREAK_N` (3) and
                 `MAX_LOG_AGE_DAYS` (90) are untouched, the registry gains no lane,
                 and the streak rule is unchanged except that the two new non-acting
                 outcomes count as non-acting. The reversal of the old "a crash
                 marker outranks a refusal" rule is deliberate and documented at the
                 test that used to assert it. `WF gate FAILED — production
                 unchanged.` is matched from the corpus only (2026-05-24, still
                 inside the window) and is deliberately NOT contracted — the emitter
                 no longer exists, so the re-capture tool would rightly refuse it.

TESTS:     `make test` — 6486 passed, 3 failed, 5 skipped (3m31s).
           Baseline on `origin/main` at 0a48d13f: 6461 passed, 6 failed, 5 skipped.
           The 3 remaining failures are the known pre-existing live-state ones
           (`test_goal7_arm_a_producer`, `test_goal7_arm_b_accrual_probe`,
           `test_position_cap_conformance`). The other 3 baseline failures were
           emitter-contract drift (`test_local_wrapper_still_emits_the_contracted_
           lines`, and both `test_recapture_emitter_contract` live-sync tests): the
           contract's line pins predated RQ#799's blend-reference block. Re-captured
           here with `ops/renquant104/recapture_emitter_contract.py` (5 line pins +
           the wrapper sha256) as part of adding the new rows — those 3 now pass.

           +25 tests on the sentinel (48 → 73 across the sentinel + re-capture
           files). Every new test is driven by REAL log bytes copied into
           `tests/fixtures/silent_refusal/`: traceback-then-verdict (2026-06-22 →
           REFUSED), SIGSEGV (2026-06-06, verbatim → CRASHED), `Training FAILED`
           (2026-07-31, verbatim → FAILED), the CALM_FRESH exit-0 refusal
           (2026-08-04 → delegators NOT-acted), the exit-2 shape (retrain_panel
           2026-08-16, verbatim). The three success fixtures are named
           `*_synth_from_emitter.log` and pinned to the contracted emitter templates,
           because no delegator success has ever occurred in any log window.

NEXT:      codex review → merge → sync the orchestrator run checkout (the sentinel
           runs from `renquant-orchestrator-run`, and `weekly_wf_promote.sh:485`
           already greps that checkout's `emitter_contract.json` for the
           FALLBACK-PROMOTED arming line, so the sync is what makes both the fix and
           the RFC#210 arming contract live). Not in scope here and worth a separate
           look: `weekly_wf_promote` has written no dated log since 2026-08-04 —
           every run since exits 2 at the orch#799 pinned-blend reference block,
           which is why `retrain-panel104` has 11 straight FAILs.
