# The sentinel is alive. The open question from #622 is answered — and replaced.

**What I established first.** #622 defect 1 left one thing explicitly open: *"Either that
alarm has been firing unheeded for a month, or the sentinel is not running. That
distinction is the first thing to establish and I have not established it."*

The liveness receipt now answers it `[本次实测 2026-07-31]`:

```
~/.renquant/sentinel/rq104_degradation_receipt.json
  written_at  2026-07-31T02:50:24+00:00
  as_of       2026-07-30
  exit_code   1
  outcome     "alarms"
  alarm_count 1
```

**The sentinel is running, and it exited 1 because it found alarms — not because it
crashed.** So the alarm has been firing, unheeded. `launchctl` currently shows **14**
`com.renquant.*` jobs with a nonzero last exit.

## Which turns the question into: did the alarm reach anybody?

Two gaps, both measured, both fixed here.

**1. `alert()` threw away the only evidence of delivery.** It returned `None`.
`renquant_common.notify.send` is deliberately built never to raise into a monitor — it
swallows the failure, increments a counter, returns `False`. That bool was the only
in-process evidence an alarm reached anyone, and `alert` discarded it: **0 of 12 call
sites** could observe delivery, because there was nothing to observe.

> That made *"raised an alarm"* and *"raised an alarm nobody received"* indistinguishable
> at every caller — the same shape as a crashed sentinel exiting with the alarm code,
> one layer up. `alert()` now returns `bool`, and returns `False` (never `None`) when the
> sender is not even importable: **sender unavailable is not sender succeeded.**

**2. `undelivered_alert_scan` was blind to the sibling failure.** `send` returns `False`
from **two** places, and they log different text:

| path | log text | level | scan saw it |
|---|---|---|:--|
| exception | `ntfy send failed (…)` | WARNING | yes |
| `RENQUANT_NO_NOTIFY` | `[ntfy suppressed] …` | INFO | **no** |

Measured: the file had **zero** references to suppression of any kind. A fleet muted by
one environment variable would drop **every** alarm while the tool built to catch
undelivered alarms reported **clean**. Now reported as its own class — suppression is a
policy, not a codec bug, and the reader must be able to tell them apart.

## Checked and NOT claimed

`.env` carries **no** `NTFY_TOPIC=` line, which looked alarming until I read
`resolve_topic`: it falls back to `DEFAULT_TOPIC`, so delivery is unaffected. **Not
published as a finding.**

`ops/undelivered_alert_scan.py` is **not scheduled** — absent from
`ops/launchd_manifest.json` and from every plist. Installing it is a machine landing and
needs operator authorization, so it is recorded here, not done.

Tests: 8, including an anti-vacuity clean-log control and a control that widening did not
lose the original failure class. Two of them failed first **for my own errors** — an
annotation compared against `bool` under `from __future__ import annotations` (it is the
string `"bool"`), and a property I named from memory as `is_permanent` when the source
says `looked_permanent`. Both fixed by reading the source.

Suite: **4795 passed / 2 skipped**.

## Round 2 — it is a SEND-ATTEMPT outcome, not delivery, and it is a primitive not a control

Codex on #672, all three points accepted.

1. **`alert() -> True` proves the request was built and accepted, not that anyone was
   told.** I called this "delivery observability"; that is the same over-reach this
   function exists to correct, **one step further along the chain**. *"The POST
   succeeded"* and *"somebody was told"* are different facts and only the first is
   observable here. The docstring, the test names and this document now say
   **send-attempt outcome**.
2. **No caller records the return value.** True. Pinned by a test that scans `ops/` for
   any assignment or branch on `alert(...)` and asserts there are **none** — it fails the
   day one appears, which is the day the claim may change.
3. **The widened scan is unscheduled.** So what this PR adds is an **observability
   primitive**, not an active delivery-monitoring control. Scheduling the scan is a
   machine landing and needs authorisation; nothing here should be read as a control
   that exists.
