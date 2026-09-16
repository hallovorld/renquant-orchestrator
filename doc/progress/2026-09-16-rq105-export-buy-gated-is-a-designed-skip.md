# 2026-09-16 — rq105 batch-scores export: a buy-gated source run is a designed skip, not "FAILED rc=1"

## Conclusion

The 06:15 page `rq105 batch scores export FAILED rc=1 (2026-09-16)` was not a
failure. The exporter refused the 2026-09-15 run because its buy funnel was
gated: `logs/daily_104/2026-09-15.log` line 423 `EMA50GateTask: SPY below
EMA50 — buys blocked`, line 428 `Phase 2b (buy scan): buy_blocked=True;
scanning candidates for decision audit, order-emission remains gated`
`[VERIFIED]`. The run was contract-clean with provenance and scored 68
candidates; 104 admitted no buys by regime rule. rq105 is downstream of
104's buy admission, so no class-A frozen vector exists for such a day BY
CONSTRUCTION. The exporter's `_health_gaps` (2026-07-17 light-signal-day
fix) is right to refuse — but it returned the same `1` as an unreadable DB
or a lane mismatch, the wrapper paged **FAILED**, and the degradation
sentinel would list the job as an exit with NO DOCUMENTED MEANING.
Precedent: identical page on 2026-07-30 for the 07-29 run (`risk_gate_vol_
dropped(29)`, same gate) `[VERIFIED: logs/rq105/batch_scores_export_2026-07-30.log]`.

## Change

- `export_batch_scores.py`: `EXIT_SOURCE_BUY_GATED = 3`. When the ONLY
  health gap is `full_buy_run(pipeline_flags)` the exporter prints a
  "SKIPPED by design" line naming both flags and exits 3; any other health
  gap — or a buy-gated run that also lacks provenance / a clean panel
  contract — still exits 1. Nothing is published on either path.
- `run_batch_scores_export.sh`: rc 3 pages `rq105 batch scores export
  SKIPPED — prior session buy-gated by design`; every other nonzero rc
  still pages FAILED.
- `agent_inbox.DESIGNED_EXIT_CODES["rq105-batch-scores-export"][3]`
  (`actionable=False`, probe `EXIT_SOURCE_BUY_GATED = 3`), so the
  degradation sentinel renders it as a designed status report.
- Tests: the designed skip (rc 3, message, nothing published); a buy-gated
  run with OTHER gaps stays rc 1 (the skip covers exactly one gap); the
  existing sell-only/containment test moves to rc 3 with the same
  "refused, nothing published" property and a docstring saying why.

## Evidence (§4(b))

- 281 passed (`test_rq105_batch_scores_export.py`, `test_agent_inbox.py`,
  and the wrapper's callers); `bash -n` on the wrapper. `[VERIFIED]`
- Anti-vacuity: against an isolated copy of `origin/main`'s exporter the
  two designed-skip tests fail and the "other gaps stay rc 1" test passes
  (it pins unchanged behaviour). `[VERIFIED]`

## What this does NOT do

It does not export a vector for a buy-gated day (that would be a class-A
signal 104 itself did not act on) and does not touch the daily's EMA50 gate.
Live on the next `renquant-orchestrator-run` ff-sync after merge.

## Addendum (14:00 the same day): the liveness check paged 🚨 rq105 DOWN on the same skip

`rq105_liveness_check` (14:00) turned the designed skip into a three-issue
DOWN page — `export_missing` (no bundle), `serving_noop` (the serving
wrapper's `SKIP upstream` line), `intraday_pairing_logger` stale (nothing
served, nothing to pair) `[VERIFIED: 09-16 14:00 page body]`. The check had
no way to tell "the exporter ran and chose not to publish" from "the 06:15
job never fired" (the 2026-08-28 boot-missed-slot incident it was built
for). `launchd_liveness.out` shows `export_missing` fired on every no-export
day since 09-01 `[VERIFIED: 09-01, 09-02, 09-03, 09-04, 09-08, 09-09, 09-10,
09-14, 09-16]`.

Second commit:

- Exporter: on the designed skip it now also writes its testimony,
  `data/rq105/batch_scores_<date>.skipped.json` (`session_date`, `reason`
  `buy_gated`, source run id/date, the two flags, exit code, timestamp), via
  the same atomic writer as the bundle. It never publishes a bundle.
- Liveness: `_designed_export_skip` reads that sidecar — fail-closed: absent,
  unreadable, another day's `session_date`, or an unknown `reason` all leave
  the original `export_missing` / `serving_noop` verdicts. When it holds:
  `check_batch_scores_export` and `check_shadow_serving` return OK with the
  evidence, the admit-contingent pairing collector is exempt (no vector →
  nothing to pair; the authoritative 0-admit signal keeps precedence when it
  holds; non-admit-contingent collectors are unaffected), and the OK line
  NAMES the skip — `rq105 liveness OK <date> [export SKIPPED by design ...]`
  — never silent.
- Tests: the 09-16 state reconstructed → rc 0, no page, named OK line; a
  sidecar for another day / with an unknown reason / corrupt → still DOWN;
  the sidecar path and reason are bound to the exporter's own literals; the
  pairing collector is exempt while a non-admit-contingent collector is not.
  190 passed across the rq105 export/liveness/inbox files. Anti-vacuity
  against `origin/main`'s liveness module: the three positive tests fail,
  the three "does not exempt" tests pass on both (they pin unchanged
  behaviour). `[VERIFIED]`
