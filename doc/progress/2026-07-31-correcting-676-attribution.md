# Correcting my own #676: "7 of 14 attributable" is wrong in both directions

**Bottom line `[本次实测 2026-07-31]`.** #676 published *"7 of 14 failing jobs cannot be
dated from their own output."* That number came from a classifier that reads each
**wrapper's source**. It **undercounts**. The obvious repair — count dated files in the
job's stdout directory — **overcounts**. Binding a dated file to the job **by name**
gives **4 of 14**, and the gap between the three is the actual finding.

| method | count | why it is wrong |
|---|---:|---|
| A — wrapper-source regex (#676) | 7 attributable | misses writes it cannot parse, and never looks outside `RenQuant/logs` |
| B — dated files in the stdout dir | **12** attributable | **12 of 14 of those directories are shared** — the file may belong to any job writing there |
| C — dated file **named for the job** | **4** | the only one that binds evidence to a producer |

## The instance that exposed A

`shadow-ab-daily` writes `~/renquant-shadow-ab/logs/2026-07-30_session.log` — **outside
the RenQuant tree entirely**. #676 classified it as *"undated evidence only"*. It has
dated session logs going back to 2026-07-10.

## The instance that exposes B

`rq104-degradation-sentinel`, `rq104-scorer-identity` and `run-surface-drift` all point
their stdout at `RenQuant/logs/rq104`, which holds **30** dated files. Method B credits
each of them with all 30. Only `rq104-scorer-identity` has any file bearing its own
name (20).

> **Neither method identifies the job's own evidence, because nothing binds a job to
> its evidence file.** That is the GOAL-5 gap, and it is a better statement than any of
> the three counts: a log directory shared by N jobs makes "there is a recent file
> here" worth nothing about any one of them.

Two jobs — `agent-pr-loop` and `crypto-session` — have **zero** dated files anywhere
near their stdout path, on either method.

## A separate live diagnosis in the same measurement

`shadow-ab-daily`'s last exit is **3**, and its wrapper defines that precisely:

```
except ShadowABContractError as exc:
    print(f"PRECHECK: {exc}", file=sys.stderr)
    raise SystemExit(3)
...
if [ "$preflight_rc" -eq 3 ]; then
    echo "PRECHECK: run manifest verification failed"
```

**`exit 3` = run-manifest verification failed at precheck.** It is running daily (dated
session logs through 07-30) and dying before it does any work — confirming the "epoch
manifest re-freeze" blocker as the live cause, not a guess.

Note the wrapper already has a rich exit vocabulary — `0/2/3/4/124` — which is exactly
the distinction `#671` had to add to the sentinel. The convention exists in one script
and not the fleet.

## What I got wrong, and how it was caught

I published 7/14 one round ago. I found the error by chasing a **different** question
(why `shadow-ab-daily` exits 3), noticing dated logs where my classifier said there were
none, and re-measuring rather than assuming the classifier was right. **The correction
came from a coincidence, not from the method** — which is why the three-way comparison
is pinned as a test instead of a better single classifier being asserted.

Tests: 4, including one asserting the two methods **disagree** — if they agreed, neither
would be evidence about the other.
