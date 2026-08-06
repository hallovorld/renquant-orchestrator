# 2026-08-05 — P0 SOLVED: the umbrella's sizing twin has the fallback but not its clamp

STATUS:   delivered (root cause + probes delivered; the umbrella fix itself is a one-line
          umbrella-repo change, repo boundary, not actioned here).
WHAT:     root-causes the umbrella's `compute_position_size` twin (used by live `live.runner`)
          missing the post-fallback clamp that landed in the pinned pipeline copy 2026-07-03
          (`6de6219`) — any candidate sized under one share falls back to 25% of portfolio
          uncapped; ships `sizing_twin_conformance.py` (fails on any divergence, 11 tests) and
          `kernel_surface_census.py` (classifies all 39 launchd jobs by bridge-vs-direct kernel path).
WHY/DIR:  P0 twin-implementation defect (GOAL-3, orch#833) — corrects an earlier overstated
          severity (no oversized order has ever reached the broker) and closes the attribution gap
          (the 07-28 run went through the pinned bridge, not the stale umbrella copy) by reading
          the log, not by inference; names the wider finding that 120 of 169 shared umbrella/pinned
          kernel files have diverged — sizing.py is one instance of systemic staleness, not an
          outlier.
EVIDENCE: reproduced 7/7 live/dry-run sizing rows through the umbrella copy (exact match to
          recorded `buy_pending` sizes; the pinned copy returns 0 for the same inputs); against
          `data/runs.alpaca.db`, 45/63 `buy_pending` rows never reached the broker and the max
          `target_pct` that DID reach the broker is 9.06% (inside the BULL_CALM cap); over an
          864-case grid, 191 divergent (always umbrella-larger), worst notional gap $24,940;
          classified all 39 launchd jobs — exactly 1 (`com.renquant.rq104-dawn-preflight`) reaches
          the stale umbrella kernel directly, and it places nothing. `[VERIFIED — this session,
          7/7 reproduction + 864-case grid + 39-job launchd classification this session]`
          artifact:      `RenQuant/backtesting/renquant_104/kernel/sizing.py` (umbrella) vs. its pinned pipeline counterpart, both read this session
          prod or exp:   prod — the umbrella copy is the one `live.runner` imports; `data/runs.alpaca.db` is the live order record
          existing data: `data/runs.alpaca.db`'s full `buy_pending` history (63 rows) and `ops/launchd_manifest.json`'s 39 jobs
          best-known?:   n/a — this compares two code copies for a bug, not two model variants for skill
          scope:         "this is the umbrella's own sizing code, prod, vs. its pinned pipeline twin — no model skill claim is made"
NEXT:     the fix is one line in the umbrella (`RenQuant/backtesting/renquant_104/kernel/sizing.py`)
          — port `6de6219`'s clamp, or delete the twin and import the pipeline's; this repo does
          not write to the umbrella so it is not actioned here. The wider 120-file divergence
          (GOAL-3, orch#833) needs its own remediation plan.

## Root cause

`compute_position_size` exists **twice**:

| copy | used by | has the 25 % fallback | has the clamp |
|---|---|---|---|
| `RenQuant/backtesting/renquant_104/kernel/sizing.py` | **`live.runner` — the live book** | ✅ | ❌ |
| `renquant-pipeline/.../kernel/sizing.py` | the reviewed pipeline | ✅ | ✅ |

Both contain an **oversize fallback**: when the sized target buys less than one
whole share, try `0.25 * portfolio_value` instead. The pipeline copy then puts
it back under the cap:

```python
cap_shares = int(target_dollars / price)
if shares > cap_shares:
    shares = cap_shares          # -> 0 when the target is sub-one-share
```

The clamp landed in the pipeline on **2026-07-03 (`6de6219`)**. **The umbrella
twin never received it** `[VERIFIED — the string `cap_shares` does not appear in
that file]`.

## Consequence

Any candidate whose target buys **less than one share** is silently allocated
**25 % of the portfolio** — regime cap, Kelly target, conviction and σ all
bypassed.

And the trigger is **inverted with respect to conviction**: the weaker the
candidate, the smaller its target, the more likely it falls under one share —
so **the weakest candidates receive the largest positions.**

## Reproduced 7 / 7 `[VERIFIED — this session]`

Feeding the umbrella copy the inputs recorded on each `buy_pending` row:

| date | name | umbrella copy says | recorded size | reached the broker? |
|---|---|---|---|---|
| 07-28 live db | TSLA | **8** (23.4 %) | **8** ✓ | **NO** — `broker_order_id` is NULL |
| 07-28 live db | EME | **3** (21.1 %) | **3** ✓ | **NO** — `broker_order_id` is NULL |
| 07-28 live db | SPG | **1** (2.2 %) | **1** ✓ | **NO** — `broker_order_id` is NULL |
| 08-03 dry-run | AMZN | **9** (22.7 %) | **9** ✓ | n/a (dry) |
| 08-03 dry-run | MRK | **20** (24.2 %) | **20** ✓ | n/a (dry) |
| 08-03 dry-run | PYPL | **47** (25.0 %) | **47** ✓ | n/a (dry) |
| 08-03 dry-run | GOOG | **1** (3.3 %) | **1** ✓ | n/a (dry) |

The **same inputs through the pinned copy** give `0, 0, 1 / 0, 0, 0, 1`.

**That is why five rounds of reproduction failed: I was running the fixed twin.**
Every "impossible" result was correct — about the wrong file.

SPG is the control: its target bought a whole share, the fallback never fired,
and **both copies agree on 1**.

### CORRECTION — I called these "placed live orders". They were not. `[VERIFIED]`

An earlier revision of this doc headed the last column **"actually placed"**. That
was wrong, and it made the P0 read one category more severe than the evidence
supports. Measured against `data/runs.alpaca.db`:

| | |
|---|---:|
| `buy_pending` rows, all time | 63 |
| …that carry a `broker_order_id` | **18** |
| …that never reached the broker | **45** |
| **max `target_pct` that DID reach the broker** | **9.06 %** (FTNT, 07-16) |
| max `target_pct` among rows that never did | 23.41 % (TSLA, 07-28) |

**Every oversized row died before the broker** — TSLA 23.41 %, LLY 22.00 %,
LLY 21.53 %, EME 21.09 %. The largest position this defect has ever actually
placed is **9.06 %**, inside the 12 % BULL_CALM cap.

Corroborating, from the run logs: the 07-28 daily run resolved
`no trade (risk_gate_vol_dropped(29))` with a `wash_sale_mass_block`
`FunnelIntegrityAlert`, and it dispatched through **`daily-bridge` registered
under `.subrepo_runtime`** — i.e. the **pinned** kernel. The only 07-28 rows with
a real `broker_order_id` are two SPG **sells**.

So the honest statement of this P0 is:

- the two copies diverge — **proven**, 191/864;
- the umbrella copy computes 21–25 % positions — **proven**;
- **the umbrella copy has never placed an oversized order at the broker** —
  measured, and it is the reason this is a latent defect and not an incident.

What remains load-bearing: something downstream is absorbing these, and *that*
is unidentified. A defect that only survives because an unrelated gate happens to
fire first is not contained — it is **unexploded**. But it has not gone off, and
saying it did would have been a fabrication in the direction of my own thesis.

## Scope of the divergence

Over an 864-case grid `[VERIFIED]`: **191 divergent**, worst notional gap
**$24,940**, largest umbrella allocation **24.9 % of portfolio value**. In every
divergent case the umbrella sizes **larger** — the defect has one direction, and
a test pins that so a reverse divergence cannot be folded silently into this
record.

## What lands here, and what does NOT

`ops/renquant104/sizing_twin_conformance.py` — compares the two implementations
over the grid and **fails on any divergence**. Plus 11 tests, including each
live order reproduced by name, the pinned copy refusing them, and an assertion
on the *source* that the clamp is present in one file and absent in the other.

**The fix itself is one line in the umbrella**, and this repo does not write to
the umbrella. The exact change:

```python
# RenQuant/backtesting/renquant_104/kernel/sizing.py, after the MIN-1-SHARE block
cap_shares = int(target_dollars / price)
if shares > cap_shares:
    shares = cap_shares
if shares < 1:
    return 0.0, 0
```

i.e. **port `6de6219` into the twin** — or better, delete the twin and import
the pipeline's. The twin is the disease; the missing clamp is only this
instance of it.

## SCOPING — which runs reach the broken twin, and one thing I have NOT established

Checked before letting this claim stand `[VERIFIED]`:

- **The multirepo bridge aliases `kernel.<stem>` → `renquant_pipeline.kernel.<stem>`**
  (`live_bridge.py:298-305`). So every job that goes through
  `-m renquant_orchestrator daily-bridge` / `live-bridge` executes the
  **PINNED** copy — the one *with* the clamp. `daily_104.sh` and
  `intraday_sell_104.sh` both take that path by default
  (`RQ_DAILY_RUNNER=multirepo`).
- **`dawn_funnel_preflight.sh` calls `-m live.runner` DIRECTLY**, with no
  bridge. That run imports the **umbrella** kernel — which is why the preflight
  reproduces the oversizing every day, and why it is a safe place to observe it.

### The attribution gap is now CLOSED — by reading the log, not by inference `[VERIFIED]`

An earlier revision left this open: *"which of the two surfaces the run that
placed the 2026-07-28 orders was using."* It is answerable, and the answer did
not need the twin evidence at all — `logs/daily_104/2026-07-28.log:24-25` records
the dispatch:

```
ok   renquant_orchestrator live-bridge  [registered under …/.subrepo_runtime/repos/renquant-orchestrator/src]
ok   renquant_orchestrator daily-bridge [registered under …/.subrepo_runtime/repos/renquant-orchestrator/src]
```

**The 07-28 run went through the bridge — the PINNED, clamped kernel** — and it
resolved `no trade`. It placed no buys at all. `RQ_DAILY_RUNNER` is set in no
LaunchAgent plist and in no manifest `environment` block, so the `umbrella`
fallback has never been armed on this machine.

I had the twin reproducing 7/7 and let that stand in for an answer for a whole
round. The dispatch line was in the first 25 lines of the log the entire time.
**Reproducing a defect tells you what a file does; it does not tell you what ran.**

### Which surfaces DO reach the stale kernel `[VERIFIED — all 39 launchd jobs]`

Classifying every job in `ops/launchd_manifest.json` by whether its wrapper goes
through the bridge or invokes `-m live.runner` directly:

| kernel surface | jobs |
|---|---:|
| bridge → **pinned** kernel (`daily104`, `intraday104`) | 2 |
| **direct → umbrella (stale) kernel** | **1** — `com.renquant.rq104-dawn-preflight` |
| no `live.runner` at all | 36 |

**Exactly one scheduled job runs the stale kernel, and it is a preflight that
places nothing.** That is the whole live exposure of a 120-file divergence today
— which is good news, and is also precisely why the divergence has been able to
grow to 120 files unnoticed.

## The wider finding

This is the **twin-implementation** defect (GOAL-3, orch#833), and `sizing.py`
is not an outlier — it is one of **120**.

Comparing every file under `RenQuant/backtesting/renquant_104/kernel/` with its
pinned counterpart `[VERIFIED — this session]`:

| | count |
|---|---:|
| umbrella kernel `.py` files | 218 |
| …with a pinned counterpart | 169 |
| **byte-identical** | **49** |
| **DIVERGED** | **120** |
| umbrella-only (no counterpart) | 49 |

The gaps are not cosmetic:

```
pipeline/task_selection.py    umbrella  341L   pinned 1002L   (-661)
kernel/sizing.py              umbrella  187L   pinned  468L   (-281)
panel_pipeline/job_panel_scoring.py
                              umbrella 1099L   pinned 4350L   (-3251)
portfolio_qp/allocator_replay.py
                              umbrella  307L   pinned 1296L   (-989)
```

**Only 49 of 169 shared files agree.** The sizing clamp is one missing fix among
a systematically stale copy — and any job that bypasses the bridge runs all of
it.

Suites: 11 tests · full suite green.

---

# RETRACTION — the severity correction above is WRONG. Two oversized orders FILLED. `[VERIFIED 2026-08-06]`

## What I claimed, and what is true

The section headed *"CORRECTION — I called these 'placed live orders'. They were
not"* concluded:

> **Every oversized row died before the broker** … The largest position this
> defect has ever actually placed is **9.06 %**, inside the 12 % BULL_CALM cap.

**That is false.** Measured directly against Alpaca's filled-order history:

```
broker : TSLA buy qty=8 @ $306.52  FILLED 2026-07-28 17:45:47  order_id ea3055f1
broker : EME  buy qty=3 @ $704.25  FILLED 2026-07-28
```

| | |
|---|---:|
| `buy_pending` rows over the 12 % BULL_CALM cap | 4 |
| **of those, ACTUALLY FILLED at the broker** | **2** |
| TSLA | **23.41 % → filled, $2,452** |
| EME | **21.09 % → filled, $2,113** |

**TSLA is 23.6 % of the live book right now** — roughly **2× its per-name cap**.
The defect did not stay latent. It placed, it filled, and the position is open.

## The error, exactly

I derived "never reached the broker" from `broker_order_id IS NULL`. That column
does not mean *not placed*; it means *the row never got the id stamped onto it*.

It is worse than unpopulated — it is **anti-correlated with reality** here:

| row | `broker_order_id` | actually filled? |
|---|---|---|
| FTNT 9.06 % | **SET** | **no** |
| APH 8.63 % | **SET** | **no** |
| AVGO 7.04 % | **SET** | **no** |
| **TSLA 23.41 %** | **NULL** | **YES** |
| **EME 21.09 %** | **NULL** | **YES** |

So the very column I used to *downgrade* the severity is the one that points the
wrong way. Every conclusion in the retracted section that rests on it is void.

## Why this happened, and it is a lesson already in my ledger

This repo already records *"a zero from an unpopulated column reads like a
measurement"*, and separately that **the `trades` table is not a position
ledger** (established later the same session, in orch#866, when a holdings
reconstruction from that table produced 18 names against a live 10).

I applied the second lesson to holdings and never went back to re-examine the
severity claim I had built on the same table hours earlier. **The broker is the
only authority for what was placed; the DB is a record of what was intended.**

## Standing conclusions, re-stated

| claim | status |
|---|---|
| the two `sizing.py` copies diverge (191/864) | **stands** |
| the umbrella copy lacks the `cap_shares` clamp | **stands** |
| the 07-28 daily run dispatched through the PINNED bridge | **stands** |
| *"no oversized order ever reached the broker"* | **RETRACTED — 2 filled** |
| *"max placed position is 9.06 %"* | **RETRACTED — it is 23.41 %** |

The scoping section's open question — *which surface placed the 07-28 orders* —
becomes materially more important, not less: something placed two positions at
~2× the per-name cap, and the pinned clamp should have refused both.
