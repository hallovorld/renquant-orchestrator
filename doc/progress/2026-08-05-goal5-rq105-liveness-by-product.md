# 2026-08-05 — GOAL-5: orch#621's "four dead jobs" is refuted; it measured the wrong object

## The claim, and what it rested on

orch#621 (P0, open) reports four rq105 launchd jobs silent for ~28 days —
**"roughly 17–19 missed weekday firings each"** — plus `shadow-serving` in a
failed exit state. Its evidence was careful about provenance: *"`StandardOutPath`
read from each plist (not guessed from a directory name)"*, giving 0-byte stdout
for `postclose`, `quote-logger`, `session-scheduler` and `shadow-serving`.

The reading of the plist was right. **The object was wrong.**

## Measured 2026-08-05 `[VERIFIED — this session]`

These wrappers redirect their own output to a DATED log —
`>> "$LOG_DIR/shadow_serving_$TS.log"`, visible at
`ops/renquant105/run_shadow_serving.sh:21`. So `StandardOutPath` stays 0 bytes
**forever, whether or not the job runs.**

Four of the six wrote a **non-empty** dated log for the 2026-08-04 session, with
fresh products:

| job | dated log (2026-08-04) | product | product freshness |
|---|---|---|---|
| quote-logger | 13:00 | `intraday_ticks.jsonl` | **Aug 4 12:59, 709 MB** |
| postclose | 13:15 | `entry_timing_shadow.jsonl` | **Aug 4 13:15, 12.4 MB** |
| batch-scores-export | 06:15 | `batch_scores_2026-08-04.json` | Aug 4 06:15 |
| shadow-serving | 13:45 | — | `SKIP not-wired … (Stage-3, #221)` |
| postclose (pairing) | 13:15 | `paired_is.jsonl` | Aug 3 13:15 — **one session stale** |
| session-scheduler | 06:25 | — | **log is 0 BYTES — no evidence either way** |

**`shadow-serving` is not crashing — it skips by design** (`run_shadow_serving.sh`
documents `EXIT_NOT_WIRED=4`), because the Stage-3 producer it consumes does not
exist yet.

### Two limits of this evidence, found in review and now encoded

`[codex on orch#815]`

1. **A 0-byte dated log is not evidence of a run.** `>> file` creates it before
   the program writes anything, and `session_scheduler_2026-08-04.log` is exactly
   that — 0 bytes, birth == mtime. The probe now reports `LOG_EMPTY` as
   **actionable**, so session-scheduler is **unestablished**, not refuted. My
   first version called it RAN, which was the same wrong-object error one level
   in.
2. **A dated log does not prove a SCHEDULED firing.**
   `shadow_serving_2026-08-04.log` was born 12:41 against a 13:45 schedule, so a
   same-day manual invocation is indistinguishable here. The probe states this
   in its own output and claims only "wrote output during the session".

### The refutation, counted correctly `[codex on orch#815]`

#621's four "dead" jobs are `postclose`, `quote-logger`, **`session-scheduler`**
and `shadow-serving`. An earlier version of this paragraph wrote "four of four"
by substituting `batch-scores-export` — which #621 listed as **surviving** — for
`session-scheduler`. That is not a rounding error; it swapped the one job still
unestablished for one the issue never disputed.

**Three of the four** have direct output evidence for 2026-08-04: `quote-logger`,
`postclose`, `shadow-serving`. That is enough to retire "silent 28 days / 17–19
missed weekday firings each" for those three. **`session-scheduler` remains
unestablished** (empty log, no product of its own), and `shadow-serving`'s
evidence is same-day `WROTE_OUTPUT`, not a proved scheduled firing. The pairing
product is a session stale.

## Also corrected: the alarm-delivery failure is already fixed

#621-adjacent, and worth stating because I nearly re-reported it as live: the
liveness alert used to die with
`'latin-1' codec can't encode character '\U0001f6a8'` (the 🚨 in the ntfy Title).
The stderr file's **last write is 2026-07-28 18:58**, and the only two failures
in it are 07-27/07-28 — before `renquant_common.notify.encode_header` landed for
exactly this bug.

That is **circumstantial, not proof** `[codex on orch#815]`: it shows the old
shell-path error has not recurred in that file, not that post-fix deliveries
succeed. Enough not to re-report it as a live fault; not enough to call it
verified.

## What lands

`ops/renquant105/rq105_job_liveness_probe.py` — read-only, asks the two
questions a 0-byte file cannot answer: **did the job write its dated log for the
session**, and **is the artefact it exists to produce fresh**. Those are
different faults and are reported differently (`NO_LOG_FOR_SESSION` vs
`PRODUCT_STALE`), because "ran but produced nothing new" and "never ran" call
for different work. A job with no artefact of its own is recorded as such rather
than being silently treated as healthy.

Run against the live 2026-08-04 session: **4 WROTE_OUTPUT, 1 PRODUCT_STALE
(pairing), 1 LOG_EMPTY (session-scheduler)**. It agrees with the existing
liveness job on the pairing fault and adds one the stdout reading could not see.

## What I am NOT doing

No launchd change of any kind. `paired_is.jsonl` being one session stale is a
real fault with an open owner (the liveness job already alarms on it), and
touching a scheduled job is a landing action under the containment protocol.

Suites: 15 tests, incl. one bound to the live 2026-08-04 logs · 5643 passed,
2 skipped repo-wide `[VERIFIED — measured after the change]`.
