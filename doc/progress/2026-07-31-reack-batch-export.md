# The batch-export ack described a failure that is no longer the failure

**Date:** 2026-07-31 · `renquant-orchestrator` · GOAL-1

STATUS:    one ack re-dispositioned, 3 tests (1 retargeted + 2 new). No code change.
WHAT:      `com.renquant.rq105-batch-scores-export`'s ack expired 2026-07-20 carrying a
           diagnosis of a DIFFERENT failure. Replaced with the measured current cause,
           a fresh `acked_at`, and an explicit `expires_at` that does not rejoin the cliff.
WHY/DIR:   GOAL-1. An ack is only worth its diagnosis; a stale one is worse than none,
           because it tells the next reader to stop looking.

EVIDENCE:  §4(b) block. Model-specific fields filled and marked.

```
artifact:      ops/renquant104/sentinel_acks.json
               (key com.renquant.rq105-batch-scores-export)
prod or exp:   prod — read by com.renquant.rq104-degradation-sentinel on every firing
existing data: sentinel run --as-of 2026-07-30: 10 jobs LOUD, 4 INFO. This job was LOUD
               with "[ACK EXPIRED: expired 10d ago, by date in clears_when (2026-07-20)]".
               Its stored reason described the Class-A absolute row floor, replaced by
               health-evidence contract #531, with a manual export that succeeded 5/5.
               The CURRENT failure text is different:
                 "run 2026-07-29-live-a68df3f8 fails class-A health evidence:
                  full_buy_run(pipeline_flags) — a frozen vector must come from a
                  contract-clean, full-buy-funnel run with training provenance;
                  refusing to export"
               [VERIFIED — logs/rq105/batch_scores_export_2026-07-30.log, this session]
best-known?:   NOT APPLICABLE as a model-variant comparison — no model, no score.
               As a disposition: this is the only diagnosis supported by the session
               record; the alternative (a 105 defect) is contradicted by the pairing
               logger being alive and writing 0 rows for want of pairs.
scope:         "this is sentinel_acks.json, PROD, one entry's text plus dates; it changes
               no job, no trading behaviour, and no code — only which sentence the
               operator reads next to this alarm, and when it returns."
```

NEXT:      The other two long-expired acks (`daily104`, `weekly-retrain-patchtst`) and
           `shadow-ab-daily` still need dispositions. Deliberately NOT in this PR — see §3.

## 1. The measured cause

The export refuses **by design**, and the precondition is right. It has been satisfiable
**once in nine sessions** `[VERIFIED — logs/daily_104/2026-07-2*.log]`:

| date | verdict | buys | fired |
|---|---|---:|---|
| 07-20 | ECONOMIC_TRADE | 2 | — |
| 07-23 / 07-24 / 07-28 / 07-29 | **STRUCTURAL_BLOCK** | **0** | **`['wash_sale_mass_block']`** |
| 07-30 | ECONOMIC_NO_TRADE | 0 | — |

So this is **not a 105 defect**. The export is starved by the 104 buy-side block, and
`intraday_pairing_logger` shows the same shape — `sessions 0, admitted pairs 0, rows
written 0` — on a day the entry-timing shadow wrote **580** rows, so the logger is alive
and simply has nothing to pair.

## 2. The new ack does three things the old one did not

- names a **falsifiable clearing condition**: `strategy-104#73` merged **and** pinned
  **and** one clean full-buy session afterwards;
- says what to do if the fix lands and the job still fails — **"this ack is WRONG and
  must be removed, not renewed"**;
- carries an explicit **`expires_at: 2026-08-14`** instead of inheriting the blanket
  14-day window, so it does **not** rejoin the 2026-07-31 cliff of six.

Expiry distribution after this change `[VERIFIED — sentinel's own `ack_expiry`]`:
`2026-07-20: 3` · `2026-07-31: 6` · `2026-08-14: 1`.

## 3. What is deliberately NOT done

**`com.renquant.shadow-ab-daily` is left LOUD.** Its last exit is **3** — the sentinel's
own **crash** code — and I could not locate its log. **An undiagnosed crash must not be
acked.** Acking it would be exactly the failure the ledger exists to prevent, and it is
the reason this PR touches one entry rather than clearing the board.

## 4. The retargeted test, argued

`test_the_committed_ledger_has_exactly_four_expired_acks_on_2026_07_30` pinned the count
at **4**. This change makes it **3**, legitimately — one ack was re-dispositioned, not
renewed to silence it.

The test is renamed and its docstring records the 4→3 move **and why**, keeps the
property it existed for (every remaining expired ack dies by a date in its **own**
`clears_when`, not the blanket window), and adds the line that matters for the future:
*if a later edit drops the count to 0 by renewing acks rather than fixing jobs, that is
what this test should be read against.*

Two new tests: the `expires_at` must **win** over the age window (else a considered
review date silently inherits a blanket one), and the `clears_when` must name a
falsifiable condition.

67 tests pass across the two ack test files.
