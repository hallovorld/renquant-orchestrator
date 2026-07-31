# An ack acknowledges a diagnosis, not a job label

**Date:** 2026-07-30 · GOAL-1 (shadow reliability gates), issue #622 · orchestrator

**Bottom line:** the ack ledger matched on **job name only**
`[VERIFIED — `acks.get(name)`, rq104_degradation_sentinel.py]`, so a job that starts
failing a **different way** stayed silenced by a note written about the old failure.
Live instance: `com.renquant.shadow-ab-daily` was acked for *"epoch-3 frozen manifest
vs 07-16/17 pin deployments"* and now exits **3**, not 1
`[VERIFIED — launchctl list, 2026-07-30]`.

## 1. What the ledger actually looked like

All 10 acks were stamped **2026-07-17** — 13 days old — and several named a clearing
date of **2026-07-20**, ten days past `[VERIFIED — sentinel_acks.json on origin/main]`.
Measuring each acked job's current `launchctl` exit code decided every case:

| acked job | measured exit | disposition |
|---|---:|---|
| `daily104` | **0** | ack removed — recovered |
| `monthly-meta-label-retrain` | **0** | ack removed — recovered |
| `rq104-liveness` | **0** | ack removed — recovered |
| `weekly-retrain-patchtst` | **0** | ack removed — recovered |
| `shadow-ab-daily` | **3** | ack removed — **code changed** |
| `conditional-retrain104` | 1 | kept, stamped `acked_exit_code: 1` |
| `retrain-panel104` | 1 | kept, stamped |
| `rq104-degradation-sentinel` | 1 | kept, stamped |
| `rq105-batch-scores-export` | 1 | kept, stamped |
| `weekly-wf-promote` | 1 | kept, stamped |

**Four acks were pure dead weight** — the job had recovered, and the only thing the
ack could still do was silence the *next* real failure.

**`shadow-ab-daily` was removed, not re-stamped.** Stamping `3` would re-acknowledge a
failure I have **not diagnosed**. The honest move is to let it alarm.

## 2. The fix

`acked_exit_code` is now part of the ack, and an ack suppresses only when the observed
code matches:

- **code matches** → INFO, as before, plus the existing expiry check
- **code differs** → `ACK DOES NOT APPLY: written for exit N, job now exits M`
- **no code recorded** → `ACK UNUSABLE` — a provenance gap is never a pass, so an ack
  that does not say *which* failure it acknowledges cannot be checked against the one
  happening now

The code check runs **before** the expiry check on purpose: a stale ack for a
*different* failure should report the mismatch, not merely that it aged out. The two
send the reader to different places, and there is a test pinning the ordering.

Every refusal quotes the original `reason`, matching the contract the expiry branch
already honours — the reader decides between fixing and re-acking without opening
the ledger.

## 3. An existing test caught the behaviour change

`test_acked_job_moves_to_info` failed, because its fixture had no `acked_exit_code`.
That is the test doing its job. The fixture was updated and the reason recorded in
its docstring — **not** deleted, and the contract was **not** softened to let it pass.

## 4. Suite

`tests/test_ack_names_the_exit_code.py` — 13 new tests, including the inverse-parser
round trip over 5 codes, an anti-vacuity control that a *matching* code still
suppresses, and two guards on the committed ledger itself (every ack records a code;
no ack claims exit 0). Sentinel suites together: **90 passed**
`[VERIFIED — pytest, this session]`.

## 5. Not addressed here

- `shadow-ab-daily`'s exit 3 now needs a real diagnosis. It will alarm until it gets
  one, which is the intended behaviour, not a regression.
- The five surviving acks keep their original clearing conditions; nothing here
  re-dates them.


---

## REBASED 2026-07-31 — the schema that landed first wins, and the default is the part worth keeping

While this branch sat, `main` shipped `ack_covers_exit` with **`acked_exit_codes` (a
list)**. That is strictly better than the scalar `acked_exit_code` proposed here: a job
can legitimately have two acked failure modes, and forcing one row per mode would split
a single diagnosis across two entries. **The list wins; this branch's scalar is
withdrawn**, along with the row-removal plan above — `main`'s ledger has moved on and
re-dispositioning ten live rows from a stale branch would be its own defect.

**What `main` did not do, and what survives from this branch: the default.**

> `ack_covers_exit` returned **True** when `acked_exit_codes` was absent — *"the
> behaviour all ten existing rows were reviewed under"*. **Nine of the ten rows had no
> declared code** `[VERIFIED — sentinel_acks.json on origin/main, 2026-07-31]`, so for
> nine jobs the check was inert: it passed because its subject was absent. That is the
> recurring shape this programme has now catalogued six times in a week.

Two changes, in the safe direction:

1. **Every row declares the code its DIAGNOSIS is about** — not the code observed today,
   which would silence whatever is happening now by construction. All ten are `[1]`.
2. **An ack with no declared codes is UNUSABLE** and stops suppressing, reported as
   itself rather than as an expiry. Because all ten now declare, the flip
   re-dispositions **nothing** on its own; it is a floor under the next ack somebody
   writes without one.

### The one row this makes loud, which is the finding

`com.renquant.shadow-ab-daily` is acked for an *"epoch-3 frozen manifest vs 07-16/17 pin
deployments"* diagnosis and exits **3** `[VERIFIED — launchctl list, 2026-07-31]`. Its
declared code is `[1]`, because that is what the diagnosis is about — so the row now
refuses to suppress, and the sentinel says why. **Declaring `[3]` instead would have
made the alarm go away by writing today's failure into yesterday's note**, which is
exactly the defect this branch exists to close.

### Test fallout, and why each one moving is correct

| test | why it changed |
|---|---|
| `test_an_ack_without_the_key_still_covers_everything` | **inverted** and renamed — it asserted the default being removed |
| 3 in `test_ack_expiry.py` | their fixtures passed a bare label, so `parse_exit_code` read `None` and the ack refused before reaching the expiry branch under test. The helper now formats `(last exit N)` as the real producer does |
| `TestAckLedger::test_acked_job_moves_to_info` | fixture gained a declared code |
| new: `test_a_missing_CODE_refuses_before_the_missing_DATE_is_reached` | pairs with the expiry test so the two refusals stay distinguishable |
| new: `test_TWO_acked_codes_both_suppress_and_a_third_does_not` | the property that made the list worth adopting over the scalar |
