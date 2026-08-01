# GOAL-1: the shadow-scorer sentinel's alarm was indistinguishable from its crash

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-1 (#622)

**Bottom line.** `rq104-shadow-scorer-sentinel` returned **1** when it alarmed. Its entry
point is `sys.exit(main())`, so an **uncaught exception also exits 1**. At the launchd
level the two were the same value, and nothing else in the record separated them.

## Measured, on the live machine

`[本次实测 2026-07-31, launchctl list]`

```
-   1   com.renquant.rq104-shadow-scorer-sentinel
```

**Its last exit is 1 right now** — and from that alone it is not possible to say whether
the sentinel did its job and found a degraded shadow feed, or died before looking.

13 `com.renquant.*` jobs currently carry a nonzero last exit; this one is the watchdog
among them, which is why it is the one fixed here.

## Why this is exactly #622

That issue's second half is *"a crashed sentinel is indistinguishable from an alarming
one."* This is that sentence at the level of a single integer. **A watchdog whose failure
and whose finding produce the same signal cannot be monitored** — any rule written over
`last_exit` is ambiguous by construction, including the ack ledger's own
`acked_exit_codes` matching.

## The change

`EXIT_ALARM = 8`, returned by the alarm path instead of 1. Chosen for being neither
**1** (Python's uncaught-exception exit) nor **2** (argparse usage error) nor **0**.

`main()` aggregates lanes with `rc |= _patrol_lane(...)`, so the codes must stay a
partition under bitwise OR: clean lanes contribute 0, alarming lanes contribute 8, and
any mixture is 0 or 8 — **never 1**. That is asserted, not assumed.

## Safety

- **No ack row exists for this job** — checked `ops/renquant104/sentinel_acks.json`
  (10 rows, none for `shadow-scorer-sentinel`), so no suppression keyed on exit 1 is
  broken by this. `[本次实测 2026-07-31]`
- **No other caller keys on this job's exit code** — swept `ops/`, `scripts/`, `tests/`.
- The alarm still fires and still pages: `alert(...)` is unchanged. Only the integer the
  process exits with is different.

## Tests

15 existing assertions moved from `rc == 1` to `rc == sentinel.EXIT_ALARM` — they were
pinning the contract this PR deliberately changes. Two new ones carry the point:

* the alarm code is **not** 1, 0 or 2;
* the codes stay a **partition under bitwise OR**, so aggregation can never manufacture 1.

**Mutation:** setting `EXIT_ALARM = 1` fails both. 75 tests pass in the module.

## Not claimed

That the current live `exit=1` was a crash rather than an alarm — **that is precisely
what cannot be determined from the record**, which is the finding. After this lands, the
next nonzero exit answers it by itself.

This changes an ops exit code, not a production trading path. It takes effect only when
the run checkout syncs; **merged is not deployed**.
