# GOAL-1: a job launchd is running that no reviewed surface declares

**Date:** 2026-08-05
**Lane:** GOAL-1 (shadow reliability gates)

## Bottom line

`com.renquant.crypto-session` is **loaded in launchd, absent from
`ops/launchd_manifest.json`, and belongs to a research lane killed 2026-07-18**
`[VERIFIED — this session]`.

```
loaded com.renquant jobs   40
manifest jobs              39
LOADED but NOT manifested   1   com.renquant.crypto-session   (last exit 2)
manifested but NOT loaded   0
```

Its plist was written **2026-07-13** — G2 crypto was killed five days later, on
07-18. So a job for a dead lane has sat on the live run surface for **23 days**.

The drift scan **does** report it (`check_launchd_surface` compares the plists on
disk against the manifest), and `com.renquant.run-surface-drift` exits 1 daily.
So this was never undetected — it was **undispositioned**, which is the GOAL-1
theme rather than an exception to it.

## The hole, which is the part worth fixing

Both existing launchd checks start from a list **someone already wrote down**:

| check | enumerates | blind to |
|---|---|---|
| `check_launchd_surface` | plists in `~/Library/LaunchAgents` | a job bootstrapped from any other path |
| `check_launchd_loaded` | `for label in sorted(manifest)` | anything not in the manifest |

crypto-session is caught **only because its plist happens to live in the one
directory the first scan walks**. `launchctl bootstrap` a job from anywhere else,
never manifest it, and **every check in that file stays quiet** — while the job
runs daily on the live surface.

That is precisely the emergency-containment path CLAUDE.md requires a durable
record for, and the scan built to catch containment drift could not see it.

## Delivered

`check_launchd_loaded_undeclared()` — starts from **launchd** (`launchctl list`)
rather than from a declared set, and reports any loaded `com.renquant.*` label
with no manifest entry, distinguishing:

- *plist on disk but unmanifested* (today's crypto-session), from
- *NO plist in the scanned directory AND no manifest entry* — the case nothing
  could see before.

Wired into the scan's `main()`. 10 tests, `loaded_labels` injectable so none of
them reads the operator's own launchd domain — a test bound to this machine
would be vacuously green on CI and red on the operator's box for reasons
unrelated to the code.

Three refusals are pinned by test:

- **launchctl unreadable → LOUD**, never "nothing is loaded". A checker that
  cannot see is indistinguishable from one that sees nothing wrong.
- **manifest unparseable → one finding**, not forty. A broken manifest must not
  make every loaded job look undeclared.
- **the message forbids the wrong remedy** — *"do not silence this by editing
  the manifest outside a reviewed change"*, per the containment protocol.

A test caught a real gap mid-write: the check trusted its **caller** to filter to
`com.renquant.*`. Left alone, the day that caller changed, every Apple agent on
the box would be reported as an undeclared RenQuant job and the noise would bury
the one real finding. It now filters itself.

## Anchor corrections

The GOAL-1 anchor reads *"#622 新开(ack 台账 4 条过期 10 天;哨兵自身 ack 让崩溃与告警不可区分)"*.
**Both clauses are stale** `[VERIFIED]`:

1. **Ack ledger: 0 of 5 expired**, not 4 — fixed by orch#839. One finding
   remains, an expiry cliff on 2026-08-16 where two acks lapse together.
2. **Crash and alarm are no longer the same observable.** Verified by *running*
   it, not by reading the claim: injecting a fault into the sentinel gives
   **exit 3** (`EXIT_INTERNAL`) and a receipt with `outcome=internal_error`,
   while the by-design alarm exits 1. The live receipt is 1.8 h old with
   `outcome=alarms, alarm_count=1`, and `check_sentinel_receipt` in the drift
   scan reads it from a separate job.

The sentinel's single alarm today is the bundled list of 14 nonzero-exit jobs
already tracked in orch#841.

## Next

`com.renquant.crypto-session` needs a decision, and it is **not mine to make
unilaterally** — retiring a loaded job is a live run-surface mutation. The two
lawful options: retire it under the containment protocol (tracked record +
literal revert steps), or legitimise it in the manifest through review. Filed as
an issue rather than acted on.
