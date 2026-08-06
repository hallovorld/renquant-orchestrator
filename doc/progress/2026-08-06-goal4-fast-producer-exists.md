# The fast-momentum producer exists and is deployed — it is four days old and fires weekly   (PR)

STATUS:   delivered — measurement only, and it **corrects orch#869**. No code ships,
          no production surface touched.

WHAT:     Establishes that `artifacts/momentum_fast/` has no data because its
          producer was added on 2026-08-04 and its first scheduled firing is
          2026-08-08 — not because no producer exists.

WHY/DIR:  GOAL-4. orch#869 named orch#845 the highest-leverage item on the premise
          that the fast-momentum factor level had *no producer*. That premise is
          wrong, which changes what #845 is worth doing about.

EVIDENCE:
artifact:      `ops/renquant104/momentum_train_weekly.sh` (deployed copy at
               `renquant-orchestrator-run`), `logs/rq104/momentum_train_2026-08-02.log`,
               `~/Library/LaunchAgents/com.renquant.momentum-train-weekly.plist`
prod or exp:   prod
existing data: orch#845 recorded the two fast lanes as having no input; orch#856
               confirmed `RAN_AND_SCORED_NOTHING` from the serving side; orch#869
               framed it as an empty factor level. None of the three checked
               whether a producer had been added.
best-known?:   yes — this is the first read of the producer's own deployment date
               against the job's schedule.
scope:         this is the weekly momentum job on this machine, prod, and it is a
               claim about **deployment timing only**. It asserts no IC, Sharpe,
               skill or return figure, and does not compare against any prior best.

| fact | value |
|---|---|
| fast lane added to the wrapper | **2026-08-04 01:47:46 −0700** `[VERIFIED — git log -S "params-version v1_fast", commit f43c1f6d (PR #775)]` |
| deployed copy matches the repo copy | **identical** `[VERIFIED — diff -q renquant-orchestrator-run/... vs ops/...]` |
| pinned model CLI supports `--params-version` | **yes** `[VERIFIED — momentum_train_run.py --help]` |
| only weekly run on record | **2026-08-02** `[VERIFIED — ls logs/rq104/momentum_train_*.log, n=1]` |
| that run's log has a fast-lane line | **no** `[VERIFIED — grep -c "fast train CLI exit" = 0]` |
| job schedule | **Saturday 05:00** `[VERIFIED — plist StartCalendarInterval = [{Weekday: 6, Hour: 5, Minute: 0}]]` |
| next firing | **2026-08-08** `[DERIVED — today 2026-08-05 Wednesday + next Weekday 6]` |

The 08-02 log ends `=== momentum-train-weekly end rc=0 ===`, while the current
wrapper's final line is `end rc=$RC fast_rc=$RC_FAST`. **That run used a wrapper
that predated the fast lane by two days.**

## What this corrects

| orch#869 said | measured |
|---|---|
| "both cells at the `fast` level are empty … because nothing produces `artifacts/momentum_fast/`" | a producer **exists, is deployed, and is byte-identical to the repo copy** — it has simply not fired yet |
| "orch#845 is the highest-leverage GOAL-4 item" | #845 may need **no code at all**; the next scheduled Saturday is the test |

I reached the wrong conclusion by checking the *artifact directory* and the *lane
configs* and never checking the *producer's own deployment date*. Absence of
output was read as absence of a producer.

NEXT:     Read `logs/rq104/momentum_train_2026-08-08.log` after Saturday 05:00 and
          record `fast_rc`. Three outcomes, all informative: `0` populates the
          factor level and orch#845 closes; `2` means the pinned CLI predates the
          flag after all (contradicted by the `--help` reading above, so it would
          mean the *deployed* pin differs from the one I read); anything else is a
          new finding.

## What this does NOT establish

- **Not that the fast lane will succeed on Saturday.** It has never run. The
  wrapper's own comment predicts an exit-2 path; the `--help` reading argues
  against it, and only the run settles it.
- **Not that the fast momentum model has any skill.** Populating a factor level
  is not evidence about the factor.
- **Not that orch#845 should be closed now.** It should be closed by a run, not
  by this document.
