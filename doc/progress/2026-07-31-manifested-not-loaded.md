# "Not loaded" hides three situations with three different remedies

**Bottom line.** Of **43** manifested jobs, **6 are not loaded** — and the drift scan
said nothing about any of them, by an explicit and correct decision.
`[VERIFIED — report_manifested_not_loaded() on the run host, 2026-07-31 06:58 PDT]`

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

## The census above is an observation, not a test — corrected after a red CI

The first version of the test file **pinned this laptop's census** (`n == 6`, and two
tests that only saw the three kinds because this host has one of each). Linux CI has no
`launchctl` at all, read **0** unloaded jobs, and went red — while the same tests passed
here for exactly the reason they failed there. **A test whose subject is the operator's
disk measures the disk, not the classifier**, and the two that passed locally were
passing over an empty loop, which is the worse half of the defect.

Classification is now tested against a **synthetic manifest** (written into `tmp_path`),
a **tmp LaunchAgents directory**, and a **mocked launchd**, so all three kinds are
present on every host. The census stays here, dated, where a changing machine is
expected rather than a build failure.

Two properties the rewrite added that the live-state version could not assert:

- a **loaded** job appears in no line — without it, a classifier that listed every
  manifested job would have passed;
- an `unreadable`/`unparsed` launchctl is **not** counted as an unloaded job. That is
  what CI was made of: on a host with no launchd, every label reads `unreadable`, and
  the report must be empty rather than 43 spurious "run checkout unsynced" findings.
  `check_launchd_loaded` already **alarms** on that status, which is the right place
  for it.

Tests: **7**, each killed by at least one of four mutations run against them (drop the
blind-status guard; classify every job as one kind; make the ambiguity sentence
unconditional; count the manifest instead of the unloaded jobs). Including one asserting
an unreadable manifest is a **problem** rather than an
empty report — a reporter that goes quiet when its input is missing is indistinguishable
from one that found nothing — and one asserting the "retired or silently unloaded"
sentence is **absent** when no job is in that state, so it cannot become an
unconditional footer.
