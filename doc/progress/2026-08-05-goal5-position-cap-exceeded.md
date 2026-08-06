# GOAL-5: the book holds 10 against a cap of 8, and the code that enforces the cap looks correct

**Date:** 2026-08-05
**Lane:** GOAL-5 (daily-run reliability P0)
**Status:** OPEN — mechanism NOT established. Filed rather than guessed.

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
