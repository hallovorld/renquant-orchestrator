# GOAL-5: every count-based admission guard shares the in-flight blind spot — and the one that looks fixed is fixing a different bug

**Date:** 2026-08-06
**Lane:** GOAL-5 (daily-run reliability P0)

## Closing a claim I left unverified

orch#866 established the root cause of the book holding 10 against a cap of 8:
`open_slots` counts **filled** positions, so three runs on 2026-08-04 each saw
`held=5`, each emitted inside its own budget, and their orders accumulated. I
then wrote:

> *"The same argument applies to `max_positions_per_sector` and any other
> count-based admission limit that reads `holdings`. Likely, since they read the
> same `holdings`, but I have not verified each."*

Verified now `[VERIFIED — this session]`.

## Live state, unchanged

```
positions 10   cap 8   in-flight unfilled orders 0
```

The book is still 2 over, with nothing pending — so this is a settled state, not
a transient mid-fill one.

## Every count-based guard in the selection path

| guard | reads | in-flight aware? |
|---|---|---|
| `max_concurrent_positions` (`task_selection.py:52`) | `len(held)` | **no** |
| `max_positions_per_sector` (`:39`, `:88`) | `held_tickers` via `SelectionContext` | **no** |
| `bear_defensive_slots` (`:62`) | `held` ∩ `defensive_set` | **no** |
| bear sleeve portfolio slots (`:825`) | `len(held) + len(long_ordered)` | **partially — see below** |

**Confirmed: they all read the same filled-positions view**, so the defect is not
specific to `max_concurrent_positions`.

## The one that looks fixed, and why it is not the fix

`ApplyBearDefensiveSleeveTask` at `:825` is the only guard that subtracts orders:

```python
long_ordered = self._long_entry_order_tickers(ctx)
portfolio_open_slots = max(max_positions - len(held) - len(long_ordered), 0)
```

I was about to report this as *"the fix already exists 770 lines down in the same
file"*. **It does not.** `_long_entry_order_tickers` (`:940`) reads
**`ctx.orders`** — the orders emitted by **this run**. It prevents a single run
from counting a name twice while building its own order list. It has no view of
orders sitting `ACCEPTED`-unfilled at the broker from a *previous* run, which is
exactly what accumulated on 08-04 across 14:54, 19:28 and 20:18.

So the two failure modes are distinct, and only one is covered anywhere:

| failure mode | covered? |
|---|---|
| one run double-counts a name inside its own batch | yes, bear sleeve only |
| **orders accumulate across runs while unfilled** | **nowhere** |

Reporting the bear sleeve as a ready-made remedy would have sent the pipeline
owners to a line that solves a different problem, and the fix would have looked
like a two-line copy when it is not.

## What the fix actually requires

`ctx.orders` is the wrong source — it is per-run by construction. The needed term
is the **broker's open-orders list**, which no guard in this path consults:

```
effective_held = filled_positions ∪ accepted_unfilled_buy_orders   # from the broker
```

and it must be applied to **all four** guards above, not just
`max_concurrent_positions`, because all four decide admission by counting.

## What this does NOT establish

- **Not that the sector cap has actually been breached.** I verified it *reads the
  same view*, not that a breach occurred. `max_positions_per_sector = 6` and the
  book holds 10 names; whether any sector exceeded 6 is unmeasured.
- **Not that the bear sleeve is wrong.** Its extra term is correct for what it
  guards. The finding is that it does not generalise.
- **Not the P/L effect** of being 2 over, which remains unmeasured and is a
  separate question from whether the control held.

Filed as an addendum to renquant-pipeline#269 (repo boundary — the fix is theirs).
