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

## 4. The emitted size bears no relation to the computed target

`SizeAndEmitTask` derives the position weight as
`max_pct = kelly_target_pct × conviction × sigma_mult` (Plan C, kelly_sizing on).
All three factors are stamped on the trade row, so the intended size is
recoverable exactly `[推导 from VERIFIED stamps]`:

```
portfolio_value          $10,565.46      (= invest / target_pct)
max_pct = 0.061255 × 0.5753 × 0.6591  =  0.023229   → 2.32 %
intended notional        $245.43
intended shares @ $309.22 = 0.794       → floors to 0
ACTUAL                    8 shares / $2,473.76 = 23.41 %
                          ratio realized / intended = 10.1×
```

EME is the same shape: intended `$245.43` → **0.330 shares → 0**; actual
**3 shares / $2,228.19 = 21.09 %**, ratio **9.1×**.

So it is not that the cap was raised, or Kelly ignored, or confidence
mis-scaled. **On that run the emitted share count bears no relation to the
computed target at all** — the intended order was *less than one share*, twice,
and eight and three shares were emitted.

### Ruled out this pass, so the next reader does not re-walk them

- **not** the `bear_only` `override_pct` path — `bear_only=false`, and that is
  the only caller that passes `override_pct`;
- **not** a top-up on an existing position — both rows are the ticker's ONLY
  live row, both `source_task=SizeAndEmitTask`, `source_job=SelectionJob`;
- **not** the QP path — `qp_target_w` / `qp_delta_w` / `qp_status` all NULL;
- **not** the Deployment Governor — `enabled=false` in the pinned config.

## 5. Reproduced: the sizing function CANNOT emit those orders

I said the settling test was to re-run the sizing against the recorded inputs.
Done, against the **pinned** pipeline's own `compute_position_size`:

```
max_pct = 0.06125511 × 0.5753494 × 0.6591158 = 0.02322928
PV = $10,565.46 (stamped)   → TSLA 0 shares, EME 0 shares
```

**Zero, at every cash level tried ($2.5k / $5k / $6.9k / $10.6k), integer and
fractional.** It is arithmetically impossible for this path, with these factors
and this portfolio value, to emit 8 and 3 shares.

### Solving for the portfolio value that DOES explain them

Integer flooring turns each order into a band on `portfolio_value`
`[推导 — exact arithmetic on the VERIFIED stamps]`:

| order | PV that floors to exactly that many shares |
|---|---|
| TSLA 8 shares | `[$106,493, $119,805)` |
| EME 3 shares | `[$95,922, $127,895)` |
| **both** | **`[$106,493, $119,805)`** |

A single portfolio value in that band explains **both orders exactly**. The
stamped PV is **$10,565.46** — the band is **10.1× to 11.3×** it.

**And the tidy story is wrong**: the config carries `initial_cash = 100000`,
which would be the obvious culprit — but **$100,000 is NOT in the band**
(it gives TSLA **7** shares, not 8; EME 3, which matches). So `initial_cash`
alone does not explain it, and I am not rounding a near-miss into a match.

## 6. The broker's own record REFUTES the portfolio-value hypothesis

I went to Alpaca's order history for that day. The orders are real, filled, and
there is a **third one in the same second** that I had not been looking at
`[VERIFIED — Alpaca /v2/orders, 2026-07-28]`:

```
17:45:47  buy TSLA  qty=8  filled 8 @ 306.5236
17:45:48  buy EME   qty=3  filled 3 @ 704.2550
17:45:48  buy SPG   qty=1  filled 1 @ 237.5200
```

Against the one intended notional of **$245.43**:

| name | fill px | intended shares | floors to | ACTUAL | actual $ | × target |
|---|---:|---:|---:|---:|---:|---:|
| SPG | 237.52 | 1.033 | **1** | **1** | $237.52 | **1.0×** |
| TSLA | 306.52 | 0.801 | **0** | **8** | $2,452.19 | **10.0×** |
| EME | 704.25 | 0.348 | **0** | **3** | $2,112.76 | **8.6×** |

**A 10× portfolio value would have made SPG ~10 shares too. It made exactly 1 —
its correct size.** So the portfolio value was fine, and my inference in §5 is
**refuted by a control that was sitting in the same second of the same run.**

### The actual pattern

The two names that got ~10× are **exactly the two whose intended share count
floored to ZERO** (0.801 and 0.348). The one that floored to a legitimate 1 got
exactly 1.

So this is not a scaling error. **It is the sub-one-share path** — the names
integer flooring would have dropped are the ones that came back oversized. That
is the same sub-one-share arithmetic already logged as a deployment blocker
(orch#608 / pipeline#224), but with the opposite sign: there it silently
dropped names, here it silently multiplied two of them by ~10.

## 7. Bounded exactly: two names were sized with 10× the position cap

Integer flooring bounds the **effective** `max_pct` each order must have used
`[推导 — exact arithmetic on VERIFIED fills]`:

| name | shares | effective `max_pct` must lie in |
|---|---:|---|
| SPG | 1 | `[0.0225, 0.0450)` |
| TSLA | 8 | `[0.2321, 0.2611)` |
| EME | 3 | `[0.2000, 0.2666)` |

The computed value is `max_pct = 0.06126 × 0.5753 × 0.6591 = 0.02323`.

- **SPG's band contains 0.02323** → it used the correct value.
- **TSLA's and EME's bands both contain 0.2323 = 10 × 0.02323** — and nothing
  else nearby.

Stated the other way: TSLA's fill implies `conviction × sigma_mult = 3.79`,
while the row stamps **0.379**. **Exactly ten times**, on two of three names, in
one cycle.

### Every branch in `task_selection.py` is now excluded

| branch | why it cannot be it |
|---|---|
| normal Kelly path | returns **0 shares** at these inputs (reproduced) |
| one-share floor rescue | `sizing.one_share_floor_enabled = **false**` in the pinned config — and it emits literally `1` share |
| bear defensive sleeve | `bear_only = false` |
| legacy non-Kelly branch | `0.12 × conv × σ = 0.0455` → TSLA **1** share |

And the deployed file is the one I read: the pinned runtime's
`task_selection.py` is **byte-identical** to my checkout's `[VERIFIED — diff]`.

### The provenance stamp is provably NOT unique

The rows say `source_task = SizeAndEmitTask`, and no branch of
`SizeAndEmitTask` can produce those two orders. So I looked for a second writer
of that string, and there is one `[VERIFIED]`:

```
kernel/pipeline/governor_sizing.py:548        source_task="SizeAndEmitTask",
```

A **different module**, with a **different sizing rule** (allocator target
weight, `max_step_per_session`, no `sigma_mult`), stamps the **same**
`source_task`. So the attribution on a live order **cannot** identify the code
that sized it — it is a string two sizers share. That is the same class of
defect as the twin `validate_order_attribution` finding in orch#833, arriving on
the money path.

### …and the governor is excluded too

`governor_sizing` stamps `"sigma_mult": None`. The TSLA and EME rows carry
`sigma_mult = 0.6591157812733786` `[VERIFIED]`. So the rows were **not** written
by the governor either — consistent with `deployment_governor.enabled = false`
in the pinned config.

So: **every emitter I can find is excluded, and the stamp that should have told
me which one it was is shared by two of them.** That is the honest state.

## 8. The instrumentation already exists — and it settles the `max_pct` question

I was about to propose recording the effective `max_pct` at the emit site. **It
is already recorded**, in `trades.decision_inputs_json` `[VERIFIED]`:

| name | recorded `max_pct` | conviction | sigma_mult | kelly_enabled | cash before |
|---|---:|---:|---:|---|---:|
| SPG | 0.02312497 | 0.3775 | — | true | — |
| TSLA | **0.02322928** | 0.5753 | 0.6591 | true | $9,162.85 |
| EME | **0.02437756** | 0.4040 | 0.9850 | true | $6,689.09 |

**`max_pct` was correct for all three.** ~2.3 % each — the Kelly path did its job.
So the cap was never raised, and my §7 phrasing ("sized with 10× the position
cap") is wrong: the cap that was *used* is on the record and it is right.

### Which revives the portfolio-value question, in a sharper form

With the **recorded** `max_pct`, each fill pins its own PV band exactly:

| name | shares | PV that yields exactly that count |
|---|---:|---|
| SPG | 1 | `[$10,271, $20,542)` ← **contains** the run's stamped $10,565 |
| TSLA | 8 | `[$105,565, $118,760)` ← does **not** |
| EME | 3 | `[$86,668, $115,558)` ← does **not** |

So within **one emit loop**, SPG sized off a portfolio value of ~$10.5 k while
TSLA and EME sized off ~$105–115 k. **Two different portfolio values for three
orders in the same cycle.**

My §6 refutation said a 10× PV would have made SPG 10 shares too. That is only
true if all three shared one PV — and the recorded `max_pct` values now show
they did not. **The refutation was right to kill the "the run's PV was 10×"
claim, and wrong to kill the PV direction entirely.**

### What is now established

- `max_pct` correct for all three — **not** a cap or Kelly failure;
- SPG consistent with the real book, TSLA and EME with a book ~10× larger;
- so the divergence is in the **portfolio value each name was sized against**,
  inside a single loop.

**Still not proposing a fix**, but the next read is now one line wide: what
`portfolio_value` does `compute_position_size` receive per iteration, and can it
change between candidates in the same loop.

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
