# AMENDMENT — blend readout horizon: fwd_20d → fwd_60d

Date: 2026-07-29. Amends the frozen readout rule from pipeline#213.
**Authority: quoted as an operator decision, 2026-07-29** ("改成 60d，重算已有场次").
**That authorization is not independently checkable from this repo** — no
record of it exists in `doc/memory/long-term-agreements.md` or any
`doc/memory/mid-term/` workstream file; see the progress doc's `best-known?`
field for the full search. The horizon change itself is verified on its own
technical merits below, independent of that governance question.
Recorded as an amendment rather than an edit because the rule was frozen, and
a frozen rule that can be quietly edited is not frozen.

## What changed

The 120-session forward ledger backfilled realized spreads from `fwd_20d`.
It now uses `fwd_60d`, and the maturity window moves with it (21 → 61 trading
days).

## Why — three independent reasons, none of them convenience

1. **The ledger was measuring a different quantity than the one certified.**
   The certified effect (+0.0687, CI lower bound +0.0156) and BOTH scored
   models are `fwd_60d` recipes. A 20-day spread answers a question the
   certification never asked, so the GATE read in Feb 2027 would have been
   evidence about something else.
2. **The shorter horizon bought no statistical power either.** GOAL-6 Stage 0
   measured H2 as NOT SUPPORTED: 20d yields ~3× the independent blocks but a
   proportionately smaller effect, leaving the power ratio flat. There was not
   even a speed argument.
3. **The maturity constant had to move with it.** `MATURITY_TDAYS` was 21
   (`fwd_20d` + 1 settle). Left at 21 against a 60-day label it would have
   marked rows mature **40 sessions before their label can exist** — the
   silent half of a horizon change, and the kind of half-migration this
   project has been bitten by before. A test now pins the two together.

## Cost, stated rather than buried

Realized rows arrive **~40 trading days later** than they would have. Sessions
recorded now mature around late October rather than mid-September. The INFO
read slips accordingly. That is the price of measuring the right thing.

## Data availability check, done before committing to it

`ticker_forward_returns` already carries `fwd_60d`: **17,084 non-null rows,
latest `as_of_date` 2026-04-30** `[VERIFIED — direct query, 2026-07-29]`. So
the column is populated and backfilled, not a new pipeline dependency.

## What is NOT changed

The realization criterion (all picks resolvable, or the row does not realize),
the statistic (mean forward excess of each arm's top-10), the 120-session
target, and the INFO/GATE structure. Only the horizon and its matching
maturity window.

## Governance-trail note (added round 2, Codex MED finding, PR #598)

The "Authority" line above quotes an operator instruction, but the only
source for that quote is this document and the PR's own commit message —
both agent-authored, not an external issue/comment/decision-record. A search
of `doc/memory/long-term-agreements.md` and every `doc/memory/mid-term/`
workstream file mentioning "60d" / "blend ledger" / `MATURITY_TDAYS` turned up
no independent record of this specific decision. See the paired progress doc
(`doc/progress/2026-07-29-blend-readout-horizon.md`) `best-known?` field for
the full account. This note documents the gap rather than closing it — a
fix-agent has no channel to verify the original instruction against.

## Existing sessions

Both recorded sessions (2026-07-27, 2026-07-28) are unrealized, so nothing
computed under the old horizon needs discarding — the change lands before any
row matured. That is luck, not design: had this been caught two months later,
the ledger would have carried a mix of horizons and the honest fix would have
been to void the early rows.
