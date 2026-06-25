# Postmortem + RFC — model fixes can't reach production (the disabled-flag graveyard)

2026-06-24. A systemic failure, raised by the operator: *"mu 做好了但是不能进 daily full —
这是一个系统问题。"* The mu fix is done but cannot reach daily-full. This document is the
reckoning and the proposed structural fix. It is not a single bug report — it names a
pattern and proposes to end it.

## The failure (lead with it)
**Correct, deployed model fixes have ZERO effect on daily-full.** They ship `default-OFF`,
behind a config flag, and are never turned on — so the live run's orders are identical
with or without them. The pipeline produces a one-way street to a graveyard of disabled
flags.

Exhibits:
- **`demean_cross_sectional` (mu intercept fix, pipeline #145)** — researched (#183),
  built, DEPLOYED in the live pin since 2026-06-23, and **dark** (`strategy_config` still
  has bare `mu_floor: 0.03`, no demean key). Zero live effect for a fix that is
  first-principles correct (Grinold cross-sectional standardization removes the +0.0245
  intercept that defeats the conviction gate by construction).
- **BULL_CALM momentum guard (#187)** — designed, default-OFF + WARN-first, gated on an
  "admitted-set validation" that has no data path → will sit dark indefinitely.
- The same shape recurs across guards (data-integrity #143, regime gates, etc.): merged,
  deployed, dark.

## How the author made it worse (process honesty)
This is part of the evidence, not a footnote:
- I treated **"PR merged / pin deployed" as progress** when the change had no live effect.
  Motion (artifacts produced) was optimized over impact (daily-full behaviour changed).
- I burned a cycle on a **proxy mu-validation that was inconclusive AND unfaithful** — a
  surrogate XGB can't reproduce the live scorer's +0.607 vol-tilt, the exact failure mode
  demean targets. I should have seen upfront it couldn't answer the question.
- I edited `decision_trace.py` and wrote a test that **imported the other copy** of the
  function (`kernel.decision_trace`, which already carried `mu`) — so the test never
  exercised my edit to the top-level builder the live runtime actually uses. Not grounded.

These are symptoms of the same disease: producing dark, unvalidated, or untested work
instead of closing the loop to live impact.

## Root causes
1. **No shadow / WARN execution wired into daily-full.** A gate change is binary: it either
   changes live orders or does nothing. There is no "run it every day, log what it WOULD
   admit, change no orders" mode actually exercised in the daily run.
2. **No accumulating decision-ledger.** daily-full does not persist the per-name history
   (`raw`, `mu`, `regime`, admission verdicts) needed to ever validate a change. The live
   decision trace did not even record `mu` (the top-level builder the live bundle uses
   omitted `expected_return`), and only ~2 sparse per-run JSONs exist. So the validation
   data is never collected → the validation can never run → the flag never flips.
3. **Enable is a manual, faith-based config edit** gated on a validation that (per #1, #2)
   is impossible. Result: permanent OFF.

## RFC — the structural fix (one mechanism, not more dark guards)
Make daily-full **shadow-run** the candidate gates every day and **persist a per-name
decision-ledger**:

1. **Live trace carries the gated quantity.** Add `expected_return` (mu) to the live
   decision-trace row (the top-level builder). [implemented — pipeline `feat/decision-trace-mu`]
2. **Append-only ledger sink.** Each daily-full appends the per-name decision rows to a
   durable `decision_ledger.parquet` keyed by `(as_of, ticker)` — accumulating history
   across runs, not sparse per-run JSON.
3. **Shadow-gate computation.** In the same run that emits the real orders, also compute —
   without changing any order — what each candidate gate (demean mu-floor, momentum
   percentile) WOULD admit/veto, and record it per name (`live_admitted`,
   `shadow_demean_admitted`, `shadow_momentum_admitted`, the values behind each).
4. **Periodic validation report.** After a short window, join the ledger to realized
   forward returns and compare shadow-admitted vs live-admitted outcomes per regime —
   a data-backed answer to "should we flip the flag", emitted as an alert.
5. **Enable with evidence.** The strategy-104 flip becomes a data-backed decision, not faith.

Outcome: the fix is **exercised live daily**, evidence **accumulates automatically**, and
enabling is **earned by data**. This single mechanism subsumes the mu validation, the
momentum-guard validation, and the missing ledger.

## What we STOP doing
- Shipping a `default-OFF` model change and calling it progress. A model change is "done"
  only when it is either live, or running in shadow with a ledger accruing the evidence to
  make it live. Deployed-but-dark is **not** done.
- Producing research/validation that doesn't close the loop (proxies that can't answer,
  tests that don't exercise the change).

## Status / next
- Phase 1 (mu in live trace) — implemented (`feat/decision-trace-mu`), test being corrected
  to import the live (top-level) builder.
- Phases 2–4 — the ledger sink + shadow-gate + validation report — are the next focused
  build. No further default-OFF model guards until this loop exists.
