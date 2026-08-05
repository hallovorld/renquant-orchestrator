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

Every one of the six jobs wrote its dated log for the 2026-08-04 session:

| job | dated log (2026-08-04) | product | product freshness |
|---|---|---|---|
| quote-logger | 13:00 | `intraday_ticks.jsonl` | **Aug 4 12:59, 709 MB** |
| postclose | 13:15 | `entry_timing_shadow.jsonl` | **Aug 4 13:15, 12.4 MB** |
| postclose (pairing) | 13:15 | `paired_is.jsonl` | Aug 3 13:15 — **one day stale** |
| batch-scores-export | 06:15 | `batch_scores_2026-08-04.json` | Aug 4 06:15 |
| session-scheduler | 06:25 | — | — |
| shadow-serving | 13:45 | — | `SKIP not-wired: no producer exists for feature_snapshot_2026-08-04.json (Stage-3, #221)` |

**`shadow-serving` is not crashing — it is skipping, by design**, because the
Stage-3 producer it consumes does not exist yet. Its non-zero exit is that
documented skip.

The single real fault is the one the existing `rq105-liveness` job already
reports on its own: `paired_is.jsonl` one session stale. Liveness is alive
(stdout Aug 4 14:00) and its exit 1 is that one complaint, not four dead jobs.

## Also corrected: the alarm-delivery failure is already fixed

#621-adjacent, and worth stating because I nearly re-reported it as live: the
liveness alert used to die with
`'latin-1' codec can't encode character '\U0001f6a8'` (the 🚨 in the ntfy Title).
The stderr file's **last write is 2026-07-28 18:58**, and the only two failures
in it are 07-27/07-28 — before `renquant_common.notify.encode_header` landed for
exactly this bug. It is repaired; there is nothing to fix here.

## What lands

`ops/renquant105/rq105_job_liveness_probe.py` — read-only, asks the two
questions a 0-byte file cannot answer: **did the job write its dated log for the
session**, and **is the artefact it exists to produce fresh**. Those are
different faults and are reported differently (`NO_LOG_FOR_SESSION` vs
`PRODUCT_STALE`), because "ran but produced nothing new" and "never ran" call
for different work. A job with no artefact of its own is recorded as such rather
than being silently treated as healthy.

Run against the live 2026-08-04 session it reproduces the liveness job's own
verdict exactly: 5 jobs RAN, 1 PRODUCT_STALE (pairing). That agreement is the
point — the probe finds nothing new; it refutes a reading, and pins the
refutation so it cannot be re-derived from stdout again.

## What I am NOT doing

No launchd change of any kind. `paired_is.jsonl` being one session stale is a
real fault with an open owner (the liveness job already alarms on it), and
touching a scheduled job is a landing action under the containment protocol.

Suites: 8 new tests, incl. one bound to the live 2026-08-04 logs · 5636 passed,
2 skipped repo-wide `[VERIFIED — measured after the change]`.
