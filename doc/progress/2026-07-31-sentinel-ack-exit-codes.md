# The ack's own text asserted a restriction nothing implemented

**Bottom line.** The sentinel's self-referential ack row says, verbatim, *"So this ack
now covers **ONLY exit 1**."* **The code never read that sentence.**
`check_launchd_exits()` matched acks on **job name alone**, so a crash at
`EXIT_INTERNAL = 3` — the code introduced precisely so a crash would stop looking like
an alarm — was demoted to INFO by the very row that claims not to hide it.

Ledger rows carrying any exit-code narrowing before this PR: **0 of 10**
`[VERIFIED — 本次实测 2026-07-31]`.

## A correction to how I started this round

I opened #622's defect 2 expecting to *build* the crash/alarm split. It already exists
on `main`: `EXIT_INTERNAL = 3`, a liveness receipt, and a separate job checking the
receipt's freshness — *"because a process cannot attest to its own liveness."* My local
checkout was stale and I nearly re-implemented a landed fix. **Reading the real file
first is what caught it**, and it is the same mistake I made chasing PatchTST.

What remained was narrower and more interesting: **the fix produced a distinction and
the consumer discarded it.**

## What landed

| | before | after |
|---|---|---|
| ack match key | job name | job name **+ exit code** |
| self-row at exit 1 | INFO | INFO (unchanged) |
| self-row at exit 3 (crash) | **INFO — silenced** | **LOUD** |
| the other 9 rows | cover all nonzero | **cover all nonzero (unchanged)** |

`ack_covers_exit()` treats a missing `acked_exit_codes` as covering everything —
the behaviour all ten rows were reviewed under — so this moves **no disposition it was
not asked to move**. Only the self-referential row gains `"acked_exit_codes": [1]`,
which is what makes its own sentence true.

An **unreadable** exit code is **not** covered. An ack that cannot be matched to a code
is an ack of something unknown, and defaulting that to "silenced" would rebuild the
defect one level up.

## The shape

This is `asserted-instead-of-measured` at its purest: a load-bearing restriction stated
in a ledger field, with nothing enforcing it, sitting inside the mechanism whose entire
job is to decide what gets silenced. The row was *more* dangerous than an un-annotated
one, because reading it told you the crash case was handled.

Tests: 7, mutation-checked — removing the call fails 1, deleting the ledger key fails 2.
Suite: **4794 passed / 2 skipped**.

Note: all 10 acks are currently expired (measured 2026-07-31), so the self-row is not
suppressing anything *today*. That is incidental: re-ack it with a fresh date and exit 3
is silenced again. The defect is structural, not a function of today's dates.
