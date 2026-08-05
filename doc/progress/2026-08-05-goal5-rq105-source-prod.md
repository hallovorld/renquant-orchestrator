# 2026-08-05 — rq105 sources its frozen vector from the 104 PROD lane again

## Operator directive

> "105 应该用 104 prod 的模型！给我修好！"

This supersedes the 2026-07-28 directive ("105 直接换成 blend 模型") that pointed
rq105's frozen batch vector at the isolated shadow-blend lane DB. The blend lane
keeps running; rq105 just stops sourcing from it.

## What was actually live `[VERIFIED — this session]`

`ops/renquant105/run_batch_scores_export.sh:26` exported
`RQ105_SCORE_SOURCE=blend`, and the last three exports confirm it on disk:

| session | source | source run | n |
|---|---|---|---|
| 2026-08-03 | blend | `2026-07-31-live-8aa713e5` | 83 |
| 2026-08-04 | blend | `2026-08-03-live-9375cbac` | 85 |
| 2026-08-05 | blend | `2026-08-04-live-de57b5a7` | 82 |

## Prod mode was probed BEFORE the flip, not assumed

Ran the exporter in prod mode into a scratch directory (production untouched):
**83/83 names, coverage 100 %**, from the real prod run
`2026-08-04-live-a199b993`, `broker_mode=alpaca` `[VERIFIED — this session]`.
So the path the directive asks for works today, and the flip is not a leap.

## Two things the probe turned up, both landed with the flip

**1. "prod" no longer means "the single-artifact model."** The prod run's
identity stamp carries **two** resolved blend components — since the z-blend
fullbook went live, PROD itself scores with a composite. **17 of the last 40
live prod runs carry two component pins** `[VERIFIED — this session]`. So the
word names the **lane** whose vector rq105 replays, not a model shape. That is
now written where the switch is, because the next reader will assume otherwise.

**2. `REQUIRED_BROKER_MODE` mapped `prod → None` — no lane check at all.**
An enumerated table whose default branch is "check nothing". While prod was the
unused branch this was merely untidy. The moment rq105 sources from it, it means
a mispointed DB exports a **shadow lane's vector stamped `score_source="prod"`**
and nothing says so. Note the asymmetry that existed from day one:
`test_blend_refuses_prod_lane_db` was written, its prod mirror was not.

Replaced by `LANE_EVIDENCE`, where **every** source names a required
`broker_mode` and a component floor:

| source | broker_mode | min blend components |
|---|---|---|
| `prod` | `alpaca` | 0 |
| `blend` | `alpaca_shadow_blend` | 2 |

Safe to enforce, and **measured rather than assumed**: `broker_mode` is
`'alpaca'` on **1701 of 1701** live runs in `runs.alpaca.db`
(2026-05-21 … 2026-08-05) `[VERIFIED — this session]`. The fixture that let
every prod test pass through a guard that did not exist (`_GOOD_BUNDLE` had no
`broker_mode`) is fixed too.

`min_blend_components` stays **0** for prod deliberately. Prod does score with
a composite today, but that is a fact about the current pinned profile, not
about the lane's identity — gating on it would fail-close rq105 the day prod's
profile changes. Wrong object.

**3. The dashboard carried a stale copy.** `rq105_status.py` re-declared
`{"prod": None, ...}` in its ImportError fallback, so it could report a run
READY that the exporter would refuse. The fallback now holds **no local copy**:
an unimportable exporter reads as unknown-source, not as "check nothing".

## Deployment — NOT done, and it needs the operator

The scheduled job runs
`/Users/renhao/git/github/renquant-orchestrator-run/ops/renquant105/run_batch_scores_export.sh`.
Merging here does **not** change what runs at 06:15. The run checkout must be
synced, and that is an operator action on a live run surface:

```
git -C /Users/renhao/git/github/renquant-orchestrator-run pull --ff-only
```

Until then rq105 keeps exporting **blend**. I have not touched that checkout.

## Two review findings, both real `[codex]`

**A valid JSON root is not a bundle.** `rq105_status.py::_batch_scores` parsed
both rq105 files and then called `.get`/`len` on the result, so a valid-JSON
non-object root (`[]`, `null`, a scalar) raised and took the **whole dashboard**
down — every other row with it. A dashboard that dies on one malformed file
reports nothing about the healthy things it also checks. Both roots are now
validated and a bad one fails closed **on its own row**, keeping the counts it
did manage to read.

**A contract line describing the version before the change.** The
`_db_latest_run` docstring still said "for a broker-mode-gated source (blend),
also reuses `_blend_lane_gaps`" after the code had stopped being blend-only. My
edit had targeted a differently-wrapped copy of that sentence and silently
matched nothing — the exact failure mode I have a rule for: *verify the old text
is gone*, and I did not. A stale contract line is worse than none, because it
reads as though someone checked. A test now asserts the old phrasing is absent.

## Tests

`test_the_WRAPPER_default_is_prod` pins the line the operator actually flips —
a test on `main()`'s default alone would have stayed green through the entire
07-28 → 08-05 blend period. Plus the prod-lane mirror tests, the
"no source may declare an absent lane check" invariant, the composite-panel
acceptance case, and three dashboard tests. 57 + 12 in the two files, full suite
green.
