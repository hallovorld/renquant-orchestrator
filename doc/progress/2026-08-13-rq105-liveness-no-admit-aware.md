# rq105 liveness: make the post-close pairing collector's staleness check no-admit-aware

STATUS:   delivered (ops/monitoring fix; source repo only — NOT deployed to -run).
WHAT:     rq105_liveness_check no longer false-fires "paired_is stale" on a day renquant105
          admits 0 names. intraday_pairing_logger writes ONE row per daily-ADMITTED name, so on a
          0-admit day it legitimately writes 0 rows and its last row keeps yesterday's date; the
          check now consults the AUTHORITATIVE session manifest and, when the session COMPLETED with
          the collector's own admission query returning ZERO names, treats the stale-dated paired_is as EXPECTED, not a failure.
WHY/DIR:  0-admit is the CURRENT norm (model has no bull edge + most watchlist names have no panel
          score, orch#799), so the daily rq105 sentinel was raising an urgent "rq105 DOWN" ntfy every
          session — alarm fatigue on the shared "renquant" topic (the exact GOAL-5 failure mode). The
          fix keeps the alarm honest: it still fires on a REAL pairing-logger failure (session
          admitted >=1 name but paired_is is stale) and on "no completed session on a trading day".
EVIDENCE: On the REAL 2026-08-13 production data (read-only), the admit-contingent collector flips
          from a false stale to OK, while the authoritative signal and the other two collectors are
          unchanged: `[VERIFIED — this session, against live logs/renquant105_pilot/]`
            BEFORE (no_admit_exempt=None):  intraday_pairing_logger -> False,
              "paired_is.jsonl last complete row date='2026-08-12' != today '2026-08-13' (stale)"
            AFTER  (0-admit exempt):        intraday_pairing_logger -> True,
              "...not updated today but session completed with 0 admitted names — pairing collector
               legitimately wrote no rows (...; manifest status='completed', counters.entries_count=0)"
            check_collector_data_outputs(Path(RQ), 2026-08-13): quote=ok, pairing=ok, entry_timing=ok.
          Same-class consistency resolved by ground truth: on this SAME 0-admit day paired_is last row
          = 08-12 (stale) but entry_timing_shadow last row = 08-13 (fresh, 16 MB written 13:15) — the
          two are NOT the same class. In production (run_postclose_loggers.sh, `--date` only)
          entry_timing_shadow's admits fall back to every ticker in the #216 tick feed, not the batch
          admits, so it is tick-feed-contingent and correctly keeps the unmodified date+mtime logic.
          artifact:      ops/renquant105/rq105_liveness_check.py; tests/test_rq105_liveness_no_admit_aware.py
          prod or exp:   prod — the daily rq105 liveness sentinel (ops/monitoring), not a research artifact
          existing data: live logs/renquant105_pilot/intraday_session_manifest_2026-08-13.json
                         (status=completed, counters.entries_count=0) + paired_is.jsonl (read-only)
          best-known?:   n/a — a monitoring false-positive fix, not a ranking of variants
          scope:         "scoped to the ADMIT-CONTINGENT post-close collector (intraday_pairing_logger)
                         only; intraday_quote_logger and entry_timing_shadow are unchanged — verified
                         entry_timing_shadow is tick-feed-contingent, not admit-contingent"
TESTS:    tests/test_rq105_liveness_no_admit_aware.py — 12 new tests PASS (the required a/b/c:
          completed+0-admit+stale -> OK; admitted>=1+stale -> still stale; fresh row -> OK unchanged;
          + authoritative-signal derivation from the manifest, and the check_collector_data_outputs
          integration incl. the exemption not leaking to non-admit-contingent collectors). Existing
          tests/test_rq105_liveness.py + tests/test_rq105_collector_scheduling.py green (the tuple-arity
          change is absorbed by a backward-compatible 4-or-5-tuple unpack). Full suite: 6269 passed,
          16 failed, 9 skipped — the 16 are the pre-existing worktree-isolation failures (test_cli
          parking-sleeve subprocess, goal7 "THIS repo not the cwd", position_cap LIVE book, and the
          13-test test_shadow_ab_daily_script subprocess harness); no rq105/liveness test among them,
          and the two pre-fix test_rq105_collector_scheduling failures are resolved. No NEW failures.
NEXT:     deploy is a SEPARATE, ask-first landing step (never in this PR): once merged, advance the
          renquant-orchestrator-run pin on THIS machine so the daily 14:00 PT launchd liveness job runs
          the fixed check — merged != deployed. No code follow-up; if a dedicated rq105 ntfy topic is
          ever stood up (RQ105_NTFY_TOPIC), route rq105-DOWN there.

**Date:** 2026-08-13
**Lane:** GOAL-5 / rq105 (daily-run reliability — sentinel honesty)

## Bottom line

The rq105 daily liveness sentinel treated a legitimately-empty post-close pairing
output as a collector failure. `intraday_pairing_logger` emits **one row per
daily-admitted name** (`pair_records`: "one raw-observation record per admitted
name"). On a 0-admit day — now the norm — it writes 0 rows, so `paired_is.jsonl`'s
last complete row stays *yesterday's* date and the `date != today` gate reported
`(stale)` and paged an urgent "rq105 DOWN".

The fix makes that one gate **no-admit-aware** for the admit-contingent collector:
before reporting stale, it reads the AUTHORITATIVE session manifest for today via
the scheduler's own resolver (`intraday_session_scheduler.default_manifest_path`).
If `status == "completed"` and `the collector's own admission query returning ZERO names`, the empty paired_is
is expected and passes. Everything else is unchanged and still alarms.

## Why entry_timing_shadow is deliberately NOT touched

The obvious risk was fixing one collector while leaving an identical bug in its
sibling. Ground truth says they are different classes. On 2026-08-13 (a 0-batch-admit
day): `paired_is.jsonl` last row = **2026-08-12** (stale) while
`entry_timing_shadow.jsonl` last row = **2026-08-13** (fresh, written 13:15). In
production `run_postclose_loggers.sh` invokes both with `--date` only;
`entry_timing_shadow.collect()` then falls back to evaluating **every ticker present
in the #216 tick feed**, not the runs-DB batch admits — so it writes rows whenever
the feed has names, independent of batch admits. It is tick-feed-contingent, keeps
the unmodified date+mtime freshness logic, and the exemption is scoped away from it
(and from the continuous quote feed) by an explicit `admit_contingent` flag.

## Fail-toward-alarming

`_completed_session_zero_admits` returns `(True, …)` ONLY on a positive confirmation
(manifest present, `status == "completed"`, `entries_count == 0`). Any uncertainty —
no manifest, unreadable, a halted/disabled session, `entries_count` missing or `>= 1`,
or the scheduler being unimportable — returns `(False, reason)`, so a real staleness
is never suppressed. The "session didn't run on a trading day" signal is never weakened.


## Review correction (BLOCKER, 2026-08-13)

The first revision keyed the exemption on the session manifest's
`counters.entries_count`. **That is not the collector's admission set.**
`SessionScheduler` increments it from intraday tick intents, whereas
`collect_pairs()` resolves admissions from the runs DB as
`load_admitted(T)` UNION `load_submitted_entries(resolve_admitting_run_date(T))`,
deduplicated on `(signal_version, ticker)` — the batch that placed the entries
ran post-close on the PREVIOUS session.

So a session could COMPLETE with zero intraday entries while the batch had
admitted names that owed pairing rows, and the exemption would have marked a
stale `paired_is` OK — suppressing exactly the failure this check exists to
catch. Guarding on a proxy instead of the object being trusted is the recurring
shape here.

**Fix:** `_pairing_admit_count()` calls the SAME functions with the SAME dedupe
key, so the two cannot drift; the exemption now requires a completed session AND
a zero count from that query. Any failure to establish the count (collector
unimportable, runs DB absent or unreadable, query error) returns "unavailable"
and the staleness STANDS.

**Oracle, not exercise:** reverting the signal to the manifest count fails 5
tests, including
`test_zero_intraday_entries_but_nonempty_batch_admits_is_NOT_exempt` — the exact
scenario the review described. Restored: **17 passed**.
