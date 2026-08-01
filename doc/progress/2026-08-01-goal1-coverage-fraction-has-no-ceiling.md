# GOAL-1 — a coverage *fraction* has been above 1.0 for six straight days, unflagged

**Date:** 2026-08-01 · `renquant-orchestrator` · GOAL-1 (shadow reliability gates, layer 3)

## Measured

The live shadow health log (`backtesting/renquant_104/logs/shadow_scorer_health.jsonl`,
16 records over 2026-07-27 … 07-31) `[本次实测 2026-08-01]`:

| date | lane | n_candidates | n_scored | coverage_frac |
|---|---|--:|--:|--:|
| 07-27 | `hf_patchtst…` | 80 | 80 | 1.0000 |
| 07-27 | `topdecile_clf_blend_leg` | 80 | **84** | **1.0500** |
| 07-28 | `topdecile_clf_blend_leg` | 77 | **85** | **1.1039** |
| 07-29 | `topdecile_clf_blend_leg` | 78 | **84** | **1.0769** |
| 07-30 | `topdecile_clf_blend_leg` | 77 | **83** | **1.0779** |
| 07-31 | `topdecile_clf_blend_leg` | 79 | **83** | **1.0506** |

`coverage_frac = n_scored / n_candidates` — a **fraction**. The clf lane exceeded 1.0 on
**6 of 6 days**; `hf_patchtst` was exactly 1.0000 every day. **Nothing flagged it.**

## Why it survived — and the part I got wrong first

Two reasons, and the second is the one worth carrying:

1. The only coverage check was a **floor**. One comparison cannot catch both "too small"
   and "too large".
2. **That floor lives in the DB-fallback branch, which these records never reach.** They
   carry an explicit `status`, so `classify()` returns on the producer's verdict and the
   number is never examined.

My first fix added a ceiling **next to the floor** — and changed nothing, because that
branch does not run for these records. I only knew because I re-ran the sentinel on the
real log and saw no new line. The check had to move **ahead of** the status branch, and
firing on the live records is what proved it. *Adding a check is not the same as adding a
check that runs.*

## What it now reports, and what it deliberately does not decide

A new state `MALFORMED_RECORD` — distinct from `DEGRADED` (the lane ran and is
untrustworthy) and `LOAD_FAIL` (it did not run). Here **the lane may be fine and the record
is not describable.**

The message states both readings and picks neither: the lane may be scoring a legitimately
wider universe than the candidate set — in which case the **denominator** is wrong, not the
lane. Deciding that needs a human. What the sentinel must not do is keep treating a
quantity that cannot be a coverage as one.

It also fires **when the producer says `fault`**: the clf lane was already alarming for
staleness, so before this the impossible number rode along inside a message about something
else.

## Threshold choice, stated

`> 1.0`, not `>= 1.0` — `hf_patchtst` reports exactly 1.0000 daily and a `>=` ceiling would
alarm on every fully-covered lane forever. **No tolerance band**: 1.1039 is not a rounding
artefact, and a tolerance would be a threshold nobody measured hiding a quantity nobody
explained.

## Not claimed

That the clf lane is scoring wrongly, that the extra 4–8 names are duplicates, or that any
decision was affected — `coverage_frac` is health telemetry, and this PR does not trace it
into the scoring path.

## Tests

8. Including the two that pin the near-miss: the ceiling must fire when the producer says
`ok`/`expected_skip` **and** when it says `fault`; plus `None` is unmeasured rather than
out of range, and low coverage stays the floor case.

Suite: **5192 passed, 2 skipped**, run before the push.
