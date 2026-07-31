# "Not loaded" hides three situations with three different remedies

**Bottom line `[本次实测 2026-08-01]`.** Of **43** manifested jobs, **6 are not loaded** —
and the drift scan said nothing about any of them, by an explicit and correct decision.

## Why the silence was deliberate, and why it still left a gap

`check_launchd_loaded`'s docstring:

> *"A job that is genuinely NOT LOADED is not reported — that is a liveness question,
> and inventing a drift alarm for it would fire on every job the operator has
> deliberately unloaded."*

**That reasoning is right and this PR does not undo it.** But a job in the **reviewed**
manifest that is not loaded is either a manifest nobody updated when the job was
retired, or a job that **silently fell out of launchd** — and nothing distinguishes
them. That is the containment shape: a persistent run-surface change with no durable
record.

So this **reports and never alarms**. A test asserts it returns **zero problems**, so
the alarm cannot come back through a side door.

## The three kinds, because "not loaded" hides them

| kind | jobs | remedy |
|---|---|---|
| plist **+** target present, not loaded | `daily103`, `open103`, `preclose103` | only a human knows whether this was retirement or a silent unload — **the manifest does not say** |
| plist absent, target present | `rq104-model-freshness` | ready to install, never installed |
| plist absent, **target absent** | `ops-audit`, `rq104-silent-refusal` | the run checkout has not been synced |

## The recursion in the third row

`ops-audit` is the aggregator whose own progress doc records that it *"included GOAL-5's
**AC5** sentinel, which had **never run**"*. **It does not run either** — no plist, and
its target is absent from the run checkout.

And `rq104-silent-refusal` **is** that AC5 sentinel. Measured today: in the manifest,
**no** installed plist, **not** in `launchctl`, wrapper **absent** from the run checkout,
and **zero** `silent_refusal_*.log` files have ever been written.

**Neither of those is a new finding** — `doc/progress/2026-07-31-ac5-scheduled-surface.md`
already carries it, titled *"AC5's sentinel has been merged for weeks and scheduled
never"*. What is new is that the daily scan now **says so out loud**, in the right
category, instead of leaving it to a document somebody has to remember.

**Not done, needs authorisation:** installing anything, or syncing the run checkout.

Tests: 5, including one asserting an unreadable manifest is a **problem** rather than an
empty report — a reporter that goes quiet when its input is missing is indistinguishable
from one that found nothing.
