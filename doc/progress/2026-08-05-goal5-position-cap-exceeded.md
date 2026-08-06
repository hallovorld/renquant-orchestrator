# GOAL-5: the book holds 10 against a cap of 8, and the code that enforces the cap looks correct

**Date:** 2026-08-05
**Lane:** GOAL-5 (daily-run reliability P0)
**Status:** ROOT CAUSE ESTABLISHED (2026-08-06 read). An earlier revision of this
doc said the mechanism was unestablished and described a single six-second batch.
Both are corrected below.

## The fact, from two independent sources `[VERIFIED — this session]`

| | |
|---|---:|
| live positions (Alpaca API) | **10** |
| `max_concurrent_positions` (prod config, top level) | **8** |
| over the cap by | **2** |

Live names: DDOG GOOG LRCX MRVL NVDA PANW SOFI TSLA VLO WELL.

This is the mechanical reason the operator's question — *"仓位是什么鬼？还有很多现金啊！"* — has a
`no open slots` answer while 47 % of the book sits in cash. `open_slots = 8 − 10 = −2`,
so the only path to any buy is a 1-for-1 rotation, and today's single qualifying
rotation (NVDA→CRWD) was refused by `correlation_guard`.

## How it happened, as far as the broker can show

Reconstructed from **filled broker orders**, not from the DB:

```
submitted 2026-08-05 11:00:02-11:00:08 UTC   ->   all filled 13:30:00-13:30:01 UTC
   DDOG 1   SOFI 9   WELL 3   VLO 2   NVDA 1   GOOG 1
```

**Six new names emitted in a single batch, six seconds wide.** Not accumulation
across runs — one emission. Immediately before it the book held **4** names
(LRCX, MRVL, TSLA, PANW), so `open_slots` should have been `8 − 4 = 4`.

**Six were emitted against four slots.**

## And yet the enforcement reads correct

- `PrepareSelectionTask` (`task_selection.py:52`) computes
  `open_slots = max_positions - len(held)`, refuses on `<= 0`, and passes the
  number into `SelectionContext`. It does not truncate itself.
- The truncation lives in the loop: `selection.py:803`,
  `if slots_filled >= ctx.open_slots: ...`
- The other `emitted >= open_slots` break (`task_selection.py:841`) belongs to
  `ApplyBearDefensiveSleeveTask` — a different path, not this one.

So a limit exists on the live path and the observed behaviour violates it. **I have
not established why**, and I am not naming a cause I cannot show.

Candidates not yet discriminated: `held` as the runner saw it may not have been
the 4 the broker implies; `max_concurrent_positions` may have resolved from a
different regime block; or `slots_filled` may count something other than
emissions.

## Two corrections to my own work in this same investigation

**1. My first reconstruction was wrong, and the consistency check I built in
caught it.** Rebuilding holdings from the `trades` table gave **18** names against
a live **10** — it contained BAC, D, GM, HON, IBM, LLY, NFLX, OXY, SPOT, WFC
(not held) and **missed LRCX and MRVL** (held). Cause: **45 of 63 `buy_pending`
rows never reached the broker**, and I counted every one. *The `trades` table is
not a position ledger.* The broker-derived reconstruction matches the live book
exactly (9 in-window + PANW bought before the window = 10).

Everything I would have said from the first reconstruction — including an
"OVER CAP" annotation on 07-28 rows that **never reached the broker at all** —
would have been wrong.

**2. I guessed the mechanism twice and the code refuted both.** First "the cap is
a boolean gate, not a quantity limit" (`selection.py:803` truncates). Then "the
dawn preflight placed them at 04:00 PDT" — **no manifest job runs at Hour=4**,
and that assumption would also have revived the sizing-P0 severity I had just
correctly narrowed.

## Next

The discriminating evidence is the 2026-08-05 11:00 UTC emitting run's own log:
what it recorded for `held`, `max_positions`, and `open_slots`. That is the next
step, and it is a read, not a guess.


---

# ROOT CAUSE — `held` counts FILLED positions, and in-flight buys are invisible `[VERIFIED]`

## Correction first: it was NOT one batch

The earlier section read Alpaca's `submitted_at` (all six at
`2026-08-05 11:00:02-11:00:08 UTC`) as one emission six seconds wide. **That is an
artifact of the broker's field**, not of our runner: an order accepted after
hours is re-stamped `submitted_at` when it is released at the next session's
pre-open. Every order in the batch shows the same 2.5 h "in-flight gap" precisely
because they were all released together, not sent together.

`logs/daily_104/2026-08-04.log` records what actually happened — **three separate
runs across 5.5 hours**:

| time (PDT) | orders ACCEPTED | `held` the runner reported |
|---|---|---:|
| 14:54:46 | DDOG ×1, SOFI ×9, NVDA ×1 | **5** |
| 19:28:16 | GOOG ×1, WELL ×3 | **5** |
| 20:18:38 | VLO ×2 | **5** |

## The mechanism

**All three runs saw `held = 5`.** The three orders accepted at 14:54 were still
`ACCEPTED`-not-filled at 19:28 and again at 20:18, so they never entered
`holdings` — and `open_slots = max_positions - len(held)` reads `holdings`.

So each run computed `open_slots = 8 − 5 = 3` and emitted **within its own
budget**: 3, then 2, then 1. Every run enforced the cap correctly against the
state it could see. **No run could see the other two.**

At the 2026-08-05 open all six filled at once:

```
4 pre-existing (LRCX, MRVL, TSLA, PANW)  +  6 filled  =  10   against a cap of 8
```

**The cap is enforced per-run against filled positions only. Accepted-but-unfilled
buy orders are invisible to it.** Three runs each obeying the cap produced a book
2 over it — the defect is not in any one run's arithmetic, it is that the budget
has no memory.

This also explains why it appeared on 08-04 specifically: that was the first day
with three buy-emitting runs whose orders all queued to the same next open.

## Why this is the load-bearing one

Sizing errors change how much of a name you buy. This changes **how many names you
hold**, past a limit that exists to bound concentration — and it did so with real
filled orders, not `buy_pending` rows that died before the broker. The book is
over its own cap **right now**.

## The fix, stated but not implemented (repo boundary: renquant-pipeline)

`open_slots` must subtract in-flight buy intents, not just filled holdings —
i.e. `effective_held = filled_positions ∪ accepted_unfilled_buy_orders`. The
broker's open-orders list is the authoritative source; `ctx.holdings` is not.

## What this does NOT establish

- **Not that any individual run misbehaved.** All three respected the cap they
  could compute. There is no bug to point at inside one run.
- **Not the P/L impact.** Whether being 2 names over the cap helped or hurt is
  unmeasured and is a separate question from whether the control held.
