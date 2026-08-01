# GOAL-1 — the mirror of the vanishing lane: a lane the config declares and nobody watches

**Date:** 2026-08-01 · `renquant-orchestrator` · GOAL-1, shadow-reliability gates

## The gap

`orch#689` made a **vanishing** lane visible. Its mirror had no detector.

`watched_lanes()` is a **hardcoded 2-tuple** `[本次实测 2026-08-01]` — `hf_patchtst` and
the clf lane. A third lane added to the config's `shadow_models` is invisible: nothing
patrols it, and nothing says so. **Both silences look identical from outside**, which is
the whole failure class GOAL-1 exists for.

## The obvious fix is wrong, and it is pinned as wrong

Deriving `watched_lanes()` from the config would close this in one line — and would
**destroy `orch#689`**: a lane *removed* from the config would leave the watch list with
it, so the sentinel would stop looking for exactly the thing whose disappearance #689
detects.

**The declared set has to stay declared. What must become visible is the drift between
the two.** A test asserts, by AST, that `watched_lanes()` neither calls
`config_declared_lanes` nor names `shadow_models`.

## What this adds

`unwatched_config_lanes()` — config-declared lanes that **no** watched lane matches
(honouring the sentinel's own `hf_patchtst_<suffix>` rule, so a correctly-wired decorated
lane is not flagged). On a finding it prints, records, and alerts, telling the reader to
add the lane to `watched_lanes()` **deliberately**, with the reason the derived version is
refused.

**Measured on the live pinned config: 0 unwatched lanes.** Both declared lanes match. The
check exists for a state that does not hold today and stays quiet until it does — asserted
directly, so this cannot become a check that alarms on reality.

## A guard that alarmed on every existing deployment — caught by the existing suite

My first version treated a **missing** `--config` as *"could not check"* and alarmed. That
is the right instinct in general and wrong here: `--config` is **optional**, so the guard
turned every deployment without it into a permanent alarm. **16 tests in
`test_rq104_shadow_scorer_sentinel.py` failed, all `assert 8 == 0`.**

The split now made explicit:

| state | behaviour |
|---|---|
| `--config` **not supplied** | the check was **not requested** — quiet, and printed as *"skipped, not passed"* |
| `--config` supplied but **unreadable** | *"could not check"* — **alarms** |

A check nobody asked for must be quiet; a check that was asked for and could not run must
not be. Both directions are asserted in one test.

## Ways this could report false confidence, each covered

- A **malformed** `shadow_models` entry is reported **and** the readable lanes are still
  checked — a bad entry is not "one fewer lane", and skipping it silently is precisely how
  an unwatched lane stays unwatched.
- A **string** `ranking` / `panel_scoring` container does not crash: `(x or {}).get(...)`
  is not a guard, since a non-empty string is truthy. **Fourth tool in this repo to need
  that sentence.**
- A config with **no** `shadow_models` is legitimate, not a defect.
- A **decorated** lane counts as watched.

## Tests

**12.** Suite: **5088 passed, 2 skipped** — run before the push.

## Not done

This detects drift; it does not add any lane to `watched_lanes()`. Adding one is a
deliberate code change with a purpose string, which is the point.
