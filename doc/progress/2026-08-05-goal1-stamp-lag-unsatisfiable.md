# 2026-08-05 — GOAL-1: the stamp-lag finding asked for the one action that could not clear it

## The finding, and why the obvious fix is wrong

The sentinel ack-ledger audit reported **3 findings**, two of them:

> `rq105-batch-scores-export`: acked_at 2026-07-31 but the row was actually last
> edited 2026-08-02 (2d) — the expiry clock is stamped with the wrong event

I went to correct the stamps to the true edit dates. **That is unsatisfiable.**
The audit dates a row by *the commit carrying its current value*, so **any edit
re-dates it to the editing commit**. Writing the old true date back produces the
same finding, one day larger. The finding asked for the one action that cannot
clear it.

## The fix I tried first, and why the suite was right to refuse it

I changed the *audit* instead: date rows on the **decision-bearing** fields only
(`acked_exit_codes` / `clears_when` / `clears_check` / `reason`), so maintaining
a row would not read as re-acking it.

The suite refused it, and correctly. It re-opens the hole closed on **#654**: a
genuine re-review and an unreviewed re-stamp must stay **INDISTINGUISHABLE**,
because claiming to tell them apart names an event the mechanism cannot see —
the guards-that-validate-the-wrong-object shape, committed *inside* the audit
built to catch it. With my change, a silent `acked_at` bump produced lag −19 and
a finding, i.e. exactly the withdrawn claim re-entering through a side door.

**Reverted, and recorded rather than retried.** A test already existed for this
precisely so it could not be re-added — it worked.

## What actually lands

The only stamp the audit can accept is the date of a **real re-review**. So both
rows were genuinely re-reviewed today and stamped with today `[VERIFIED]`:

| row | what I verified | deadline |
|---|---|---|
| `rq105-batch-scores-export` | precondition (strategy-104#73, `wash_sale_min_material_npv`) has **not** landed; diagnosis stands | `expires_at` already explicit **2026-08-14 — unchanged** |
| `shadow-ab-daily` | precondition **still unmet**: the drift scan still reports `runtime/renquant-model` dirty (`M README.md`), the same drift the reason names | had **no** `expires_at`; stamping today would have moved the derived deadline 08-15 → **08-19**, so it is pinned to **2026-08-15** |

**A re-review must never buy time.** Neither deadline moves.

Result: **3 findings → 1** (the remaining one is the 08-16 expiry cliff, which
is 2 acks and belongs to whoever owns that threshold — moving someone else's
expiry to break a "burst" of two would be arbitrary).

## The near-miss worth writing down

I began this expecting today's operator-authorised sync to have cleared
`shadow-ab-daily`'s precondition. It did not: that sync moved
**`renquant-orchestrator-run`**, and this job executes from the **pinned subrepo
runtime** — a different surface, which is exactly what orch#819 documented and
what I nearly forgot the same day. The note is now in the ack row itself, where
the next reader meets it.

## A second finding, in the suite

The anti-vacuity control demanded that the **live** ledger contain a stale row.
It could therefore only pass **while the ledger was defective** — fixing the two
rows retired the very evidence that the audit can detect staleness at all.

> A positive control that dies when the thing it guards is repaired is not a
> control.

It is synthetic now, built on a purpose-made repo, and available forever.

## A third one, same shape

`test_the_re_dispositioned_ack_expires_by_its_OWN_explicit_date` asserted
`acked_at == "2026-07-31"` — pinning a value that **legitimately moves on every
re-review**, inside a test whose stated point is that an explicit `expires_at`
beats the blanket 14-day window. It broke the moment the row was honestly
re-reviewed.

It now pins the **property**: the explicit deadline must differ from
`acked_at + 14` (otherwise the row cannot demonstrate anything) **and must be
earlier** — which is the same "a re-review must never buy time" rule, now
enforced by a test rather than by my intention.

Three tests today, all the same lesson from different angles: **a test that
pins today's value instead of the invariant fails when the thing is repaired,
not when it breaks.**

Suites: 51 in the audit file (was 50) · full suite green.
