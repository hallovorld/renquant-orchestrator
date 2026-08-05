# 2026-08-05 — TSLA's 23.5 % was not drift. It was bought that way.

## What the operator asked me to measure

Design orch#848 listed Defect C as *"TSLA is 23.5 % against a 12 % cap; the cap
appears to bind at buy time only; nothing trims drift"* and said the next step
was **C1: measure whether a trim path exists at all, before proposing a
trimmer.** Doing that measurement **refuted my own hypothesis**, twice.

## 1. A trim path exists — and has NEVER run live

`TrimHeldTask` (`kernel/pipeline/task_trim.py`) emits `kelly_trim` partial sells
when a holding drifts above its Kelly target by more than the hysteresis band.

```
kelly_trim rows in the trades table:  250
… of which carry a trade_date (LIVE):   0
```

`[VERIFIED — this session]`. All 250 are simulation rows. **It has fired in
backtest only, never once on the live book.** So "nothing trims" was accidentally
true, but for a reason I had not established: the trimmer is not missing, it is
inert on the live path.

*(It is not the Deployment Governor suppressing it: `deployment_governor.enabled
= false` in the pinned config `[VERIFIED]`.)*

## 2. And drift is not how TSLA got to 23.5 % — the BUY was oversized

```
2026-07-28  TSLA  BULL_CALM  target_pct 0.2341  kelly_target_pct 0.0613   3.8x kelly, cap 0.12
2026-07-28  EME   BULL_CALM  target_pct 0.2109  kelly_target_pct 0.0613   3.4x kelly, cap 0.12
```

`[VERIFIED — trades table]`. The sizing stack stamped **~2× the regime cap and
~3.8× the model's own Kelly target**, at entry, on the same day, for two names.

Every other live buy since 2026-07-01 sized between **0.007 and 0.091** — all
comfortably under the cap. **2 of 33.** So this is an *event*, not the normal
path, and an event is exactly the thing that goes unnoticed without a check.

## 3. Both breaches came from ONE run, and it was off the schedule

```
EME    run 2026-07-28-live-6194047c   created 2026-07-28 17:45:49
TSLA   run 2026-07-28-live-6194047c   created 2026-07-28 17:45:49
```

Every other live run on 2026-07-28 sits on a **12-minute grid** — 13:30, 13:42,
13:54, 14:00 … 17:36, **17:48**, 18:00 … `[VERIFIED]`. **17:45:49 is not on it.**
So the only two oversized buys this book has taken came from a single cycle that
was not part of the scheduled cadence.

The probe now names the run and its creation time on every breach row, because
"which cycle did this" is the first question a reader has and it was not
answerable from the trade record alone.

**I have not established what triggered that run**, and I am not guessing. What
is established: it was `run_type=live`, `broker_mode=alpaca`, `BULL_CALM`,
`buy_blocked=false`, and it placed two orders at ~3.5× the sizing target.

## Why this matters more than the number

The largest position in the book — **23.5 % of a $10.9k live account** — is one
the model's own sizing did not choose. That reframes the operator's other
question, *"新模型要不要改一下持仓?"*: **the book is not currently expressing the
model's sizing**, so a model change cannot be evaluated against it either.

## What lands

`ops/renquant104/position_cap_conformance.py` — read-only. For every LIVE buy it
compares the recorded `target_pct` against the regime's declared
`max_position_pct` and the Kelly target that was stamped alongside it.

Silence is never read as compliance. Each way the answer can be unknown is its
own **actionable** state, and none of them defaults to "within limits":

| state | means |
|---|---|
| `WITHIN_CAP` | target ≤ the declared cap |
| `OVER_REGIME_CAP` | the breach |
| `NO_CAP_DECLARED_FOR_REGIME` | the config is silent for that regime — **inventing a cap here is the failure this file exists to catch one level up** |
| `REGIME_NOT_RECORDED` | the row cannot be judged |
| `TARGET_PCT_NOT_RECORDED` | same |

Simulation rows (no `trade_date`) are excluded — with 250 sim `kelly_trim` rows
in the same table, mixing them would drown the live count.

## Not claimed

Not that 0.12 is the right cap, nor that Kelly is the right target. This
compares **what was done** against **what the deployed config says** — a config
the book is supposed to be expressing.

I have **not** established *why* the 07-28 sizing overrode both. That is the
next measurement, and I am not proposing a fix to a mechanism I have not yet
found.

Suites: 13 tests, incl. the live-bound one pinning 2-of-33 and the ~3.8× ratio ·
full suite green.
