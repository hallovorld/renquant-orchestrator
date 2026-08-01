# PatchTST lane: the governance handoff, merit removed (GOAL-5)

## What changed after review

`[codex on orch#731]`: *"limb A is correctly an orchestrator-owned compliance record, but
limb B is neither frozen nor owned here … those choices can determine the verdict, so
delegating them after recording comparator means is not a preregistered decision rule."*

Accepted in full. The merit half is **deleted from this repo**, not rewritten:

* the null, the dependence correction, the calibration criteria and the test level were
  all deferred to a future model-side method — any of which can determine the verdict;
* worse, the removed draft recorded the co-committed arms' means **before** those choices
  were made, which is a HARKing surface I created rather than closed.

What remains here is the deterministic compliance record and the operator handoff, which
is what this repo owns.

## Facts unchanged

Staleness **625 d** vs the **28 d** `STALENESS_MAX_DAYS` limit (≈ **22×**); the weekly
retrain **has not acted on 4 consecutive runs**, 3 of them crashes. `[本次实测 2026-08-01]`
The 28-vs-30 ambiguity is recorded in the design doc: the config's `max_age_days: 30`
belongs to `.panel_ltr.asset_embeddings`, a different (and disabled) object.

## Follow-up, elsewhere

The complete merit preregistration — method, calibration acceptance criteria, α, failure
handling, committed-series provenance — belongs in `renquant-model` and is being filed
there. This document links to it and asserts nothing about it.

Docs only. No code, no config, no production surface touched.
