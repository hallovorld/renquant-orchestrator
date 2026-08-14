# rq105 shadow-serving: silence the expected "Stage-3 not wired" ntfy

STATUS:    fix — the scheduled rq105 shadow-serving job stops paging on a
           designed, stable deferral. Small ops-script change, behaviour-preserving
           except it no longer ntfy's the expected not-wired skip.

WHAT:      `ops/renquant105/run_shadow_serving.sh`: the not-wired branch (feature
           snapshot has no producer — Stage-3 not built) no longer sources notify.sh
           + `rq_notify`s "no feature-snapshot producer yet (Stage-3 wiring pending)
           — see #221"; it now only `skip_log`s (durable) + exits `EXIT_NOT_WIRED`.
           Real-failure ntfy's (missing upstream scores; bundle-verification failure)
           are UNCHANGED.

WHY/DIR:   Operator-flagged 2026-08-14 (pasted the ntfy, "这是啥!解决掉!"). The
           `com.renquant.rq105-shadow-serving` launchd job runs on a schedule (last
           exit 4 = EXIT_NOT_WIRED) and ntfy'd EVERY run because its input
           (`$FEATURE_SNAPSHOT`) has no producer — Stage-3 (intraday re-scoring) is a
           deliberately-deferred FUTURE stage (RFC #208 Stage-3; the current 105 path
           is Stage-1 shadow → canary, which does not need it). A healthy job paging a
           designed, unchanged deferral every run is pure noise, same class as the
           pairing-logger false-stale alarm.

EVIDENCE:
  artifact:      `ops/renquant105/run_shadow_serving.sh` (the not-wired ntfy removed;
                 skip_log + exit retained) + this progress doc.
  prod or exp:   neither — behaviour-preserving ops-script change; no live/production
                 write, no model/decision change, no order path touched.
  existing data: `launchctl list` shows `com.renquant.rq105-shadow-serving` loaded,
                 last exit 4; the script's not-wired branch (L42-51 pre-fix) ntfy'd
                 every run; the feature snapshot has no producer (Stage-3 not built,
                 tracked #208/#221); `serving_features.py` (the persistence writer)
                 exists in renquant-pipeline but is not yet wired to produce the
                 Stage-3 snapshot.
  best-known?:   yes — silences ONLY the expected/stable deferral; the durable
                 skip_log keeps the record, and both real-failure ntfy paths are
                 untouched, so a genuine break still pages. A comment documents how to
                 restore the ntfy if the state ever becomes unexpected.
  scope:         "quiets one expected recurring status ntfy from a scheduled rq105
                 shadow-serving job. Does NOT build Stage-3, does NOT change the model
                 or any decision, does NOT touch the order path. Deploy to the -run
                 checkout is a separate operator-gated landing."

TESTS:     none — ops shell script; behaviour-preserving except the removed ntfy.
           Manual read-through: the two real-failure ntfy branches (missing scores,
           bundle-verification) are unchanged.

NEXT:      codex review → merge → operator-gated deploy to renquant-orchestrator-run
           (the running copy). Separately, building Stage-3 (wiring the feature-snapshot
           producer for intraday re-scoring) remains future work, after the 105 canary.
