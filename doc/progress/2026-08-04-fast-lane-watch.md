# The fast-momentum lane gets its watcher — the unwatched-lane test did its job

**Date:** 2026-08-04 · `renquant-orchestrator` · GOAL-8 / strategy-104#84 follow-up

STATUS:    code + test pins; deploys via the routine run-checkout sync.
WHAT:      (1) shadow-scorer sentinel registry gains the third WatchedLane
           `momentum_fast_v1_shadow` — watched from DECLARATION day, with
           the pre-activation gate keeping the not-yet-published window
           quiet (the v0 precedent, registry docstring); (2) the live
           primary-parity pin gains a BOUNDED pending exception for exactly
           the fast ledger path while it is unpublished (mirrors s104's
           PENDING_FIRST_ARTIFACT: the named set shrinks to empty in the
           same change that records the first publish; any OTHER
           unresolvable path still flips the test red); (3) the registry
           pin test moves 2 → 3 lanes.
WHY/DIR:   s104#84 declared the lane; the DESIGNED tests went red on clean
           main within one sync (`unwatched=['momentum_fast_v1_shadow']`,
           `n_unresolvable=1`) — exactly what they exist to force. This PR
           answers them rather than relaxing them.

EVIDENCE:

```
artifact:      ops/renquant104/rq104_shadow_scorer_sentinel.py,
               tests/test_rq104_shadow_scorer_sentinel.py,
               tests/test_strategy_config_primary_parity.py, this doc
prod or exp:   ops watch surface; no trading behaviour
existing data: pre-fix on clean main: 2 failed (unwatched-lane,
               primary-parity n_unresolvable=1).  [VERIFIED — reproduced
               on the run checkout this session]
post-fix:      full suite 5502 passed / 0 failed; the parity exception is
               path-exact and existence-gated (the moment the ledger file
               appears, the pending set self-empties and the strict pin
               resumes).  [VERIFIED]
best-known?:   NOT APPLICABLE — watch/parity bookkeeping, no model claim.
scope:         "sentinel registry + two test pins + this doc; no serving,
                no job, no config change."
```

NEXT:      after the first Saturday fast publish: s104 deletes its pending
           key + this repo's parity pending set returns to empty semantics
           automatically (existence-gated); nothing else to lift.

## Revert

git revert; the two designed tests go red again on the machine — the
reminder returns.
