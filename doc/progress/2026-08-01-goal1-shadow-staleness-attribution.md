# GOAL-1 — two identical DEGRADED alarms, and the cheaper-looking one is the unfixable one

**Date:** 2026-08-01 · `renquant-orchestrator` · GOAL-1 (shadow reliability gates)

## Bottom line

Run as of the 2026-07-31 session, `rq104_shadow_scorer_sentinel.py` fires on both watched
lanes with alarms that read the same `[本次实测 2026-08-01]`:

```
[hf_patchtst]              degraded: stale_625d_limit_28d
[topdecile_clf_blend_leg]  degraded: stale_94d_limit_28d
```

They are not the same failure. The rawlabel corpus every downstream label depends on ends
at **2026-04-28** — 94 days before that session:

| lane | stale | implied cutoff | beyond the frontier | status |
|---|--:|---|--:|---|
| `topdecile_clf_blend_leg` | 94d | **2026-04-28** | **0d** | **FRONTIER-BOUND** |
| `hf_patchtst` | 625d | 2024-11-13 | **531d** | **INDEPENDENTLY STALE** |

**clf is trained to the frontier, to the day.** Retraining it cannot reduce its staleness
by one day; only advancing the corpus can. **PatchTST is 531 days behind a frontier that
was available to it** — that is a lane-owned failure.

**The inversion is the defect:** an operator sees `94d` and `625d`, and the smaller,
cheaper-looking number is the one that **cannot be fixed in the lane**, while the alarming
one is the one that can. Two identical-looking alarms actively point work in the wrong
direction.

## Why this is structural rather than a backlog

A 60-trading-day forward label cannot be observed until 60 trading days have passed, so the
corpus frontier is permanently that far behind the calendar, and a lane trained to it is
*always* "stale" against a 28-day limit. This is the same shape GOAL-5 measured on the
promote path the same night, where one freshness axis subtracts the frontier and its
sibling — same cutoff, same run — does not.

## The frontier is reported with its trust state, never as a bare fact

The rawlabel provenance sidecar stamps `source_panel_frontier: 2026-04-28` at
`2026-07-26T17:02:30Z`, and an **invalidation receipt written 2026-07-30T20:12:50Z** — the
`panel-only=581` lockstep failure — is newer. So the frontier is live but **uncertified**,
and every verdict derived from it is emitted **`provisional`**. Suppressing the date would
hide the attribution rather than qualify it; presenting it bare would rest the whole
finding on a number nobody certified.

`UNKNOWN` is a real outcome. A missing, malformed, or non-date `source_panel_frontier`
attributes **nothing** and exits **3** — not 0. An **unreadable** receipt counts as an
invalidation, because treating a corrupt file as absent would let it certify the corpus.

## Scope

Read-only; no live surface touched; the sentinel itself is unchanged, so no alarm changes
severity. This adds the attribution as a separate step so the two alarms can be told apart.
Whether the sentinel should *consume* it — and downgrade a frontier-bound lane — is a
policy change on a live alarm path and is not made here.

## Not claimed

That `hf_patchtst`'s 531d has a single cause, or which one. That clf would be healthy if
the corpus advanced — only that its staleness is not attributable to the lane. That the
28-day limit is wrong; it is unsatisfiable *for a frontier-bound lane*, which is a
statement about the pair, not about the limit.

## Tests

18. Both directions of every trust state: an older receipt does **not** invalidate a newer
provenance, an unreadable one does, and a receipt with no timestamp invalidates rather than
being ignored. Suite: **5162 passed, 2 skipped**, run before the push.
