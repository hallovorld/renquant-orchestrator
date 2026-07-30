# The shadow sentinel had two ways to be blind. Only one was the matcher.

**Date:** 2026-07-30 · GOAL-1 · orchestrator
**Occasioned by** a forensic pass on the three nonzero-exit jobs surfaced by #643.

**First, a correction I owe #643.** I called those three *"三个真故障 / three real
failures"*. **They are not failures.** All three are sentinels that reached a verdict
and exited with that verdict's code — `_STATUS_EXIT_CODE = {OK: 0, CRITICAL: 1,
WARN: 2}` for scorer-identity, `return 1` only after `alert(...)` for the shadow
sentinel, `exit_code = 2` when APY < threshold for weekly-apy
`[VERIFIED — each module's own source]`. Calling an alarm a failure is the same
category error as calling a `STRUCTURAL_BLOCK` a no-trade.

## 1. Defect A — the two lane matchers disagreed

`_matches_shadow_lane` accepts the exact name **or** `SHADOW_NAME_<suffix>`. It was
applied on the JSONL path only. The DB fallback used SQL `=`
`[VERIFIED — one call site at :534 vs `active_scorer = ? OR model_type = ?` at :606]`.
The served lane is `hf_patchtst_pt07_strict_seed44_previous_primary` — accepted by
the matcher, rejected by `=`.

**Fixed by sharing one function**, not by adding a SQL `LIKE`. A second matcher
expressed in SQL is a twin implementation, and on this programme the copy that runs
is never the copy a reader finds first.

## 2. Defect B — and it is the one that actually bit

The fix above does **not** change the reading for 07-28 or 07-29, and I checked
rather than assumed. Since **2026-07-22**, every `candidate_scores` row in
`runs.alpaca_shadow.db` carries `active_scorer = NULL`
`[VERIFIED — read-only query, `mode=ro&immutable=1`]`:

| date | rows | identifiable under ANY matcher |
|---|---:|---:|
| 2026-07-20 | 70 | 70 |
| 2026-07-21 | 213 | 71 |
| **2026-07-22 → 07-29** | 88 / 85 / 85 / 95 / 360 / 98 | **0** |

The store simply stopped recording which scorer produced a row. **That is a
producer-side regression and it is NOT fixed here** — it needs whoever writes
`candidate_scores`.

## 3. What IS fixed: the fallback stops overclaiming

Reporting `loaded=False` on an all-NULL column asserts *"the shadow lane scored
nothing"*. The truth is *"this store cannot answer the question"* — and the
pipeline's own JSONL for the same dates says `loaded=True, n_scored=77` and `85`
`[VERIFIED — shadow_scorer_health.jsonl]`. So `loaded` is now **`None`** when the
column carries no information, and a boolean otherwise. Same wrong-object shape as
defect A, one level down.

## 4. Two mistakes of mine, caught in-session

1. **My test fixture, not the fix, failed first.** Four new tests errored with
   `no such column: run_type` — my `pipeline_runs` schema omitted the column the
   real query filters on. Transcribed from the query and recorded in the fixture.
2. **A patch landed at the wrong scope.** My first attempt inserted the new flag via
   `locals().get(...)` into the **dataclass** rather than the function, because the
   anchor string occurs twice. Reverted and initialised on both real code paths.

## 5. Suite

**73 passed** `[VERIFIED — pytest, this session]`, including a lookalike-prefix
control (`hf_patchtstXX` must NOT match), an unrelated-scorer control, and an
anti-vacuity control that a populated column still yields a boolean — otherwise
every reading becomes "unknown" and the sentinel says nothing at all.
