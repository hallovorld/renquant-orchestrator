# `hf_patchtst` lane: the governance handoff

**Scope: compliance only.** This document decides nothing about whether the lane has
skill. That question is preregistered in `renquant-model` and **no merit verdict exists
until that artifact does** — see "Merit" below.

Reviewed `[codex on orch#731]`: *"limb B is neither frozen nor owned here … delegating
them after recording comparator means is not a preregistered decision rule."* Correct.
The merit half has been removed from this repo entirely rather than rewritten here.

## The compliance facts

Deterministic, no inference, no threshold invented here:

| fact | value | source |
|---|---|---|
| served artifact staleness | **625 d** (624 d on 2026-07-30) | `rq104_shadow_scorer_sentinel --as-of 2026-07-31` `[本次实测 2026-08-01]` |
| shadow staleness limit | **28 d** (`STALENESS_MAX_DAYS`) | `ops/renquant104/rq104_shadow_scorer_sentinel.py:284`, RFC #210 |
| breach factor | **≈ 22×** | `[推导]` from the two rows above |
| weekly retrain | **has not acted on 4 consecutive runs**, 3 of them crashes | `rq104_silent_refusal_sentinel --dry-run` `[本次实测]`; orch#724 |
| sentinel verdict, every session day | `NOT ACTIONABLE / DEGRADED` | as above |

The 28-day limit is RFC #210 and predates this document. Applying it is compliance, not a
bar chosen after seeing data.

### An ambiguity that had to be resolved before quoting a limit

The sentinel reports `limit_28d`; the pinned config carries `max_age_days: 30`. They are
**different objects** — the 30 belongs to `.panel_ltr.asset_embeddings` (a node that is
itself `enabled=False`) and has nothing to do with model freshness. Quoting it would have
put the wrong limit into a governance record.

## The handoff

A lane 625 days past a 28-day limit is out of compliance, and orch#724 records why it
cannot self-correct: the weekly retrain crashes on corpus schema drift upstream. So the
operator choice is:

* **retire** the lane, or
* **fix the retrain** (orch#724, upstream in the umbrella corpus builder) and let it
  re-qualify under the existing 28-day limit.

Both are live-surface changes and operator decisions. This document names the breach and
hands it over; it does not make the call.

**Compliance is sufficient on its own.** Retirement on these grounds needs no merit
verdict, and a merit verdict — whenever it arrives — cannot by itself return an
out-of-compliance artifact to service.

## Merit — explicitly out of scope here

Whether `hf_patchtst` carries skill is preregistered in `renquant-model` (see the merit
prereg filed alongside model#153/#154). It is **not** frozen in this repo, and nothing in
this document may be read as evidence about it. Until that model-side artifact exists and
is executed under its own terms, the correct statement is: **no merit verdict is
available.**
