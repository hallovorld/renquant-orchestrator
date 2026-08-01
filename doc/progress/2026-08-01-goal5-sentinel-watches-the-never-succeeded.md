# AC5 sentinel: watch the jobs that have never succeeded (GOAL-5)

## What landed

Three promotion-adjacent jobs joined the silent-refusal sentinel's `WATCHED` registry —
`weekly-wf-promote`, `conditional-retrain104`, `retrain-panel104` — and `WatchedJob`
gained an optional refusal vocabulary (`refusal_re: str | None`): an anomaly-gated chain
either completes or fails; a line meaning "looked and declined" does not exist for it,
and a placeholder regex would be a guessed pattern, which this module forbids.

## The doctrine amendment, stated where it applies

The module requires patterns read off reality. For a job that has NEVER succeeded inside
its log window, no action line exists in any log — and refusing to watch it for that
reason would exclude exactly the jobs a silent-refusal sentinel exists for. Amendment:
the action pattern is read off the EMITTER SOURCE (the literal `echo` in the wrapper),
and a pinning test asserts the pattern still appears in that script — skipping loudly on
machines without the umbrella — so a reworded emitter breaks the test instead of
silently blinding the watch.

## A registry entry retired because its measurement went false

`UNWATCHABLE_LANES["weekly-wf-promote"]` recorded "dated log surface last wrote
2026-05-24". Re-measured 2026-08-01: **54 dated logs exist through 2026-08-01**, REJECTED
decision lines on 6 of the last 8. A registry of measured reasons must retire entries
whose measurements no longer hold, or it becomes the thing it guards against.

## What the extended sentinel sees, first dry-run `[本次实测 2026-08-01]`

| lane | verdict |
|---|---|
| weekly-wf-promote | **36 non-acting runs** (refused streak incl. 2026-08-01; 15 crashed) |
| conditional-retrain104 | **22 non-acting, 22 crashed** — every VIX-trigger firing in 59 dated logs ended in `Gated WF promote chain FAILED`; 0 completions ever |
| retrain-panel104 | **10 non-acting, 10 failed** — 7 weekly delegations, 7 `delegated weekly_wf_promote FAIL`, 0 PASS |
| weekly-retrain-patchtst | 5 non-acting (2026-08-01 run refused again) |

Nothing has promoted through any watched lane inside the visible log windows. The ack
ledger's `clears_when` for conditional-retrain104 ("next VIX-anomaly trigger runs the
gated chain clean") has been TESTED and failed 22 times.

## The emitter contract is now IN-REPO and CI-enforced `[codex on orch#738]`

The review was right that a skip-in-CI absolute-path test left the three production
classifications resting on a developer-local contract. `ops/renquant104/
emitter_contract.json` now versions each source-derived line verbatim (script:line,
wrapper sha256 at capture, observed-in-logs citation where one exists). CI tests —
running everywhere — bind every WATCHED pattern to a rendered form of its contracted
template and refuse lanes without a contract row. The local source pin remains as the
drift detector: on the dev box it catches a cross-repo wording change the day it lands.
Residual honestly stated: a wording change landing while nobody runs the local suite is
detected at the next local run, not instantly — the CI half guarantees pattern↔contract
consistency, the local half guarantees contract↔reality freshness.

## Judgement calls, disclosed

* The healthy idle line "No anomaly triggers fired" classifies as SKIP, not refusal — an
  anomaly-gated job's quiet days are not a refusal streak, and counting them would
  manufacture alarm fatigue.
* Shell-echoed failures (`chain FAILED`, `delegated … FAIL`) carry no Traceback, so each
  new job declares a job-specific `failure_re` that includes its real failure lines.

Tests: 7 added (real-line fixtures per job, None-vocabulary classification through the
real classifier, registry membership, emitter-source pins). Suite: full run below.
