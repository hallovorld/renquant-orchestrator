# 2026-09-15 — shadow-scorer sentinel: a frozen prereg instrument's age is not a fault

## Conclusion

Since 2026-09-14 the 14:45 `rq104 SHADOW SCORER DEGRADED [topdecile_clf_blend_leg]`
page fires every session on age alone:
`cutoff_lag_140d_over_112d(floor_84d+slack_28d), trained_49d_limit_28d`.
The lane's artifact (`sha256:1e644354e0981f47`, trained 2026-07-28, cutoff
2026-04-28) is the INSTRUMENT of the preregistered 120-session forward
ledger (operator-directed activation 2026-07-26, pipeline#213 frozen
readout: INFO read ~mid-Nov 2026 at 60 matured sessions, GATE ~Feb 2027 at
120). Retraining it mid-ledger would change what the ledger measures, so its
training age is a property of the experiment. The producer's two age axes
are the right verdict for a lane whose retrain chain silently stopped and
the wrong one here — and without this change the page repeats every
session until February.

The sentinel now carries a `FROZEN_INSTRUMENTS` registry (lane, the exact
served `content_sha256`, `until`, authority, reason). A DEGRADED record whose
every reason is an age reason, on a registered lane, for the registered
artifact, on a date not past `until`, is reclassified `FROZEN_AGED`: quiet
like HEALTHY, and printed by name so the patrol SAYS it happened. Everything
else on that lane alarms exactly as before — a load failure, thin coverage,
missing provenance, a malformed record, a DIFFERENT artifact in the lane
(someone retrained it), or any record past `until`.

## Evidence (§4(b))

Read-only runs against the live health log, `--as-of 2026-09-15`,
`RENQUANT_NO_NOTIFY=1` `[VERIFIED]`:

| sentinel | verdict |
|---|---|
| deployed (`renquant-orchestrator-run`) | `[topdecile_clf_blend_leg] NOT ACTIONABLE / DEGRADED: 2 consecutive session day(s) — 2026-09-14 [degraded: cutoff_lag_139d_over_112d(...), trained_48d_limit_28d]; 2026-09-15 [...]` → EXIT_ALARM |
| this branch | `[topdecile_clf_blend_leg]: FROZEN INSTRUMENT — age-only degradation on 2 day(s) (2026-09-14, 2026-09-15) is by design until 2027-02-28 (authority: ...); non-age faults on this lane still alarm.` then `3 lane(s) patrolled ... — no finding` → 0 |

Tests: 106 passed (`tests/test_rq104_shadow_scorer_sentinel.py`). Seven new
tests: quiet-and-named on the frozen artifact; the same reasons on an
unregistered lane still alarm (the exemption is keyed on the registry, not
the reason text); a non-age fault on the frozen lane still alarms; a
different artifact in the lane must meet the age bar; past `until` the
freeze lapses; a frozen day + a load failure is not a degraded streak (as a
healthy day + a failure is not); registry entries name watched lanes and
the producer's reason vocabulary is matched exactly (verbatim strings from
`backtesting/renquant_104/logs/shadow_scorer_health.jsonl`).

## What this does NOT do

- Does not change the producer (renquant-pipeline `shadow_health`) or the
  served config; the freeze is a sentinel-side policy bound to the exact
  artifact the ledger was registered on.
- Does not affect the `model freshness` monitor's shadow-panel axis (a
  different lane: the PatchTST `momentum_fast` shadow config, 217d).

## Deploy

The sentinel runs from `renquant-orchestrator-run` (14:45); live on the
next `-run` ff-sync after merge. Until then the page keeps firing daily.
