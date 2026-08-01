# ack ledger: a narrative-only `clears_when` is now a finding (GOAL-1)

## What landed

`classify_clears_when()` in `ops/renquant104/ack_ledger_audit.py`: every ack's clearing
condition is bucketed — ISO date (the sentinel's own extractor already acts on these),
repo-qualified PR/issue reference, testable key/path token, or bare `#NN`. Two new
findings: a **stated** condition with no machine-bindable fragment ("narrative-only"),
and a bare `#NN` with no repo qualifier ("unresolvable as written"). Classification
only — nothing queries GitHub or the filesystem to CHECK a condition, because an audit
that needs the network is an audit that silently stops running.

## Why

Surveyed 2026-08-01 (orch#733): only **4 of 10** live acks carry any fragment a checker
could bind to, and **6 of the 9 expired** rows expired purely via the `acked_at + 14d`
backstop — their `clears_when` never participated. A clearing condition nobody can
evaluate is a promise that cannot clear or hold the ack it decorates; until now that
state was an invisible default.

Live run `[本次实测]`: 6 narrative-only findings (conditional-retrain104,
monthly-meta-label-retrain, retrain-panel104, rq104-degradation-sentinel, rq104-liveness,
weekly-wf-promote) + 1 bare-ref finding (`#75`, which matches unrelated merged PRs in
three repos and nothing in strategy-104).

## Two judgement calls, stated

* **An ABSENT `clears_when` is not a finding.** A row that promised nothing is governed
  by the backstop, visibly; the finding is for a stated condition no machine can bind to.
* **rq105-batch-scores-export contains both** `renquant-strategy-104#73` and a later bare
  "#73" — the bucket records the bare ref, the finding's qualified-ref guard keeps it
  quiet. A test pins this.

## Fixture change, disclosed

The test fixtures' default `clears_when` was the narrative string "some condition"; under
the new finding a "clean ledger" fixture was no longer clean. The default is now a
qualified-ref clause (feeding no date into `ack_expiry`, so fixture expiries are
untouched), and narrative-only fixtures opt in explicitly. This redefines "clean" to
include machine-checkability — deliberate, and the reviewer should weigh it.

Tests: 7 added (buckets, bare-vs-qualified, parity with the sentinel's date extractor on
every live row, live-ledger pins). File suite: 28 passed.
